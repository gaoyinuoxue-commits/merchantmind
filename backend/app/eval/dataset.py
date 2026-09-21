"""Offline ground-truth case set for agent evaluation (>= 50 cases).

Cases are deterministic and aligned with the synthetic world archetypes in
world_gen. Every expectation must be explainable from real seeded data.
"""
from __future__ import annotations

from typing import Any, Dict, List

_ARCHETYPE_MERCHANTS = {
    "fatigue_budget": ["M001", "M008"],
    "season_decline": ["M002", "M010"],
    "new_product_growth": ["M003", "M006"],
    "traffic_cost": ["M004", "M009"],
    "stable": ["M005", "M007"],
}

_ARCHETYPE_QUERY = {
    "fatigue_budget": "最近 ROI 一直下滑，CTR 也在掉，素材是不是疲劳了？预算要不要调？",
    "season_decline": "换季之后 GMV 一直下滑，生意越来越差，诊断一下原因",
    "new_product_growth": "新品最近表现怎么样，爬坡期投放上给点建议",
    "traffic_cost": "流量越来越贵，CPM 一直涨，投产快撑不住了，怎么办？",
    "stable": "看看最近整体经营情况，给点投放建议",
}

_ARCHETYPE_INTENT = {
    "fatigue_budget": "performance_diagnosis",
    "season_decline": "performance_diagnosis",
    "new_product_growth": "strategy_consultation",
    "traffic_cost": "performance_diagnosis",
    "stable": "strategy_consultation",
}

_BASE_TOOLS = ["get_shop_profile", "get_ad_performance", "get_recent_business_events"]


def _diagnosis_cases() -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    # 10 archetype-aligned diagnosis cases
    for archetype, merchants in _ARCHETYPE_MERCHANTS.items():
        for merchant_id in merchants:
            expected = {
                "intent": _ARCHETYPE_INTENT[archetype],
                "tools_required": list(_BASE_TOOLS),
                "causes_top3_any": [],
                "primary_in": [],
            }
            if archetype == "fatigue_budget":
                expected["tools_required"].append("get_material_performance")
                expected["causes_top3_any"] = [
                    "material_fatigue",
                    "budget_cpm_spiral",
                    "traffic_cost_increase",
                ]
                expected["causes_min_hits"] = 2
            elif archetype == "season_decline":
                expected["primary_in"] = ["season_decline"]
            elif archetype == "new_product_growth":
                expected["causes_top3_any"] = ["new_product_ramp"]
                expected["causes_min_hits"] = 1
            elif archetype == "traffic_cost":
                expected["causes_top2_any"] = ["traffic_cost_increase"]
                expected["causes_min_hits"] = 1
            cases.append({
                "id": f"diag_arch_{merchant_id}",
                "type": "diagnosis",
                "merchant_id": merchant_id,
                "message": _ARCHETYPE_QUERY[archetype],
                "expected": expected,
            })

    # 10 generic decline diagnosis cases (every merchant has fatigue evidence)
    for i in range(1, 11):
        merchant_id = f"M{i:03d}"
        cases.append({
            "id": f"diag_generic_{merchant_id}",
            "type": "diagnosis",
            "merchant_id": merchant_id,
            "message": "为什么最近 ROI 一直下滑，帮我诊断一下",
            "expected": {
                "intent": "performance_diagnosis",
                "tools_required": list(_BASE_TOOLS),
                "causes_top3_any": ["material_fatigue"],
                "causes_min_hits": 1,
            },
        })

    # 10 strategy consultation cases
    for i in range(1, 11):
        merchant_id = f"M{i:03d}"
        cases.append({
            "id": f"strategy_{merchant_id}",
            "type": "diagnosis",
            "merchant_id": merchant_id,
            "message": "接下来的投放策略有什么建议？",
            "expected": {
                "intent": "strategy_consultation",
                "tools_required": list(_BASE_TOOLS),
                "require_primary": True,
            },
        })
    return cases


_KNOWLEDGE_CASES = [
    ("kn_fatigue", "M001", "素材疲劳的判断标准是什么，怎么定义素材疲劳", ["diag_fatigue", "bp_fatigue_versions"]),
    ("kn_budget_cpm", "M001", "加预算进了更贵流量池是什么意思，定义是什么", ["diag_budget_cpm", "biz_budget_step"]),
    ("kn_traffic", "M004", "行业里 CPM 上涨一般多少算异常，有基准吗", ["diag_traffic_cost", "case_traffic_cost"]),
    ("kn_season", "M002", "换季需求下滑时的投放规则是什么，有案例吗", ["diag_season_decline", "case_season_exit"]),
    ("kn_new_product", "M003", "新品爬坡期一般多少天，行业基准是什么", ["diag_new_product", "biz_new_product_support"]),
    ("kn_roi_def", "M005", "ROI 投产比到底是怎么计算的，口径是什么", ["metric_roi"]),
    ("kn_ctr", "M008", "CTR 点击率的计算口径是什么，点击率怎么算", ["metric_ctr"]),
    ("kn_case", "M001", "有没有素材疲劳、预算失控最后失败的真实案例", ["case_fatigue_budget"]),
]


def _knowledge_cases() -> List[Dict[str, Any]]:
    return [
        {
            "id": case_id,
            "type": "knowledge",
            "merchant_id": merchant_id,
            "message": message,
            "expected": {
                "intent": "knowledge_query",
                "knowledge_slugs": slugs,
                "knowledge_k": 5,
                "knowledge_min_hits": 1,
            },
        }
        for case_id, merchant_id, message, slugs in _KNOWLEDGE_CASES
    ]


_ACTION_CASES = [
    ("act_budget_down_20", "M002", "帮我把预算降低 20%", "budget_change"),
    ("act_budget_down_10", "M005", "最近花费太高，压预算 10%", "budget_change"),
    ("act_budget_up_15", "M003", "预算提高 15%，我要放量", "budget_change"),
    ("act_budget_up_20", "M009", "加预算 20% 冲一波 GMV", "budget_change"),
    ("act_pause_1", "M008", "暂停一下爆款转化计划", "campaign_pause"),
    ("act_pause_2", "M010", "把引流拉新计划停掉", "campaign_pause"),
]


def _action_cases() -> List[Dict[str, Any]]:
    return [
        {
            "id": case_id,
            "type": "action",
            "merchant_id": merchant_id,
            "message": message,
            "expected": {
                "intent": "action_request",
                "action_type": action_type,
            },
        }
        for case_id, merchant_id, message, action_type in _ACTION_CASES
    ]


def _greeting_cases() -> List[Dict[str, Any]]:
    return [
        {
            "id": "greet_1",
            "type": "greeting",
            "merchant_id": "M001",
            "message": "你好",
            "expected": {"intent": "greeting", "no_tools": True},
        },
        {
            "id": "greet_2",
            "type": "greeting",
            "merchant_id": "M005",
            "message": "在吗，介绍下你能做什么",
            "expected": {"intent": "greeting", "no_tools": True},
        },
    ]


def _clarify_cases() -> List[Dict[str, Any]]:
    return [
        {
            "id": "clarify_vague_1",
            "type": "clarify",
            "merchant_id": "M001",
            "message": "这个东西怎么样啊",
            "expected": {"clarify": True, "no_tools": True},
        },
        {
            "id": "clarify_vague_2",
            "type": "clarify",
            "merchant_id": "M006",
            "message": "那玩意儿靠谱吗",
            "expected": {"clarify": True, "no_tools": True},
        },
    ]


_MEMORY_CASES = [
    (
        "mem_budget", "M001",
        "我们决定加预算放量冲 GMV", "放量",
        "预算怎么花比较合理",
    ),
    (
        "mem_traffic", "M004",
        "我们主要靠直播信息流引流", "直播信息流",
        "直播信息流这条流量渠道还要继续投吗",
    ),
    (
        "mem_style", "M006",
        "我们一直用真人口播风格拍素材", "口播",
        "口播风格的素材还要继续做吗",
    ),
    (
        "mem_audience", "M007",
        "我们主要客户是年轻白领", "年轻白领",
        "年轻白领这个人群转化率怎么样",
    ),
    (
        "mem_category", "M010",
        "我们主营连衣裙和半身裙", "连衣裙",
        "连衣裙这个类目接下来怎么投",
    ),
    (
        "mem_city", "M003",
        "我们重点做下沉市场", "下沉",
        "下沉市场的城市还值得加预算吗",
    ),
]


def _memory_cases() -> List[Dict[str, Any]]:
    return [
        {
            "id": case_id,
            "type": "memory",
            "merchant_id": merchant_id,
            "message": setup,
            "setup_message": setup,
            "followup_message": followup,
            "expected": {"memory_contains": keyword},
        }
        for case_id, merchant_id, setup, keyword, followup in _MEMORY_CASES
    ]


def ground_truth_cases() -> List[Dict[str, Any]]:
    cases = (
        _diagnosis_cases()
        + _knowledge_cases()
        + _action_cases()
        + _greeting_cases()
        + _clarify_cases()
        + _memory_cases()
    )
    return cases
