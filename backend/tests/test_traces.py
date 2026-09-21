from __future__ import annotations

import pytest

from app.knowledge.service import KnowledgeService
from app.models.tool_call import ToolCallLog
from app.models.trace import TraceRun, TraceSpan
from app.services.seed_service import SeedService
from app.services.world_gen import world_dataset
from app.trace.service import TraceService
from sqlalchemy import func, select


@pytest.fixture()
def world(db):
    SeedService(db).seed_all(world_dataset())
    KnowledgeService(db).seed_catalog()
    return db


def test_trace_service_records_spans_and_finish_summary(db) -> None:
    tracer = TraceService(db)
    trace_id = tracer.start_run("为什么 ROI 下滑", merchant_id="M001")

    class _Ctx:
        intent = {"intent": "performance_query", "confidence": 0.9}
        needs_clarification = False
        quality_retried = True

        class _D(dict):
            pass

        diagnosis = {
            "quality_score": 0.82,
            "primary_cause": {"code": "material_fatigue", "confidence": 0.8},
        }

    tracer.hook("intent", {"intent": "performance_query", "confidence": 0.9})
    tracer.hook("plan", {"steps": 4})
    tracer.hook(
        "tool_call",
        {"tool": "get_ad_performance", "success": True, "latency_ms": 12.5},
    )
    tracer.hook("tool_call", {"tool": "get_shop_profile", "success": False, "error": "execution_error"})
    tracer.hook("diagnosis", {"quality_score": 0.82, "primary_cause": "material_fatigue"})
    tracer.finish_run(_Ctx())

    summary = tracer.summary(trace_id)
    assert summary["primary_cause"] == "material_fatigue"
    assert summary["quality_score"] == 0.82
    assert summary["retry_count"] == 1
    assert summary["tool_call_count"] == 2
    assert "get_shop_profile" in summary["failed_tools"]
    assert summary["latency_ms"] > 0
    types = [stage["span_type"] for stage in summary["stages"]]
    assert {"intent", "planner", "tool_call", "diagnosis"} <= set(types)
    assert "payload" not in summary["stages"][0]


def test_agent_run_persists_trace_via_http(world, api_client) -> None:
    response = api_client.post(
        "/api/agent/run",
        json={"merchant_id": "M001", "message": "为什么最近 ROI 一直下滑，帮我诊断"},
    )
    assert response.status_code == 200
    trace_id = response.json()["trace_id"]
    assert trace_id.startswith("TR")

    trace_response = api_client.get(f"/api/traces/{trace_id}")
    assert trace_response.status_code == 200
    body = trace_response.json()
    assert body["intent"]
    assert body["tool_call_count"] >= 3
    assert body["label"] == "SYNTHETIC"
    stage_types = {stage["span_type"] for stage in body["stages"]}
    assert {"intent", "planner", "tool_call", "diagnosis"} <= stage_types
    assert "SYNTHETIC" in body["analysis_summary"] or "工具调用" in body["analysis_summary"]

    db = world
    linked = db.scalar(
        select(func.count())
        .select_from(ToolCallLog)
        .where(ToolCallLog.trace_id == trace_id)
    )
    assert linked == body["tool_call_count"]

    listed = api_client.get("/api/traces", params={"merchant_id": "M001"}).json()["items"]
    assert any(row["trace_id"] == trace_id for row in listed)

    missing = api_client.get("/api/traces/TR00000000000000")
    assert missing.status_code == 404


def test_act_blocked_and_executed_both_traced(world, api_client) -> None:
    run_response = api_client.post(
        "/api/agent/run",
        json={"merchant_id": "M001", "message": "为什么最近 ROI 一直下滑，帮我诊断"},
    )
    actions = run_response.json()["actions"]
    assert actions

    medium = next((action for action in actions if action["requires_confirmation"]), None)
    if medium is not None:
        blocked = api_client.post(
            "/api/agent/act",
            json={"merchant_id": "M001", "action": medium, "confirmed": False},
        )
        assert blocked.status_code == 409
        blocked_trace = blocked.json()["detail"]["trace_id"]
        summary = api_client.get(f"/api/traces/{blocked_trace}").json()
        assert summary["decision"] == "clarification_required"
        assert summary["stages"][-1]["status"] == "blocked"

    low = next(action for action in actions if not action["requires_confirmation"])
    executed = api_client.post(
        "/api/agent/act",
        json={"merchant_id": "M001", "action": low, "confirmed": True, "observe_days": 7},
    )
    assert executed.status_code == 200
    trace_id = executed.json()["trace_id"]
    summary = api_client.get(f"/api/traces/{trace_id}").json()
    assert summary["status"] == "done"
    assert any(stage["span_type"] == "action" for stage in summary["stages"])

    db = world
    run = db.get(TraceRun, trace_id)
    assert run.tool_call_count == 0
    assert db.scalar(select(func.count()).select_from(TraceSpan).where(TraceSpan.trace_id == trace_id)) >= 1
