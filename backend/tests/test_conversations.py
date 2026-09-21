from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import Conversation, Merchant, Message
from app.services.conversation_service import ConversationService
from app.services.seed_service import SeedService
from app.services.seed_datasets import smoke_dataset


@pytest.fixture()
def merchant(db):
    SeedService(db).seed_all(smoke_dataset())
    return "SMOKE001"


def test_create_conversation_and_ordered_messages(db, merchant) -> None:
    service = ConversationService(db)
    conversation = service.create_conversation(merchant)
    assert conversation.title.endswith("诊断对话")

    service.add_message(conversation.conversation_id, "user", "为什么 ROI 下降？")
    service.add_message(conversation.conversation_id, "assistant", "正在分析…",
                        meta={"intent": "performance_diagnosis"})

    messages = service.messages(conversation.conversation_id)
    assert [m.seq for m in messages] == [1, 2]
    assert messages[1].meta == {"intent": "performance_diagnosis"}


def test_conversation_validation(db, merchant) -> None:
    service = ConversationService(db)
    with pytest.raises(KeyError):
        service.create_conversation("GHOST")
    conversation = service.create_conversation(merchant)
    with pytest.raises(ValueError):
        service.add_message(conversation.conversation_id, "alien", "x")
    with pytest.raises(KeyError):
        service.add_message("CV_nope", "user", "x")


def test_conversation_delete_cascades_messages(db, merchant) -> None:
    service = ConversationService(db)
    conversation = service.create_conversation(merchant)
    service.add_message(conversation.conversation_id, "user", "hi")
    db.delete(db.get(Merchant, merchant))
    db.commit()
    assert db.scalar(select(func.count()).select_from(Conversation)) == 0
    assert db.scalar(select(func.count()).select_from(Message)) == 0


def test_conversation_api(api_client, merchant) -> None:
    created = api_client.post("/api/conversations", json={"merchant_id": merchant})
    assert created.status_code == 201
    conversation_id = created.json()["conversation_id"]

    missing = api_client.post("/api/conversations", json={"merchant_id": "GHOST"})
    assert missing.status_code == 404

    posted = api_client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "最近 CTR 为什么跌？"},
    )
    assert posted.status_code == 201
    assert posted.json()["seq"] == 1
    assert posted.json()["role"] == "user"

    bad_role = api_client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"role": "root", "content": "x"},
    )
    assert bad_role.status_code == 422

    detail = api_client.get(f"/api/conversations/{conversation_id}").json()
    assert len(detail["messages"]) == 1
    assert detail["messages"][0]["content"] == "最近 CTR 为什么跌？"

    listing = api_client.get("/api/conversations", params={"merchant_id": merchant})
    assert len(listing.json()) == 1

    ghost = api_client.get("/api/conversations/CV_nope")
    assert ghost.status_code == 404
