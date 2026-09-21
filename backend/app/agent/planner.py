"""Decision planner: turns intent + signals into an ordered tool plan."""
from __future__ import annotations

from typing import Any, Dict, List

from app.agent.intent import (
    INTENT_ACTION,
    INTENT_GREETING,
    INTENT_KNOWLEDGE,
    INTENT_PERFORMANCE,
    INTENT_STRATEGY,
    IntentResult,
)


def _step(kind: str, tool: str = "", arguments: Dict[str, Any] = None, reason: str = "") -> Dict[str, Any]:
    return {"kind": kind, "tool": tool, "arguments": arguments or {}, "reason": reason}


def build_plan(intent: IntentResult, merchant_id: str, query: str) -> List[Dict[str, Any]]:
    domains = set(intent.signals.get("domains", []))
    plan: List[Dict[str, Any]] = []

    if intent.intent == INTENT_GREETING:
        return plan

    if intent.intent == INTENT_KNOWLEDGE:
        plan.append(
            _step(
                "knowledge",
                reason="知识型问题，走知识库 RAG 检索，不调用业务数据工具",
            )
        )
        return plan

    plan.append(
        _step(
            "tool",
            "get_shop_profile",
            {"merchant_id": merchant_id},
            "先确认商家画像、行业阶段与当前模拟日期",
        )
    )
    plan.append(
        _step(
            "tool",
            "get_ad_performance",
            {"merchant_id": merchant_id, "days": 7},
            "获取近 7 天大盘指标与环比，定位异常指标层",
        )
    )

    if intent.intent == INTENT_ACTION:
        if "material" in domains:
            plan.append(
                _step(
                    "tool",
                    "get_material_performance",
                    {"merchant_id": merchant_id, "days": 7},
                    "动作涉及素材，先看素材状态与疲劳度",
                )
            )
        if "budget" in domains:
            plan.append(
                _step(
                    "tool",
                    "get_ad_performance",
                    {"merchant_id": merchant_id, "days": 30},
                    "预算动作需要 30 天趋势确认当前消耗与 ROI 水位",
                )
            )
        plan.append(
            _step(
                "tool",
                "get_recent_business_events",
                {"merchant_id": merchant_id, "days": 60},
                "执行前确认近期是否已有同类调整事件",
            )
        )
        return plan

    if intent.intent in (INTENT_PERFORMANCE, INTENT_STRATEGY):
        plan.append(
            _step(
                "tool",
                "get_recent_business_events",
                {"merchant_id": merchant_id, "days": 60},
                "用近期业务事件解释指标拐点（新品/调预算/活动/季节）",
            )
        )
        if "material" in domains or "ctr" in intent.signals.get("metrics", []):
            plan.append(
                _step(
                    "tool",
                    "get_material_performance",
                    {"merchant_id": merchant_id, "days": 14},
                    "CTR 与素材信号需要素材级疲劳状态佐证",
                )
            )
        if "product" in domains or "cvr" in intent.signals.get("metrics", []):
            plan.append(
                _step(
                    "tool",
                    "get_product_performance",
                    {"merchant_id": merchant_id, "days": 14},
                    "CVR 异常需要商品力（评分/库存/销量）证据",
                )
            )
        if not {"material", "product"} & domains:
            plan.append(
                _step(
                    "tool",
                    "get_material_performance",
                    {"merchant_id": merchant_id, "days": 14},
                    "诊断默认排查素材疲劳这一高频根因",
                )
            )
        plan.append(
            _step(
                "tool",
                "get_historical_cases",
                {"merchant_id": merchant_id, "query": query, "limit": 3},
                "检索相似历史案例做类比归因",
            )
        )
        plan.append(
            _step(
                "knowledge",
                reason="补充与问题匹配的诊断规则和最佳实践作为知识证据",
            )
        )

    return plan
