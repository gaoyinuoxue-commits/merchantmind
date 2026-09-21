"""Shared metric aggregation over real performance_daily rows."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.performance import PerformanceDaily

# Gross margin by industry; ROI is reported on the profit basis
# (GMV * margin / ad spend), so ROI < 1 means the campaign loses money.
INDUSTRY_MARGINS = {
    "womenswear": 0.30,
    "beauty": 0.45,
    "food": 0.25,
    "home": 0.30,
    "electronics": 0.18,
}


def margin_for_industry(industry: Optional[str]) -> float:
    return INDUSTRY_MARGINS.get(industry or "", 0.30)


def anchor_date(db: Session, merchant_id: str) -> Optional[date]:
    return db.scalar(
        select(func.max(PerformanceDaily.date)).where(
            PerformanceDaily.merchant_id == merchant_id
        )
    )


def _rates(rows: List[Tuple], margin: float = 1.0) -> Dict[str, Any]:
    gmv = float(sum(r[0] for r in rows))
    spend = float(sum(r[1] for r in rows))
    impressions = int(sum(r[2] for r in rows))
    clicks = int(sum(r[3] for r in rows))
    conversions = int(sum(r[4] for r in rows))
    return {
        "gmv": round(gmv, 2),
        "ad_spend": round(spend, 2),
        "impressions": impressions,
        "clicks": clicks,
        "conversions": conversions,
        "ctr": round(clicks / impressions, 6) if impressions else None,
        "cpm": round(spend / impressions * 1000, 2) if impressions else None,
        "cvr": round(conversions / clicks, 6) if clicks else None,
        "aov": round(gmv / conversions, 2) if conversions else None,
        "roi": round(gmv * margin / spend, 4) if spend else None,
    }


def window_metrics(
    db: Session,
    merchant_id: str,
    days: int,
    end: Optional[date] = None,
    margin: Optional[float] = None,
) -> Dict[str, Any]:
    end = end or anchor_date(db, merchant_id)
    if end is None:
        return {"window": {"days": days}, "current": None, "previous": None, "delta_pct": {}}
    if margin is None:
        from app.models.merchant import Merchant

        merchant = db.get(Merchant, merchant_id)
        margin = margin_for_industry(merchant.industry if merchant else None)
    current_start = end - timedelta(days=days - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)

    columns = (
        PerformanceDaily.gmv,
        PerformanceDaily.ad_spend,
        PerformanceDaily.impressions,
        PerformanceDaily.clicks,
        PerformanceDaily.conversions,
    )

    def fetch(start: date, finish: date) -> Dict[str, Any]:
        rows = db.execute(
            select(*columns).where(
                PerformanceDaily.merchant_id == merchant_id,
                PerformanceDaily.date.between(start, finish),
            )
        ).all()
        metrics = _rates(rows, margin)
        metrics["date_from"] = start.isoformat()
        metrics["date_to"] = finish.isoformat()
        return metrics

    current = fetch(current_start, end)
    previous = fetch(previous_start, previous_end)
    delta = {}
    for key in ("gmv", "ad_spend", "ctr", "cpm", "cvr", "roi"):
        new, old = current.get(key), previous.get(key)
        if new is not None and old not in (None, 0):
            delta[key] = round((new - old) / old * 100, 2)
        else:
            delta[key] = None
    return {
        "window": {"days": days, "anchor_date": end.isoformat()},
        "current": current,
        "previous": previous,
        "delta_pct": delta,
    }
