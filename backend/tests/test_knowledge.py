from __future__ import annotations

from sqlalchemy import func, select

from app.knowledge.catalog import catalog_entries
from app.knowledge.service import KnowledgeService, rewrite_query
from app.models.knowledge import KnowledgeItem
from app.services.seed_service import SeedService
from app.services.world_gen import world_dataset


def test_catalog_covers_six_types_and_50_plus() -> None:
    entries = catalog_entries()
    assert len(entries) >= 50
    types_ = {entry["type"] for entry in entries}
    assert types_ == {
        "business_rule",
        "diagnostic_rule",
        "industry_insight",
        "best_practice",
        "metric_definition",
        "case",
    }
    for entry in entries:
        assert entry["content"] and entry["title"]
        assert entry["version"] >= 1


def test_seed_versions_and_idempotency(db) -> None:
    service = KnowledgeService(db)
    result = service.seed_catalog()
    assert result["entries"] == len(catalog_entries())
    assert result["archived_old_versions"] == 2

    rows = list(db.scalars(select(KnowledgeItem)).all())
    by_slug = {}
    for row in rows:
        by_slug.setdefault(row.slug, []).append(row)
    case_versions = sorted(by_slug["case_fatigue_budget"], key=lambda r: r.version)
    assert [r.version for r in case_versions] == [1, 2, 3]
    assert [r.status for r in case_versions] == ["archived", "archived", "verified"]
    assert all(row.embedding is not None for row in rows)

    total = db.scalar(select(func.count()).select_from(KnowledgeItem))
    second = service.seed_catalog()
    assert second["archived_old_versions"] == 0
    assert db.scalar(select(func.count()).select_from(KnowledgeItem)) == total


def test_query_rewrite_expands_terms() -> None:
    rewritten = rewrite_query("加预算后投产一直掉")
    assert "ROI" in rewritten and "CPM" in rewritten and "预算" in rewritten


def test_rag_retrieval_finds_right_knowledge(db) -> None:
    KnowledgeService(db).seed_catalog()
    service = KnowledgeService(db)

    fatigue = service.retrieve("素材疲劳导致点击率下滑要不要加预算？", industry="womenswear", top_k=5)
    assert fatigue
    slugs = {item["slug"] for item in fatigue[:3]}
    assert "diag_fatigue" in slugs or "diag_budget_cpm" in slugs
    assert "case_fatigue_budget" in slugs
    assert all(item["score"] > 0 for item in fatigue)

    definition = service.retrieve("ROI 是什么怎么算？", top_k=3)
    assert definition[0]["slug"] == "metric_roi"
    assert all(item["version"] >= 1 for item in definition)


def test_propose_candidate_and_verify_creates_version(db) -> None:
    service = KnowledgeService(db)
    service.seed_catalog()
    candidate = service.propose_candidate(
        {
            "slug": "diag_fatigue",
            "type": "diagnostic_rule",
            "industry": None,
            "title": "素材疲劳诊断补充版",
            "content": "补充：CTR 7 日趋势是先行指标",
            "recommendation": "先换素材",
            "merchant_count": 3,
            "quality_score": 0.7,
        }
    )
    assert candidate.status == "candidate"
    assert candidate.version == 2

    verified = service.verify(candidate.knowledge_id)
    assert verified.status == "verified"
    assert verified.version == 3
    db.expire_all()
    old_verified = list(
        db.scalars(
            select(KnowledgeItem).where(
                KnowledgeItem.slug == "diag_fatigue",
                KnowledgeItem.status == "verified",
            )
        ).all()
    )
    assert len(old_verified) == 1
    assert old_verified[0].knowledge_id == verified.knowledge_id


def test_scan_patterns_detects_world_signal(db) -> None:
    SeedService(db).seed_all(world_dataset())
    service = KnowledgeService(db)
    candidate = service.propose_from_merchant_patterns()
    assert candidate is not None
    assert candidate.status == "candidate"
    assert candidate.merchant_count >= 2


def test_knowledge_http_api(api_client, db) -> None:
    KnowledgeService(db).seed_catalog()
    response = api_client.post(
        "/api/knowledge/query",
        json={"query": "点击率一直掉是什么原因", "industry": "womenswear", "top_k": 3},
    )
    assert response.status_code == 200
    results = response.json()
    assert len(results) <= 3
    assert results[0]["type"] in {"diagnostic_rule", "metric_definition"}

    missing = api_client.post("/api/knowledge/NOPE/verify")
    assert missing.status_code == 404
