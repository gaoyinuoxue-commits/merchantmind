from __future__ import annotations

import pytest

from app.badcase.service import BadcaseService
from app.eval.service import EvaluationService
from app.knowledge.service import KnowledgeService
from app.monitoring.service import DEMO_LABEL, SYNTHETIC_BUSINESS_LABEL, MonitoringService
from app.services.seed_service import SeedService
from app.services.world_gen import world_dataset


@pytest.fixture()
def world(db):
    SeedService(db).seed_all(world_dataset())
    KnowledgeService(db).seed_catalog()
    return db


def test_monitoring_overview_labels_and_shape(world) -> None:
    db = world
    snapshot = MonitoringService(db).overview(window_days=30)

    assert snapshot["label"] == DEMO_LABEL
    monitoring = snapshot["monitoring"]
    assert monitoring["label"] == DEMO_LABEL
    assert snapshot["ai_capability"]["label"] == DEMO_LABEL
    assert snapshot["agent_usage"]["label"] == DEMO_LABEL
    business = snapshot["business_kpi"]
    assert business["label"] == SYNTHETIC_BUSINESS_LABEL

    for key in (
        "requests", "succeeded", "success_rate", "tool_calls", "tool_failures",
        "memory_writes", "memory_conflicts", "retrieval_misses", "hallucinations",
        "retries", "latency_p50_ms", "token_proxy_total", "feedback_count", "helpful_rate",
    ):
        assert key in monitoring

    assert business["anchor_date"] is not None
    assert business["fatigued_materials"] >= 1
    assert 0 < business["fatigued_share"] <= 1
    assert business["roi"]["recent"] is not None
    assert business["roi"]["previous"] is not None
    assert business["window"] == "last 7 days vs previous 7 days"


def test_monitoring_aggregates_real_activity(world, api_client) -> None:
    db = world
    EvaluationService(db).run_evaluation(judge="heuristic", case_ids=["greet_1", "diag_arch_M001", "mem_budget"])
    BadcaseService(db).create_feedback(rating=5, merchant_id="M001")
    BadcaseService(db).create_feedback(rating=2, comment="不准", merchant_id="M001")

    run = api_client.post(
        "/api/agent/run", json={"merchant_id": "M001", "message": "为什么最近 ROI 一直下滑，帮我诊断"}
    ).json()
    low_action = next(action for action in run["actions"] if not action["requires_confirmation"])
    executed = api_client.post(
        "/api/agent/act",
        json={"merchant_id": "M001", "action": low_action, "confirmed": True},
    )
    assert executed.status_code == 200

    snapshot = MonitoringService(db).overview()
    monitoring = snapshot["monitoring"]
    assert monitoring["requests"] >= 4
    assert monitoring["success_rate"] == 1.0
    assert monitoring["tool_failure_rate"] == 0.0
    assert monitoring["hallucination_rate"] == 0.0
    assert monitoring["latency_p95_ms"] is not None
    assert monitoring["token_proxy_total"] > monitoring["requests"] * 700
    assert monitoring["feedback_count"] == 2
    assert monitoring["helpful_rate"] == 0.5
    assert monitoring["memory_writes"] >= 1

    capability = snapshot["ai_capability"]
    assert capability["eval_run_id"] is not None
    assert capability["judge"] == "heuristic"
    assert capability["task_success_rate"] >= 0
    assert capability["answer_quality_proxy"] is not None

    usage = snapshot["agent_usage"]
    assert usage["actions_requested"] >= 1
    assert usage["actions_executed"] >= 1
    assert usage["execution_rate"] is not None

    api = api_client.get("/api/monitoring/overview", params={"window_days": 7})
    assert api.status_code == 200
    assert api.json()["monitoring"]["label"] == DEMO_LABEL
    assert api.json()["business_kpi"]["label"] == SYNTHETIC_BUSINESS_LABEL
    assert api_client.get("/api/monitoring/overview", params={"window_days": 0}).status_code == 422


def test_helpful_rate_none_without_feedback(world) -> None:
    db = world
    monitoring = MonitoringService(db).overview()["monitoring"]
    assert monitoring["feedback_count"] == 0
    assert monitoring["helpful_rate"] is None


def test_merchant_directory_endpoints(world, api_client) -> None:
    listing = api_client.get("/api/merchants")
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert listing.json()["label"] == "SYNTHETIC"
    assert len(items) >= 3
    merchant_id = items[0]["merchant_id"]

    detail = api_client.get(f"/api/merchants/{merchant_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["label"] == "SYNTHETIC"
    assert len(body["performance"]) >= 1
    assert len(body["campaigns"]) >= 1
    assert len(body["materials"]) >= 1
    assert {"date", "gmv", "ad_spend", "ctr", "cpm", "roi"} <= set(body["performance"][0])

    assert api_client.get("/api/merchants/NOPE").status_code == 404
