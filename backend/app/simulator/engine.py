"""Merchant Simulator (Phase 4).

Advances the synthetic world forward in time using the same business rules
as the historical generator. Actions (budget change, campaign pause, new
material ...) are supplied as *effects* and produce real performance rows
plus business events (source = ``action`` / ``simulator``). Deterministic:
the same state + effects always produce the same next days.

Observe -> Think -> Act -> Observe Again loop support (Phase 13) is built on
top of :meth:`SimulatorService.advance`.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import BusinessEvent, Campaign, Material, Merchant, PerformanceDaily
from app.models.enums import (
    BusinessEventType,
    CampaignStatus,
    EventSource,
    MaterialStatus,
    MaterialType,
)

FATIGUE_GRACE = 7
FATIGUE_HALFLIFE_DAYS = 12


def _noise(merchant_id: str, day: date) -> float:
    digest = hashlib.sha256(f"{merchant_id}:{day.isoformat()}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return 1.0 + (value - 0.5) * 0.08


class SimulatorService:
    def __init__(self, db: Session):
        self.db = db

    def current_date(self, merchant_id: str) -> Optional[date]:
        return self.db.scalar(
            select(func.max(PerformanceDaily.date))
            .where(PerformanceDaily.merchant_id == merchant_id)
        )

    def state(self, merchant_id: str) -> Dict[str, Any]:
        merchant = self.db.get(Merchant, merchant_id)
        if merchant is None:
            raise KeyError(f"unknown merchant_id: {merchant_id}")
        current = self.current_date(merchant_id)
        rows = self.db.scalars(
            select(PerformanceDaily)
            .where(PerformanceDaily.merchant_id == merchant_id)
            .order_by(desc(PerformanceDaily.date))
            .limit(7)
        ).all()
        summary: Dict[str, Any] = {}
        if rows:
            summary = {
                "avg_gmv": round(sum(r.gmv for r in rows) / len(rows), 2),
                "avg_ad_spend": round(sum(r.ad_spend for r in rows) / len(rows), 2),
                "avg_roi": round(sum(r.roi for r in rows) / len(rows), 3),
                "avg_ctr": round(sum(r.ctr for r in rows) / len(rows), 5),
                "avg_cpm": round(sum(r.cpm for r in rows) / len(rows), 3),
                "avg_cvr": round(sum(r.cvr for r in rows) / len(rows), 5),
            }
        return {
            "merchant_id": merchant_id,
            "current_date": current.isoformat() if current else None,
            "last_7d": summary,
            "label": "SYNTHETIC",
        }

    def _latest_material_age(self, merchant_id: str, day: date) -> Optional[int]:
        event = self.db.scalar(
            select(BusinessEvent)
            .where(
                BusinessEvent.merchant_id == merchant_id,
                BusinessEvent.event_type == BusinessEventType.NEW_MATERIAL.value,
            )
            .order_by(desc(BusinessEvent.event_time))
            .limit(1)
        )
        if event is None:
            return None
        return (day - event.event_time.date()).days

    def _add_event(
        self,
        merchant_id: str,
        day: date,
        etype: BusinessEventType,
        description: str,
        data: Optional[Dict[str, Any]] = None,
        source: EventSource = EventSource.SIMULATOR,
    ) -> BusinessEvent:
        prefix = f"E{merchant_id[1:]}S"
        existing = self.db.scalar(
            select(BusinessEvent.event_id)
            .where(BusinessEvent.event_id.like(f"{prefix}%"))
            .order_by(desc(BusinessEvent.event_id))
            .limit(1)
        )
        seq = int(existing[len(prefix):]) + 1 if existing else 1
        event = BusinessEvent(
            event_id=f"{prefix}{seq:04d}",
            merchant_id=merchant_id,
            event_type=etype.value,
            event_time=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
            .replace(hour=9),
            description=description,
            structured_data=data or {},
            source=source.value,
        )
        self.db.add(event)
        return event

    def advance(
        self,
        merchant_id: str,
        days: int = 1,
        effects: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if days < 1 or days > 30:
            raise ValueError("days must be between 1 and 30")
        if self.db.get(Merchant, merchant_id) is None:
            raise KeyError(f"unknown merchant_id: {merchant_id}")
        effects = effects or []

        current = self.current_date(merchant_id)
        if current is None:
            raise ValueError("merchant has no historical performance; seed the world first")

        history = self.db.scalars(
            select(PerformanceDaily)
            .where(PerformanceDaily.merchant_id == merchant_id)
            .order_by(desc(PerformanceDaily.date))
            .limit(7)
        ).all()
        base_spend = sum(r.ad_spend for r in history) / len(history)
        base_cpm = sum(r.cpm for r in history) / len(history)
        base_cvr = sum(r.cvr for r in history) / len(history)
        base_aov = sum(r.aov for r in history) / len(history)
        margin = self._margin(merchant_id)

        spend_factor = 1.0
        cpm_factor = 1.0
        ctr_reset = 1.0
        demand_factor = 1.0
        emitted: List[Dict[str, Any]] = []

        for effect in effects:
            etype = effect.get("type")
            if etype == "budget_change":
                factor = float(effect.get("factor", 1.0))
                spend_factor *= factor
                cpm_factor *= 1.0 + 0.35 * (factor - 1.0)
                self._add_event(
                    merchant_id, current + timedelta(days=1),
                    BusinessEventType.BUDGET_CHANGE,
                    f"模拟动作：日预算调整为原来的 {factor:.0%}",
                    {"factor": factor, **{k: v for k, v in effect.items() if k != "type"}},
                    source=EventSource.ACTION,
                )
                emitted.append({"event_type": "budget_change", "factor": factor})
            elif etype == "campaign_pause":
                factor = float(effect.get("spend_factor", 0.6))
                spend_factor *= factor
                campaign_id = effect.get("campaign_id")
                if campaign_id:
                    campaign = self.db.get(Campaign, campaign_id)
                    if campaign is not None:
                        campaign.status = CampaignStatus.PAUSED.value
                self._add_event(
                    merchant_id, current + timedelta(days=1),
                    BusinessEventType.CAMPAIGN_PAUSE,
                    "模拟动作：暂停低效广告计划",
                    {"campaign_id": campaign_id},
                    source=EventSource.ACTION,
                )
                emitted.append({"event_type": "campaign_pause"})
            elif etype == "new_material":
                ctr_reset *= float(effect.get("ctr_factor", 1.25))
                material = self._create_material(merchant_id, current + timedelta(days=1), effect)
                self._add_event(
                    merchant_id, current + timedelta(days=1),
                    BusinessEventType.NEW_MATERIAL,
                    f"模拟动作：上线新素材 {material.material_id}",
                    {"material_id": material.material_id,
                     "campaign_id": material.campaign_id},
                    source=EventSource.ACTION,
                )
                emitted.append({"event_type": "new_material",
                                "material_id": material.material_id})
            elif etype == "traffic_cost_increase":
                cpm_factor *= float(effect.get("factor", 1.2))
            elif etype == "demand":
                demand_factor *= float(effect.get("factor", 1.0))
            else:
                raise ValueError(f"unknown simulator effect: {etype}")

        new_rows: List[Dict[str, Any]] = []
        initial_roi = history[0].roi
        observed_ctr = sum(r.ctr for r in history) / len(history)
        refreshed = any(effect.get("type") == "new_material" for effect in effects)
        anchor_ctr = observed_ctr * ctr_reset if refreshed else observed_ctr
        age_at_anchor = 0 if refreshed else (
            self._latest_material_age(merchant_id, current) or FATIGUE_GRACE
        )

        def fatigue(age_days: Optional[int]) -> float:
            if age_days is None:
                return 1.0
            return max(
                0.55, 1.0 / (1.0 + max(0, age_days - FATIGUE_GRACE) / FATIGUE_HALFLIFE_DAYS)
            )

        for offset in range(1, days + 1):
            day = current + timedelta(days=offset)
            age = self._latest_material_age(merchant_id, day)
            ctr = anchor_ctr * fatigue(age) / fatigue(age_at_anchor)
            weekend = 1.18 if day.weekday() >= 5 else 1.0
            noise = _noise(merchant_id, day)

            spend = max(50.0, base_spend * spend_factor * noise)
            cpm = base_cpm * cpm_factor * (1.0 + (noise - 1.0) / 2)
            impressions = max(1000, int(spend / cpm * 1000))
            clicks = max(10, int(impressions * ctr))
            conversions = int(clicks * base_cvr * demand_factor * weekend)
            gmv = round(conversions * base_aov * noise, 2)
            row = PerformanceDaily(
                merchant_id=merchant_id,
                date=day,
                gmv=gmv,
                ad_spend=round(spend, 2),
                impressions=impressions,
                clicks=clicks,
                ctr=round(clicks / impressions, 5),
                cpm=round(spend / impressions * 1000, 3),
                conversions=conversions,
                cvr=round(conversions / clicks, 5),
                aov=round(gmv / conversions, 2) if conversions else round(base_aov, 2),
                roi=round(gmv * margin / spend, 3),
            )
            self.db.add(row)
            new_rows.append(row)
            if offset == days and row.roi < initial_roi * 0.7:
                event = self._add_event(
                    merchant_id, day, BusinessEventType.SALES_DECLINE,
                    f"模拟推进：ROI 降至 {row.roi:.2f}，较动作前 {initial_roi:.2f} 明显下滑",
                    {"roi_before": initial_roi, "roi_after": row.roi},
                )
                emitted.append({"event_type": "sales_decline",
                                "event_id": event.event_id})

        self.db.commit()
        return {
            "merchant_id": merchant_id,
            "from_date": current.isoformat(),
            "to_date": (current + timedelta(days=days)).isoformat(),
            "days_added": len(new_rows),
            "performance": [
                {
                    "date": r.date.isoformat(), "gmv": r.gmv, "ad_spend": r.ad_spend,
                    "impressions": r.impressions, "clicks": r.clicks, "ctr": r.ctr,
                    "cpm": r.cpm, "conversions": r.conversions, "cvr": r.cvr,
                    "aov": r.aov, "roi": r.roi,
                }
                for r in new_rows
            ],
            "events_emitted": emitted,
            "label": "SYNTHETIC",
        }

    def _margin(self, merchant_id: str) -> float:
        margins = {
            "womenswear": 0.30, "beauty": 0.45, "food": 0.25,
            "home": 0.30, "electronics": 0.18,
        }
        merchant = self.db.get(Merchant, merchant_id)
        return margins.get(merchant.industry, 0.3)

    def _create_material(
        self, merchant_id: str, day: date, effect: Dict[str, Any]
    ) -> Material:
        campaign_id = effect.get("campaign_id")
        if not campaign_id:
            campaign_id = self.db.scalar(
                select(Campaign.campaign_id)
                .where(Campaign.merchant_id == merchant_id)
                .order_by(Campaign.campaign_id)
                .limit(1)
            )
        count = self.db.scalar(
            select(Material.material_id)
            .where(Material.material_id.like(f"MT{merchant_id[1:]}X%"))
            .order_by(desc(Material.material_id))
            .limit(1)
        )
        seq = int(count[-3:]) + 1 if count else 1
        material = Material(
            material_id=f"MT{merchant_id[1:]}X{seq:03d}",
            campaign_id=campaign_id,
            merchant_id=merchant_id,
            material_type=effect.get("material_type", MaterialType.VIDEO.value),
            material_name=effect.get("material_name", "模拟器新素材"),
            status=MaterialStatus.ACTIVE.value,
        )
        self.db.add(material)
        self.db.flush()
        return material
