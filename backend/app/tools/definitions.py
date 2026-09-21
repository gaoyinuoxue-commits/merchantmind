"""Six read-only agent tools backed by the real database."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.knowledge.service import KnowledgeService
from app.models.campaign import Campaign
from app.models.event import BusinessEvent
from app.models.material import Material
from app.models.merchant import Merchant, MerchantIndustry
from app.models.product import Product
from app.tools.base import ToolSpec, register
from app.tools.metrics import anchor_date, window_metrics

_MERCHANT_ID = {"type": "string", "minLength": 1}


def _require_merchant(db: Session, merchant_id: str) -> Merchant:
    merchant = db.get(Merchant, merchant_id)
    if merchant is None:
        raise KeyError(f"merchant {merchant_id!r} not found")
    return merchant


def get_shop_profile(db: Session, arguments: Dict[str, Any]) -> Dict[str, Any]:
    merchant = _require_merchant(db, arguments["merchant_id"])
    industries = list(
        db.scalars(
            select(MerchantIndustry.industry).where(
                MerchantIndustry.merchant_id == merchant.merchant_id
            )
        ).all()
    )
    counts = {
        "products": db.scalar(
            select(func.count()).select_from(Product).where(Product.merchant_id == merchant.merchant_id)
        ),
        "campaigns": db.scalar(
            select(func.count()).select_from(Campaign).where(Campaign.merchant_id == merchant.merchant_id)
        ),
        "materials": db.scalar(
            select(func.count()).select_from(Material).where(Material.merchant_id == merchant.merchant_id)
        ),
    }
    anchor = anchor_date(db, merchant.merchant_id)
    return {
        "merchant_id": merchant.merchant_id,
        "merchant_name": merchant.merchant_name,
        "industry": merchant.industry,
        "industries": industries,
        "sub_industry": merchant.sub_industry,
        "business_stage": merchant.business_stage,
        "gmv_level": merchant.gmv_level,
        "city": merchant.city,
        "current_date": anchor.isoformat() if anchor else None,
        "asset_counts": counts,
        "label": "SYNTHETIC",
    }


def get_ad_performance(db: Session, arguments: Dict[str, Any]) -> Dict[str, Any]:
    merchant = _require_merchant(db, arguments["merchant_id"])
    metrics = window_metrics(db, merchant.merchant_id, arguments.get("days", 7))
    data: Dict[str, Any] = {"merchant_id": merchant.merchant_id, **metrics, "label": "SYNTHETIC"}

    campaign_id = arguments.get("campaign_id")
    if campaign_id:
        campaign = db.get(Campaign, campaign_id)
        if campaign is None or campaign.merchant_id != merchant.merchant_id:
            raise KeyError(f"campaign {campaign_id!r} not found")
        campaigns = list(
            db.scalars(
                select(Campaign).where(Campaign.merchant_id == merchant.merchant_id)
            ).all()
        )
        total_budget = sum(c.budget for c in campaigns if c.status != "paused") or 1.0
        share = campaign.budget / total_budget if campaign.status != "paused" else 0.0
        data["campaign_id"] = campaign_id
        data["allocation_basis"] = "allocated_by_budget"
        if data["current"]:
            data["current"] = {
                key: (round(value * share, 4) if isinstance(value, (int, float)) and key not in
                      ("date_from", "date_to") else value)
                for key, value in data["current"].items()
            }
    return data


def get_product_performance(db: Session, arguments: Dict[str, Any]) -> Dict[str, Any]:
    merchant = _require_merchant(db, arguments["merchant_id"])
    days = arguments.get("days", 7)
    metrics = window_metrics(db, merchant.merchant_id, days)
    stmt = select(Product).where(Product.merchant_id == merchant.merchant_id)
    product_id = arguments.get("product_id")
    if product_id:
        stmt = stmt.where(Product.product_id == product_id)
    products = list(db.scalars(stmt.order_by(Product.sales.desc())).all())
    if product_id and not products:
        raise KeyError(f"product {product_id!r} not found")
    total_sales = sum(p.sales for p in products) or 1

    items = []
    for product in products:
        share = product.sales / total_sales
        item = {
            "product_id": product.product_id,
            "product_name": product.product_name,
            "category": product.category,
            "status": product.status,
            "price": product.price,
            "gross_margin": round((product.price - product.cost) / product.price, 4)
            if product.price
            else None,
            "inventory": product.inventory,
            "cumulative_sales": product.sales,
            "conversion_rate": product.conversion_rate,
        }
        if metrics["current"]:
            current = metrics["current"]
            item["window_metrics"] = {
                "gmv": round(current["gmv"] * share, 2),
                "ad_spend": round(current["ad_spend"] * share, 2),
                "conversions": int(round(current["conversions"] * share)),
                "roi": current["roi"],
            }
        items.append(item)
    return {
        "merchant_id": merchant.merchant_id,
        "days": days,
        "allocation_basis": "allocated_by_cumulative_sales",
        "products": items,
        "label": "SYNTHETIC",
    }


def get_material_performance(db: Session, arguments: Dict[str, Any]) -> Dict[str, Any]:
    merchant = _require_merchant(db, arguments["merchant_id"])
    days = arguments.get("days", 7)
    metrics = window_metrics(db, merchant.merchant_id, days)
    stmt = select(Material).where(Material.merchant_id == merchant.merchant_id)
    material_id = arguments.get("material_id")
    if material_id:
        stmt = stmt.where(Material.material_id == material_id)
    materials = list(db.scalars(stmt).all())
    if material_id and not materials:
        raise KeyError(f"material {material_id!r} not found")

    status_weight = {"active": 1.0, "fatigued": 0.55, "paused": 0.25, "archived": 0.05}
    weights = {m.material_id: status_weight.get(m.status, 0.3) for m in materials}
    total_weight = sum(weights.values()) or 1.0

    items = []
    for material in materials:
        share = weights[material.material_id] / total_weight
        item = {
            "material_id": material.material_id,
            "campaign_id": material.campaign_id,
            "material_name": material.material_name,
            "material_type": material.material_type,
            "status": material.status,
            "weight": round(weights[material.material_id], 3),
        }
        if metrics["current"]:
            current = metrics["current"]
            impressions = int(round(current["impressions"] * share))
            clicks = int(round(current["clicks"] * share))
            spend = round(current["ad_spend"] * share, 2)
            item["window_metrics"] = {
                "impressions": impressions,
                "clicks": clicks,
                "ad_spend": spend,
                "ctr": round(clicks / impressions, 6) if impressions else None,
                "cpm": round(spend / impressions * 1000, 2) if impressions else None,
            }
        items.append(item)
    items.sort(key=lambda row: row.get("weight", 0), reverse=True)
    return {
        "merchant_id": merchant.merchant_id,
        "days": days,
        "allocation_basis": "allocated_by_material_status",
        "materials": items,
        "label": "SYNTHETIC",
    }


def get_historical_cases(db: Session, arguments: Dict[str, Any]) -> Dict[str, Any]:
    merchant = _require_merchant(db, arguments["merchant_id"])
    query = arguments.get("query") or f"{merchant.industry} 经营诊断案例"
    limit = arguments.get("limit", 3)
    cases = KnowledgeService(db).retrieve(
        query=query,
        industry=merchant.industry,
        top_k=limit,
        types=["case"],
    )
    return {
        "merchant_id": merchant.merchant_id,
        "query": query,
        "cases": cases,
        "label": "SYNTHETIC_KNOWLEDGE",
    }


def get_recent_business_events(db: Session, arguments: Dict[str, Any]) -> Dict[str, Any]:
    merchant = _require_merchant(db, arguments["merchant_id"])
    days = arguments.get("days", 30)
    anchor = anchor_date(db, merchant.merchant_id)
    stmt = select(BusinessEvent).where(BusinessEvent.merchant_id == merchant.merchant_id)
    if anchor is not None:
        stmt = stmt.where(BusinessEvent.event_time >= anchor - timedelta(days=days))
    events = list(db.scalars(stmt.order_by(BusinessEvent.event_time.desc())).all())
    return {
        "merchant_id": merchant.merchant_id,
        "days": days,
        "events": [
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "event_time": event.event_time.isoformat(),
                "description": event.description,
                "structured_data": event.structured_data,
                "source": event.source,
            }
            for event in events
        ],
        "label": "SYNTHETIC",
    }


_TOOL_OUTPUT = {
    "type": "object",
    "description": "tool payload, all business data labeled SYNTHETIC",
}


def register_tools() -> None:
    register(
        ToolSpec(
            name="get_shop_profile",
            description="查询商家基础画像：行业、阶段、城市、商品/计划/素材资产数量与当前模拟日期。",
            input_schema={
                "type": "object",
                "properties": {"merchant_id": _MERCHANT_ID},
                "required": ["merchant_id"],
            },
            output_schema=_TOOL_OUTPUT,
            permission="read",
            risk_level="read",
            handler=get_shop_profile,
        )
    )
    register(
        ToolSpec(
            name="get_ad_performance",
            description="查询近 N 天广告大盘指标（曝光/点击/花费/GMV/CTR/CPM/CVR/ROI）及环比变化，可指定计划按预算占比拆分。",
            input_schema={
                "type": "object",
                "properties": {
                    "merchant_id": _MERCHANT_ID,
                    "days": {"type": "integer", "minimum": 1, "maximum": 90},
                    "campaign_id": {"type": "string"},
                },
                "required": ["merchant_id"],
            },
            output_schema=_TOOL_OUTPUT,
            permission="read",
            risk_level="read",
            handler=get_ad_performance,
        )
    )
    register(
        ToolSpec(
            name="get_product_performance",
            description="查询商品表现：价格/库存/累计销量/毛利率，并按累计销量占比拆分近 N 天窗口指标。",
            input_schema={
                "type": "object",
                "properties": {
                    "merchant_id": _MERCHANT_ID,
                    "days": {"type": "integer", "minimum": 1, "maximum": 90},
                    "product_id": {"type": "string"},
                },
                "required": ["merchant_id"],
            },
            output_schema=_TOOL_OUTPUT,
            permission="read",
            risk_level="read",
            handler=get_product_performance,
        )
    )
    register(
        ToolSpec(
            name="get_material_performance",
            description="查询素材表现与疲劳状态：按素材状态权重拆分近 N 天曝光/点击/CTR/CPM。",
            input_schema={
                "type": "object",
                "properties": {
                    "merchant_id": _MERCHANT_ID,
                    "days": {"type": "integer", "minimum": 1, "maximum": 90},
                    "material_id": {"type": "string"},
                },
                "required": ["merchant_id"],
            },
            output_schema=_TOOL_OUTPUT,
            permission="read",
            risk_level="read",
            handler=get_material_performance,
        )
    )
    register(
        ToolSpec(
            name="get_historical_cases",
            description="从知识库检索与当前问题相关的历史案例（向量召回+重排），用于类比诊断。",
            input_schema={
                "type": "object",
                "properties": {
                    "merchant_id": _MERCHANT_ID,
                    "query": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["merchant_id"],
            },
            output_schema=_TOOL_OUTPUT,
            permission="read",
            risk_level="read",
            handler=get_historical_cases,
        )
    )
    register(
        ToolSpec(
            name="get_recent_business_events",
            description="查询近 N 天业务事件（新品、新素材、预算调整、活动、季节变化等）及事件来源。",
            input_schema={
                "type": "object",
                "properties": {
                    "merchant_id": _MERCHANT_ID,
                    "days": {"type": "integer", "minimum": 1, "maximum": 120},
                },
                "required": ["merchant_id"],
            },
            output_schema=_TOOL_OUTPUT,
            permission="read",
            risk_level="read",
            handler=get_recent_business_events,
        )
    )


register_tools()
