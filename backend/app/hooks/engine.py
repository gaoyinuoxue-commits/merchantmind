"""Four hook families + uncertainty handling.

- PreHook: ambiguous intent -> ask before doing anything
- ToolHook: critical tool failure -> evidence gap handling
- RiskHook: action risk classification (used by phase 13 action loop)
- PostHook: diagnosis quality gate with one retry, dual-hypothesis uncertainty
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config.settings import get_settings

INTENT_CONFIDENCE_FLOOR = 0.5
DIAGNOSIS_CONFIDENCE_FLOOR = 0.5
DUAL_HYPOTHESIS_MARGIN = 0.08

CRITICAL_TOOLS = {"get_shop_profile", "get_ad_performance"}


class PreHook:
    def check(self, intent: Dict[str, Any]) -> Optional[Dict[str, str]]:
        if intent["intent"] in {"greeting", "knowledge_query"}:
            return None
        if intent["confidence"] < INTENT_CONFIDENCE_FLOOR:
            return {
                "needs_clarification": "true",
                "question": "我还没完全理解您的问题——您最想排查的是整体 ROI、点击率(CTR)、转化率(CVR)，还是某项具体操作（如调预算/换素材）？",
            }
        return None


class ToolHook:
    def critical_failures(self, observations: List[Dict[str, Any]]) -> List[str]:
        failed = {
            observation.get("tool")
            for observation in observations
            if not observation.get("success")
        }
        return sorted(failed & CRITICAL_TOOLS)


class PostHook:
    def __init__(self) -> None:
        self.settings = get_settings()

    def evaluate(
        self,
        report: Dict[str, Any],
        attempt: int,
        supplemental_done: bool,
        threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        primary = report.get("primary_cause")
        alternative = report.get("alternative_cause")
        if primary and alternative:
            margin = primary["confidence"] - alternative["confidence"]
            if margin < DUAL_HYPOTHESIS_MARGIN:
                report["dual_hypothesis"] = True
                report["confidence_note"] = (
                    f"主因({primary['code']})与备择({alternative['code']})置信度接近（差 {margin:.2f}），"
                    "建议补充信息后再做高风险动作"
                )

        floor = threshold if threshold is not None else self.settings.quality_retry_threshold
        if report["quality_score"] >= floor:
            return {"decision": "pass"}
        if attempt == 0 and not supplemental_done:
            return {"decision": "retry", "reason": "quality_below_threshold_collect_more_evidence"}
        return {
            "decision": "clarify",
            "question": "现有数据不足以给出可靠结论，能否补充：现象开始时间、近期做过的调整、关注的商品或计划？",
        }


class RiskHook:
    def classify(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action_type == "new_material":
            return {"risk_level": "low", "requires_confirmation": False}
        if action_type == "budget_change":
            change_pct = abs(float(params.get("change_pct", 0)))
            if change_pct > 30:
                return {"risk_level": "high", "requires_confirmation": True}
            return {"risk_level": "medium", "requires_confirmation": True}
        if action_type in {"campaign_pause", "campaign_restart"}:
            return {"risk_level": "high", "requires_confirmation": True}
        return {"risk_level": "medium", "requires_confirmation": True}
