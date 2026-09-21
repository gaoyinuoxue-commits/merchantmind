"""A/B experiment runner (Phase 17).

Runs the same ground-truth subset under multiple RunProfile variants and
compares Task Success / Quality / Hallucination / Latency / Token Cost.

Live dimensions (change offline behaviour now): memory_top_k, knowledge_top_k,
memory ranking weights, quality_retry_threshold.
Recorded dimensions (need an LLM backend): model, temperature, prompt_version.
Knowledge is versioned via knowledge_item(slug, version, status).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.actions import parse_requested_action
from app.agent.orchestrator import AgentOrchestrator, RunProfile
from app.eval.dataset import ground_truth_cases
from app.eval.judges import judge_case
from app.eval.service import _percentile
from app.experiments.variants import DEFAULT_CASE_IDS, DEFAULT_VARIANTS
from app.models.experiment import Experiment, ExperimentVariantRun
from app.trace.service import TraceService

_METRIC_KEYS = (
    "task_success_rate",
    "hallucination_rate",
    "retry_rate",
    "tool_accuracy",
    "cause_recall_at_3",
    "knowledge_recall_at_5",
    "latency_p50_ms",
    "latency_avg_ms",
    "token_proxy_total",
)


class ExperimentService:
    def __init__(self, db: Session):
        self.db = db

    def create_experiment(
        self,
        name: str = "默认 A/B 实验",
        variants: Optional[List[Dict[str, Any]]] = None,
        case_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        variants = variants or [dict(item) for item in DEFAULT_VARIANTS]
        wanted_ids = case_ids or list(DEFAULT_CASE_IDS)
        by_id = {case["id"]: case for case in ground_truth_cases()}
        cases = [
            by_id[case_id]
            for case_id in wanted_ids
            if case_id in by_id and by_id[case_id]["type"] != "memory"
        ]
        if not variants or len(variants) < 2:
            raise ValueError("experiment needs at least two variants")
        if not cases:
            raise ValueError("experiment case set is empty")

        experiment = Experiment(
            name=name,
            case_ids=[case["id"] for case in cases],
            variants=variants,
            results={"status": "running"},
        )
        self.db.add(experiment)
        self.db.commit()

        # Warm caches once so the baseline (always first) is not penalised by
        # cold-start latency. The warmup run is deliberately untraced.
        warmup = cases[0]
        AgentOrchestrator(self.db).run(warmup["merchant_id"], warmup["message"])

        summaries: List[Dict[str, Any]] = []
        for variant in variants:
            metrics, case_rows, applied, recorded = self._run_variant(variant, cases)
            run = ExperimentVariantRun(
                experiment_id=experiment.id,
                variant_name=variant["name"],
                config=variant.get("config", {}),
                total=metrics["total"],
                passed=metrics["passed"],
                metrics=metrics,
                cases=case_rows,
            )
            self.db.add(run)
            summaries.append(
                {
                    "variant_name": variant["name"],
                    "config": variant.get("config", {}),
                    "applied_dimensions": applied,
                    "recorded_dimensions": recorded,
                    **metrics,
                }
            )
        self.db.commit()

        results = self._comparison(summaries)
        experiment.results = results
        experiment.status = "done"
        self.db.commit()
        return self.get_experiment(experiment.id)

    def _run_variant(
        self, variant: Dict[str, Any], cases: List[Dict[str, Any]]
    ) -> tuple:
        config = variant.get("config", {})
        profile = RunProfile(
            memory_top_k=config.get("memory_top_k"),
            knowledge_top_k=config.get("knowledge_top_k"),
            memory_weights=config.get("memory_weights"),
            quality_retry_threshold=config.get("quality_retry_threshold"),
            model=config.get("model"),
            temperature=config.get("temperature"),
            prompt_version=config.get("prompt_version"),
        )

        passed = 0
        latencies: List[float] = []
        retries = 0
        hallucinations = 0
        tokens = 0
        sub_scores: Dict[str, List[float]] = {
            "tool_recall": [],
            "cause_recall_at_3": [],
            "knowledge_recall_at_5": [],
        }
        by_type: Dict[str, Dict[str, Any]] = {}
        case_rows: List[Dict[str, Any]] = []

        for case in cases:
            tracer = TraceService(self.db)
            trace_id = tracer.start_run(case["message"], merchant_id=case["merchant_id"])
            orchestrator = AgentOrchestrator(
                self.db, hooks=[tracer.hook], trace_id=trace_id, profile=profile
            )
            ctx = orchestrator.run(case["merchant_id"], case["message"], extract_memory=True)
            parsed_action = parse_requested_action(case["message"]) if case["type"] == "action" else None
            verdict = judge_case(case, ctx, parsed_action=parsed_action)
            tracer.finish_run(ctx, status="passed" if verdict["passed"] else "failed")
            summary = tracer.summary(trace_id)

            latency = summary["latency_ms"] if summary else None
            token_cost = (
                len(case["message"])
                + 768
                + 40 * len(getattr(ctx, "memories", []))
                + 60 * len(getattr(ctx, "knowledge", []))
            )
            passed += int(verdict["passed"])
            if latency is not None:
                latencies.append(latency)
            retries += int(getattr(ctx, "quality_retried", False))
            hallucinations += int(bool(verdict["hallucination"]))
            tokens += token_cost
            for key in sub_scores:
                if key in verdict:
                    sub_scores[key].append(verdict[key])

            bucket = by_type.setdefault(case["type"], {"total": 0, "passed": 0})
            bucket["total"] += 1
            bucket["passed"] += int(verdict["passed"])
            case_rows.append(
                {
                    "case_id": case["id"],
                    "case_type": case["type"],
                    "passed": verdict["passed"],
                    "latency_ms": latency,
                    "retry": bool(getattr(ctx, "quality_retried", False)),
                    "hallucination": bool(verdict["hallucination"]),
                    "trace_id": trace_id,
                }
            )

        total = len(cases)
        for bucket in by_type.values():
            bucket["success_rate"] = round(bucket["passed"] / bucket["total"], 3)

        def avg(values: List[float]) -> Optional[float]:
            return round(sum(values) / len(values), 3) if values else None

        metrics = {
            "total": total,
            "passed": passed,
            "task_success_rate": round(passed / total, 4) if total else 0.0,
            "tool_accuracy": avg(sub_scores["tool_recall"]),
            "cause_recall_at_3": avg(sub_scores["cause_recall_at_3"]),
            "knowledge_recall_at_5": avg(sub_scores["knowledge_recall_at_5"]),
            "hallucination_rate": round(hallucinations / total, 4) if total else 0.0,
            "retry_rate": round(retries / total, 4) if total else 0.0,
            "latency_p50_ms": _percentile(latencies, 50),
            "latency_p95_ms": _percentile(latencies, 95),
            "latency_avg_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "token_proxy_total": tokens,
            "by_type": by_type,
        }
        return metrics, case_rows, profile.applied_dimensions(), profile.recorded_dimensions()

    def _comparison(self, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        baseline_name = summaries[0]["variant_name"]
        baseline = summaries[0]
        ranking = sorted(
            (item["variant_name"] for item in summaries),
            key=lambda name: next(
                (
                    -item["task_success_rate"],
                    item["hallucination_rate"],
                    item["retry_rate"],
                    item["latency_avg_ms"] or 0.0,
                )
                for item in summaries
                if item["variant_name"] == name
            ),
        )
        deltas: Dict[str, Dict[str, Optional[float]]] = {}
        for item in summaries[1:]:
            row: Dict[str, Optional[float]] = {}
            for key in (
                "task_success_rate",
                "hallucination_rate",
                "retry_rate",
                "latency_p50_ms",
                "latency_avg_ms",
                "token_proxy_total",
            ):
                new = item.get(key)
                old = baseline.get(key)
                if new is None or old is None:
                    row[key] = None
                elif key == "token_proxy_total":
                    row[key] = new - old
                else:
                    row[key] = round(new - old, 4)
            deltas[item["variant_name"]] = row
        return {
            "baseline": baseline_name,
            "winner": ranking[0],
            "ranking": ranking,
            "deltas_vs_baseline": deltas,
            "variants": summaries,
            "metrics_legend": [key for key in _METRIC_KEYS],
            "note": "Demo/Simulation Metrics；model/temperature/prompt_version 为录制维度，接入真实 LLM 后生效。",
        }

    def list_experiments(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.db.scalars(
            select(Experiment).order_by(Experiment.id.desc()).limit(limit)
        ).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "status": row.status,
                "case_count": len(row.case_ids),
                "variant_count": len(row.variants),
                "winner": (row.results or {}).get("winner"),
                "created_at": row.created_at,
                "label": "SYNTHETIC",
            }
            for row in rows
        ]

    def get_experiment(self, experiment_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.get(Experiment, experiment_id)
        if row is None:
            return None
        return {
            "id": row.id,
            "name": row.name,
            "status": row.status,
            "case_ids": row.case_ids,
            "variants": row.variants,
            "results": row.results,
            "runs": [
                {
                    "id": run.id,
                    "variant_name": run.variant_name,
                    "config": run.config,
                    "total": run.total,
                    "passed": run.passed,
                    "metrics": run.metrics,
                    "cases": run.cases,
                }
                for run in row.runs
            ],
            "created_at": row.created_at,
            "label": "SYNTHETIC",
        }
