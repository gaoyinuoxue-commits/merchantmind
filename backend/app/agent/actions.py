"""Action proposal, risk grading and the Observe→Act→Observe loop."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.hooks.engine import RiskHook

if TYPE_CHECKING:
    from app.agent.orchestrator import RunContext
from app.simulator.engine import SimulatorService
from app.tools.metrics import window_metrics

_PCT = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")


def _risk(action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    return RiskHook().classify(action_type, params)


def _fatigued_campaign(ctx: RunContext) -> Optional[str]:
    for observation in ctx.observations:
        if observation.get("tool") != "get_material_performance":
            continue
        for material in observation.get("data", {}).get("materials", []):
            if material.get("status") == "fatigued":
                return material.get("campaign_id")
    return None


def _actions_for_code(code: str, ctx: RunContext) -> List[Dict[str, Any]]:
    if code == "material_fatigue":
        params = {
            "type": "new_material",
            "material_name": "诊断建议：迭代卖点的新素材",
            "ctr_factor": 1.25,
        }
        actions = [_action(
            "new_material", params,
            title="上线 1 条保留验证卖点的新素材并小流量测试",
            rationale="用新鲜素材恢复 CTR，避免在疲劳素材上加预算；模拟器假设新素材 CTR 提升约 25%。",
        )]
        campaign_id = _fatigued_campaign(ctx)
        if campaign_id:
            actions.append(_action(
                "campaign_pause", {"type": "campaign_pause", "campaign_id": campaign_id},
                title=f"暂停疲劳素材所在计划 {campaign_id}",
                rationale="高风险动作：暂停后该计划花费显著下降，建议在新素材跑稳后再执行。",
            ))
        return actions
    if code in {"budget_cpm_spiral", "traffic_cost_increase"}:
        return [_action(
            "budget_change", {"type": "budget_change", "factor": 0.85, "change_pct": -15},
            title="预算回调 15%，观察 CPM 与 ROI 是否修复",
            rationale="CPM 高位时小步降预算止血，单次幅度控制在 20% 以内，48 小时后再评估。",
        )]
    if code == "season_decline":
        return [_action(
            "budget_change", {"type": "budget_change", "factor": 0.8, "change_pct": -20},
            title="过季品预算下调 20%，为应季新品腾出预算",
            rationale="需求侧衰退不应靠加预算对抗，应把预算迁移到应季商品素材。",
        )]
    if code == "product_weakness":
        return [_action(
            "new_material",
            {"type": "new_material", "material_name": "诊断建议：突出卖点与口碑的新素材", "ctr_factor": 1.15},
            title="围绕高转化商品重做卖点素材",
            rationale="商品侧短板先优化表达与承接，素材侧动作风险最低。",
        )]
    if code == "new_product_ramp":
        return [_action(
            "observe",
            {"type": "observe", "days": 14},
            title="维持预算稳定，继续观察新品 14 天爬坡",
            rationale="新品扶持期内不按单日 ROI 决策，属只读观察动作。",
            risk_override={"risk_level": "read", "requires_confirmation": False},
        )]
    return []


def propose_for_diagnosis(report: Optional[Dict[str, Any]], ctx: RunContext) -> List[Dict[str, Any]]:
    if not report or not report.get("primary_cause"):
        return []
    primary = report["primary_cause"]
    actions = _actions_for_code(primary["code"], ctx)

    # A strong alternative hypothesis still earns a low-risk supplemental
    # proposal (e.g. creative refresh when traffic cost is the primary cause).
    seen = {action["action_type"] for action in actions}
    for cause in report.get("candidate_causes", [])[1:]:
        if cause["code"] != "material_fatigue" or cause["confidence"] < 0.7:
            continue
        for extra in _actions_for_code("material_fatigue", ctx):
            if extra["action_type"] == "new_material" and "new_material" not in seen:
                actions.append(extra)
                seen.add("new_material")
    return actions


def parse_requested_action(text: str) -> Optional[Dict[str, Any]]:
    lowered = text
    increase_words = ("加预算", "提预算", "提高预算", "增加预算", "放量", "冲量")
    decrease_words = ("降预算", "减少预算", "压预算", "控制花费", "降低预算", "预算降低", "下调预算", "预算下调")
    pause_words = ("暂停", "关掉", "停掉")
    match = _PCT.search(text)
    explicit = float(match.group(1)) if match else None

    if any(word in lowered for word in increase_words):
        pct = explicit if explicit is not None else 15.0
        factor = 1.0 + abs(pct) / 100.0
        return _action(
            "budget_change",
            {"type": "budget_change", "factor": round(factor, 3), "change_pct": round(abs(pct), 2)},
            title=f"提预算 {abs(pct):g}%",
            rationale="用户主动发起的预算上调",
        )
    if any(word in lowered for word in decrease_words):
        pct = explicit if explicit is not None else 15.0
        factor = 1.0 - abs(pct) / 100.0
        return _action(
            "budget_change",
            {"type": "budget_change", "factor": round(factor, 3), "change_pct": round(-abs(pct), 2)},
            title=f"降预算 {abs(pct):g}%",
            rationale="用户主动发起的预算下调",
        )
    if any(word in lowered for word in pause_words):
        return _action(
            "campaign_pause",
            {"type": "campaign_pause"},
            title="暂停广告计划",
            rationale="用户主动发起的暂停动作，需指定计划并二次确认",
        )
    return None


def _action(
    action_type: str,
    params: Dict[str, Any],
    title: str,
    rationale: str,
    risk_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    risk = risk_override or _risk(action_type, params)
    return {
        "action_type": action_type,
        "title": title,
        "rationale": rationale,
        "params": params,
        "risk_level": risk["risk_level"],
        "requires_confirmation": risk["requires_confirmation"],
        "label": "SYNTHETIC",
    }


def execute_loop(
    db: Session,
    merchant_id: str,
    action: Dict[str, Any],
    confirmed: bool,
    observe_days: int = 7,
) -> Dict[str, Any]:
    """Observe → Act → Observe: snapshot before, advance simulator, snapshot after."""
    risk = _risk(action["action_type"], action.get("params", {}))
    if risk["requires_confirmation"] and not confirmed:
        return {
            "status": "confirmation_required",
            "risk_level": risk["risk_level"],
            "action": action,
            "message": "该动作属于中/高风险，需要 confirmed=true 二次确认后才会执行。",
        }

    before = window_metrics(db, merchant_id, 7)
    simulator = SimulatorService(db)
    params = dict(action.get("params", {}))
    effect_type = params.pop("type")
    effects = [] if action["action_type"] == "observe" else [{"type": effect_type, **params}]
    result = simulator.advance(
        merchant_id, days=observe_days, effects=effects
    )
    after = window_metrics(db, merchant_id, 7)
    return {
        "status": "executed",
        "risk_level": risk["risk_level"],
        "action": action,
        "observe_days": observe_days,
        "before": before.get("current"),
        "after": after.get("current"),
        "delta_after_vs_before": _diff(before.get("current"), after.get("current")),
        "events_emitted": result.get("events_emitted", []),
        "label": "SYNTHETIC",
    }


def _diff(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not before or not after:
        return {}
    out = {}
    for key in ("ctr", "cpm", "cvr", "roi", "gmv", "ad_spend"):
        old, new = before.get(key), after.get(key)
        if old not in (None, 0) and new is not None:
            out[key] = round((new - old) / old * 100, 2)
    return out
