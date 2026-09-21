from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentRunIn(BaseModel):
    merchant_id: str = Field(min_length=1, max_length=32)
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: Optional[str] = None


class ProposedAction(BaseModel):
    action_type: str
    title: str
    rationale: str
    params: Dict[str, Any]
    risk_level: str
    requires_confirmation: bool
    label: str = "SYNTHETIC"


class ActionExecuteIn(BaseModel):
    merchant_id: str = Field(min_length=1, max_length=32)
    action: Dict[str, Any]
    confirmed: bool = False
    observe_days: int = Field(default=7, ge=1, le=30)


class AgentRunOut(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    reply: str
    intent: Dict[str, Any]
    plan: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]
    memory: List[Dict[str, Any]]
    knowledge: List[Dict[str, Any]]
    diagnosis: Optional[Dict[str, Any]] = None
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    quality_retried: bool = False
    trace_id: Optional[str] = None
    label: str = "SYNTHETIC"
