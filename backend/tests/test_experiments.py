from __future__ import annotations

import pytest

from app.agent.orchestrator import AgentOrchestrator, RunProfile
from app.experiments.service import ExperimentService
from app.experiments.variants import DEFAULT_CASE_IDS, DEFAULT_VARIANTS
from app.knowledge.service import KnowledgeService
from app.models.experiment import Experiment, ExperimentVariantRun
from app.services.seed_service import SeedService
from app.services.world_gen import world_dataset
from sqlalchemy import func, select


@pytest.fixture()
def world(db):
    SeedService(db).seed_all(world_dataset())
    KnowledgeService(db).seed_catalog()
    return db


def test_default_experiment_runs_all_variants_with_metrics(world) -> None:
    db = world
    result = ExperimentService(db).create_experiment()
    assert result["status"] == "done"
    assert result["label"] == "SYNTHETIC"
    assert len(result["runs"]) == len(DEFAULT_VARIANTS) == 5
    assert result["case_ids"] == DEFAULT_CASE_IDS

    for run in result["runs"]:
        assert run["total"] == len(DEFAULT_CASE_IDS)
        metrics = run["metrics"]
        assert metrics["task_success_rate"] >= 0.9
        assert metrics["hallucination_rate"] == 0.0
        assert metrics["latency_p50_ms"] > 0
        assert metrics["latency_p95_ms"] >= metrics["latency_p50_ms"]
        assert metrics["token_proxy_total"] > 0
        assert sum(bucket["total"] for bucket in metrics["by_type"].values()) == run["total"]
        assert len(run["cases"]) == run["total"]
        assert run["cases"][0]["trace_id"].startswith("TR")

    comparison = result["results"]
    assert comparison["baseline"] == "baseline"
    assert comparison["winner"] in {v["name"] for v in DEFAULT_VARIANTS}
    assert set(comparison["ranking"]) == {v["name"] for v in DEFAULT_VARIANTS}
    assert "baseline" not in comparison["deltas_vs_baseline"]
    for delta in comparison["deltas_vs_baseline"].values():
        assert set(delta) >= {"task_success_rate", "hallucination_rate", "latency_p50_ms", "token_proxy_total"}

    names = {run["variant_name"] for run in result["runs"]}
    assert {"baseline", "strict_gate", "knowledge_topk_5", "memory_topk_3", "semantic_ranking"} == names
    strict = next(run for run in result["runs"] if run["variant_name"] == "strict_gate")
    kn5 = next(run for run in result["runs"] if run["variant_name"] == "knowledge_topk_5")
    baseline = next(run for run in result["runs"] if run["variant_name"] == "baseline")
    assert strict["metrics"]["retry_rate"] >= baseline["metrics"]["retry_rate"]
    assert kn5["metrics"]["token_proxy_total"] <= baseline["metrics"]["token_proxy_total"]

    stored = db.get(Experiment, result["id"])
    assert stored is not None
    assert db.scalar(
        select(func.count()).select_from(ExperimentVariantRun).where(
            ExperimentVariantRun.experiment_id == result["id"]
        )
    ) == 5


def test_recorded_dimensions_pass_through(world) -> None:
    db = world
    variants = [
        {"name": "baseline", "config": {}},
        {
            "name": "llm_qwen_v2",
            "config": {"model": "qwen2", "temperature": 0.2, "prompt_version": "v2_evidence_first"},
        },
    ]
    result = ExperimentService(db).create_experiment(
        name="录制维度实验", variants=variants, case_ids=["greet_1", "kn_fatigue"]
    )
    qwen = next(item for item in result["results"]["variants"] if item["variant_name"] == "llm_qwen_v2")
    assert qwen["recorded_dimensions"] == ["model", "temperature", "prompt_version"]
    assert qwen["applied_dimensions"] == []


def test_profile_overrides_change_runtime_behaviour(world) -> None:
    db = world
    wide = AgentOrchestrator(db, profile=RunProfile(knowledge_top_k=8)).run(
        "M001", "素材疲劳的判断标准是什么，怎么定义素材疲劳"
    )
    narrow = AgentOrchestrator(db, profile=RunProfile(knowledge_top_k=2)).run(
        "M001", "素材疲劳的判断标准是什么，怎么定义素材疲劳"
    )
    assert wide.intent["intent"] == "knowledge_query"
    assert len(narrow.knowledge) <= 2
    assert len(wide.knowledge) >= len(narrow.knowledge)


def test_experiment_validation_and_http(world, api_client) -> None:
    db = world
    with pytest.raises(ValueError):
        ExperimentService(db).create_experiment(variants=[{"name": "only", "config": {}}])
    with pytest.raises(ValueError):
        ExperimentService(db).create_experiment(case_ids=["no_such_case"])

    created = api_client.post(
        "/api/experiments",
        json={
            "name": "接口实验",
            "variants": [
                {"name": "baseline", "config": {}},
                {"name": "topk_3", "config": {"memory_top_k": 3}},
            ],
            "case_ids": ["greet_1", "clarify_vague_1"],
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert len(body["runs"]) == 2
    assert body["results"]["winner"]

    listed = api_client.get("/api/experiments")
    assert listed.status_code == 200
    assert any(item["id"] == body["id"] for item in listed.json()["items"])

    detail = api_client.get(f"/api/experiments/{body['id']}")
    assert detail.status_code == 200
    assert api_client.get("/api/experiments/999999").status_code == 404

    bad = api_client.post(
        "/api/experiments", json={"variants": [{"name": "only", "config": {}}]}
    )
    assert bad.status_code == 400
