from __future__ import annotations

import pytest

from app.eval.dataset import ground_truth_cases
from app.eval.judges import CAUSE_WHITELIST, detect_hallucination
from app.eval.service import EvaluationService
from app.knowledge.service import KnowledgeService
from app.models.evaluation import EvalCaseResult, EvalRun
from app.models.trace import TraceRun
from app.services.seed_service import SeedService
from app.services.world_gen import world_dataset
from sqlalchemy import func, select


@pytest.fixture()
def world(db):
    SeedService(db).seed_all(world_dataset())
    KnowledgeService(db).seed_catalog()
    return db


def _metric_rates(metrics):
    return [
        metrics["task_success_rate"],
        metrics["tool_accuracy"],
        metrics["cause_recall_at_3"],
        metrics["knowledge_recall_at_5"],
        metrics["hallucination_rate"],
        metrics["retry_rate"],
    ]


def test_dataset_scale_and_type_distribution() -> None:
    cases = ground_truth_cases()
    assert len(cases) >= 50
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))
    counts = {}
    for case in cases:
        counts[case["type"]] = counts.get(case["type"], 0) + 1
    assert counts == {
        "diagnosis": 30,
        "knowledge": 8,
        "action": 6,
        "greeting": 2,
        "clarify": 2,
        "memory": 6,
    }
    memory_cases = [case for case in cases if case["type"] == "memory"]
    assert all(case.get("followup_message") for case in memory_cases)


def test_rule_run_persists_results_and_full_metric_set(world) -> None:
    db = world
    result = EvaluationService(db).run_evaluation(judge="rule", note="pytest rule")
    metrics = result["metrics"]
    run_id = result["eval_run_id"]

    assert result["judge"] == "rule"
    assert result["label"] == "SYNTHETIC"
    assert metrics["total"] == 54
    assert metrics["passed"] == metrics["total"]
    assert metrics["task_success_rate"] >= 0.85
    assert metrics["hallucination_rate"] == 0.0
    assert metrics["tool_accuracy"] >= 0.95
    assert metrics["cause_recall_at_3"] >= 0.9
    assert metrics["knowledge_recall_at_5"] >= 0.8
    assert 0.0 <= metrics["retry_rate"] <= 1.0
    for rate in _metric_rates(metrics):
        assert 0.0 <= rate <= 1.0
    assert metrics["latency_p50_ms"] > 0
    assert metrics["latency_p95_ms"] >= metrics["latency_p50_ms"]
    assert metrics["latency_avg_ms"] >= metrics["latency_p50_ms"] * 0.5
    assert metrics["token_proxy_total"] > 54 * 768
    assert sum(bucket["total"] for bucket in metrics["by_type"].values()) == 54

    run = db.get(EvalRun, run_id)
    assert run is not None
    assert run.total == 54
    assert run.judge == "rule"
    assert run.label == "SYNTHETIC"

    case_count = db.scalar(
        select(func.count()).select_from(EvalCaseResult).where(EvalCaseResult.eval_run_id == run_id)
    )
    assert case_count == 54

    detail = EvaluationService(db).get_run(run_id)
    by_type = {}
    for case in detail["cases"]:
        by_type.setdefault(case["case_type"], []).append(case)
        assert case["trace_id"].startswith("TR")
        assert db.get(TraceRun, case["trace_id"]) is not None
        assert case["judged_by"] == "rule"
        assert case["metrics"]["hallucination"] is False
        prediction = case["prediction"]
        for code in prediction["candidate_codes"]:
            assert code in CAUSE_WHITELIST

    memory_cases = by_type["memory"]
    traffic_memory = next(case for case in memory_cases if case["case_id"] == "mem_traffic")
    assert any("直播信息流" in content for content in traffic_memory["prediction"]["followup_memory"])

    list_view = EvaluationService(db).list_runs()
    assert any(row["eval_run_id"] == run_id for row in list_view)
    assert EvaluationService(db).get_run(999999) is None


def test_heuristic_run_carries_llm_proxy_scores(world) -> None:
    db = world
    result = EvaluationService(db).run_evaluation(judge="heuristic")
    detail = EvaluationService(db).get_run(result["eval_run_id"])
    for case in detail["cases"]:
        assert case["judged_by"] == "heuristic_llm_proxy"
        assert case["judge_score"] is not None
        assert 0.0 <= case["judge_score"] <= 1.0
    assert result["metrics"]["human_rated"] == 0
    assert result["metrics"]["human_agreement_rate"] is None


def test_human_verdict_recomputes_aggregates(world) -> None:
    db = world
    result = EvaluationService(db).run_evaluation()
    case_result_id = db.scalar(
        select(EvalCaseResult.id)
        .where(EvalCaseResult.eval_run_id == result["eval_run_id"])
        .order_by(EvalCaseResult.id)
        .limit(1)
    )
    response = EvaluationService(db).record_human_verdict(case_result_id, 5, "证据充分")
    metrics = response["run"]["metrics"]
    assert metrics["human_rated"] == 1
    assert metrics["human_agreement_rate"] == 1.0

    case = db.get(EvalCaseResult, case_result_id)
    assert case.human_rating == 5
    assert case.human_feedback == "证据充分"

    with pytest.raises(KeyError):
        EvaluationService(db).record_human_verdict(999999, 3)


def test_eval_http_endpoints_and_404(world, api_client) -> None:
    created = api_client.post("/api/eval/runs", params={"judge": "rule"})
    assert created.status_code == 200
    run_id = created.json()["eval_run_id"]
    assert created.json()["metrics"]["total"] == 54

    listed = api_client.get("/api/eval/runs")
    assert listed.status_code == 200
    assert any(row["eval_run_id"] == run_id for row in listed.json()["items"])
    assert listed.json()["label"] == "SYNTHETIC"

    detail = api_client.get(f"/api/eval/runs/{run_id}")
    assert detail.status_code == 200
    assert len(detail.json()["cases"]) == 54

    assert api_client.get("/api/eval/runs/999999").status_code == 404
    assert api_client.post("/api/eval/runs", params={"judge": "bogus"}).status_code == 422

    db = world
    result_pk = db.scalar(
        select(EvalCaseResult.id)
        .where(EvalCaseResult.eval_run_id == run_id)
        .order_by(EvalCaseResult.id)
        .limit(1)
    )
    verdict = api_client.post(f"/api/eval/cases/{result_pk}/human", json={"rating": 4})
    assert verdict.status_code == 200
    assert verdict.json()["run"]["metrics"]["human_rated"] == 1

    bad_rating = api_client.post(f"/api/eval/cases/{result_pk}/human", json={"rating": 9})
    assert bad_rating.status_code == 422
    assert api_client.post("/api/eval/cases/999999/human", json={"rating": 3}).status_code == 404


def test_detect_hallucination_flags_ungrounded_claims() -> None:
    class _Ctx:
        diagnosis = {
            "candidate_causes": [
                {
                    "code": "mystery_cause",
                    "evidence": [{"source": "get_secret_tool"}],
                    "knowledge_slugs": ["missing_slug"],
                }
            ]
        }
        observations = [{"tool": "get_shop_profile", "success": True}]
        knowledge = []

    violations = detect_hallucination(_Ctx())
    assert "unknown_cause:mystery_cause" in violations
    assert any(v.startswith("evidence_without_observation") for v in violations)
    assert "knowledge_not_grounded:missing_slug" in violations
