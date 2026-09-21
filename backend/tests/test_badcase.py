from __future__ import annotations

import pytest

from app.badcase.classifier import classify_case_failure, classify_trace
from app.badcase.service import BadcaseService
from app.eval.service import EvaluationService
from app.models.badcase import Badcase, Feedback
from app.models.trace import TraceRun
from app.services.seed_service import SeedService
from app.services.world_gen import world_dataset
from sqlalchemy import func, select


@pytest.fixture()
def world(db):
    SeedService(db).seed_all(world_dataset())
    return db


def _verdict(**overrides):
    base = {
        "passed": False,
        "hallucination": False,
        "hallucination_violations": [],
        "intent_match": True,
        "tool_recall": 1.0,
        "primary_ok": True,
        "causes_min_hits_ok": True,
        "action_type_match": True,
        "no_tools": True,
        "extracted": True,
        "recalled": True,
    }
    base.update(overrides)
    return base


def test_classifier_buckets_every_failure_category() -> None:
    prediction = {"failed_tools": [], "needs_clarification": False}

    case = {"id": "c1", "type": "knowledge", "message": "q", "expected": {}}
    triage = classify_case_failure(
        case, _verdict(hallucination=True, hallucination_violations=["unknown_cause:x"]), prediction
    )
    assert triage["error_type"] == "hallucination"
    assert triage["severity"] == "high"

    tool = classify_case_failure(
        {"id": "c2", "type": "diagnosis"}, _verdict(), {"failed_tools": ["get_ad_performance"]}
    )
    assert tool["error_type"] == "tool"
    assert tool["affected_module"] == "tools.service"

    mem_miss = classify_case_failure(
        {"id": "c3", "type": "memory"}, _verdict(extracted=False), prediction
    )
    assert mem_miss["error_type"] == "retrieval"
    assert mem_miss["affected_module"] == "memory.governance"

    mem_recall = classify_case_failure(
        {"id": "c4", "type": "memory"}, _verdict(extracted=True, recalled=False), prediction
    )
    assert mem_recall["affected_module"] == "memory.retrieval"

    kn = classify_case_failure(
        {"id": "c5", "type": "knowledge"}, _verdict(intent_match=True), prediction
    )
    assert kn["error_type"] == "retrieval"
    assert kn["affected_module"] == "knowledge.service"

    action = classify_case_failure(
        {"id": "c6", "type": "action"}, _verdict(action_type_match=False), prediction
    )
    assert action["error_type"] == "routing"
    assert action["affected_module"] == "agent.actions"

    routing = classify_case_failure(
        {"id": "c7", "type": "diagnosis"},
        _verdict(intent_match=False),
        {"failed_tools": [], "needs_clarification": False},
    )
    assert routing["error_type"] == "routing"
    assert routing["affected_module"] == "agent.intent"

    reasoning = classify_case_failure(
        {"id": "c8", "type": "diagnosis"},
        _verdict(primary_ok=False),
        {"failed_tools": [], "needs_clarification": False},
    )
    assert reasoning["error_type"] == "reasoning"
    assert reasoning["affected_module"] == "agent.diagnosis"


def test_failed_eval_case_auto_opens_dedup_badcase(world) -> None:
    db = world
    result = EvaluationService(db).run_evaluation(case_ids=["kn_fatigue"])
    assert result["metrics"]["passed"] == 0

    badcases = db.scalars(select(Badcase).where(Badcase.source == "eval")).all()
    assert len(badcases) == 1
    badcase = badcases[0]
    assert badcase.case_id == "kn_fatigue"
    assert badcase.error_type == "retrieval"
    assert badcase.affected_module == "knowledge.service"
    assert badcase.status == "open"
    assert badcase.eval_run_id == result["eval_run_id"]
    assert badcase.suggested_fix
    assert badcase.evidence["prediction"]["intent"] == "knowledge_query"

    EvaluationService(db).run_evaluation(case_ids=["kn_fatigue"])
    db.expire_all()
    remaining = db.scalars(select(Badcase).where(Badcase.source == "eval")).all()
    assert len(remaining) == 1
    assert remaining[0].occurrence_count == 2
    assert len(remaining[0].evidence["eval_run_ids"]) == 2


def test_passing_eval_cases_open_no_badcase(world) -> None:
    db = world
    from app.knowledge.service import KnowledgeService

    KnowledgeService(db).seed_catalog()
    EvaluationService(db).run_evaluation(case_ids=["greet_1", "greet_2"])
    assert db.scalar(select(func.count()).select_from(Badcase)) == 0


def test_feedback_positive_and_negative_paths(world) -> None:
    db = world
    service = BadcaseService(db)

    positive = service.create_feedback(rating=5, comment="很有帮助", merchant_id="M001")
    assert positive["helpful"] is True
    assert positive["badcase_id"] is None

    trace = TraceRun(
        trace_id="TRfeedback0000001",
        merchant_id="M001",
        query="这个东西怎么样啊",
        status="clarification_required",
        needs_clarification=True,
    )
    db.add(trace)
    db.commit()

    negative = service.create_feedback(
        rating=2, comment="答非所问", trace_id=trace.trace_id, merchant_id="M001"
    )
    assert negative["helpful"] is False
    badcase = service.get_badcase(negative["badcase_id"])
    assert badcase.source == "human"
    assert badcase.reporter == "human"
    assert badcase.error_type == "routing"
    assert badcase.feedback_id is not None
    assert badcase.evidence["rating"] == 2

    feedback = db.get(Feedback, positive["feedback_id"])
    assert feedback.helpful is True
    assert len(service.list_feedback(limit=10)) == 2


def test_classify_trace_returns_none_when_healthy() -> None:
    class _Healthy:
        needs_clarification = False
        status = "done"

    assert classify_trace(_Healthy(), []) is None


def test_badcase_http_endpoints(world, api_client) -> None:
    good = api_client.post(
        "/api/feedback", json={"rating": 5, "comment": "不错", "merchant_id": "M001"}
    )
    assert good.status_code == 200
    assert good.json()["badcase_id"] is None
    assert api_client.post("/api/feedback", json={"rating": 9}).status_code == 422

    bad = api_client.post(
        "/api/feedback", json={"rating": 1, "comment": "完全不准", "merchant_id": "M001"}
    )
    assert bad.status_code == 200
    badcase_id = bad.json()["badcase_id"]

    listing = api_client.get("/api/badcases", params={"status": "open"})
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["label"] == "SYNTHETIC"
    assert api_client.get("/api/badcases", params={"error_type": "routing"}).json()["items"] == []

    detail = api_client.get(f"/api/badcases/{badcase_id}")
    assert detail.status_code == 200
    assert detail.json()["error_type"] == "other"

    patched = api_client.patch(f"/api/badcases/{badcase_id}", json={"status": "fixed"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "fixed"
    assert patched.json()["resolved_at"] is not None

    invalid = api_client.patch(f"/api/badcases/{badcase_id}", json={"status": "bogus"})
    assert invalid.status_code == 400
    assert api_client.get("/api/badcases/999999").status_code == 404
    assert api_client.patch("/api/badcases/999999", json={"status": "fixed"}).status_code == 404

    feedback_list = api_client.get("/api/feedback")
    assert feedback_list.status_code == 200
    assert len(feedback_list.json()["items"]) == 2
    assert feedback_list.json()["label"] == "SYNTHETIC"
