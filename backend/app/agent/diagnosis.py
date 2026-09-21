"""Evidence aggregation and attribution.

Each candidate cause must attach concrete evidence (metric deltas, entity
states, events, knowledge). The diagnosis engine returns a primary hypothesis,
an alternative hypothesis, a confidence and a quality score used by hooks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.agent.orchestrator import RunContext


CAUSE_KNOWLEDGE_SLUGS: Dict[str, tuple] = {
    "material_fatigue": ("diag_fatigue", "bp_fatigue_versions", "case_fatigue_budget"),
    "budget_cpm_spiral": ("diag_budget_cpm", "biz_budget_step", "case_fatigue_budget"),
    "traffic_cost_increase": ("diag_traffic_cost", "case_traffic_cost"),
    "season_decline": ("diag_season_decline", "case_season_exit"),
    "product_weakness": ("diag_low_rating", "diag_inventory"),
    "new_product_ramp": ("diag_new_product", "biz_new_product_support", "case_new_growth"),
}


def referenced_slugs(report: Dict[str, Any]) -> List[str]:
    wanted: List[str] = []
    for cause in report.get("candidate_causes", []):
        for slug in CAUSE_KNOWLEDGE_SLUGS.get(cause.get("code"), ()):
            if slug not in wanted:
                wanted.append(slug)
    return wanted


@dataclass
class Cause:
    code: str
    title: str
    confidence: float
    explanation: str
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    knowledge_slugs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "confidence": round(self.confidence, 4),
            "explanation": self.explanation,
            "evidence": self.evidence,
            "knowledge_slugs": self.knowledge_slugs,
        }


def _observations(ctx: RunContext) -> Dict[str, Dict[str, Any]]:
    """One data payload per tool. For windowed tools keep the SHORTEST window
    (most sensitive deltas); events keep the LONGEST window."""
    result = {}
    for observation in ctx.observations:
        tool = observation.get("tool")
        if not tool or not observation.get("success"):
            continue
        data = observation.get("data") or {}
        if tool not in result:
            result[tool] = data
            continue
        days = (data.get("window") or data).get("days") if tool == "get_ad_performance" else data.get("days")
        previous = result[tool]
        prev_days = (previous.get("window") or previous).get("days") if tool == "get_ad_performance" else previous.get("days")
        if days is None or prev_days is None:
            continue
        if tool == "get_recent_business_events":
            if days > prev_days:
                result[tool] = data
        elif days < prev_days:
            result[tool] = data
    return result


def _delta(ad: Dict[str, Any], key: str) -> Optional[float]:
    return (ad.get("delta_pct") or {}).get(key)


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _recent(events: List[Dict[str, Any]], etype: str, within_days: int, anchor: datetime) -> List[Dict[str, Any]]:
    hits = []
    for event in events:
        if event["event_type"] != etype:
            continue
        occurred = _parse_dt(event.get("event_time"))
        if occurred is not None and 0 <= (anchor - occurred).days <= within_days:
            hits.append(event)
    return hits


def diagnose(ctx: RunContext) -> Dict[str, Any]:
    data = _observations(ctx)
    ad = data.get("get_ad_performance", {})
    materials_data = data.get("get_material_performance", {})
    products_data = data.get("get_product_performance", {})
    events_data = data.get("get_recent_business_events", {})

    causes: List[Cause] = []
    roi_delta = _delta(ad, "roi")
    ctr_delta = _delta(ad, "ctr")
    cpm_delta = _delta(ad, "cpm")
    gmv_delta = _delta(ad, "gmv")

    fatigued = [m for m in materials_data.get("materials", []) if m.get("status") == "fatigued"]
    events = events_data.get("events", [])
    event_times = [t for t in (_parse_dt(e.get("event_time")) for e in events) if t is not None]
    anchor = max(event_times) if event_times else datetime.now(timezone.utc)
    event_types = {event["event_type"] for event in events}
    budget_events = _recent(events, "budget_change", 45, anchor)
    fatigue_events = _recent(events, "material_fatigue", 30, anchor)
    traffic_events = _recent(events, "traffic_cost_increase", 45, anchor)
    traffic_sales_events = _recent(events, "sales_decline", 30, anchor)
    season_events = _recent(events, "season_change", 45, anchor)
    decline_events = _recent(events, "conversion_decline", 30, anchor)
    new_product_events = _recent(events, "new_product", 45, anchor)
    growth_events = _recent(events, "sales_growth", 45, anchor)

    knowledge_map = {k["slug"]: k for k in ctx.knowledge}

    # 1. material fatigue — entity state / fatigue events are the primary
    # signal; end-window deltas only adjust confidence (decline can predate the
    # last two weeks).
    if fatigued or fatigue_events:
        confidence = 0.55 + min(0.2, len(fatigued) * 0.05)
        confidence += min(0.15, len(fatigue_events) * 0.05)
        if ctr_delta is not None:
            if ctr_delta < -3:
                confidence += 0.1
            elif ctr_delta > 5:
                confidence -= 0.1
        # Fatigued creative is structurally common in this world; it only
        # reaches top confidence with a clearly negative end-window CTR.
        confidence = max(0.5, min(0.95, confidence))
        if ctr_delta is not None:
            confidence = min(confidence, 0.95 if ctr_delta <= -3 else 0.9)
        else:
            confidence = min(confidence, 0.9)
        evidence = []
        if fatigued:
            evidence.append(
                {
                    "source": "get_material_performance",
                    "fact": f"{len(fatigued)} 条素材处于 fatigued 状态",
                    "material_ids": [m["material_id"] for m in fatigued[:5]],
                }
            )
        if fatigue_events:
            evidence.append(
                {
                    "source": "get_recent_business_events",
                    "fact": f"{len(fatigue_events)} 起素材疲劳事件",
                    "event_ids": [e["event_id"] for e in fatigue_events[:3]],
                }
            )
        if ctr_delta is not None:
            evidence.append({"source": "get_ad_performance", "fact": f"CTR 环比 {ctr_delta}%"})
        causes.append(
            Cause(
                code="material_fatigue",
                title="素材疲劳导致点击率下滑",
                confidence=min(0.95, confidence),
                explanation="老素材重复触达目标人群，CTR 趋势性走弱；若同期提预算还会叠加 CPM 抬升。",
                evidence=evidence,
                knowledge_slugs=[s for s in CAUSE_KNOWLEDGE_SLUGS["material_fatigue"] if s in knowledge_map],
            )
        )

    # 2. budget -> CPM spiral
    def _raised(event: Dict[str, Any]) -> bool:
        data = event.get("structured_data", {}) or {}
        factor = data.get("factor")
        change_pct = data.get("change_pct")
        if factor is not None:
            return float(factor) > 1.0
        if change_pct is not None:
            return float(change_pct) > 0
        return False

    raised_budget_events = [event for event in budget_events if _raised(event)]
    if raised_budget_events or (budget_events and cpm_delta is not None and cpm_delta > 3):
        confidence = 0.6
        if raised_budget_events:
            confidence += 0.1
        if fatigued:
            confidence += 0.08
        if traffic_events:
            confidence += 0.05
        if cpm_delta is not None and cpm_delta > 8:
            confidence += 0.07
        if roi_delta is not None and roi_delta < 0:
            confidence += 0.07
        causes.append(
            Cause(
                code="budget_cpm_spiral",
                title="提预算触发更贵流量池，CPM 抬升、ROI 回落",
                confidence=min(0.9, confidence),
                explanation="预算/出价上调后竞得更贵曝光，若素材承接力不足则 ROI 加速下滑。",
                evidence=[
                    {"source": "get_recent_business_events",
                     "fact": f"近 45 天预算上调事件 {len(raised_budget_events or budget_events)} 次",
                     "event_ids": [e["event_id"] for e in (raised_budget_events or budget_events)[:3]]},
                    {"source": "get_ad_performance",
                     "fact": f"CPM 环比 {cpm_delta}%，ROI 环比 {roi_delta}%"},
                ],
                knowledge_slugs=[s for s in CAUSE_KNOWLEDGE_SLUGS["budget_cpm_spiral"] if s in knowledge_map],
            )
        )

    # 3. market traffic cost — recent traffic-cost events are the anchor;
    # end-window CPM delta only adds confidence (shocks can predate the window).
    if traffic_events or (cpm_delta is not None and cpm_delta > 6 and (ctr_delta is None or ctr_delta > -4)):
        confidence = 0.72 + min(0.16, 0.08 * len(traffic_events))
        if cpm_delta is not None and cpm_delta > 3:
            confidence += 0.06
        if roi_delta is not None and roi_delta < 0:
            confidence += 0.08
        if traffic_sales_events:
            confidence += 0.1
        evidence = []
        if traffic_events:
            evidence.append(
                {"source": "get_recent_business_events",
                 "fact": f"近 45 天流量成本上涨事件 {len(traffic_events)} 起",
                 "event_ids": [e["event_id"] for e in traffic_events[:3]]}
            )
        evidence.append(
            {"source": "get_ad_performance", "fact": f"CPM 环比 {cpm_delta}%，CTR 环比 {ctr_delta}%"}
        )
        causes.append(
            Cause(
                code="traffic_cost_increase",
                title="大盘流量成本上涨（非自身操作问题）",
                confidence=min(0.9, confidence),
                explanation="CPM 普涨而 CTR 基本稳定，符合行业竞争加剧/大促前流量变贵的特征。",
                evidence=evidence,
                knowledge_slugs=[s for s in CAUSE_KNOWLEDGE_SLUGS["traffic_cost_increase"] if s in knowledge_map],
            )
        )

    # 4. season decline
    if season_events or (
        gmv_delta is not None and gmv_delta < -10 and (ctr_delta is None or ctr_delta > -6)
    ):
        confidence = 0.75 if season_events else 0.45
        if decline_events:
            confidence += 0.1
        if season_events and decline_events:
            confidence += 0.05
        if gmv_delta is not None and gmv_delta < -5:
            confidence += 0.08
        evidence = []
        if season_events:
            evidence.append(
                {"source": "get_recent_business_events",
                 "fact": "近 45 天存在季节变化事件",
                 "event_ids": [e["event_id"] for e in season_events[:3]]}
            )
        if decline_events:
            evidence.append(
                {"source": "get_recent_business_events",
                 "fact": f"近 30 天转化下滑事件 {len(decline_events)} 起"}
            )
        evidence.append({"source": "get_ad_performance", "fact": f"GMV 环比 {gmv_delta}%"})
        causes.append(
            Cause(
                code="season_decline",
                title="季节性/需求侧衰退",
                confidence=min(0.98, confidence),
                explanation="多素材表现一致走弱、GMV 收缩而 CTR 未明显恶化，更像需求侧回落而非素材问题。",
                evidence=evidence,
                knowledge_slugs=[s for s in CAUSE_KNOWLEDGE_SLUGS["season_decline"] if s in knowledge_map],
            )
        )

    # 5. product-side CVR problem
    products = products_data.get("products", [])
    weak_products = [
        p for p in products
        if (p.get("conversion_rate") is not None and p["conversion_rate"] < 0.015)
        or (p.get("inventory") is not None and 0 < p["inventory"] < 20)
    ]
    if weak_products:
        causes.append(
            Cause(
                code="product_weakness",
                title="商品侧短板压制转化（低转化/低库存）",
                confidence=0.55,
                explanation="点击后的转化由商品力决定，低转化或低库存商品会浪费广告流量。",
                evidence=[
                    {"source": "get_product_performance",
                     "fact": f"{len(weak_products)} 个商品低转化或低库存",
                     "product_ids": [p["product_id"] for p in weak_products[:5]]},
                ],
                knowledge_slugs=[s for s in CAUSE_KNOWLEDGE_SLUGS["product_weakness"] if s in knowledge_map],
            )
        )

    # 6. new product ramp (recent launches, reinforced by sales growth)
    if new_product_events or growth_events:
        ramp_confidence = 0.5 + min(0.2, 0.05 * len(new_product_events))
        if growth_events:
            ramp_confidence += 0.1
        causes.append(
            Cause(
                code="new_product_ramp",
                title="新品爬坡期，指标波动属正常",
                confidence=min(0.85, ramp_confidence),
                explanation="新品上线早期缺少销量评价积累，ROI 波动大，不宜按单日表现频繁调整。",
                evidence=[
                    {"source": "get_recent_business_events",
                     "fact": f"近 45 天新品事件 {len(new_product_events)} 次、增长事件 {len(growth_events)} 次",
                     "event_ids": [e["event_id"] for e in (new_product_events or growth_events)[:3]]}
                ],
                knowledge_slugs=[s for s in CAUSE_KNOWLEDGE_SLUGS["new_product_ramp"] if s in knowledge_map],
            )
        )

    causes.sort(key=lambda cause: cause.confidence, reverse=True)
    primary = causes[0].to_dict() if causes else None
    alternative = causes[1].to_dict() if len(causes) > 1 else None

    successful = [o for o in ctx.observations if o.get("success")]
    failed = [o for o in ctx.observations if not o.get("success")]
    evidence_count = sum(len(c.evidence) for c in causes)
    coverage = min(1.0, len(successful) / 4.0)
    evidence_quality = min(1.0, evidence_count / 5.0)
    knowledge_support = 1.0 if any(c.knowledge_slugs for c in causes) else 0.3
    penalty = 0.15 * len(failed)
    quality_score = max(
        0.0,
        min(1.0, 0.4 * coverage + 0.35 * evidence_quality + 0.25 * knowledge_support - penalty),
    )
    confidence = primary["confidence"] if primary else 0.3

    follow_up_questions = []
    if primary is None:
        follow_up_questions.append("您最关注的是整体 ROI、点击量还是转化率？")
    if confidence < 0.5:
        follow_up_questions.append("这个现象大概从什么时候开始？期间做过哪些调整？")

    return {
        "primary_cause": primary,
        "alternative_cause": alternative,
        "candidate_causes": [cause.to_dict() for cause in causes],
        "confidence": round(confidence, 4),
        "quality_score": round(quality_score, 4),
        "follow_up_questions": follow_up_questions,
        "failed_observations": [o["step"] for o in failed],
        "label": "SYNTHETIC",
    }
