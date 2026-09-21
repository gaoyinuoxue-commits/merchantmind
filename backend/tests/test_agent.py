from __future__ import annotations

import pytest

from app.agent.intent import (
    INTENT_ACTION,
    INTENT_GREETING,
    INTENT_KNOWLEDGE,
    INTENT_PERFORMANCE,
    classify_intent,
    is_metric_lookup,
)
from app.agent.orchestrator import AgentOrchestrator
from app.agent.planner import build_plan
from app.models import Conversation, Merchant, Message
from app.models.performance import PerformanceDaily
from app.services.conversation_service import ConversationService
from app.knowledge.service import KnowledgeService
from app.services.seed_service import SeedService
from app.services.world_gen import world_dataset
from sqlalchemy import func, select


@pytest.fixture()
def world(db):
    SeedService(db).seed_all(world_dataset())
    KnowledgeService(db).seed_catalog()
    return "M001"


def test_intent_classifier() -> None:
    assert classify_intent("为什么最近 ROI 一直下滑？").intent == INTENT_PERFORMANCE
    assert classify_intent("帮我把预算提高 30%").intent == INTENT_ACTION
    assert classify_intent("ROI 是什么怎么算的？").intent == INTENT_KNOWLEDGE
    assert classify_intent("你好").intent == INTENT_GREETING
    diagnosis = classify_intent("CTR 下降素材是不是疲劳了")
    assert diagnosis.intent == INTENT_PERFORMANCE
    assert "ctr" in diagnosis.signals["metrics"]
    assert "material" in diagnosis.signals["domains"]


def test_planner_selects_tools_by_signal() -> None:
    intent = classify_intent("为什么点击率 CTR 一直掉，素材疲劳了吗")
    plan = build_plan(intent, "M001", "为什么点击率一直掉")
    tools = [step.get("tool") for step in plan if step["kind"] == "tool"]
    assert "get_shop_profile" in tools
    assert "get_ad_performance" in tools
    assert "get_material_performance" in tools
    assert "get_historical_cases" in tools
    assert any(step["kind"] == "knowledge" for step in plan)

    action = classify_intent("帮我加预算放量")
    action_plan = build_plan(action, "M001", "帮我加预算放量")
    day_windows = [
        step["arguments"].get("days")
        for step in action_plan
        if step.get("tool") == "get_ad_performance"
    ]
    assert 30 in day_windows

    assert build_plan(classify_intent("你好"), "M001", "你好") == []


def test_orchestrator_runs_full_loop(db, world) -> None:
    orchestrator = AgentOrchestrator(db)
    ctx = orchestrator.run(world, "为什么最近 ROI 一直下滑？素材是不是疲劳了，要不要加预算？")
    assert ctx.intent["intent"] == INTENT_PERFORMANCE
    assert all(observation["success"] for observation in ctx.observations)
    tools = [observation["tool"] for observation in ctx.observations if observation["tool"]]
    assert "get_ad_performance" in tools
    assert "get_material_performance" in tools
    assert len(ctx.knowledge) >= 1
    assert ctx.memories == [] or all("score" in m for m in ctx.memories)


def test_orchestrator_extracts_preference_memory(db, world) -> None:
    orchestrator = AgentOrchestrator(db)
    ctx = orchestrator.run(world, "我们决定加预算放量冲 GMV")
    assert ctx.extracted_memory_count >= 1
    second = AgentOrchestrator(db).run(world, "预算怎么花比较好")
    assert any("放量" in m["content"] for m in second.memories)


def test_agent_http_run_end_to_end(api_client, db, world) -> None:
    response = api_client.post(
        "/api/agent/run",
        json={"merchant_id": "M001", "message": "为什么最近 ROI 一直下滑？"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"]["intent"] == INTENT_PERFORMANCE
    assert body["conversation_id"]
    assert len(body["plan"]) >= 3
    assert "意图识别" in body["reply"]

    messages = db.scalar(select(func.count()).select_from(Message))
    assert messages == 2

    follow_up = api_client.post(
        "/api/agent/run",
        json={
            "merchant_id": "M001",
            "message": "那素材疲劳了怎么办？",
            "conversation_id": body["conversation_id"],
        },
    )
    assert follow_up.status_code == 200
    assert follow_up.json()["conversation_id"] == body["conversation_id"]
    assert db.scalar(select(func.count()).select_from(Conversation)) == 1
    assert db.scalar(select(func.count()).select_from(Message)) == 4

    greeting = api_client.post(
        "/api/agent/run", json={"merchant_id": "M001", "message": "你好"}
    )
    assert greeting.status_code == 200
    assert greeting.json()["plan"] == []

    missing = api_client.post(
        "/api/agent/run", json={"merchant_id": "NOPE", "message": "你好"}
    )
    assert missing.status_code == 404


def test_is_metric_lookup_detects_value_requests() -> None:
    assert is_metric_lookup("现在的ROI是多少")
    assert is_metric_lookup("帮我查一下点击率")
    assert is_metric_lookup("今天花了多少钱")
    assert not is_metric_lookup("ROI 怎么样")
    assert not is_metric_lookup("为什么 ROI 下滑")
    assert not is_metric_lookup("怎么提升 ROI")
    assert not is_metric_lookup("投产比一般多少")
    assert not is_metric_lookup("年轻白领这个人群转化率怎么样")
    assert not is_metric_lookup("今天天气怎么样")


def test_orchestrator_metric_lookup_without_diagnosis(db, world) -> None:
    ctx = AgentOrchestrator(db).run(world, "现在的 ROI 是多少")
    assert ctx.metric_lookup is not None
    assert ctx.diagnosis is None
    latest = ctx.metric_lookup["latest"]
    assert latest and latest["current"]["roi"] is not None
    # Recomputed value matches the stored physical column for the anchor day.
    anchor = latest["window"]["anchor_date"]
    from datetime import date as date_type

    row = db.scalar(
        select(PerformanceDaily).where(
            PerformanceDaily.merchant_id == world,
            PerformanceDaily.date == date_type.fromisoformat(anchor),
        )
    )
    assert abs(latest["current"]["roi"] - row.roi) < 0.02
    tools = [o["tool"] for o in ctx.observations if o["tool"]]
    assert "get_ad_performance" in tools


def test_metric_lookup_http_returns_number(api_client, db, world) -> None:
    resp = api_client.post(
        "/api/agent/run",
        json={"merchant_id": "M001", "message": "现在的ROI是多少"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "指标直查" in body["reply"]
    assert "ROI =" in body["reply"]
    assert "意图识别" not in body["reply"]
    assert body["diagnosis"] is None
