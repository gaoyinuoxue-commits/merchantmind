from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.actions import execute_loop, parse_requested_action, propose_for_diagnosis
from app.agent.intent import INTENT_ACTION, INTENT_GREETING, INTENT_KNOWLEDGE
from app.agent.orchestrator import AgentOrchestrator, RunContext
from app.db.session import get_db
from app.models.merchant import Merchant
from app.schemas.agent import ActionExecuteIn, AgentRunIn, AgentRunOut
from app.services.conversation_service import ConversationService
from app.trace.service import TraceService

router = APIRouter(prefix="/agent", tags=["agent"])

GREETING = "你好，我是 MerchantMind 经营诊断助手。可以问我「为什么最近 ROI 下滑」「要不要加预算」这类经营问题。"


def _build_reply(ctx: RunContext, actions: list) -> str:
    if ctx.intent["intent"] == INTENT_GREETING:
        return GREETING
    if ctx.needs_clarification and ctx.clarification_question:
        return f"需要先确认一下：{ctx.clarification_question}"

    lines = [f"【意图识别】{ctx.intent['intent']}（置信度 {ctx.intent['confidence']}）"]

    if ctx.intent["intent"] == INTENT_KNOWLEDGE:
        if ctx.knowledge:
            lines.append("【知识解答】")
            for item in ctx.knowledge[:3]:
                lines.append(f"· {item['title']}：{item['content'][:160]}")
        return "\n".join(lines)

    report = ctx.diagnosis or {}
    primary = report.get("primary_cause")
    if primary:
        lines.append(
            f"【主要归因】{primary['title']}（置信度 {primary['confidence']}）：{primary['explanation']}"
        )
        evidence_lines = [f"  - {e['source']}: {e['fact']}" for e in primary["evidence"][:3]]
        lines.extend(evidence_lines)
    alternative = report.get("alternative_cause")
    if alternative:
        lines.append(f"【备择假设】{alternative['title']}（置信度 {alternative['confidence']}）")
    if report.get("dual_hypothesis"):
        lines.append(f"【不确定性】{report['confidence_note']}")
    lines.append(
        f"【证据质量】quality_score={report.get('quality_score')}"
        f"{'（已自动补充证据重试一次）' if ctx.quality_retried else ''}"
    )
    if actions:
        lines.append("【建议动作】")
        for action in actions:
            confirm = "需确认" if action["requires_confirmation"] else "可直接执行"
            lines.append(f"· [{action['risk_level']}/{confirm}] {action['title']}")
    if report.get("follow_up_questions"):
        lines.append("【追问建议】" + "；".join(report["follow_up_questions"]))
    lines.append("数据来源：SYNTHETIC 合成商家世界，指标均由真实入库数据计算。")
    return "\n".join(lines)


@router.post("/run", response_model=AgentRunOut)
def run_agent(payload: AgentRunIn, db: Session = Depends(get_db)) -> dict:
    merchant = db.get(Merchant, payload.merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="merchant not found")

    conversations = ConversationService(db)
    if payload.conversation_id:
        conversation = conversations.get(payload.conversation_id)
        if conversation is None or conversation.merchant_id != payload.merchant_id:
            raise HTTPException(status_code=404, detail="conversation not found")
    else:
        conversation = conversations.create_conversation(payload.merchant_id)

    user_message = conversations.add_message(
        conversation.conversation_id, "user", payload.message
    )

    tracer = TraceService(db)
    trace_id = tracer.start_run(
        payload.message,
        merchant_id=payload.merchant_id,
        conversation_id=conversation.conversation_id,
    )
    orchestrator = AgentOrchestrator(db, hooks=[tracer.hook], trace_id=trace_id)
    ctx = orchestrator.run(payload.merchant_id, payload.message)

    actions = []
    if not ctx.needs_clarification and ctx.intent["intent"] == INTENT_ACTION:
        requested = parse_requested_action(payload.message)
        if requested:
            actions = [requested]
    if not actions and ctx.diagnosis:
        actions = propose_for_diagnosis(ctx.diagnosis, ctx)

    tracer.finish_run(ctx, status="clarified" if ctx.needs_clarification else "done")
    reply = _build_reply(ctx, actions)
    assistant_message = conversations.add_message(
        conversation.conversation_id,
        "assistant",
        reply,
        meta={
            "intent": ctx.intent,
            "diagnosis": ctx.diagnosis,
            "actions": actions,
            "needs_clarification": ctx.needs_clarification,
            "quality_retried": ctx.quality_retried,
            "label": "SYNTHETIC",
        },
    )

    return {
        "conversation_id": conversation.conversation_id,
        "user_message_id": user_message.message_id,
        "assistant_message_id": assistant_message.message_id,
        "reply": reply,
        "intent": ctx.intent,
        "plan": ctx.plan,
        "observations": [
            {key: value for key, value in observation.items() if key != "data"}
            for observation in ctx.observations
        ],
        "memory": ctx.memories,
        "knowledge": [
            {
                "knowledge_id": k["knowledge_id"],
                "title": k["title"],
                "type": k["type"],
                "score": k["score"],
            }
            for k in ctx.knowledge
        ],
        "diagnosis": ctx.diagnosis,
        "actions": actions,
        "needs_clarification": ctx.needs_clarification,
        "clarification_question": ctx.clarification_question,
        "quality_retried": ctx.quality_retried,
        "trace_id": trace_id,
        "label": "SYNTHETIC",
    }


@router.post("/act")
def execute_action(payload: ActionExecuteIn, db: Session = Depends(get_db)) -> dict:
    merchant = db.get(Merchant, payload.merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="merchant not found")
    if "type" not in payload.action.get("params", {}):
        raise HTTPException(status_code=400, detail="action.params.type is required")
    tracer = TraceService(db)
    trace_id = tracer.start_run(
        f"执行动作：{payload.action.get('params', {}).get('type')}",
        merchant_id=payload.merchant_id,
    )
    result = execute_loop(
        db,
        payload.merchant_id,
        payload.action,
        confirmed=payload.confirmed,
        observe_days=payload.observe_days,
    )
    tracer.record(
        "action",
        f"动作执行：{payload.action.get('params', {}).get('type')}",
        payload={
            "action_type": payload.action.get("params", {}).get("type"),
            "risk_level": result.get("risk_level") or payload.action.get("risk_level"),
            "status": result["status"],
        },
        status="blocked" if result["status"] == "confirmation_required" else "ok",
    )
    tracer.finish_run(
        status="confirmation_required" if result["status"] == "confirmation_required" else "done",
        intent="action_request",
        needs_clarification=result["status"] == "confirmation_required",
    )
    result["trace_id"] = trace_id
    if result["status"] == "confirmation_required":
        raise HTTPException(status_code=409, detail=result)
    return result
