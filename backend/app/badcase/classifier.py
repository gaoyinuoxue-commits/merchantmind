"""Deterministic failure triage for badcases.

Every failed evaluation case / negative feedback is bucketed into exactly one
of the five spec categories so each owning module can be fixed independently:
Routing / Retrieval / Tool / Reasoning / Hallucination.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

ROUTING = "routing"
RETRIEVAL = "retrieval"
TOOL = "tool"
REASONING = "reasoning"
HALLUCINATION = "hallucination"
OTHER = "other"

_SUGGESTED_FIX = {
    "agent.intent": "扩充意图关键词与业务信号词表，回归 Ground Truth 路由用例。",
    "agent.actions": "扩充动作解析词表（动词/百分比/同义词），补充动作类用例。",
    "memory.governance": "扩充记忆抽取槽位模式，降低陈述型事实的漏抽率。",
    "memory.retrieval": "校准记忆召回权重（语义/时效/重要性/相关性）与 Top-K。",
    "knowledge.service": "补充知识条目或优化 embedding 召回、行业过滤与 Top-K。",
    "tools.service": "检查工具入参与数据源稳定性，增加失败重试与降级路径。",
    "agent.diagnosis": "校准病因证据规则、事件时效窗口与置信度公式。",
    "agent.grounding": "收紧 grounding 校验：证据须来自成功观测、知识须命中已召回 slug。",
    "human.feedback": "用户负反馈，等待人工分诊并补充复现路径。",
    "agent.loop": "通用编排失败，需人工分诊定位具体阶段。",
}


def _fix(module: str) -> str:
    return _SUGGESTED_FIX.get(module, "人工分诊后给出修复建议。")


def classify_case_failure(
    case: Dict[str, Any],
    verdict: Dict[str, Any],
    prediction: Dict[str, Any],
) -> Dict[str, str]:
    """Map one failed evaluation case to error_type/module/root_cause/fix."""
    case_type = case["type"]
    violations = verdict.get("hallucination_violations") or []

    if verdict.get("hallucination"):
        return {
            "error_type": HALLUCINATION,
            "affected_module": "agent.grounding",
            "root_cause": "检测到无证据断言：" + "、".join(violations),
            "suggested_fix": _fix("agent.grounding"),
            "severity": "high",
        }

    failed_tools = prediction.get("failed_tools") or []
    if failed_tools:
        return {
            "error_type": TOOL,
            "affected_module": "tools.service",
            "root_cause": "工具调用失败：" + "、".join(failed_tools),
            "suggested_fix": _fix("tools.service"),
            "severity": "high",
        }

    if case_type == "memory":
        if not verdict.get("extracted"):
            return {
                "error_type": RETRIEVAL,
                "affected_module": "memory.governance",
                "root_cause": "长期事实未被抽取进记忆库。",
                "suggested_fix": _fix("memory.governance"),
                "severity": "medium",
            }
        return {
            "error_type": RETRIEVAL,
            "affected_module": "memory.retrieval",
            "root_cause": "记忆已写入但后续轮次未召回到。",
            "suggested_fix": _fix("memory.retrieval"),
            "severity": "medium",
        }

    if case_type == "knowledge":
        return {
            "error_type": RETRIEVAL,
            "affected_module": "knowledge.service",
            "root_cause": "知识召回未命中 Ground Truth slug。",
            "suggested_fix": _fix("knowledge.service"),
            "severity": "medium",
        }

    if case_type == "action" and not verdict.get("action_type_match", True):
        return {
            "error_type": ROUTING,
            "affected_module": "agent.actions",
            "root_cause": "动作请求解析出的 action_type 与期望不符。",
            "suggested_fix": _fix("agent.actions"),
            "severity": "medium",
        }

    if not verdict.get("intent_match", True) or prediction.get("needs_clarification"):
        return {
            "error_type": ROUTING,
            "affected_module": "agent.intent",
            "root_cause": "意图分类错误或在不该澄清时触发了澄清。",
            "suggested_fix": _fix("agent.intent"),
            "severity": "medium",
        }

    if case_type == "diagnosis" and not (
        verdict.get("primary_ok", True) and verdict.get("causes_min_hits_ok", True)
    ):
        return {
            "error_type": REASONING,
            "affected_module": "agent.diagnosis",
            "root_cause": "病因归因与 Ground Truth 不一致（主因/候选命中不足）。",
            "suggested_fix": _fix("agent.diagnosis"),
            "severity": "medium",
        }

    if case_type == "greeting" and not verdict.get("no_tools", True):
        return {
            "error_type": ROUTING,
            "affected_module": "agent.loop",
            "root_cause": "寒暄类请求触发了工具调用。",
            "suggested_fix": _fix("agent.loop"),
            "severity": "low",
        }

    return {
        "error_type": OTHER,
        "affected_module": "agent.loop",
        "root_cause": "未归类失败，需人工分诊。",
        "suggested_fix": _fix("agent.loop"),
        "severity": "low",
    }


def classify_trace(trace: Any, spans: list) -> Optional[Dict[str, str]]:
    """Triage an online TraceRun; return None when the run looks healthy."""
    failed_tools = [
        span.name for span in spans if span.span_type == "tool_call" and span.status != "ok"
    ]
    if failed_tools:
        return {
            "error_type": TOOL,
            "affected_module": "tools.service",
            "root_cause": "线上运行工具调用失败：" + "、".join(failed_tools),
            "suggested_fix": _fix("tools.service"),
            "severity": "high",
        }
    if getattr(trace, "needs_clarification", False):
        return {
            "error_type": ROUTING,
            "affected_module": "agent.intent",
            "root_cause": "线上运行以澄清结束，可能存在路由/置信度问题。",
            "suggested_fix": _fix("agent.intent"),
            "severity": "low",
        }
    if getattr(trace, "status", "") == "failed":
        return {
            "error_type": OTHER,
            "affected_module": "agent.loop",
            "root_cause": "线上运行标记为失败。",
            "suggested_fix": _fix("agent.loop"),
            "severity": "medium",
        }
    return None
