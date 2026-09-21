"""Persistence-backed execution traces for agent runs.

Every run produces one TraceRun and a list of TraceSpans (intent, memory,
planner, tool calls, knowledge, hooks, diagnosis, action). The external API
exposes only a compact Analysis Summary; raw tool payloads are never returned.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.trace import TraceRun, TraceSpan

_STAGE_SPAN = {
    "intent": ("intent", "意图识别"),
    "memory_recall": ("memory", "记忆召回"),
    "memory_extract": ("memory", "记忆抽取"),
    "plan": ("planner", "决策规划"),
    "tool_call": ("tool_call", "工具调用"),
    "knowledge": ("knowledge", "知识检索"),
    "diagnosis": ("diagnosis", "证据归因"),
    "quality_retry": ("hook", "质检补证重试"),
    "clarification": ("hook", "追问澄清"),
    "action": ("action", "动作执行"),
    "pre_hook": ("hook", "前置澄清"),
}


def new_trace_id() -> str:
    return "TR" + secrets.token_hex(7)


class TraceService:
    def __init__(self, db: Session):
        self.db = db
        self._order = 0
        self._open_span: Optional[TraceSpan] = None
        self._started_at = datetime.now(timezone.utc)
        self.run: Optional[TraceRun] = None

    def start_run(
        self,
        query: str,
        merchant_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        trace = TraceRun(
            trace_id=new_trace_id(),
            merchant_id=merchant_id,
            conversation_id=conversation_id,
            query=query,
            status="running",
        )
        self.db.add(trace)
        self.db.commit()
        self.run = trace
        return trace.trace_id

    def hook(self, stage: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """StageHook compatible callback for AgentOrchestrator."""
        span_type, default_name = _STAGE_SPAN.get(stage, ("stage", stage))
        name = default_name
        status = "ok"
        compact: Dict[str, Any] = {}
        if stage == "tool_call":
            name = payload.get("tool", "工具调用")
            status = "error" if payload.get("success") is False else "ok"
            compact = {
                "tool": name,
                "success": payload.get("success", True),
                "latency_ms": payload.get("latency_ms"),
            }
            if payload.get("error"):
                compact["error"] = payload["error"]
        elif stage == "intent":
            compact = {
                "intent": payload.get("intent"),
                "confidence": payload.get("confidence"),
            }
            name = f"意图识别：{payload.get('intent')}"
        elif stage == "plan":
            compact = {"steps": payload.get("steps")}
        elif stage in ("memory_recall", "knowledge"):
            compact = {"items": payload.get("items")}
        elif stage == "memory_extract":
            compact = {"extracted": payload.get("extracted")}
        elif stage == "diagnosis":
            compact = {
                "quality_score": payload.get("quality_score"),
                "primary_cause": payload.get("primary_cause"),
            }
            name = f"证据归因：{payload.get('primary_cause') or '未定位'}"
        elif stage == "quality_retry":
            compact = {"steps": payload.get("steps")}
            status = "retry"
        elif stage == "action":
            name = f"动作执行：{payload.get('action_type', '-')}"
            compact = {
                "action_type": payload.get("action_type"),
                "risk_level": payload.get("risk_level"),
                "status": payload.get("status"),
            }
            status = "ok" if payload.get("status") == "executed" else "blocked"
        elif stage == "clarification":
            status = "clarify"
            compact = {"reason": payload.get("reason")}
        elif stage == "pre_hook":
            status = "clarify"
        self.record(span_type, name, payload=compact, status=status)

    def record(
        self,
        span_type: str,
        name: str,
        payload: Optional[Dict[str, Any]] = None,
        status: str = "ok",
    ) -> TraceSpan:
        now = datetime.now(timezone.utc)
        if self._open_span is not None:
            self._close(self._open_span, now)
        self._order += 1
        span = TraceSpan(
            trace_id=self._trace_id,
            span_order=self._order,
            span_type=span_type,
            name=name,
            status=status,
            payload=payload or {},
        )
        self.db.add(span)
        self.db.commit()
        self._open_span = span
        return span

    def finish_run(self, context: Any = None, status: str = "done", **extra: Any) -> None:
        now = datetime.now(timezone.utc)
        if self._open_span is not None:
            self._close(self._open_span, now)
            self._open_span = None
        trace = self.db.get(TraceRun, self._trace_id)
        if trace is None:
            return
        latency = (now - self._started_at).total_seconds() * 1000.0
        trace.latency_ms = round(latency, 2)
        trace.status = status
        if context is not None:
            intent = getattr(context, "intent", {}) or {}
            trace.intent = intent.get("intent")
            trace.needs_clarification = bool(getattr(context, "needs_clarification", False))
            trace.retry_count = 1 if getattr(context, "quality_retried", False) else 0
            diagnosis = getattr(context, "diagnosis", None)
            if diagnosis:
                trace.quality_score = diagnosis.get("quality_score")
                primary = diagnosis.get("primary_cause") or {}
                trace.primary_cause = primary.get("code")
                trace.confidence = primary.get("confidence")
        for key, value in extra.items():
            if hasattr(trace, key) and value is not None:
                setattr(trace, key, value)
        tool_count = self.db.scalar(
            select(func.count())
            .select_from(TraceSpan)
            .where(TraceSpan.trace_id == trace.trace_id, TraceSpan.span_type == "tool_call")
        )
        trace.tool_call_count = int(tool_count or 0)
        trace.ended_at = now
        self.db.commit()

    def _close(self, span: TraceSpan, now: datetime) -> None:
        if span.created_at.tzinfo is None:
            started = span.created_at.replace(tzinfo=timezone.utc)
        else:
            started = span.created_at
        span.latency_ms = round((now - started).total_seconds() * 1000.0, 2)
        self.db.commit()

    @property
    def _trace_id(self) -> str:
        if self.run is None:
            raise RuntimeError("trace run not started")
        return self.run.trace_id

    def summary(self, trace_id: str) -> Optional[Dict[str, Any]]:
        trace = self.db.get(TraceRun, trace_id)
        if trace is None:
            return None
        spans = list(trace.spans)
        stages = [
            {
                "span_type": span.span_type,
                "name": span.name,
                "status": span.status,
                "latency_ms": span.latency_ms,
            }
            for span in spans
        ]
        tool_spans = [span for span in spans if span.span_type == "tool_call"]
        failed_tools = [
            span.payload.get("tool")
            for span in tool_spans
            if span.status == "error"
        ]
        decision = "completed"
        if trace.status == "running":
            decision = "running"
        elif trace.needs_clarification:
            decision = "clarification_required"
        elif trace.retry_count:
            decision = "completed_with_supplemental_evidence"
        parts = [f"意图={trace.intent or '-'}"]
        if trace.primary_cause:
            parts.append(f"主要归因={trace.primary_cause}")
        parts.append(f"工具调用={trace.tool_call_count}")
        parts.append(f"质量分={trace.quality_score if trace.quality_score is not None else '-'}")
        return {
            "trace_id": trace.trace_id,
            "merchant_id": trace.merchant_id,
            "query": trace.query,
            "intent": trace.intent,
            "status": trace.status,
            "decision": decision,
            "primary_cause": trace.primary_cause,
            "confidence": trace.confidence,
            "quality_score": trace.quality_score,
            "needs_clarification": trace.needs_clarification,
            "retry_count": trace.retry_count,
            "tool_call_count": trace.tool_call_count,
            "failed_tools": [tool for tool in failed_tools if tool],
            "latency_ms": trace.latency_ms,
            "created_at": trace.created_at,
            "analysis_summary": "；".join(parts),
            "stages": stages,
            "label": "SYNTHETIC",
        }

    def list_runs(self, merchant_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        stmt = select(TraceRun).order_by(TraceRun.created_at.desc()).limit(limit)
        if merchant_id:
            stmt = select(TraceRun).where(TraceRun.merchant_id == merchant_id).order_by(
                TraceRun.created_at.desc()
            ).limit(limit)
        rows = self.db.scalars(stmt).all()
        return [
            {
                "trace_id": row.trace_id,
                "merchant_id": row.merchant_id,
                "query": row.query[:60],
                "intent": row.intent,
                "primary_cause": row.primary_cause,
                "quality_score": row.quality_score,
                "status": row.status,
                "needs_clarification": row.needs_clarification,
                "retry_count": row.retry_count,
                "tool_call_count": row.tool_call_count,
                "latency_ms": row.latency_ms,
                "created_at": row.created_at,
                "label": "SYNTHETIC",
            }
            for row in rows
        ]
