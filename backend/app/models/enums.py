from __future__ import annotations

from enum import Enum


class Industry(str, Enum):
    WOMENSWEAR = "womenswear"
    BEAUTY = "beauty"
    FOOD = "food"
    HOME = "home"
    ELECTRONICS = "electronics"


class BusinessStage(str, Enum):
    NEW = "new"
    GROWTH = "growth"
    MATURE = "mature"
    DECLINING = "declining"


class ProductStatus(str, Enum):
    ON_SALE = "on_sale"
    PAUSED = "paused"
    OUT_OF_STOCK = "out_of_stock"
    ARCHIVED = "archived"


class CampaignObjective(str, Enum):
    AWARENESS = "awareness"
    TRAFFIC = "traffic"
    CONVERSION = "conversion"
    PRODUCT_SALES = "product_sales"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class MaterialType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    CAROUSEL = "carousel"
    SHORT_VIDEO = "short_video"
    COPY = "copy"


class MaterialStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    FATIGUED = "fatigued"
    ARCHIVED = "archived"


class BusinessEventType(str, Enum):
    NEW_PRODUCT = "new_product"
    NEW_MATERIAL = "new_material"
    BUDGET_CHANGE = "budget_change"
    CAMPAIGN_PAUSE = "campaign_pause"
    CAMPAIGN_RESTART = "campaign_restart"
    MATERIAL_FATIGUE = "material_fatigue"
    TRAFFIC_COST_INCREASE = "traffic_cost_increase"
    CONVERSION_DECLINE = "conversion_decline"
    SALES_GROWTH = "sales_growth"
    SALES_DECLINE = "sales_decline"
    SEASON_CHANGE = "season_change"
    INVENTORY_CHANGE = "inventory_change"


class EventSource(str, Enum):
    SIMULATOR = "simulator"
    MANUAL = "manual"
    SYSTEM = "system"
    ACTION = "action"


class MemoryType(str, Enum):
    FACT = "fact"
    PROFILE = "profile"
    PREFERENCE = "preference"
    DERIVED_INSIGHT = "derived_insight"


class MemoryStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    REJECTED = "rejected"


class MemorySource(str, Enum):
    CONVERSATION = "conversation"
    EVENT = "event"
    DERIVED = "derived"
    MANUAL = "manual"


class KnowledgeType(str, Enum):
    BUSINESS_RULE = "business_rule"
    DIAGNOSTIC_RULE = "diagnostic_rule"
    INDUSTRY_INSIGHT = "industry_insight"
    BEST_PRACTICE = "best_practice"
    METRIC_DEFINITION = "metric_definition"
    CASE = "case"


class KnowledgeStatus(str, Enum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    ARCHIVED = "archived"
