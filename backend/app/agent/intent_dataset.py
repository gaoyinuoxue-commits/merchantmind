"""Labelled Chinese intent dataset for the offline intent classifier.

This is genuine supervised training data, not a download:
- ``HANDWRITTEN`` sentences are written explicitly per intent and mimic real
  merchant chat (colloquial, typos, weak/no keyword phrasing).
- ``expansions()`` deterministically expands slot templates (metric/domain
  slots + polite affixes) and is used ONLY for training augmentation.
- ``build_dataset`` holds out a stratified slice of *hand-written* sentences as
  the test set, so evaluation reflects real generalization rather than the
  template distribution.

Labels stay aligned with app.agent.intent (5 classes).
"""
from __future__ import annotations

import random
from itertools import product
from typing import Dict, List, Tuple

LABELS: List[str] = [
    "performance_diagnosis",
    "strategy_consultation",
    "action_request",
    "knowledge_query",
    "greeting",
]

HANDWRITTEN: Dict[str, List[str]] = {
    "greeting": [
        "你好", "在吗", "您好", "hi", "hello", "早上好", "晚上好", "在不在",
        "客服在吗", "嗨", "请问有人吗", "你好呀", "哈喽", "在的吗", "有人工吗",
        "哈喽哈喽", "hey", "早上好呀", "下午好", "喂", "你好客服", "大神在吗",
        "在么", "晚上好呀", "你好，在吗",
    ],
    "knowledge_query": [
        "ROI 是什么意思", "点击率是怎么算的", "CVR 的定义是什么",
        "女装行业 CTR 一般多少算正常", "CPM 的口径是什么", "ROI 计算公式是啥",
        "什么是素材疲劳", "能不能给我讲个案例", "复购率指的是什么",
        "客单价怎么定义", "流量成本一般在什么水平", "规则上一天最多能调几次预算",
        "有没有类似商家的真实例子", "AOV 是什么指标", "千次曝光成本怎么算",
        "预算消耗率是什么意思", "大促前后 CPM 通常什么规律", "素材疲劳一般第几天出现",
        "行业基准 ROI 多少才算合格", "库存预警线一般设多少", "什么叫冷启动",
        "CPA 是什么意思", "能解释下投产比这个概念吗", "平台的流量分发规则是怎样的",
        "转化率行业平均大概多少", "请问什么是千次曝光",
    ],
    "action_request": [
        "帮我把这个计划暂停掉", "关掉表现最差的那条素材", "把日预算提高 20%",
        "预算降 30%", "停掉这个广告组", "帮我上新一条视频素材",
        "直接帮我放量", "这个商品降价 10%", "把那个暂停的计划重启",
        "帮我执行刚才那个建议", "日预算加到 8000", "先暂停两天看看",
        "帮我换一批新素材", "提高出价抢点量", "这个月先减少花费",
        "把所有疲劳素材关掉", "帮我操作一下预算", "立刻停投这条",
        "预算稍微加一点", "把那个高花费低转化的计划关了", "帮我把老素材下了",
        "就按你说的做", "暂停所有 ROI 低于 1 的计划", "给我把出价压下来",
        "新建一个计划并开跑", "停掉，别再花钱了",
        "就按你说的办", "行，就这么做", "确认执行", "照你说的来",
        "可以，就按这个方案操作", "按你建议的做吧",
    ],
    "performance_diagnosis": [
        "为什么最近 ROI 一直下降", "点击率掉了是什么原因",
        "最近 CPM 涨得好厉害", "ROI 下滑了帮我诊断一下",
        "钱花了但是没成交怎么回事", "广告突然没效果了", "最近投产越来越差",
        "为什么 GMV 在走低", "转化率突然变差了",
        "流量越来越贵但是单没多", "钱烧得很快却没单", "有曝光没点击是什么情况",
        "最近点击率一直上不去", "ROI 异常波动帮我看看", "成本变高了什么原因",
        "为什么最近投放一直在亏钱", "店铺数据突然掉了", "广告效率明显变差了",
        "为什么我投得越多亏得越多", "点击率和转化最近都在跌",
        "预算花完了成交却很少", "我什么都没改为什么 ROI 掉了",
        "搜索流量的成本突然涨了", "我的计划是不是出问题了",
        "最近两天花不出去钱还没单", "钱花得好快单却不多",
        "为什么同样的预算效果差这么多",
    ],
    "strategy_consultation": [
        "新品怎么推广比较好", "接下来该怎么优化", "帮我出一个投放策略",
        "ROI 低要怎么提升", "素材应该往什么方向做", "预算怎么分配更合理",
        "冷启动期应该怎么打", "换季了投放要怎么调整", "给我一些提升转化率的建议",
        "现在这个阶段适合放量吗", "怎么提高点击率", "帮我做下个月的投放规划",
        "小店铺要怎么控制成本", "女装类目应该怎么打", "日常优化的重点是什么",
        "怎么判断该不该加预算", "给一个下一步的打法", "库存压力大该怎么清货",
        "怎么提升老客复购", "新店前两周应该怎么投", "想提升 GMV 该怎么做",
        "出价策略一般怎么定", "素材的迭代节奏怎么安排", "如何平衡规模和利润",
        "旺季前要做哪些准备",
    ],
}

# Slot values reused by the deterministic augmentation templates.
_METRIC = ["ROI", "CTR", "CVR", "CPM", "GMV", "转化率", "点击率", "花费", "投产"]
_DOMAIN = ["素材", "计划", "商品", "预算", "出价", "广告组"]

_PREFIX = ["", "", "请问", "麻烦问下", "我想问下", "最近"]
_SUFFIX = ["", "", "？", "呢", "啊", "谢谢"]

_TEMPLATES: Dict[str, List[str]] = {
    "performance_diagnosis": [
        "为什么{m}一直在下降", "{m}突然下滑是什么原因", "{m}变差了帮我看看",
        "{d}的{m}掉得厉害怎么回事", "为什么{d}没效果了", "{m}异常帮我诊断",
        "最近{d}一直亏钱", "钱花了{m}却上不去",
    ],
    "strategy_consultation": [
        "怎么提升{m}", "{d}应该怎么优化", "如何把{m}做上去",
        "给我一套{d}优化方案", "{d}怎么安排比较合理", "想改善{m}有什么建议",
        "下一步怎么调{d}", "怎么规划{d}更合适",
    ],
    "action_request": [
        "帮我调整{d}", "把{d}关了", "暂停这个{d}", "提高{d}", "降低{d}",
        "立刻操作{d}", "帮我执行{d}调整", "把{d}改一下",
        "按你说的做", "照你说的来", "就这么办", "确认执行", "可以执行",
        "按这个方案操作", "马上执行", "按建议处理",
    ],
    "knowledge_query": [
        "{m}是什么", "{m}怎么算", "{m}的定义和口径", "行业里{m}一般多少",
        "{d}有什么规则限制", "讲一下{m}的概念",
        "有没有{d}案例", "有没有{m}的例子", "给个{d}的真实例子",
        "{m}一般什么水平",
    ],
    "greeting": [
        "你好", "在吗", "哈喽", "hi",
    ],
}


def _expand_template(template: str) -> List[str]:
    slots = {"m": _METRIC, "d": _DOMAIN}
    candidates = {template}
    for key, values in slots.items():
        token = "{" + key + "}"
        if token in template:
            candidates = {
                base.replace(token, value)
                for base in candidates
                for value in values
            }
    out = set()
    for base in candidates:
        for prefix, suffix in product(_PREFIX, _SUFFIX):
            text = f"{prefix}{base}{suffix}".strip()
            if text:
                out.add(text)
    return sorted(out)


def expansions() -> Dict[str, List[str]]:
    """Deterministic training-only augmentation (slot + affix combinations)."""
    result: Dict[str, List[str]] = {}
    for label, templates in _TEMPLATES.items():
        seen = set(HANDWRITTEN[label])
        bucket: List[str] = []
        for template in templates:
            for text in _expand_template(template):
                if text not in seen:
                    seen.add(text)
                    bucket.append(text)
        result[label] = bucket
    return result


def build_dataset(
    test_frac: float = 0.25, seed: int = 20260915
) -> Tuple[List[str], List[int], List[str], List[int]]:
    """Return (train_texts, train_labels, test_texts, test_labels).

    Test split is a stratified slice of HANDWRITTEN sentences only; augmented
    samples are appended to train. Label ids index ``LABELS``.
    """
    rng = random.Random(seed)
    train_texts: List[str] = []
    train_labels: List[int] = []
    test_texts: List[str] = []
    test_labels: List[int] = []

    aug = expansions()
    for label_id, label in enumerate(LABELS):
        sentences = list(dict.fromkeys(HANDWRITTEN[label]))
        rng.shuffle(sentences)
        n_test = max(1, round(len(sentences) * test_frac))
        test_rows = sentences[:n_test]
        train_rows = sentences[n_test:]
        test_texts.extend(test_rows)
        test_labels.extend([label_id] * len(test_rows))
        train_texts.extend(train_rows)
        train_labels.extend([label_id] * len(train_rows))
        train_texts.extend(aug[label])
        train_labels.extend([label_id] * len(aug[label]))

    paired = list(zip(train_texts, train_labels))
    rng.shuffle(paired)
    train_texts = [row[0] for row in paired]
    train_labels = [row[1] for row in paired]
    return train_texts, train_labels, test_texts, test_labels
