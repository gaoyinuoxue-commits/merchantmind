"""Badcase & feedback lifecycle service (Phase 16).

Failures are turned into triaged badcases automatically: failed evaluation
cases are bucketed by badcase.classifier, and negative user feedback opens a
human-sourced badcase (optionally pre-classified from its trace).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.badcase.classifier import classify_case_failure, classify_trace
from app.models.badcase import Badcase, Feedback
from app.models.trace import TraceRun

_RESOLVED_STATUSES = {"fixed", "wont_fix", "ignored"}
_VALID_STATUSES = {"open", "in_review"} | _RESOLVED_STATUSES


class BadcaseService:
    def __init__(self, db: Session):
        self.db = db

    def report_failed_case(
        self,
        case: Dict[str, Any],
        verdict: Dict[str, Any],
        prediction: Dict[str, Any],
        trace_id: Optional[str],
        eval_run_id: Optional[int],
    ) -> Badcase:
        triage = classify_case_failure(case, verdict, prediction)
        case_id = case["id"]

        existing = self.db.scalar(
            select(Badcase).where(
                Badcase.source == "eval",
                Badcase.case_id == case_id,
                Badcase.status == "open",
            ).order_by(Badcase.id.desc())
        )
        title = f"[{case['type']}] {case_id}：{case['message'][:60]}"
        evidence = {
            "case_id": case_id,
            "case_type": case["type"],
            "expected": case.get("expected"),
            "prediction": prediction,
            "violations": verdict.get("hallucination_violations", []),
            "eval_run_ids": [eval_run_id],
            "trace_ids": [trace_id],
        }
        if existing is not None:
            existing.occurrence_count += 1
            existing.eval_run_id = eval_run_id
            merged = dict(existing.evidence)
            merged["eval_run_ids"] = list(merged.get("eval_run_ids", [])) + [eval_run_id]
            merged["trace_ids"] = list(merged.get("trace_ids", [])) + [trace_id]
            existing.evidence = merged
            self.db.flush()
            return existing

        badcase = Badcase(
            source="eval",
            trace_id=trace_id,
            eval_run_id=eval_run_id,
            case_id=case_id,
            merchant_id=case.get("merchant_id"),
            title=title,
            error_type=triage["error_type"],
            affected_module=triage["affected_module"],
            root_cause=triage["root_cause"],
            suggested_fix=triage["suggested_fix"],
            severity=triage["severity"],
            evidence=evidence,
            reporter="system",
        )
        self.db.add(badcase)
        self.db.flush()
        return badcase

    def create_feedback(
        self,
        rating: int,
        comment: Optional[str] = None,
        trace_id: Optional[str] = None,
        merchant_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        helpful = rating >= 4
        feedback = Feedback(
            trace_id=trace_id,
            merchant_id=merchant_id,
            conversation_id=conversation_id,
            rating=rating,
            helpful=helpful,
            comment=comment,
        )
        self.db.add(feedback)
        self.db.flush()

        badcase_id = None
        if rating <= 3:
            trace = self.db.get(TraceRun, trace_id) if trace_id else None
            triage = None
            if trace is not None:
                triage = classify_trace(trace, list(trace.spans))
            if triage is None:
                triage = {
                    "error_type": "other",
                    "affected_module": "human.feedback",
                    "root_cause": comment or "用户负反馈，未填写原因。",
                    "suggested_fix": "人工分诊后给出修复建议。",
                    "severity": "medium" if rating <= 2 else "low",
                }
            headline = (comment or getattr(trace, "query", None) or "用户负反馈")[:60]
            badcase = Badcase(
                source="human",
                trace_id=trace_id,
                feedback_id=feedback.id,
                merchant_id=merchant_id or getattr(trace, "merchant_id", None),
                title=f"用户负反馈：{headline}",
                error_type=triage["error_type"],
                affected_module=triage["affected_module"],
                root_cause=triage["root_cause"],
                suggested_fix=triage["suggested_fix"],
                severity=triage["severity"],
                evidence={"rating": rating, "comment": comment, "trace_id": trace_id},
                reporter="human",
            )
            self.db.add(badcase)
            self.db.flush()
            badcase_id = badcase.id

        self.db.commit()
        return {
            "feedback_id": feedback.id,
            "rating": rating,
            "helpful": helpful,
            "badcase_id": badcase_id,
            "label": "SYNTHETIC",
        }

    def list_feedback(self, limit: int = 50) -> List[Feedback]:
        return list(
            self.db.scalars(
                select(Feedback).order_by(Feedback.id.desc()).limit(limit)
            ).all()
        )

    def list_badcases(
        self,
        status: Optional[str] = None,
        error_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Badcase]:
        stmt = select(Badcase).order_by(Badcase.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(Badcase.status == status)
        if error_type:
            stmt = stmt.where(Badcase.error_type == error_type)
        return list(self.db.scalars(stmt).all())

    def get_badcase(self, badcase_id: int) -> Optional[Badcase]:
        return self.db.get(Badcase, badcase_id)

    def update_badcase(self, badcase_id: int, changes: Dict[str, Any]) -> Badcase:
        badcase = self.db.get(Badcase, badcase_id)
        if badcase is None:
            raise KeyError(badcase_id)
        status = changes.get("status")
        if status is not None:
            if status not in _VALID_STATUSES:
                raise ValueError(f"invalid status: {status}")
            badcase.status = status
            if status in _RESOLVED_STATUSES:
                badcase.resolved_at = datetime.now(timezone.utc)
            elif status in {"open", "in_review"}:
                badcase.resolved_at = None
        for field_name in ("root_cause", "suggested_fix", "severity"):
            if field_name in changes and changes[field_name] is not None:
                setattr(badcase, field_name, changes[field_name])
        self.db.commit()
        return badcase
