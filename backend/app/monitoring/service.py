"""Read-only monitoring & KPI aggregation (Phase 18).

Three layers from real persisted rows, never mocked:
1. Online monitoring (Demo/Simulation Metrics): requests/success/tool failure/
   memory writes/conflicts/retrieval miss/hallucination/latency/token/retry/helpful.
2. AI capability + Agent usage (from evaluation/traces/conversations/feedback).
3. Business outcome (Synthetic Business Metrics): ROI/CTR/GMV/CPM window deltas,
   fatigued materials, resolution time, action execution rate.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.eval.service import _percentile
from app.models.conversation import Conversation, Message
from app.models.evaluation import EvalCaseResult, EvalRun
from app.models.material import Material
from app.models.memory import MemoryConflict, MemoryItem
from app.models.badcase import Feedback
from app.models.performance import PerformanceDaily
from app.models.merchant import Merchant
from app.models.trace import TraceRun, TraceSpan
from app.tools.metrics import margin_for_industry

DEMO_LABEL = "Demo/Simulation Metrics"
SYNTHETIC_BUSINESS_LABEL = "Synthetic Business Metrics"
_SUCCESS_STATUSES = {"done", "passed"}


def _rate(numerator: int, denominator: int) -> Optional[float]:
    return round(numerator / denominator, 4) if denominator else None


class MonitoringService:
    def __init__(self, db: Session):
        self.db = db

    def overview(self, window_days: int = 30) -> Dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(days=window_days)
        return {
            "window_days": window_days,
            "generated_at": datetime.now(timezone.utc),
            "monitoring": {**self._monitoring(since), "label": DEMO_LABEL},
            "ai_capability": {**self._ai_capability(), "label": DEMO_LABEL},
            "agent_usage": {**self._agent_usage(since), "label": DEMO_LABEL},
            "business_kpi": {**self._business_kpi(), "label": SYNTHETIC_BUSINESS_LABEL},
            "label": DEMO_LABEL,
        }

    def _monitoring(self, since: datetime) -> Dict[str, Any]:
        runs = list(self.db.scalars(
            select(TraceRun)
            .where(TraceRun.created_at >= since)
            .options(selectinload(TraceRun.spans))
        ).all())
        requests = len(runs)
        succeeded = sum(1 for run in runs if run.status in _SUCCESS_STATUSES)
        clarifications = sum(1 for run in runs if run.needs_clarification)
        blocked = sum(1 for run in runs if run.status in {"blocked", "confirmation_required"})
        retries = sum(run.retry_count or 0 for run in runs)

        tool_calls = 0
        tool_failures = 0
        retrieval_calls = 0
        retrieval_misses = 0
        token_proxy = 0
        for run in runs:
            context_items = 0
            for span in run.spans:
                if span.span_type == "tool_call":
                    tool_calls += 1
                    if span.status == "error":
                        tool_failures += 1
                elif span.span_type == "memory" and span.name == "记忆召回":
                    retrieval_calls += 1
                    items = int((span.payload or {}).get("items") or 0)
                    context_items += items
                    if items == 0:
                        retrieval_misses += 1
                elif span.span_type == "knowledge":
                    retrieval_calls += 1
                    items = int((span.payload or {}).get("items") or 0)
                    context_items += items
                    if items == 0:
                        retrieval_misses += 1
            token_proxy += len(run.query or "") + 768 + 40 * context_items

        latencies = [run.latency_ms for run in runs if run.latency_ms is not None]
        hallucinations = self.db.scalar(
            select(func.count())
            .select_from(EvalCaseResult)
            .where(
                EvalCaseResult.created_at >= since,
                EvalCaseResult.metrics["hallucination"].as_boolean().is_(True),
            )
        )

        feedback_total = self.db.scalar(
            select(func.count()).select_from(Feedback).where(Feedback.created_at >= since)
        )
        helpful = self.db.scalar(
            select(func.count())
            .select_from(Feedback)
            .where(Feedback.created_at >= since, Feedback.helpful.is_(True))
        )
        memory_writes = self.db.scalar(
            select(func.count())
            .select_from(MemoryItem)
            .where(MemoryItem.first_seen_at >= since)
        )
        memory_conflicts = self.db.scalar(
            select(func.count())
            .select_from(MemoryConflict)
            .where(MemoryConflict.created_at >= since)
        )

        return {
            "requests": requests,
            "succeeded": succeeded,
            "success_rate": _rate(succeeded, requests),
            "clarifications": clarifications,
            "blocked_actions": blocked,
            "tool_calls": tool_calls,
            "tool_failures": tool_failures,
            "tool_failure_rate": _rate(tool_failures, tool_calls),
            "memory_writes": int(memory_writes or 0),
            "memory_conflicts": int(memory_conflicts or 0),
            "retrieval_calls": retrieval_calls,
            "retrieval_misses": retrieval_misses,
            "retrieval_miss_rate": _rate(retrieval_misses, retrieval_calls),
            "hallucinations": int(hallucinations or 0),
            "hallucination_rate": _rate(int(hallucinations or 0), requests),
            "retries": retries,
            "retry_rate": _rate(retries, requests),
            "latency_avg_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "latency_p50_ms": _percentile(latencies, 50),
            "latency_p95_ms": _percentile(latencies, 95),
            "token_proxy_total": token_proxy,
            "feedback_count": int(feedback_total or 0),
            "helpful_count": int(helpful or 0),
            "helpful_rate": _rate(int(helpful or 0), int(feedback_total or 0)),
        }

    def _ai_capability(self) -> Dict[str, Any]:
        latest = self.db.scalars(
            select(EvalRun).order_by(EvalRun.id.desc()).limit(1)
        ).first()
        if latest is None:
            return {"eval_run_id": None}
        metrics = latest.metrics or {}
        quality_run = self.db.scalars(
            select(EvalRun).where(EvalRun.judge == "heuristic").order_by(EvalRun.id.desc()).limit(1)
        ).first()
        answer_quality = None
        if quality_run is not None:
            scores = [
                row.judge_score
                for row in quality_run.cases
                if row.judge_score is not None
            ]
            answer_quality = round(sum(scores) / len(scores), 3) if scores else None
        return {
            "eval_run_id": latest.id,
            "judge": latest.judge,
            "task_success_rate": metrics.get("task_success_rate"),
            "tool_accuracy": metrics.get("tool_accuracy"),
            "cause_recall_at_3": metrics.get("cause_recall_at_3"),
            "knowledge_recall_at_5": metrics.get("knowledge_recall_at_5"),
            "hallucination_rate": metrics.get("hallucination_rate"),
            "answer_quality_proxy": answer_quality,
        }

    def _agent_usage(self, since: datetime) -> Dict[str, Any]:
        conversations = list(self.db.scalars(
            select(Conversation).where(Conversation.created_at >= since)
        ).all())
        conv_ids = [c.conversation_id for c in conversations]
        multi_turn = 0
        if conv_ids:
            rows = self.db.execute(
                select(Message.conversation_id, func.count())
                .where(Message.conversation_id.in_(conv_ids), Message.role == "user")
                .group_by(Message.conversation_id)
            ).all()
            multi_turn = sum(1 for _, count in rows if count >= 2)

        action_spans = list(self.db.scalars(
            select(TraceSpan)
            .join(TraceRun, TraceSpan.trace_id == TraceRun.trace_id)
            .where(TraceSpan.span_type == "action", TraceRun.created_at >= since)
        ).all())
        executed = sum(1 for span in action_spans if span.status == "ok")
        blocked = sum(1 for span in action_spans if span.status == "blocked")

        return {
            "conversations": len(conversations),
            "multi_turn_conversations": multi_turn,
            "follow_up_rate": _rate(multi_turn, len(conversations)),
            "actions_requested": len(action_spans),
            "actions_executed": executed,
            "actions_blocked": blocked,
            "execution_rate": _rate(executed, len(action_spans)),
            "human_confirmation_rate": _rate(blocked, len(action_spans)),
        }

    def _business_kpi(self) -> Dict[str, Any]:
        anchor = self.db.scalar(select(func.max(PerformanceDaily.date)))
        if anchor is None:
            return {"anchor_date": None}
        recent_start = anchor - timedelta(days=6)
        previous_start = anchor - timedelta(days=13)

        merchant_industry = {
            m.merchant_id: m.industry
            for m in self.db.scalars(select(Merchant)).all()
        }

        def totals(start, end) -> Tuple[float, float, int, int, int, float]:
            rows = list(self.db.scalars(
                select(PerformanceDaily).where(
                    PerformanceDaily.date >= start, PerformanceDaily.date <= end
                )
            ).all())
            return (
                sum(r.gmv or 0 for r in rows),
                sum(r.ad_spend or 0 for r in rows),
                sum(r.clicks or 0 for r in rows),
                sum(r.impressions or 0 for r in rows),
                len(rows),
                sum(
                    (r.gmv or 0)
                    * margin_for_industry(merchant_industry.get(r.merchant_id))
                    for r in rows
                ),
            )

        def unpack(rows):
            return {
                "gmv": rows[0], "ad_spend": rows[1], "clicks": rows[2],
                "impressions": rows[3], "days": rows[4], "gross_profit": rows[5],
            }

        recent = unpack(totals(recent_start, anchor))
        previous = unpack(totals(previous_start, recent_start - timedelta(days=1)))

        def pct_change(new: float, old: float) -> Optional[float]:
            return round((new - old) / old * 100, 2) if old else None

        roi_recent = recent["gross_profit"] / recent["ad_spend"] if recent["ad_spend"] else None
        roi_previous = previous["gross_profit"] / previous["ad_spend"] if previous["ad_spend"] else None
        ctr_recent = recent["clicks"] / recent["impressions"] if recent["impressions"] else None
        ctr_previous = previous["clicks"] / previous["impressions"] if previous["impressions"] else None
        cpm_recent = recent["ad_spend"] / recent["impressions"] * 1000 if recent["impressions"] else None
        cpm_previous = previous["ad_spend"] / previous["impressions"] * 1000 if previous["impressions"] else None

        fatigued = self.db.scalar(
            select(func.count()).select_from(Material).where(Material.status == "fatigued")
        )
        materials_total = self.db.scalar(select(func.count()).select_from(Material))

        durations = self.db.execute(
            select(
                Message.conversation_id,
                func.max(Message.created_at),
                func.min(Message.created_at),
            ).group_by(Message.conversation_id)
        ).all()
        minutes = [
            (max_at - min_at).total_seconds() / 60.0
            for _, max_at, min_at in durations
            if max_at and min_at and max_at > min_at
        ]
        resolution_minutes = round(sum(minutes) / len(minutes), 2) if minutes else None

        return {
            "anchor_date": anchor.isoformat(),
            "window": "last 7 days vs previous 7 days",
            "roi": {
                "recent": round(roi_recent, 3) if roi_recent is not None else None,
                "previous": round(roi_previous, 3) if roi_previous is not None else None,
                "change_pct": pct_change(roi_recent, roi_previous)
                if roi_recent is not None and roi_previous else None,
            },
            "ctr": {
                "recent": round(ctr_recent, 5) if ctr_recent is not None else None,
                "previous": round(ctr_previous, 5) if ctr_previous is not None else None,
                "change_pct": pct_change(ctr_recent, ctr_previous)
                if ctr_recent is not None and ctr_previous else None,
            },
            "cpm": {
                "recent": round(cpm_recent, 2) if cpm_recent is not None else None,
                "previous": round(cpm_previous, 2) if cpm_previous is not None else None,
                "change_pct": pct_change(cpm_recent, cpm_previous)
                if cpm_recent is not None and cpm_previous else None,
            },
            "gmv_change_pct": pct_change(recent["gmv"], previous["gmv"]),
            "fatigued_materials": int(fatigued or 0),
            "fatigued_share": _rate(int(fatigued or 0), int(materials_total or 0)),
            "resolution_minutes_avg": resolution_minutes,
        }
