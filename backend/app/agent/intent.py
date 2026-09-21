"""Deterministic local intent classifier with signal extraction."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

INTENT_PERFORMANCE = "performance_diagnosis"
INTENT_STRATEGY = "strategy_consultation"
INTENT_ACTION = "action_request"
INTENT_KNOWLEDGE = "knowledge_query"
INTENT_GREETING = "greeting"

_KEYWORDS = {
    INTENT_ACTION: [
        "帮我", "暂停", "关掉", "关闭", "停掉", "提预算", "加预算", "降预算", "压预算",
        "提高预算", "减少预算", "调价", "降价", "上新", "换素材", "执行", "直接操作", "放量",
    ],
    INTENT_PERFORMANCE: [
        "为什么", "下降", "下滑", "变差", "掉了", "走低", "异常", "诊断",
        "没效果", "花了钱", "烧钱", "没成交", "没单", "roi", "ctr", "cvr",
        "cpm", "点击率", "转化率", "投产", "成本变高",
    ],
    INTENT_KNOWLEDGE: [
        "是什么", "什么意思", "怎么算", "定义", "口径", "案例", "规则",
        "行业里", "基准", "一般多少", "知识",
    ],
    INTENT_STRATEGY: [
        "怎么做", "如何", "建议", "策略", "规划", "优化", "提升", "怎么办",
        "下一步", "打法",
    ],
    INTENT_GREETING: ["你好", "在吗", "您好", "hi", "hello"],
}

_METRICS = {
    "roi": ["roi", "投产", "投入产出"],
    "ctr": ["ctr", "点击率"],
    "cvr": ["cvr", "转化率", "成交率"],
    "cpm": ["cpm", "千次曝光", "流量成本"],
    "spend": ["花费", "消耗", "预算花", "ad_spend"],
    "gmv": ["gmv", "成交额", "销售额"],
}

_DOMAINS = {
    "material": ["素材", "创意", "视频", "图片", "疲劳"],
    "budget": ["预算", "出价", "放量", "花费"],
    "new_product": ["新品", "新款", "上新"],
    "season": ["换季", "季节", "应季", "过季"],
    "traffic_cost": ["流量贵", "大盘", "竞争", "cpm涨", "流量"],
    "product": ["商品", "链接", "评分", "库存", "评价", "类目", "品类"],
    "campaign": ["计划", "账户", "定向", "人群"],
}

_PRIORITY = [
    INTENT_GREETING,
    INTENT_ACTION,
    INTENT_KNOWLEDGE,
    INTENT_PERFORMANCE,
    INTENT_STRATEGY,
]


@dataclass
class IntentResult:
    intent: str
    confidence: float
    signals: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": round(self.confidence, 4),
            "signals": self.signals,
        }


_NEGATIVE_CONTEXT = {
    # "叠加预算" contains "加预算" as a substring but is not an action request.
    "加预算": re.compile(r"(?<!叠)加预算"),
}


def _hits(text: str, words: List[str]) -> List[str]:
    lowered = text.lower()
    hits = []
    for word in words:
        token = word.lower()
        if token not in lowered:
            continue
        guarded = _NEGATIVE_CONTEXT.get(word)
        if guarded is not None and not guarded.search(text):
            continue
        hits.append(word)
    return hits


def extract_signals(text: str) -> Dict[str, List[str]]:
    """Metric/domain keyword signals shared by the rule and ML classifiers.

    The ML model predicts the intent label; the planner still needs these
    structural signals, so they are extracted deterministically regardless of
    which classifier is used.
    """
    metrics = []
    for metric, words in _METRICS.items():
        if _hits(text, words):
            metrics.append(metric)
    domains = []
    for domain, words in _DOMAINS.items():
        if _hits(text, words):
            domains.append(domain)
    return {"metrics": metrics, "domains": domains}


def classify_intent(text: str) -> IntentResult:
    scores = {}
    matched = {}
    for intent, words in _KEYWORDS.items():
        hits = _hits(text, words)
        scores[intent] = len(hits)
        matched[intent] = hits

    signals = extract_signals(text)
    metrics = signals["metrics"]
    domains = signals["domains"]

    total = sum(scores.values())
    if total == 0:
        if metrics or domains:
            return IntentResult(
                intent=INTENT_STRATEGY,
                confidence=0.6,
                signals={"metrics": metrics, "domains": domains, "matched": []},
            )
        return IntentResult(
            intent=INTENT_STRATEGY,
            confidence=0.35,
            signals={"metrics": [], "domains": [], "matched": []},
        )

    best = max(_PRIORITY, key=lambda intent: (scores[intent], -_PRIORITY.index(intent)))
    confidence = 0.5 + 0.5 * scores[best] / total

    return IntentResult(
        intent=best,
        confidence=min(0.98, confidence),
        signals={"metrics": metrics, "domains": domains, "matched": matched[best]},
    )


# --- Metric lookup vs diagnosis/strategy/benchmark disambiguation ----------
# "现在 ROI 是多少 / 帮我查一下点击率" asks for a current value; it must not
# be routed to the "why did it drop" diagnosis pipeline.

# Explicit value-request cues only. Note that "怎么样/如何了" is deliberately
# excluded: it asks for analysis/status rather than a bare number and must keep
# the normal flow (memory recall + diagnosis), not the lookup shortcut.
_LOOKUP_CUES = re.compile(
    r"多少|几多|多大|多高"
    r"|查一下|查一查|查下|查询|帮我查|帮忙查"
    r"|看下|看看|看一下|看一看"
)

# Any of these means the user wants attribution, advice, a definition or an
# industry benchmark rather than their own current number -> not a lookup.
_NON_LOOKUP_CUES = re.compile(
    r"为什么|为啥|为何|怎么会|原因|归因"
    r"|是什么|什么意思|怎么算|口径|定义"
    r"|怎么提升|如何提升|怎么提高|如何提高|怎么办"
    r"|怎么优化|如何优化|怎么改善|如何改善"
    r"|怎么才能|如何才能|要不要|该不该|应不应该"
    r"|一般|通常|正常|标准|基准|平均|行业里"
    r"|合适|应该.{0,3}多少|设.{0,3}多少|定.{0,3}多少"
    r"|调.{0,3}多少|加.{0,3}多少|降.{0,3}多少"
)

_SPEND_HINT = re.compile(r"花费|消耗|花了|烧了|花钱|预算")


def is_metric_lookup(text: str, signals: Dict[str, List[str]] = None) -> bool:
    """True when the utterance asks for the merchant's own current metric.

    Requires (a) a metric subject, (b) an explicit value-request cue, and
    (c) no attribution/advice/definition/benchmark cue. Deliberately errs on
    the side of False so ambiguous cases keep the original diagnosis flow.
    """
    signals = signals if signals is not None else extract_signals(text)
    has_metric = bool(signals.get("metrics")) or bool(_SPEND_HINT.search(text))
    if not has_metric:
        return False
    if _NON_LOOKUP_CUES.search(text):
        return False
    return bool(_LOOKUP_CUES.search(text))
