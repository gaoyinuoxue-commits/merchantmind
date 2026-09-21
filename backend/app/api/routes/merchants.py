from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.campaign import Campaign
from app.models.material import Material
from app.models.merchant import Merchant, MerchantIndustry
from app.models.performance import PerformanceDaily

router = APIRouter(prefix="/merchants", tags=["merchants"])


def _merchant_dict(merchant: Merchant, industries: List[MerchantIndustry]) -> Dict[str, Any]:
    return {
        "merchant_id": merchant.merchant_id,
        "merchant_name": merchant.merchant_name,
        "industry": merchant.industry,
        "sub_industry": merchant.sub_industry,
        "business_stage": merchant.business_stage,
        "gmv_level": merchant.gmv_level,
        "city": merchant.city,
        "industries": [
            {
                "industry": item.industry,
                "sub_industry": item.sub_industry,
                "is_primary": item.is_primary,
            }
            for item in industries
        ],
        "label": "SYNTHETIC",
    }


@router.get("")
def list_merchants(db: Session = Depends(get_db)) -> Dict[str, Any]:
    merchants = list(db.scalars(select(Merchant).order_by(Merchant.merchant_id)).all())
    tags = list(db.scalars(select(MerchantIndustry)).all())
    by_merchant: Dict[str, List[MerchantIndustry]] = {}
    for tag in tags:
        by_merchant.setdefault(tag.merchant_id, []).append(tag)
    return {
        "items": [_merchant_dict(m, by_merchant.get(m.merchant_id, [])) for m in merchants],
        "label": "SYNTHETIC",
    }


@router.get("/{merchant_id}")
def get_merchant(merchant_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    merchant = db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="merchant not found")
    industries = list(
        db.scalars(
            select(MerchantIndustry).where(MerchantIndustry.merchant_id == merchant_id)
        ).all()
    )
    performance = list(
        db.scalars(
            select(PerformanceDaily)
            .where(PerformanceDaily.merchant_id == merchant_id)
            .order_by(PerformanceDaily.date.desc())
            .limit(30)
        ).all()
    )
    performance.reverse()
    campaigns = list(
        db.scalars(
            select(Campaign)
            .where(Campaign.merchant_id == merchant_id)
            .order_by(Campaign.campaign_id)
        ).all()
    )
    materials = list(
        db.scalars(
            select(Material)
            .where(Material.merchant_id == merchant_id)
            .order_by(Material.material_id)
        ).all()
    )
    return {
        **_merchant_dict(merchant, industries),
        "performance": [
            {
                "date": row.date.isoformat(),
                "gmv": row.gmv,
                "ad_spend": row.ad_spend,
                "impressions": row.impressions,
                "clicks": row.clicks,
                "ctr": row.ctr,
                "cpm": row.cpm,
                "conversions": row.conversions,
                "cvr": row.cvr,
                "roi": row.roi,
            }
            for row in performance
        ],
        "campaigns": [
            {
                "campaign_id": row.campaign_id,
                "campaign_name": row.campaign_name,
                "objective": row.objective,
                "budget": row.budget,
                "status": row.status,
            }
            for row in campaigns
        ],
        "materials": [
            {
                "material_id": row.material_id,
                "campaign_id": row.campaign_id,
                "material_type": row.material_type,
                "material_name": row.material_name,
                "status": row.status,
            }
            for row in materials
        ],
    }
