from __future__ import annotations

import pytest

from app.knowledge.service import KnowledgeService

pytestmark = pytest.mark.usefixtures("db")


@pytest.fixture()
def service(db):
    svc = KnowledgeService(db)
    svc.seed_catalog()
    return svc


def _assert_shape(rows, expected_strategy: str):
    assert rows, "retrieval returned no rows"
    for row in rows:
        assert row["score"] > 0
        assert row["score_breakdown"]["strategy"] == expected_strategy
        assert row["title"] and row["content"]


def test_vector_strategy_dense_retrieval(service) -> None:
    service.retrieval_strategy = "vector"
    rows = service.retrieve("为什么投广告不赚钱了", top_k=8)
    _assert_shape(rows, "vector")
    assert rows[0]["score_breakdown"]["semantic"] > 0


def test_bm25_strategy_lexical_retrieval(service) -> None:
    service.retrieval_strategy = "bm25"
    rows = service.retrieve("素材疲劳 点击率 CTR 下滑", top_k=8)
    _assert_shape(rows, "bm25")
    # Strong lexical signal: a fatigue-related card should rank at the top.
    assert "fatigue" in rows[0]["slug"] or "疲劳" in rows[0]["title"]


def test_hybrid_strategy_fuses_vector_and_bm25(service) -> None:
    service.retrieval_strategy = "hybrid"
    rows = service.retrieve("素材疲劳导致点击率下滑怎么解决", top_k=8)
    _assert_shape(rows, "hybrid")


def test_strategy_selection_is_configurable(service) -> None:
    # Same query, three strategies are independently selectable and all valid.
    for strategy in ("vector", "bm25", "hybrid"):
        service.retrieval_strategy = strategy
        rows = service.retrieve("ROI 下滑原因", top_k=5)
        assert rows
        assert rows[0]["score_breakdown"]["strategy"] == strategy
