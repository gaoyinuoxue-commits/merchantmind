from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, Merchant, Message

VALID_ROLES = {"user", "assistant", "system"}


class ConversationService:
    def __init__(self, db: Session):
        self.db = db

    def create_conversation(
        self, merchant_id: str, title: Optional[str] = None
    ) -> Conversation:
        merchant = self.db.get(Merchant, merchant_id)
        if merchant is None:
            raise KeyError(f"unknown merchant_id: {merchant_id}")
        conversation = Conversation(
            conversation_id=f"CV{uuid.uuid4().hex[:12]}",
            merchant_id=merchant_id,
            title=title or f"{merchant.merchant_name} · 诊断对话",
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def list_conversations(self, merchant_id: str) -> List[Conversation]:
        return list(self.db.scalars(
            select(Conversation)
            .where(Conversation.merchant_id == merchant_id)
            .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
        ).all())

    def get(self, conversation_id: str) -> Conversation:
        conversation = self.db.get(Conversation, conversation_id)
        if conversation is None:
            raise KeyError(f"unknown conversation_id: {conversation_id}")
        return conversation

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Message:
        if role not in VALID_ROLES:
            raise ValueError(f"invalid role: {role}")
        conversation = self.get(conversation_id)
        next_seq = (
            self.db.scalar(
                select(func.coalesce(func.max(Message.seq), 0)).where(
                    Message.conversation_id == conversation_id
                )
            )
            + 1
        )
        message = Message(
            message_id=f"MSG{uuid.uuid4().hex[:16]}",
            conversation_id=conversation_id,
            seq=next_seq,
            role=role,
            content=content,
            meta=meta,
            trace_id=trace_id,
        )
        self.db.add(message)
        conversation.title = conversation.title
        self.db.commit()
        self.db.refresh(message)
        return message

    def messages(self, conversation_id: str) -> List[Message]:
        self.get(conversation_id)
        return list(self.db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.seq)
        ).all())
