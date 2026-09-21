from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.memory.extractor import extract_memories
from app.memory.governance import MemoryGovernanceService
from app.memory.retrieval import MemoryRetrievalService
from app.models.merchant import Merchant
from app.models.memory import MemoryConflict, MemoryItem


@pytest.fixture()
def shop(db):
    merchant = Merchant(
        merchant_id="T-MEM-1",
        merchant_name="记忆测试店",
        industry="apparel",
        business_stage="growth",
        city="杭州",
    )
    db.add(merchant)
    db.commit()
    return merchant


def test_extractor_detects_budget_preference_and_slot() -> None:
    candidates = extract_memories("我们最近愿意加预算放量，主拍实拍风格")
    slots = {c["tags"][0] for c in candidates}
    assert "budget_preference" in slots
    budget = next(c for c in candidates if c["tags"][0] == "budget_preference")
    assert budget["tags"][1] == "budget_preference:放量增长"
    assert budget["type"] == "preference"


def test_ingest_dedup_accumulates_evidence(db, shop) -> None:
    service = MemoryGovernanceService(db)
    first = service.ingest_candidate(
        "T-MEM-1", "profile", "主营法式连衣裙，客群偏年轻女性",
        tags=["category", "法式连衣裙"], importance=0.7, confidence=0.8,
    )
    second = service.ingest_candidate(
        "T-MEM-1", "profile", "主营法式连衣裙，客群偏年轻女性",
        tags=["category", "法式连衣裙"], importance=0.7, confidence=0.8,
    )
    assert first.memory_id == second.memory_id
    assert second.evidence_count == 2
    assert second.confidence > first.confidence or second.evidence_count == 2
    total = db.scalar(select(func.count()).select_from(MemoryItem))
    assert total == 1


def test_conflict_supersedes_old_without_overwrite(db, shop) -> None:
    service = MemoryGovernanceService(db)
    old = service.ingest_candidate(
        "T-MEM-1", "preference", "倾向控制成本，压低预算",
        tags=["budget_preference", "budget_preference:控制成本"],
        importance=0.6, confidence=0.65,
    )
    new = service.ingest_candidate(
        "T-MEM-1", "preference", "现在希望加预算放量冲GMV",
        tags=["budget_preference", "budget_preference:放量增长"],
        importance=0.95, confidence=0.9,
    )
    db.refresh(old)
    assert old.status == "superseded"
    assert new.status == "active"
    conflicts = list(db.scalars(select(MemoryConflict)).all())
    assert len(conflicts) == 1
    assert conflicts[0].resolution == "newer_wins"
    assert conflicts[0].previous_memory_id == old.memory_id


def test_candidate_promotion_and_expiry(db, shop) -> None:
    service = MemoryGovernanceService(db)
    weak = service.ingest_candidate(
        "T-MEM-1", "fact", "某条不确定的经营信息",
        tags=["general_fact"], importance=0.5, confidence=0.4,
    )
    assert weak.status == "candidate"
    service.promote(weak.memory_id)
    assert weak.status == "active"

    weak.last_seen_at = datetime.now(timezone.utc) - timedelta(days=300)
    db.commit()
    expired = service.expire_stale()
    assert expired == 1
    db.refresh(weak)
    assert weak.status == "expired"


def test_recall_weighted_scoring_only_active(db, shop) -> None:
    governance = MemoryGovernanceService(db)
    relevant = governance.ingest_candidate(
        "T-MEM-1", "preference", "商家偏好加预算放量投放广告",
        tags=["budget_preference", "budget_preference:放量增长"],
        importance=0.9, confidence=0.9,
    )
    governance.ingest_candidate(
        "T-MEM-1", "profile", "主营小众户外冲锋衣，男性客群",
        tags=["category", "户外冲锋衣"], importance=0.8, confidence=0.85,
    )
    recall = MemoryRetrievalService(db)
    results = recall.recall("T-MEM-1", "预算花费投放要不要加预算？", top_k=2)
    assert results
    assert results[0]["memory_id"] == relevant.memory_id
    top = results[0]
    breakdown = top["score_breakdown"]
    assert set(breakdown) == {"semantic", "recency", "importance", "relevance"}
    assert 0.0 <= top["score"] <= 1.0
    assert all(item["status"] == "active" for item in results)


def test_memory_http_api_roundtrip(api_client, db, shop) -> None:
    response = api_client.post(
        "/api/memories/extract",
        json={"merchant_id": "T-MEM-1", "text": "我们决定加预算放量，主做短视频信息流"},
    )
    assert response.status_code == 201
    memories = response.json()
    assert len(memories) >= 1

    recall = api_client.post(
        "/api/memories/recall",
        json={"merchant_id": "T-MEM-1", "query": "预算怎么调"},
    )
    assert recall.status_code == 200
    assert isinstance(recall.json(), list)

    missing = api_client.post(
        "/api/memories/extract",
        json={"merchant_id": "NOPE", "text": "加预算"},
    )
    assert missing.status_code == 404
