from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SimulatorEffect(BaseModel):
    type: str = Field(..., description="budget_change | campaign_pause | new_material | "
                                       "traffic_cost_increase | demand")
    factor: Optional[float] = None
    spend_factor: Optional[float] = None
    ctr_factor: Optional[float] = None
    campaign_id: Optional[str] = None
    material_type: Optional[str] = None
    material_name: Optional[str] = None


class AdvanceRequest(BaseModel):
    merchant_id: str = Field(..., min_length=1, max_length=32)
    days: int = Field(1, ge=1, le=30)
    effects: List[SimulatorEffect] = Field(default_factory=list)


class PerformanceRow(BaseModel):
    date: str
    gmv: float
    ad_spend: float
    impressions: int
    clicks: int
    ctr: float
    cpm: float
    conversions: int
    cvr: float
    aov: float
    roi: float


class AdvanceResponse(BaseModel):
    merchant_id: str
    from_date: str
    to_date: str
    days_added: int
    performance: List[PerformanceRow]
    events_emitted: List[Dict[str, Any]]
    label: str = "SYNTHETIC"


class SimulatorState(BaseModel):
    merchant_id: str
    current_date: Optional[str]
    last_7d: Dict[str, float]
    label: str = "SYNTHETIC"
