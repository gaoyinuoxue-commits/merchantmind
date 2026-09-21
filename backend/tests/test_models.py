from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    BusinessEvent,
    Campaign,
    Material,
    Merchant,
    MerchantIndustry,
    PerformanceDaily,
    Product,
)
from app.models.enums import (
    BusinessEventType,
    BusinessStage,
    CampaignObjective,
    CampaignStatus,
    EventSource,
    Industry,
    MaterialStatus,
    MaterialType,
    ProductStatus,
)


def _make_merchant(merchant_id: str = "T001") -> Merchant:
    return Merchant(
        merchant_id=merchant_id,
        merchant_name="测试商家",
        industry=Industry.WOMENSWEAR,
        sub_industry="春装",
        business_stage=BusinessStage.GROWTH,
        gmv_level="10w-50w",
        city="上海",
    )


def test_full_graph_crud_and_timestamps(db) -> None:
    merchant = _make_merchant()
    merchant.industries.append(
        MerchantIndustry(industry="womenswear", sub_industry="春装", is_primary=True)
    )
    db.add(merchant)
    db.flush()

    db.add_all(
        [
            Campaign(
                campaign_id="C001",
                merchant_id="T001",
                campaign_name="秋装引流",
                objective=CampaignObjective.CONVERSION,
                budget=1000.0,
                status=CampaignStatus.ACTIVE,
            ),
            Product(
                product_id="P001",
                merchant_id="T001",
                product_name="白衬衫",
                category="衬衫",
                price=99.0,
                cost=35.0,
                inventory=500,
                sales=120,
                conversion_rate=0.042,
                status=ProductStatus.ON_SALE,
            ),
        ]
    )
    db.flush()

    db.add(
        Material(
            material_id="M001",
            campaign_id="C001",
            merchant_id="T001",
            material_type=MaterialType.VIDEO,
            material_name="穿搭短视频",
            status=MaterialStatus.ACTIVE,
        )
    )
    db.add(
        PerformanceDaily(
            merchant_id="T001",
            date=date(2026, 9, 1),
            gmv=12800.0,
            ad_spend=1000.0,
            impressions=50000,
            clicks=950,
            conversions=42,
            roi=3.1,
        )
    )
    event_time = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    db.add(
        BusinessEvent(
            event_id="E001",
            merchant_id="T001",
            event_type=BusinessEventType.NEW_MATERIAL,
            event_time=event_time,
            description="新增素材",
            structured_data={"material_id": "M001"},
            source=EventSource.SYSTEM,
        )
    )
    db.commit()

    loaded = db.get(Merchant, "T001")
    assert loaded is not None
    assert loaded.merchant_name == "测试商家"
    assert loaded.industry == "womenswear"
    assert loaded.created_at is not None
    assert loaded.updated_at is not None
    assert len(loaded.industries) == 1
    assert loaded.industries[0].sub_industry == "春装"
    assert loaded.industries[0].is_primary is True

    product = db.get(Product, "P001")
    assert product is not None
    assert product.status == "on_sale"

    event = db.get(BusinessEvent, "E001")
    assert event is not None
    assert event.structured_data == {"material_id": "M001"}
    assert event.event_time == event_time

    assert db.scalar(select(func.count()).select_from(PerformanceDaily)) == 1


def test_performance_merchant_date_unique(db) -> None:
    db.add(_make_merchant("T002"))
    db.commit()
    common = dict(merchant_id="T002", gmv=1.0, ad_spend=1.0, impressions=1, clicks=1,
                  conversions=1)
    db.add(PerformanceDaily(date=date(2026, 9, 1), **common))
    db.flush()
    db.add(PerformanceDaily(date=date(2026, 9, 1), **common))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    db.add(PerformanceDaily(date=date(2026, 9, 2), **common))
    db.commit()
    assert db.scalar(select(func.count()).select_from(PerformanceDaily)) == 1


def test_merchant_industry_tag_unique(db) -> None:
    merchant = _make_merchant("T003")
    merchant.industries.append(
        MerchantIndustry(industry="beauty", sub_industry="", is_primary=True)
    )
    db.add(merchant)
    db.commit()
    db.add(
        MerchantIndustry(
            merchant_id="T003", industry="beauty", sub_industry="", is_primary=False
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    db.add(
        MerchantIndustry(
            merchant_id="T003", industry="beauty", sub_industry="护肤", is_primary=False
        )
    )
    db.commit()
    assert db.scalar(select(func.count()).select_from(MerchantIndustry)) == 2


def test_foreign_key_rejects_orphan(db) -> None:
    db.add(
        Product(
            product_id="PX",
            merchant_id="GHOST",
            product_name="无主商品",
            price=1.0,
            cost=1.0,
            status=ProductStatus.ON_SALE,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    db.add(_make_merchant("T004"))
    db.flush()
    db.add(
        Material(
            material_id="MX",
            campaign_id="GHOST",
            merchant_id="T004",
            material_type=MaterialType.IMAGE,
            material_name="无主素材",
            status=MaterialStatus.ACTIVE,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_merchant_delete_cascades_children(db) -> None:
    merchant = _make_merchant("T005")
    merchant.industries.append(
        MerchantIndustry(industry="womenswear", sub_industry="", is_primary=True)
    )
    db.add(merchant)
    db.flush()
    db.add_all(
        [
            Campaign(
                campaign_id="C005",
                merchant_id="T005",
                campaign_name="计划",
                objective=CampaignObjective.TRAFFIC,
                budget=100.0,
                status=CampaignStatus.ACTIVE,
            ),
            Product(
                product_id="P005",
                merchant_id="T005",
                product_name="商品",
                price=10.0,
                cost=5.0,
                status=ProductStatus.ON_SALE,
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            Material(
                material_id="M005",
                campaign_id="C005",
                merchant_id="T005",
                material_type=MaterialType.IMAGE,
                material_name="素材",
                status=MaterialStatus.ACTIVE,
            ),
            PerformanceDaily(
                merchant_id="T005",
                date=date(2026, 9, 1),
                gmv=10.0,
                ad_spend=1.0,
                impressions=10,
                clicks=2,
                conversions=1,
            ),
            BusinessEvent(
                event_id="E005",
                merchant_id="T005",
                event_type=BusinessEventType.SALES_GROWTH,
                event_time=datetime(2026, 9, 1, tzinfo=timezone.utc),
                source=EventSource.SIMULATOR,
            ),
        ]
    )
    db.commit()

    db.delete(db.get(Merchant, "T005"))
    db.commit()

    for model in (
        MerchantIndustry,
        Product,
        Campaign,
        Material,
        PerformanceDaily,
        BusinessEvent,
    ):
        assert db.scalar(select(func.count()).select_from(model)) == 0, model.__tablename__
