from __future__ import annotations

import pytest

from app.agent.actions import execute_loop, propose_for_diagnosis
from app.agent.orchestrator import AgentOrchestrator
from app.knowledge.service import KnowledgeService
from app.services.seed_service import SeedService
from app.services.world_gen import world_dataset


@pytest.fixture()
def world(db):
    SeedService(db).seed_all(world_dataset())
    KnowledgeService(db).seed_catalog()
    return db


def test_m001_diagnosis_fatigue_budget_chain(world) -> None:
    ctx = AgentOrchestrator(world).run(
        "M001", "为什么最近 ROI 一直下滑，CTR 也在掉，要不要加预算？"
    )
    report = ctx.diagnosis
    assert report is not None
    codes = [cause["code"] for cause in report["candidate_causes"]]
    assert "material_fatigue" in codes
    assert report["primary_cause"]["evidence"]
    assert report["primary_cause"]["knowledge_slugs"]
    assert report["quality_score"] >= 0.7
    if not ctx.quality_retried:
        assert ctx.quality_decision == "pass"


def test_pre_hook_asks_clarification_for_vague_query(world) -> None:
    ctx = AgentOrchestrator(world).run("M001", "这个东西怎么样啊")
    assert ctx.needs_clarification is True
    assert ctx.clarification_question
    assert ctx.observations == []


def test_actions_graded_by_risk(world) -> None:
    ctx = AgentOrchestrator(world).run(
        "M001", "为什么 CTR 一直下滑，素材疲劳了吗？"
    )
    actions = propose_for_diagnosis(ctx.diagnosis, ctx)
    assert actions
    low = [a for a in actions if a["action_type"] == "new_material"]
    assert low and low[0]["risk_level"] == "low"
    assert low[0]["requires_confirmation"] is False
    pauses = [a for a in actions if a["action_type"] == "campaign_pause"]
    if pauses:
        assert pauses[0]["risk_level"] == "high"
        assert pauses[0]["requires_confirmation"] is True


def test_observe_act_observe_loop_and_confirmation(world) -> None:
    action = {
        "action_type": "new_material",
        "params": {"type": "new_material", "material_name": "测试新素材", "ctr_factor": 1.3},
        "risk_level": "low",
        "requires_confirmation": False,
    }
    result = execute_loop(world, "M001", action, confirmed=False)
    assert result["status"] == "executed"
    assert result["before"] is not None and result["after"] is not None
    assert "roi" in result["delta_after_vs_before"] or "ctr" in result["delta_after_vs_before"]
    assert result["events_emitted"]

    medium = {
        "action_type": "budget_change",
        "params": {"type": "budget_change", "factor": 0.85, "change_pct": -15},
        "risk_level": "medium",
        "requires_confirmation": True,
    }
    blocked = execute_loop(world, "M001", medium, confirmed=False)
    assert blocked["status"] == "confirmation_required"
    executed = execute_loop(world, "M001", medium, confirmed=True)
    assert executed["status"] == "executed"


def test_agent_diagnosis_and_act_http(api_client, world) -> None:
    run = api_client.post(
        "/api/agent/run",
        json={"merchant_id": "M001", "message": "ROI 下降是什么原因，帮我诊断一下"},
    )
    assert run.status_code == 200
    body = run.json()
    assert body["diagnosis"]["primary_cause"]
    assert body["actions"]

    medium_action = next(
        (a for a in body["actions"] if a["action_type"] == "budget_change"), None
    )
    if medium_action is not None:
        blocked = api_client.post(
            "/api/agent/act",
            json={"merchant_id": "M001", "action": medium_action, "confirmed": False},
        )
        assert blocked.status_code == 409

    low_action = next(a for a in body["actions"] if not a["requires_confirmation"])
    executed = api_client.post(
        "/api/agent/act",
        json={"merchant_id": "M001", "action": low_action, "confirmed": False},
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == "executed"
