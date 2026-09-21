from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolInvokeIn(BaseModel):
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolSpecOut(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    permission: str
    risk_level: str


class ToolInvokeOut(BaseModel):
    tool: str
    arguments: Dict[str, Any]
    data: Dict[str, Any]


class ToolCallLogOut(BaseModel):
    id: int
    tool_name: str
    merchant_id: Optional[str]
    trace_id: Optional[str]
    arguments: Dict[str, Any]
    result_summary: Optional[str]
    latency_ms: Optional[float]
    success: bool
    error: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
