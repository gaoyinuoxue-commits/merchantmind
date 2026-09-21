"""Rule-based candidate memory extractor (offline local 'LLM').

Scans Chinese merchant utterances for durable facts / profiles / preferences
and tags each candidate with a conflict slot. Two candidates sharing a slot
with different values are treated as contradictory by governance.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

_SLOT_PATTERNS = [
    (
        "budget_preference",
        [
            (re.compile(r"(放量|冲量|加预算|提预算|增加预算|愿意加投)"), "放量增长"),
            (re.compile(r"(控成本|压预算|降预算|减少预算|省钱|控制花费)"), "控制成本"),
        ],
    ),
    (
        "traffic_source",
        [
            (re.compile(r"(主要靠|依赖|重点投|一直投).{0,6}(信息流|搜索|直播|短视频|自然流|商城)"), None),
        ],
    ),
    (
        "creative_style",
        [
            (re.compile(r"(实拍|真人出镜|口播|剧情|图文|工厂图|白底图|种草)风格"), None),
        ],
    ),
    (
        "audience",
        [
            (re.compile(r"(客群|目标人群|主要客户|买家).{0,12}"), None),
            (re.compile(r"(年轻|学生|宝妈|白领|中老年|男性|女性|下沉|高端)"), None),
        ],
    ),
    (
        "category",
        [
            (re.compile(r"(主营|主打|主要卖|核心品类).{0,16}"), None),
        ],
    ),
    (
        "city_tier",
        [
            (re.compile(r"(一线城市|二线城市|下沉市场|县城|地级市|北上广深)"), None),
        ],
    ),
]

_PREFERENCE_HINT = re.compile(r"(偏好|习惯|希望|不想|不愿意|倾向|接受|排斥)")
_PROFILE_HINT = re.compile(r"(主营|主打|客群|定位|品类|我们店|本店)")
_FACT_HINT = re.compile(r"(成立|开店|仓库|团队|复购率|客单价|价格带|SKU)")


def _trim(text: str, start: int, head: int, tail: int) -> str:
    snippet = text[max(0, start - head) : start + tail]
    return re.sub(r"\s+", " ", snippet).strip("，。,.!！?？ ")


def extract_memories(text: str) -> List[Dict[str, Any]]:
    candidates = []
    seen_slots = set()
    for slot, patterns in _SLOT_PATTERNS:
        for regex, canonical in patterns:
            match = regex.search(text)
            if not match:
                continue
            if canonical:
                content = f"{slot}:{canonical}"
                display = f"商家经营偏好倾向：{canonical}"
            else:
                content = _trim(text, match.start(), 2, 24)
                display = content
            key = (slot, content)
            if key in seen_slots:
                continue
            seen_slots.add(key)
            mtype = "preference" if slot in {"budget_preference", "creative_style", "traffic_source"} else "profile"
            importance = 0.85 if slot == "budget_preference" else 0.7
            candidates.append(
                {
                    "type": mtype,
                    "content": display,
                    "tags": [slot, content],
                    "importance": importance,
                    "confidence": 0.65,
                    "slot": slot,
                    "value": content,
                }
            )
            break
    if not candidates:
        if _PREFERENCE_HINT.search(text):
            candidates.append(
                {
                    "type": "preference",
                    "content": text.strip()[:120],
                    "tags": ["general_preference"],
                    "importance": 0.6,
                    "confidence": 0.55,
                    "slot": None,
                    "value": None,
                }
            )
        elif _PROFILE_HINT.search(text) or _FACT_HINT.search(text):
            candidates.append(
                {
                    "type": "fact",
                    "content": text.strip()[:120],
                    "tags": ["general_fact"],
                    "importance": 0.55,
                    "confidence": 0.55,
                    "slot": None,
                    "value": None,
                }
            )
    return candidates
