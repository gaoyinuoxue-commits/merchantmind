from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models import BusinessEvent, Material, PerformanceDaily
from app.services.seed_service import SeedService
from app.services.world_gen import END_DATE, world_dataset
from app.simulator.engine import SimulatorService, _noise


@pytest.fixture()
def world(db):
    SeedService(db).seed_all(world_dataset())
    return db


def test_noise_is_deterministic() -> None:
    from datetime import date

    assert _noise("M001", date(2026, 9, 13)) == _noise("M001", date(2026, 9, 13))
    assert _noise("M001", date(2026, 9, 13)) != _noise("M002", date(2026, 9, 13))


def test_state_points_at_world_end(world) -> None:
    state = SimulatorService(world).state("M001")
    assert state["current_date"] == END_DATE.isoformat()
    assert state["last_7d"]["avg_roi"] > 0
    assert state["label"] == "SYNTHETIC"


def test_advance_extends_timeline_coherently(world) -> None:
    service = SimulatorService(world)
    result = service.advance("M001", days=3)

    assert result["days_added"] == 3
    assert result["from_date"] == END_DATE.isoformat()
    assert result["to_date"] == (END_DATE + timedelta(days=3)).isoformat()

    count = world.scalar(
        select(func.count())
        .select_from(PerformanceDaily)
        .where(PerformanceDaily.merchant_id == "M001")
    )
    assert count == 93
    dates = [r["date"] for r in result["performance"]]
    assert dates == [
        (END_DATE + timedelta(days=i)).isoformat() for i in range(1, 4)
    ]
    for row in result["performance"]:
        assert 0 < row["clicks"] <= row["impressions"]
        assert 0 <= row["conversions"] <= row["clicks"]
        assert row["roi"] >= 0


def test_unknown_merchant_and_bad_days(world) -> None:
    service = SimulatorService(world)
    with pytest.raises(KeyError):
        service.advance("GHOST", days=1)
    with pytest.raises(ValueError):
        service.advance("M001", days=0)


def test_budget_change_effect_raises_spend_and_cpm(world) -> None:
    before = SimulatorService(world).state("M005")["last_7d"]
    result = SimulatorService(world).advance(
        "M005", days=2, effects=[{"type": "budget_change", "factor": 1.5}]
    )
    first = result["performance"][0]
    assert first["ad_spend"] == pytest.approx(before["avg_ad_spend"] * 1.5, rel=0.08)
    assert first["cpm"] > before["avg_cpm"]

    action_events = world.scalars(
        select(BusinessEvent).where(
            BusinessEvent.merchant_id == "M005",
            BusinessEvent.source == "action",
            BusinessEvent.event_type == "budget_change",
        )
    ).all()
    assert len(action_events) == 1


def test_new_material_effect_creates_material_and_lifts_ctr(world) -> None:
    service = SimulatorService(world)
    baseline = service.state("M005")["last_7d"]["avg_ctr"]
    result = service.advance(
        "M005", days=1,
        effects=[{"type": "new_material", "ctr_factor": 1.3, "material_type": "video"}],
    )
    assert result["performance"][0]["ctr"] > baseline
    material = world.scalar(
        select(Material).where(Material.merchant_id == "M005",
                               Material.material_id.like("MT005X%"))
    )
    assert material is not None
    assert material.status == "active"


def test_sequential_advances_append_distinct_days(world) -> None:
    service = SimulatorService(world)
    first = service.advance("M001", days=1)
    second = service.advance("M001", days=1)
    assert first["performance"][0]["date"] != second["performance"][0]["date"]
    count = world.scalar(
        select(func.count())
        .select_from(PerformanceDaily)
        .where(PerformanceDaily.merchant_id == "M001")
    )
    assert count == 92


def test_simulator_state_http(world, api_client) -> None:
    response = api_client.get("/api/simulator/state/M001")
    assert response.status_code == 200
    body = response.json()
    assert body["current_date"] == END_DATE.isoformat()
    assert body["last_7d"]["avg_roi"] > 0
    assert body["label"] == "SYNTHETIC"

    assert api_client.get("/api/simulator/state/GHOST").status_code == 404


def test_simulator_advance_http_happy_path(world, api_client) -> None:
    response = api_client.post(
        "/api/simulator/advance",
        json={
            "merchant_id": "M005",
            "days": 2,
            "effects": [{"type": "budget_change", "factor": 1.5}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["days_added"] == 2
    assert body["label"] == "SYNTHETIC"
    assert len(body["performance"]) == 2
    assert body["events_emitted"]


def test_simulator_advance_http_error_paths(world, api_client) -> None:
    assert (
        api_client.post("/api/simulator/advance", json={"merchant_id": "GHOST", "days": 1}).status_code
        == 404
    )
    invalid_effect = api_client.post(
        "/api/simulator/advance",
        json={"merchant_id": "M001", "days": 1, "effects": [{"type": "teleport"}]},
    )
    assert invalid_effect.status_code == 400
    assert api_client.post(
        "/api/simulator/advance", json={"merchant_id": "M001", "days": 0}
    ).status_code == 422
    assert api_client.post(
        "/api/simulator/advance", json={"merchant_id": "M001", "days": 31}
    ).status_code == 422
    assert api_client.post("/api/simulator/advance", json={"days": 1}).status_code == 422

