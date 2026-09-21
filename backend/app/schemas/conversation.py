from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    merchant_id: str = Field(..., min_length=1, max_length=32)
    title: Optional[str] = Field(None, max_length=128)


class MessageCreate(BaseModel):
    role: str = Field("user", pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1)
    meta: Optional[Dict[str, Any]] = None


class MessageOut(BaseModel):
    message_id: str
    seq: int
    role: str
    content: str
    meta: Optional[Dict[str, Any]]
    trace_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    conversation_id: str
    merchant_id: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationOut):
    messages: List[MessageOut]
