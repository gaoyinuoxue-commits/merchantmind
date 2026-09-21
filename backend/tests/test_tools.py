from __future__ import annotations

import pytest

from app.knowledge.service import KnowledgeService
from app.models.tool_call import ToolCallLog
from app.services.seed_service import SeedService
from app.services.world_gen import world_dataset
from app.tools.base import all_tools
from app.tools.service import ToolError, ToolService


@pytest.fixture()
def world(db):
    SeedService(db).seed_all(world_dataset())
    KnowledgeService(db).seed_catalog()
    return "M001"


def test_registry_lists_six_read_only_tools() -> None:
    names = {tool.name for tool in all_tools()}
    assert names == {
        "get_shop_profile",
        "get_ad_performance",
        "get_product_performance",
        "get_material_performance",
        "get_historical_cases",
        "get_recent_business_events",
    }
    assert all(tool.permission == "read" for tool in all_tools())
    assert all(tool.risk_level == "read" for tool in all_tools())


def test_shop_profile_tool(db, world) -> None:
    result = ToolService(db).invoke("get_shop_profile", {"merchant_id": world})
    data = result["data"]
    assert data["merchant_id"] == "M001"
    assert data["asset_counts"]["products"] == 12
    assert data["asset_counts"]["campaigns"] == 3
    assert data["current_date"] == "2026-09-12"
    assert data["label"] == "SYNTHETIC"


def test_ad_performance_tool_has_window_and_delta(db, world) -> None:
    result = ToolService(db).invoke("get_ad_performance", {"merchant_id": world, "days": 7})
    current = result["data"]["current"]
    assert current["impressions"] > 0 and current["clicks"] > 0
    assert current["roi"] is not None
    assert "roi" in result["data"]["delta_pct"]


def test_entity_tools_return_allocations(db, world) -> None:
    products = ToolService(db).invoke(
        "get_product_performance", {"merchant_id": world, "days": 14}
    )["data"]
    assert len(products["products"]) == 12
    assert products["allocation_basis"] == "allocated_by_cumulative_sales"

    materials = ToolService(db).invoke(
        "get_material_performance", {"merchant_id": world, "days": 7}
    )["data"]
    assert materials["materials"]
    statuses = {m["status"] for m in materials["materials"]}
    assert "fatigued" in statuses

    cases = ToolService(db).invoke(
        "get_historical_cases", {"merchant_id": world, "query": "素材疲劳 ROI 下滑"}
    )["data"]
    assert cases["cases"]
    assert cases["cases"][0]["slug"] == "case_fatigue_budget"

    events = ToolService(db).invoke(
        "get_recent_business_events", {"merchant_id": world, "days": 90}
    )["data"]
    assert events["events"]


def test_tool_validation_and_not_found(db, world) -> None:
    service = ToolService(db)
    with pytest.raises(ToolError) as exc:
        service.invoke("get_ad_performance", {"merchant_id": world, "days": 400})
    assert exc.value.code == "invalid_arguments"
    with pytest.raises(ToolError) as exc:
        service.invoke("get_shop_profile", {"merchant_id": "MISSING"})
    assert exc.value.code == "not_found"
    with pytest.raises(ToolError) as exc:
        service.invoke("not_a_tool", {"merchant_id": world})
    assert exc.value.code == "unknown_tool"


def test_tool_calls_are_audited(db, world) -> None:
    service = ToolService(db)
    service.invoke("get_shop_profile", {"merchant_id": world})
    with pytest.raises(ToolError):
        service.invoke("get_shop_profile", {"merchant_id": "MISSING"})
    logs = list(service.recent_calls(limit=10))
    assert len(logs) == 2
    assert {log.success for log in logs} == {True, False}
    assert logs[0].error is not None or logs[1].error is not None
    assert db.query(ToolCallLog).count() == 2


def test_tools_http_api(api_client, db, world) -> None:
    catalog = api_client.get("/api/tools")
    assert catalog.status_code == 200
    assert len(catalog.json()) == 6

    invoked = api_client.post(
        "/api/tools/get_ad_performance/invoke",
        json={"arguments": {"merchant_id": "M001", "days": 7}},
    )
    assert invoked.status_code == 200
    assert invoked.json()["tool"] == "get_ad_performance"

    bad = api_client.post(
        "/api/tools/get_ad_performance/invoke",
        json={"arguments": {"merchant_id": "M001", "days": 999}},
    )
    assert bad.status_code == 400

    missing = api_client.post(
        "/api/tools/nope/invoke", json={"arguments": {}}
    )
    assert missing.status_code == 404
