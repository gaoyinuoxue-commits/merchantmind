"""Evaluation runner: executes ground-truth cases through the real
orchestrator, judges them, persists per-case verdicts and aggregates the
Phase 15 metric set (Recall@K / Task Success / Tool Accuracy / Hallucination /
P50-P95 latency / token proxy / Retry)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.actions import parse_requested_action
from app.agent.orchestrator import AgentOrchestrator
from app.badcase.service import BadcaseService
from app.eval.dataset import ground_truth_cases
from app.eval.judges import heuristic_reply_score, judge_case
from app.models.evaluation import EvalCaseResult, EvalRun
from app.trace.service import TraceService


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return round(ordered[index], 2)


class EvaluationService:
    def __init__(self, db: Session):
        self.db = db

    def run_evaluation(
        self,
        judge: str = "rule",
        case_ids: Optional[List[str]] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        cases = ground_truth_cases()
        if case_ids:
            wanted = set(case_ids)
            cases = [case for case in cases if case["id"] in wanted]

        run = EvalRun(judge=judge, note=note, metrics={"status": "running"})
        self.db.add(run)
        self.db.commit()

        for case in cases:
            self._execute_case(run.id, case, judge)

        return self.aggregate_run(run.id)

    def _execute_case(self, run_id: int, case: Dict[str, Any], judge: str) -> None:
        merchant_id = case["merchant_id"]
        tracer = TraceService(self.db)
        trace_id = tracer.start_run(case["message"], merchant_id=merchant_id)
        orchestrator = AgentOrchestrator(self.db, hooks=[tracer.hook], trace_id=trace_id)

        followup_ctx = None
        ctx = orchestrator.run(merchant_id, case["message"], extract_memory=True)
        token_proxy = (
            len(case["message"])
            + 768
            + 40 * len(ctx.memories)
            + 60 * len(ctx.knowledge)
        )

        if case["type"] == "memory":
            followup_orchestrator = AgentOrchestrator(
                self.db, hooks=[tracer.hook], trace_id=trace_id
            )
            followup_ctx = followup_orchestrator.run(
                merchant_id, case["followup_message"], extract_memory=True
            )
            token_proxy += (
                len(case["followup_message"])
                + 768
                + 40 * len(followup_ctx.memories)
                + 60 * len(followup_ctx.knowledge)
            )

        parsed_action = None
        if case["type"] == "action":
            parsed_action = parse_requested_action(case["message"])

        verdict = judge_case(case, ctx, parsed_action=parsed_action, followup_ctx=followup_ctx)
        final_ctx = followup_ctx or ctx
        tracer.finish_run(final_ctx, status="passed" if verdict["passed"] else "failed")
        summary = tracer.summary(trace_id)

        metrics = {
            "latency_ms": summary["latency_ms"] if summary else None,
            "retry": bool(getattr(final_ctx, "quality_retried", False)),
            "token_proxy": token_proxy,
            "hallucination": verdict["hallucination"],
        }
        for key in (
            "intent_match",
            "tool_recall",
            "cause_recall_at_3",
            "knowledge_recall_at_5",
        ):
            if key in verdict:
                metrics[key] = verdict[key]

        prediction = {
            "intent": (getattr(ctx, "intent", {}) or {}).get("intent"),
            "primary_cause": ((getattr(ctx, "diagnosis", None) or {}).get("primary_cause") or {}).get("code"),
            "candidate_codes": [
                cause.get("code")
                for cause in ((getattr(ctx, "diagnosis", None) or {}).get("candidate_causes") or [])
            ],
            "observed_tools": [
                observation.get("tool")
                for observation in getattr(ctx, "observations", [])
                if observation.get("success") and observation.get("tool")
            ],
            "knowledge_slugs": [item.get("slug") for item in getattr(ctx, "knowledge", [])][:8],
            "needs_clarification": getattr(ctx, "needs_clarification", False),
            "parsed_action": (parsed_action or {}).get("action_type"),
        }
        if followup_ctx is not None:
            prediction["followup_memory"] = [
                item.get("content") for item in getattr(followup_ctx, "memories", [])
            ]

        judge_score = None
        judged_by = "rule"
        if judge == "heuristic":
            judge_score = heuristic_reply_score(final_ctx)
            judged_by = "heuristic_llm_proxy"

        result = EvalCaseResult(
            eval_run_id=run_id,
            case_id=case["id"],
            case_type=case["type"],
            merchant_id=merchant_id,
            message=case["message"],
            passed=verdict["passed"],
            metrics=metrics,
            prediction=prediction,
            trace_id=trace_id,
            judge_score=judge_score,
            judged_by=judged_by,
        )
        self.db.add(result)
        if not verdict["passed"]:
            BadcaseService(self.db).report_failed_case(
                case=case,
                verdict=verdict,
                prediction=prediction,
                trace_id=trace_id,
                eval_run_id=run_id,
            )
        self.db.commit()

    def aggregate_run(self, run_id: int) -> Dict[str, Any]:
        run = self.db.get(EvalRun, run_id)
        if run is None:
            raise KeyError(run_id)
        cases = list(run.cases)
        total = len(cases)
        passed = sum(1 for case in cases if case.passed)
        latencies = [case.metrics.get("latency_ms") for case in cases if case.metrics.get("latency_ms") is not None]
        retries = sum(1 for case in cases if case.metrics.get("retry"))
        hallucinations = sum(1 for case in cases if case.metrics.get("hallucination"))
        tokens = sum(int(case.metrics.get("token_proxy", 0)) for case in cases)

        def avg(key: str) -> Optional[float]:
            values = [case.metrics.get(key) for case in cases if case.metrics.get(key) is not None]
            return round(sum(values) / len(values), 3) if values else None

        by_type: Dict[str, Dict[str, Any]] = {}
        for case in cases:
            bucket = by_type.setdefault(case.case_type, {"total": 0, "passed": 0})
            bucket["total"] += 1
            bucket["passed"] += int(case.passed)
        for bucket in by_type.values():
            bucket["success_rate"] = round(bucket["passed"] / bucket["total"], 3)

        human_rated = [case.human_rating for case in cases if case.human_rating is not None]
        metrics = {
            "total": total,
            "passed": passed,
            "task_success_rate": round(passed / total, 4) if total else 0.0,
            "tool_accuracy": avg("tool_recall"),
            "cause_recall_at_3": avg("cause_recall_at_3"),
            "knowledge_recall_at_5": avg("knowledge_recall_at_5"),
            "hallucination_rate": round(hallucinations / total, 4) if total else 0.0,
            "retry_rate": round(retries / total, 4) if total else 0.0,
            "latency_p50_ms": _percentile(latencies, 50),
            "latency_p95_ms": _percentile(latencies, 95),
            "latency_avg_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "token_proxy_total": tokens,
            "by_type": by_type,
            "human_rated": len(human_rated),
            "human_agreement_rate": round(
                sum(1 for rating in human_rated if rating >= 4) / len(human_rated), 3
            ) if human_rated else None,
        }
        run.total = total
        run.passed = passed
        run.metrics = metrics
        self.db.commit()
        return {
            "eval_run_id": run.id,
            "judge": run.judge,
            "created_at": run.created_at,
            "metrics": metrics,
            "label": "SYNTHETIC",
        }

    def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        runs = self.db.scalars(select(EvalRun).order_by(EvalRun.id.desc()).limit(limit)).all()
        return [
            {
                "eval_run_id": run.id,
                "judge": run.judge,
                "total": run.total,
                "passed": run.passed,
                "task_success_rate": (run.metrics or {}).get("task_success_rate"),
                "created_at": run.created_at,
                "label": "SYNTHETIC",
            }
            for run in runs
        ]

    def get_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        run = self.db.get(EvalRun, run_id)
        if run is None:
            return None
        return {
            "eval_run_id": run.id,
            "judge": run.judge,
            "note": run.note,
            "created_at": run.created_at,
            "metrics": run.metrics,
            "cases": [
                {
                    "case_result_id": case.id,
                    "case_id": case.case_id,
                    "case_type": case.case_type,
                    "merchant_id": case.merchant_id,
                    "message": case.message,
                    "passed": case.passed,
                    "metrics": case.metrics,
                    "prediction": case.prediction,
                    "trace_id": case.trace_id,
                    "judge_score": case.judge_score,
                    "judged_by": case.judged_by,
                    "human_rating": case.human_rating,
                    "human_feedback": case.human_feedback,
                }
                for case in run.cases
            ],
            "label": "SYNTHETIC",
        }

    def record_human_verdict(
        self, case_result_id: int, rating: int, feedback: Optional[str] = None
    ) -> Dict[str, Any]:
        case = self.db.get(EvalCaseResult, case_result_id)
        if case is None:
            raise KeyError(case_result_id)
        case.human_rating = rating
        case.human_feedback = feedback
        self.db.commit()
        summary = self.aggregate_run(case.eval_run_id)
        return {"case_result_id": case_result_id, "run": summary}
