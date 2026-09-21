from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import (
    Badcase,
    BusinessEvent,
    Campaign,
    Conversation,
    EvalCaseResult,
    EvalRun,
    Experiment,
    ExperimentVariantRun,
    Feedback,
    KnowledgeItem,
    Material,
    MemoryConflict,
    MemoryItem,
    Merchant,
    MerchantIndustry,
    Message,
    PerformanceDaily,
    Product,
    ToolCallLog,
    TraceRun,
    TraceSpan,
)

# Children first, parents last (TRUNCATE ... CASCADE makes order non-critical).
# Tables introduced by later phases but safe to truncate alongside the world.
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

TABLES_RESET_ORDER = [
    ExperimentVariantRun,
    Experiment,
    Badcase,
    Feedback,
    EvalCaseResult,
    EvalRun,
    TraceSpan,
    TraceRun,
    Message,
    Conversation,
    MemoryConflict,
    MemoryItem,
    KnowledgeItem,
    ToolCallLog,
    BusinessEvent,
    Material,
    PerformanceDaily,
    Product,
    Campaign,
    MerchantIndustry,
    Merchant,
]


def enum_value(value: Any, enum_cls: Type[Enum], field: str) -> str:
    """Accept either an enum member or its value; reject unknown strings."""
    if isinstance(value, enum_cls):
        return value.value
    allowed = {member.value for member in enum_cls}
    if isinstance(value, str) and value in allowed:
        return value
    raise ValueError(
        f"invalid value {value!r} for {field}; allowed: {', '.join(sorted(allowed))}"
    )


class SeedService:
    """Idempotent seeding over PostgreSQL ON CONFLICT upserts.

    Phase 2 provides the mechanism; Phase 3 plugs in the full Synthetic
    Merchant World dataset.
    """

    def __init__(self, db: Session):
        self.db = db

    def reset(self) -> None:
        """Remove all business data (keeps extensions / alembic history)."""
        table_names = ", ".join(model.__table__.name for model in reversed(TABLES_RESET_ORDER))
        self.db.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
        self.db.commit()

    def counts(self) -> Dict[str, int]:
        from sqlalchemy import func, select

        result: Dict[str, int] = {}
        for model in TABLES_RESET_ORDER:
            total = self.db.execute(select(func.count()).select_from(model)).scalar_one()
            result[model.__table__.name] = int(total)
        return result

    def _upsert(
        self,
        model: Any,
        rows: List[Dict[str, Any]],
        conflict_target: Any,
        *,
        by_constraint: bool = False,
        conflict_columns: Optional[Tuple[str, ...]] = None,
    ) -> int:
        if not rows:
            return 0
        stmt = pg_insert(model).values(rows)
        if by_constraint:
            stmt = stmt.on_conflict_do_update(
                constraint=conflict_target,
                set_={
                    column: stmt.excluded[column]
                    for column in rows[0]
                    if column not in (conflict_columns or ())
                },
            )
        else:
            pk_name = conflict_target.name
            stmt = stmt.on_conflict_do_update(
                index_elements=[conflict_target],
                set_={
                    column: stmt.excluded[column] for column in rows[0] if column != pk_name
                },
            )
        self.db.execute(stmt)
        self.db.commit()
        return len(rows)

    def seed_merchants(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = [
            {
                "merchant_id": row["merchant_id"],
                "merchant_name": row["merchant_name"],
                "industry": enum_value(row["industry"], Industry, "industry"),
                "sub_industry": row.get("sub_industry"),
                "business_stage": enum_value(
                    row["business_stage"], BusinessStage, "business_stage"
                ),
                "gmv_level": row.get("gmv_level"),
                "city": row.get("city"),
            }
            for row in rows
        ]
        return self._upsert(Merchant, payload, Merchant.merchant_id)

    def seed_merchant_industries(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = [
            {
                "merchant_id": row["merchant_id"],
                "industry": enum_value(row["industry"], Industry, "industry"),
                "sub_industry": row.get("sub_industry") or "",
                "is_primary": bool(row.get("is_primary", False)),
            }
            for row in rows
        ]
        if not payload:
            return 0
        stmt = pg_insert(MerchantIndustry).values(payload)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_merchant_industry_tag",
            set_={"is_primary": stmt.excluded.is_primary},
        )
        self.db.execute(stmt)
        self.db.commit()
        return len(payload)

    def seed_products(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = [
            {
                "product_id": row["product_id"],
                "merchant_id": row["merchant_id"],
                "product_name": row["product_name"],
                "category": row.get("category"),
                "price": float(row["price"]),
                "cost": float(row["cost"]),
                "inventory": int(row.get("inventory", 0)),
                "sales": int(row.get("sales", 0)),
                "conversion_rate": row.get("conversion_rate"),
                "status": enum_value(row["status"], ProductStatus, "status"),
            }
            for row in rows
        ]
        return self._upsert(Product, payload, Product.product_id)

    def seed_campaigns(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = [
            {
                "campaign_id": row["campaign_id"],
                "merchant_id": row["merchant_id"],
                "campaign_name": row["campaign_name"],
                "objective": enum_value(row["objective"], CampaignObjective, "objective"),
                "budget": float(row["budget"]),
                "status": enum_value(row["status"], CampaignStatus, "status"),
            }
            for row in rows
        ]
        return self._upsert(Campaign, payload, Campaign.campaign_id)

    def seed_materials(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = [
            {
                "material_id": row["material_id"],
                "campaign_id": row["campaign_id"],
                "merchant_id": row["merchant_id"],
                "material_type": enum_value(
                    row["material_type"], MaterialType, "material_type"
                ),
                "material_name": row["material_name"],
                "status": enum_value(row["status"], MaterialStatus, "status"),
            }
            for row in rows
        ]
        return self._upsert(Material, payload, Material.material_id)

    def seed_performance(self, rows: Iterable[Mapping[str, Any]]) -> int:
        def _as_date(value: Any) -> Any:
            if isinstance(value, date):
                return value
            if isinstance(value, str):
                return date.fromisoformat(value[:10])
            return value

        payload = [
            {
                "merchant_id": row["merchant_id"],
                "date": _as_date(row["date"]),
                "gmv": float(row.get("gmv", 0.0)),
                "ad_spend": float(row.get("ad_spend", 0.0)),
                "impressions": int(row.get("impressions", 0)),
                "clicks": int(row.get("clicks", 0)),
                "ctr": row.get("ctr"),
                "cpm": row.get("cpm"),
                "conversions": int(row.get("conversions", 0)),
                "cvr": row.get("cvr"),
                "aov": row.get("aov"),
                "roi": row.get("roi"),
            }
            for row in rows
        ]
        return self._upsert(
            PerformanceDaily,
            payload,
            "merchant_date",
            by_constraint=True,
            conflict_columns=("merchant_id", "date"),
        )

    def seed_events(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = [
            {
                "event_id": row["event_id"],
                "merchant_id": row["merchant_id"],
                "event_type": enum_value(row["event_type"], BusinessEventType, "event_type"),
                "event_time": row["event_time"],
                "description": row.get("description"),
                "structured_data": dict(row.get("structured_data") or {}),
                "source": enum_value(row.get("source", "system"), EventSource, "source"),
            }
            for row in rows
        ]
        return self._upsert(BusinessEvent, payload, BusinessEvent.event_id)

    def seed_all(self, dataset: Mapping[str, Iterable[Mapping[str, Any]]]) -> Dict[str, int]:
        return {
            "merchants": self.seed_merchants(dataset.get("merchants", [])),
            "merchant_industries": self.seed_merchant_industries(
                dataset.get("merchant_industries", [])
            ),
            "products": self.seed_products(dataset.get("products", [])),
            "campaigns": self.seed_campaigns(dataset.get("campaigns", [])),
            "materials": self.seed_materials(dataset.get("materials", [])),
            "performance_daily": self.seed_performance(dataset.get("performance_daily", [])),
            "business_events": self.seed_events(dataset.get("business_events", [])),
        }
