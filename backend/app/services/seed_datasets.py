"""Seed datasets.

Phase 2 ships a minimal ``smoke_dataset`` purely to verify the seeding
mechanism end to end. Phase 3 replaces it with the full Synthetic Merchant
World (10+ merchants, 100+ products/campaigns, 60-90 days of daily data...).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict


def smoke_dataset() -> Dict[str, list[Dict[str, Any]]]:
    now = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    return {
        "merchants": [
            {
                "merchant_id": "SMOKE001",
                "merchant_name": "冒烟测试商家",
                "industry": "womenswear",
                "sub_industry": "春季女装",
                "business_stage": "growth",
                "gmv_level": "10w-50w",
                "city": "杭州",
            }
        ],
        "merchant_industries": [
            {
                "merchant_id": "SMOKE001",
                "industry": "womenswear",
                "sub_industry": "春季女装",
                "is_primary": True,
            }
        ],
        "products": [
            {
                "product_id": "SP001",
                "merchant_id": "SMOKE001",
                "product_name": "基础款白衬衫",
                "category": "衬衫",
                "price": 99.0,
                "cost": 35.0,
                "inventory": 500,
                "sales": 120,
                "conversion_rate": 0.042,
                "status": "on_sale",
            }
        ],
        "campaigns": [
            {
                "campaign_id": "SC001",
                "merchant_id": "SMOKE001",
                "campaign_name": "秋装引流计划",
                "objective": "conversion",
                "budget": 1000.0,
                "status": "active",
            }
        ],
        "materials": [
            {
                "material_id": "SM001",
                "campaign_id": "SC001",
                "merchant_id": "SMOKE001",
                "material_type": "video",
                "material_name": "白衬衫穿搭短视频",
                "status": "active",
            }
        ],
        "performance_daily": [
            {
                "merchant_id": "SMOKE001",
                "date": date(2026, 9, 1),
                "gmv": 12800.0,
                "ad_spend": 1000.0,
                "impressions": 50000,
                "clicks": 950,
                "ctr": 0.019,
                "cpm": 20.0,
                "conversions": 42,
                "cvr": 0.044,
                "aov": 304.8,
                "roi": 3.1,
            }
        ],
        "business_events": [
            {
                "event_id": "SE001",
                "merchant_id": "SMOKE001",
                "event_type": "new_material",
                "event_time": now,
                "description": "新增素材：白衬衫穿搭短视频",
                "structured_data": {"material_id": "SM001", "campaign_id": "SC001"},
                "source": "system",
            }
        ],
    }
