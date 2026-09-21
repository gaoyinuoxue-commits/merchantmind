from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

from app.models import BusinessEvent, Merchant, MerchantIndustry, PerformanceDaily
from app.services.seed_datasets import smoke_dataset
from app.services.seed_service import SeedService, enum_value
from app.models.enums import Industry


EXPECTED_TABLES = {
    "experiment_variant_run",
    "experiment",
    "badcase",
    "feedback",
    "eval_run",
    "eval_case_result",
    "trace_run",
    "trace_span",
    "message",
    "conversation",
    "memory_conflict",
    "memory_item",
    "knowledge_item",
    "tool_call_log",
    "merchant",
    "merchant_industry",
    "product",
    "campaign",
    "material",
    "performance_daily",
    "business_event",
}

NON_SEEDED_TABLES = {
    "experiment_variant_run",
    "experiment",
    "badcase",
    "feedback",
    "eval_run",
    "eval_case_result",
    "trace_run",
    "trace_span",
    "message",
    "conversation",
    "memory_conflict",
    "memory_item",
    "knowledge_item",
    "tool_call_log",
}


def test_seed_smoke_inserts_every_table(db) -> None:
    seeder = SeedService(db)
    inserted = seeder.seed_all(smoke_dataset())

    assert set(inserted.keys()) == {
        "merchants",
        "merchant_industries",
        "products",
        "campaigns",
        "materials",
        "performance_daily",
        "business_events",
    }
    assert all(value == 1 for value in inserted.values())

    counts = seeder.counts()
    assert set(counts.keys()) == EXPECTED_TABLES
    assert counts["message"] == 0
    assert counts["conversation"] == 0
    assert all(v == 1 for k, v in counts.items() if k not in NON_SEEDED_TABLES)

    merchant = db.get(Merchant, "SMOKE001")
    assert merchant is not None
    assert merchant.merchant_name == "冒烟测试商家"
    assert merchant.industry == "womenswear"

    event = db.get(BusinessEvent, "SE001")
    assert event is not None
    assert event.structured_data == {"material_id": "SM001", "campaign_id": "SC001"}


def test_seed_is_idempotent(db) -> None:
    seeder = SeedService(db)

    seeder.seed_all(smoke_dataset())
    counts_after_first = seeder.counts()
    seeder.seed_all(smoke_dataset())
    counts_after_second = seeder.counts()

    assert counts_after_first == counts_after_second
    assert all(
        value == 1 for key, value in counts_after_second.items()
        if key not in NON_SEEDED_TABLES
    )


def test_seed_updates_existing_rows(db) -> None:
    seeder = SeedService(db)
    dataset = smoke_dataset()
    seeder.seed_all(dataset)

    updated = smoke_dataset()
    updated["merchants"][0]["merchant_name"] = "改名后的商家"
    updated["performance_daily"][0]["gmv"] = 999.0
    updated["merchant_industries"][0]["is_primary"] = False
    seeder.seed_all(updated)

    merchant = db.get(Merchant, "SMOKE001")
    assert merchant is not None
    assert merchant.merchant_name == "改名后的商家"

    performance = db.scalar(
        select(PerformanceDaily).where(
            PerformanceDaily.merchant_id == "SMOKE001",
            PerformanceDaily.date == date(2026, 9, 1),
        )
    )
    assert performance is not None
    assert performance.gmv == pytest.approx(999.0)

    tag = db.scalar(select(MerchantIndustry))
    assert tag is not None
    assert tag.is_primary is False
    assert db.scalar(select(func.count()).select_from(MerchantIndustry)) == 1


def test_reset_clears_business_tables(db) -> None:
    seeder = SeedService(db)
    seeder.seed_all(smoke_dataset())
    assert all(
        value == 1 for key, value in seeder.counts().items()
        if key not in NON_SEEDED_TABLES
    )

    seeder.reset()
    assert all(value == 0 for value in seeder.counts().values())


def test_enum_value_validation() -> None:
    assert enum_value("womenswear", Industry, "industry") == "womenswear"
    assert enum_value(Industry.BEAUTY, Industry, "industry") == "beauty"

    with pytest.raises(ValueError, match="invalid value"):
        enum_value("not_an_industry", Industry, "industry")
    with pytest.raises(ValueError):
        enum_value(None, Industry, "industry")


def test_empty_sections_insert_nothing(db) -> None:
    seeder = SeedService(db)
    result = seeder.seed_all({})
    assert set(result.keys()) == {
        "merchants",
        "merchant_industries",
        "products",
        "campaigns",
        "materials",
        "performance_daily",
        "business_events",
    }
    assert all(value == 0 for value in result.values())
    assert all(value == 0 for value in seeder.counts().values())


def test_seed_rejects_invalid_enum_value(db) -> None:
    seeder = SeedService(db)
    dataset = smoke_dataset()
    dataset["campaigns"][0]["objective"] = "invalid_objective"
    with pytest.raises(ValueError, match="invalid value"):
        seeder.seed_all(dataset)
    assert seeder.counts()["campaign"] == 0
