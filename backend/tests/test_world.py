from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from app.models import (
    BusinessEvent,
    Campaign,
    Material,
    Merchant,
    PerformanceDaily,
    Product,
)
from app.services.seed_service import SeedService
from app.services.world_gen import (
    END_DATE,
    START_DATE,
    WINDOW_DAYS,
    world_dataset,
)


def test_world_is_deterministic() -> None:
    first = world_dataset()
    second = world_dataset()
    assert first == second


def test_world_scale_and_window() -> None:
    dataset = world_dataset()
    assert len(dataset["merchants"]) == 10
    assert len(dataset["products"]) >= 100
    assert len(dataset["campaigns"]) >= 20
    assert len(dataset["materials"]) >= 100
    assert len(dataset["performance_daily"]) == 10 * WINDOW_DAYS
    assert len(dataset["business_events"]) >= 100
    assert dataset["performance_daily"][0]["date"] == START_DATE.isoformat()
    assert dataset["performance_daily"][-1]["date"] == END_DATE.isoformat()


def test_world_metrics_are_internally_consistent() -> None:
    for row in world_dataset()["performance_daily"]:
        assert row["impressions"] > 0
        assert 0 < row["clicks"] <= row["impressions"]
        assert 0 <= row["conversions"] <= row["clicks"]
        assert abs(row["ctr"] - row["clicks"] / row["impressions"]) < 1e-4
        assert abs(row["cpm"] - row["ad_spend"] / row["impressions"] * 1000) < 0.01
        assert row["roi"] >= 0
        assert row["gmv"] >= 0


def test_flagship_merchant_tells_fatigue_budget_story() -> None:
    perf = [
        row for row in world_dataset()["performance_daily"]
        if row["merchant_id"] == "M001"
    ]
    early = [r for r in perf if r["date"] <= "2026-08-10"]
    late = [r for r in perf if r["date"] >= "2026-09-05"]
    early_roi = sum(r["roi"] for r in early) / len(early)
    late_roi = sum(r["roi"] for r in late) / len(late)
    assert late_roi < early_roi * 0.8

    events = world_dataset()["business_events"]
    types = {e["event_type"] for e in events if e["merchant_id"] == "M001"}
    assert {"material_fatigue", "budget_change", "traffic_cost_increase"} <= types


def test_full_world_seeds_and_is_idempotent(db) -> None:
    seeder = SeedService(db)
    inserted = seeder.seed_all(world_dataset())
    assert inserted["merchants"] == 10
    assert inserted["performance_daily"] == 900

    assert db.scalar(select(func.count()).select_from(Merchant)) == 10
    assert db.scalar(select(func.count()).select_from(Product)) == 120
    assert db.scalar(select(func.count()).select_from(Campaign)) == 30
    assert db.scalar(select(func.count()).select_from(Material)) == 111
    assert db.scalar(select(func.count()).select_from(PerformanceDaily)) == 900
    assert db.scalar(select(func.count()).select_from(BusinessEvent)) >= 300

    first_counts = seeder.counts()
    seeder.seed_all(world_dataset())
    assert seeder.counts() == first_counts


def test_world_date_range_is_complete(db) -> None:
    seeder = SeedService(db)
    seeder.seed_all(world_dataset())
    rows = db.scalars(
        select(PerformanceDaily.date)
        .where(PerformanceDaily.merchant_id == "M001")
        .order_by(PerformanceDaily.date)
    ).all()
    assert rows[0] == START_DATE
    assert rows[-1] == END_DATE
    assert len(rows) == (END_DATE - START_DATE).days + 1
    assert isinstance(rows[0], date)
