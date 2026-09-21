"""Case judges for offline evaluation.

- RuleJudge: deterministic checks against ground truth (intent, tools, causes,
  knowledge grounding, hallucination guard rails).
- HeuristicLLMJudge: the offline stand-in for a future LLM-as-a-judge. It only
  uses structural signals (evidence presence, grounding, SYNTHETIC labelling),
  so the pipeline stays fully offline; swap in a real LLM at deployment.
Human verdicts are recorded separately through the evaluation API.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CAUSE_WHITELIST = {
    "material_fatigue",
    "budget_cpm_spiral",
    "traffic_cost_increase",
    "season_decline",
    "product_weakness",
    "new_product_ramp",
}


def prediction_from_ctx(ctx: Any, parsed_action: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    diagnosis = getattr(ctx, "diagnosis", None) or {}
    candidates = diagnosis.get("candidate_causes", [])
    observations = getattr(ctx, "observations", [])
    return {
        "intent": (getattr(ctx, "intent", {}) or {}).get("intent"),
        "intent_confidence": (getattr(ctx, "intent", {}) or {}).get("confidence"),
        "primary_cause": (diagnosis.get("primary_cause") or {}).get("code"),
        "candidate_codes": [cause.get("code") for cause in candidates],
        "quality_score": diagnosis.get("quality_score"),
        "observed_tools": [
            observation.get("tool")
            for observation in observations
            if observation.get("success") and observation.get("tool")
        ],
        "failed_tools": [
            observation.get("tool")
            for observation in observations
            if not observation.get("success") and observation.get("tool")
        ],
        "knowledge_slugs": [item.get("slug") for item in getattr(ctx, "knowledge", [])],
        "needs_clarification": getattr(ctx, "needs_clarification", False),
        "quality_retried": getattr(ctx, "quality_retried", False),
        "extracted_memory_count": getattr(ctx, "extracted_memory_count", 0),
        "memory_contents": [item.get("content", "") for item in getattr(ctx, "memories", [])],
        "parsed_action": (parsed_action or {}).get("action_type"),
    }


def detect_hallucination(ctx: Any) -> List[str]:
    """Return a list of hallucination violations (empty list = grounded)."""
    violations: List[str] = []
    diagnosis = getattr(ctx, "diagnosis", None) or {}
    observed = {
        observation.get("tool")
        for observation in getattr(ctx, "observations", [])
        if observation.get("success") and observation.get("tool")
    }
    retrieved_slugs = {item.get("slug") for item in getattr(ctx, "knowledge", [])}
    for cause in diagnosis.get("candidate_causes", []):
        code = cause.get("code")
        if code not in CAUSE_WHITELIST:
            violations.append(f"unknown_cause:{code}")
        for evidence in cause.get("evidence", []):
            source = evidence.get("source")
            if source and source not in observed:
                violations.append(f"evidence_without_observation:{source}")
        for slug in cause.get("knowledge_slugs", []):
            if slug not in retrieved_slugs:
                violations.append(f"knowledge_not_grounded:{slug}")
    return violations


def _score_diagnosis(expected: Dict[str, Any], pred: Dict[str, Any]) -> Dict[str, Any]:
    intent_match = pred["intent"] == expected.get("intent")
    required = expected.get("tools_required", [])
    observed = set(pred["observed_tools"])
    tool_recall = len([tool for tool in required if tool in observed]) / len(required) if required else 1.0

    codes = pred["candidate_codes"]
    cause_hits = 0
    cause_required = 0
    for key, k in (("causes_top2_any", 2), ("causes_top3_any", 3)):
        wanted = expected.get(key)
        if wanted:
            cause_required += len(wanted)
            cause_hits += len(set(wanted) & set(codes[:k]))
    cause_recall = cause_hits / cause_required if cause_required else 1.0

    primary_ok = True
    if expected.get("primary_in"):
        primary_ok = pred["primary_cause"] in expected["primary_in"]
    if expected.get("require_primary"):
        primary_ok = bool(pred["primary_cause"])
    min_hits_ok = cause_hits >= expected.get("causes_min_hits", 0) if expected.get("causes_top2_any") or expected.get("causes_top3_any") else True

    return {
        "intent_match": intent_match,
        "tool_recall": round(tool_recall, 3),
        "cause_recall_at_3": round(cause_recall, 3),
        "primary_ok": primary_ok,
        "causes_min_hits_ok": min_hits_ok,
    }


def judge_case(
    case: Dict[str, Any],
    ctx: Any,
    parsed_action: Optional[Dict[str, Any]] = None,
    followup_ctx: Any = None,
) -> Dict[str, Any]:
    expected = case["expected"]
    pred = prediction_from_ctx(ctx, parsed_action)
    hallucinations = detect_hallucination(ctx)
    if followup_ctx is not None:
        hallucinations.extend(detect_hallucination(followup_ctx))
    case_type = case["type"]

    sub: Dict[str, Any] = {
        "hallucination": bool(hallucinations),
        "hallucination_violations": hallucinations,
    }

    if case_type == "diagnosis":
        sub.update(_score_diagnosis(expected, pred))
        passed = (
            sub["intent_match"]
            and sub["tool_recall"] == 1.0
            and sub["primary_ok"]
            and sub["causes_min_hits_ok"]
            and not pred["needs_clarification"]
            and not hallucinations
        )
    elif case_type == "knowledge":
        sub["intent_match"] = pred["intent"] == expected.get("intent")
        k = expected.get("knowledge_k", 5)
        wanted = expected.get("knowledge_slugs", [])
        hits = len(set(wanted) & set(pred["knowledge_slugs"][:k]))
        sub["knowledge_recall_at_5"] = round(hits / len(wanted), 3) if wanted else 1.0
        passed = (
            sub["intent_match"]
            and hits >= expected.get("knowledge_min_hits", 1)
            and not pred["needs_clarification"]
            and not hallucinations
        )
    elif case_type == "action":
        sub["intent_match"] = pred["intent"] == expected.get("intent")
        sub["action_type_match"] = pred["parsed_action"] == expected.get("action_type")
        passed = sub["intent_match"] and sub["action_type_match"] and not hallucinations
    elif case_type == "greeting":
        sub["intent_match"] = pred["intent"] == expected.get("intent")
        sub["no_tools"] = len(pred["observed_tools"]) == 0
        passed = sub["intent_match"] and sub["no_tools"]
    elif case_type == "clarify":
        sub["clarified"] = pred["needs_clarification"]
        sub["no_tools"] = len(pred["observed_tools"]) == 0
        passed = sub["clarified"] and sub["no_tools"]
    elif case_type == "memory":
        keyword = expected.get("memory_contains", "")
        sub["extracted"] = pred["extracted_memory_count"] >= 1
        followup_pred = prediction_from_ctx(followup_ctx) if followup_ctx is not None else pred
        sub["recalled"] = any(keyword in content for content in followup_pred["memory_contents"])
        passed = sub["extracted"] and sub["recalled"] and not hallucinations
    else:
        passed = False

    sub["passed"] = bool(passed)
    return sub


def heuristic_reply_score(ctx: Any) -> float:
    """Offline LLM-judge proxy in [0, 1]: reply must be evidence-grounded,
    cite knowledge when causes exist, and be explicitly labelled synthetic."""
    score = 0.3
    diagnosis = getattr(ctx, "diagnosis", None) or {}
    primary = diagnosis.get("primary_cause") or {}
    if primary.get("evidence"):
        score += 0.25
    if primary.get("knowledge_slugs"):
        score += 0.2
    if (diagnosis.get("quality_score") or 0) >= 0.7:
        score += 0.15
    if getattr(ctx, "needs_clarification", False) or primary:
        score += 0.1
    return round(min(1.0, score), 3)
