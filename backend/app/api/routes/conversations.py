from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    MessageCreate,
    MessageOut,
)
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationOut, status_code=201)
def create_conversation(
    payload: ConversationCreate, db: Session = Depends(get_db)
) -> ConversationOut:
    service = ConversationService(db)
    try:
        conversation = service.create_conversation(payload.merchant_id, payload.title)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ConversationOut.model_validate(conversation)


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    merchant_id: str, db: Session = Depends(get_db)
) -> list[ConversationOut]:
    return [
        ConversationOut.model_validate(c)
        for c in ConversationService(db).list_conversations(merchant_id)
    ]


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str, db: Session = Depends(get_db)
) -> ConversationDetail:
    service = ConversationService(db)
    try:
        conversation = service.get(conversation_id)
        messages = service.messages(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ConversationDetail(
        **ConversationOut.model_validate(conversation).model_dump(),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.post("/{conversation_id}/messages", response_model=MessageOut, status_code=201)
def add_message(
    conversation_id: str,
    payload: MessageCreate,
    db: Session = Depends(get_db),
) -> MessageOut:
    service = ConversationService(db)
    try:
        message = service.add_message(
            conversation_id, payload.role, payload.content, payload.meta
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageOut.model_validate(message)
