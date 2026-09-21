"""Default A/B variants and the stratified experiment case subset."""
from __future__ import annotations

from typing import Any, Dict, List

DEFAULT_VARIANTS: List[Dict[str, Any]] = [
    {
        "name": "baseline",
        "config": {
            "memory_top_k": 5,
            "knowledge_top_k": 8,
            "quality_retry_threshold": 0.70,
        },
    },
    {"name": "memory_topk_3", "config": {"memory_top_k": 3}},
    {"name": "knowledge_topk_5", "config": {"knowledge_top_k": 5}},
    {
        "name": "semantic_ranking",
        "config": {
            "memory_weights": {
                "semantic": 0.50,
                "recency": 0.15,
                "importance": 0.15,
                "relevance": 0.20,
            }
        },
    },
    {"name": "strict_gate", "config": {"quality_retry_threshold": 0.90}},
]

DEFAULT_CASE_IDS: List[str] = [
    "diag_arch_M001",
    "diag_arch_M002",
    "diag_arch_M003",
    "diag_arch_M004",
    "diag_arch_M005",
    "diag_arch_M008",
    "diag_arch_M010",
    "diag_generic_M001",
    "diag_generic_M004",
    "diag_generic_M010",
    "strategy_M001",
    "strategy_M005",
    "kn_fatigue",
    "kn_budget_cpm",
    "kn_roi_def",
    "kn_case",
    "act_budget_down_10",
    "act_budget_up_15",
    "act_pause_1",
    "greet_1",
    "clarify_vague_1",
]
