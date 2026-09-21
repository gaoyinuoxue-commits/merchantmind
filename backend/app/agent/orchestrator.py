"""Self-built agent orchestration loop.

intent → memory recall → decision plan → tool execution → evidence bundle.
Diagnosis/decision layers (phases 11-13) attach to the same run context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agent.diagnosis import diagnose, referenced_slugs
from app.agent.intent import INTENT_GREETING, INTENT_KNOWLEDGE, is_metric_lookup
from app.agent.intent_ml import classify_with_backend
from app.agent.planner import build_plan
from app.hooks.engine import PostHook, PreHook, ToolHook
from app.knowledge.service import KnowledgeService
from app.memory.retrieval import MemoryRetrievalService
from app.tools.service import ToolError, ToolService

StageHook = Callable[[str, Dict[str, Any]], None]


@dataclass
class RunProfile:
    """Per-run override of pipeline knobs (Phase 17 A/B experiment variants).

    model/temperature/prompt_version are recorded but inert without a real LLM
    backend; the remaining dimensions change offline behaviour immediately.
    """

    memory_top_k: Optional[int] = None
    knowledge_top_k: Optional[int] = None
    memory_weights: Optional[Dict[str, float]] = None
    quality_retry_threshold: Optional[float] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    prompt_version: Optional[str] = None
    intent_backend: Optional[str] = None

    def applied_dimensions(self) -> List[str]:
        dims = []
        if self.memory_top_k is not None:
            dims.append("memory_top_k")
        if self.knowledge_top_k is not None:
            dims.append("knowledge_top_k")
        if self.memory_weights is not None:
            dims.append("memory_ranking_weights")
        if self.quality_retry_threshold is not None:
            dims.append("quality_retry_threshold")
        if self.intent_backend is not None:
            dims.append("intent_backend")
        return dims

    def recorded_dimensions(self) -> List[str]:
        dims = []
        if self.model is not None:
            dims.append("model")
        if self.temperature is not None:
            dims.append("temperature")
        if self.prompt_version is not None:
            dims.append("prompt_version")
        return dims


@dataclass
class RunContext:
    merchant_id: str
    query: str
    intent: Dict[str, Any] = field(default_factory=dict)
    memories: List[Dict[str, Any]] = field(default_factory=list)
    plan: List[Dict[str, Any]] = field(default_factory=list)
    observations: List[Dict[str, Any]] = field(default_factory=list)
    knowledge: List[Dict[str, Any]] = field(default_factory=list)
    extracted_memory_count: int = 0
    trace_id: Optional[str] = None
    diagnosis: Optional[Dict[str, Any]] = None
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    quality_retried: bool = False
    quality_decision: Optional[str] = None
    metric_lookup: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "merchant_id": self.merchant_id,
            "query": self.query,
            "intent": self.intent,
            "plan": self.plan,
            "observations": self.observations,
            "memory": self.memories,
            "knowledge": self.knowledge,
            "extracted_memory_count": self.extracted_memory_count,
            "diagnosis": self.diagnosis,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "quality_retried": self.quality_retried,
            "quality_decision": self.quality_decision,
            "metric_lookup": self.metric_lookup,
            "label": "SYNTHETIC",
        }


def _summarize(tool: str, data: Dict[str, Any]) -> str:
    if tool == "get_shop_profile":
        counts = data.get("asset_counts", {})
        return (
            f"{data.get('merchant_name')}｜{data.get('industry')}｜{data.get('business_stage')}｜"
            f"商品{counts.get('products', 0)}/计划{counts.get('campaigns', 0)}/素材{counts.get('materials', 0)}"
        )
    if tool == "get_ad_performance":
        current = data.get("current") or {}
        delta = data.get("delta_pct") or {}
        return (
            f"近{data.get('window', {}).get('days')}天 ROI={current.get('roi')} "
            f"CTR={current.get('ctr')} CPM={current.get('cpm')} "
            f"GMV环比={delta.get('gmv')}% ROI环比={delta.get('roi')}%"
        )
    if tool == "get_material_performance":
        materials = data.get("materials", [])
        fatigued = [m for m in materials if m.get("status") == "fatigued"]
        paused = [m for m in materials if m.get("status") == "paused"]
        return f"素材{len(materials)}条（疲劳{len(fatigued)}/暂停{len(paused)}）"
    if tool == "get_product_performance":
        products = data.get("products", [])
        low_stock = [p for p in products if (p.get("inventory") or 0) < 50]
        top = products[0]["product_name"] if products else "-"
        return f"商品{len(products)}个，销量第一：{top}，低库存{len(low_stock)}个"
    if tool == "get_historical_cases":
        cases = data.get("cases", [])
        return "案例：" + "；".join(case["title"] for case in cases[:3])
    if tool == "get_recent_business_events":
        events = data.get("events", [])
        types = {}
        for event in events:
            types[event["event_type"]] = types.get(event["event_type"], 0) + 1
        headline = "，".join(f"{key}×{value}" for key, value in sorted(types.items()))
        return f"{len(events)}个事件（{headline or '无'}）"
    return "ok"


class AgentOrchestrator:
    def __init__(
        self,
        db: Session,
        hooks: Optional[List[StageHook]] = None,
        trace_id: Optional[str] = None,
        profile: Optional[RunProfile] = None,
    ):
        self.db = db
        self.hooks = hooks or []
        self.trace_id = trace_id
        self.profile = profile or RunProfile()
        self.tools = ToolService(db, trace_id=trace_id)

    def _emit(self, stage: str, payload: Dict[str, Any]) -> None:
        for hook in self.hooks:
            hook(stage, payload)

    def run(self, merchant_id: str, query: str, extract_memory: bool = True) -> RunContext:
        ctx = RunContext(merchant_id=merchant_id, query=query, trace_id=self.trace_id)

        intent = classify_with_backend(query, self.profile.intent_backend)
        ctx.intent = intent.to_dict()
        self._emit("intent", ctx.intent)

        # Durable facts/preferences stated by the merchant must be captured even
        # when the utterance itself is too thin to pass the confidence gate below.
        if extract_memory and intent.intent != INTENT_GREETING:
            from app.memory.governance import MemoryGovernanceService

            extracted = MemoryGovernanceService(self.db).extract_from_text(merchant_id, query)
            ctx.extracted_memory_count = len(extracted)
            self._emit("memory_extract", {"extracted": len(extracted)})

        pre = PreHook().check(ctx.intent)
        if pre is not None:
            ctx.needs_clarification = True
            ctx.clarification_question = pre["question"]
            self._emit("pre_hook", {"reason": "intent_confidence_low"})
            return ctx

        if intent.intent == INTENT_GREETING:
            return ctx

        # "ROI 是多少 / 点击率怎么样" -> fetch current numbers only, no
        # memory/knowledge grounding and no attribution diagnosis.
        if is_metric_lookup(query, intent.signals):
            self._run_metric_lookup(ctx)
            return ctx

        ctx.memories = MemoryRetrievalService(self.db).recall(
            merchant_id,
            query,
            top_k=self.profile.memory_top_k or 5,
            weight_overrides=self.profile.memory_weights,
        )
        self._emit("memory_recall", {"items": len(ctx.memories)})

        ctx.plan = build_plan(intent, merchant_id, query)
        self._emit("plan", {"steps": len(ctx.plan)})

        self._execute_steps(ctx, merchant_id, query, ctx.plan)

        if intent.intent == INTENT_KNOWLEDGE:
            return ctx

        ctx.diagnosis = self._grounded_diagnosis(ctx)
        primary = ctx.diagnosis.get("primary_cause") or {}
        self._emit(
            "diagnosis",
            {
                "quality_score": ctx.diagnosis["quality_score"],
                "primary_cause": primary.get("code"),
            },
        )

        post = PostHook().evaluate(
            ctx.diagnosis,
            attempt=0,
            supplemental_done=False,
            threshold=self.profile.quality_retry_threshold,
        )
        ctx.quality_decision = post["decision"]
        if post["decision"] == "retry":
            ctx.quality_retried = True
            supplemental = self._supplemental_plan(ctx)
            self._emit("quality_retry", {"steps": len(supplemental)})
            self._execute_steps(ctx, merchant_id, query, supplemental)
            ctx.diagnosis = self._grounded_diagnosis(ctx)
            final = PostHook().evaluate(
                ctx.diagnosis,
                attempt=1,
                supplemental_done=True,
                threshold=self.profile.quality_retry_threshold,
            )
            ctx.quality_decision = final["decision"]
            if final["decision"] == "clarify":
                ctx.needs_clarification = True
                ctx.clarification_question = final["question"]
        elif post["decision"] == "clarify":
            ctx.needs_clarification = True
            ctx.clarification_question = post["question"]

        if ToolHook().critical_failures(ctx.observations):
            ctx.needs_clarification = True
            ctx.clarification_question = "核心经营数据暂时取不到，无法完成诊断，请稍后再试。"
            self._emit("clarification", {"reason": "critical_tool_failure"})

        return ctx

    def _grounded_diagnosis(self, ctx: RunContext) -> Dict[str, Any]:
        """Run diagnose, then fetch verified knowledge entries for every slug
        the causes reference but semantic recall missed, and re-derive."""
        report = diagnose(ctx)
        wanted = set(referenced_slugs(report))
        have = {item["slug"] for item in ctx.knowledge}
        missing = wanted - have
        if missing:
            grounded = KnowledgeService(self.db).get_by_slugs(list(missing))
            ctx.knowledge.extend(grounded)
            report = diagnose(ctx)
        return report

    def _run_metric_lookup(self, ctx: RunContext) -> None:
        """Read-only current-value lookup: shop profile + latest day + 7-day."""
        merchant_id = ctx.merchant_id
        steps = [
            {
                "kind": "tool",
                "tool": "get_shop_profile",
                "arguments": {"merchant_id": merchant_id},
                "reason": "确认商家与当前模拟日期",
            },
            {
                "kind": "tool",
                "tool": "get_ad_performance",
                "arguments": {"merchant_id": merchant_id, "days": 1},
                "reason": "取最新当天指标与日环比",
            },
            {
                "kind": "tool",
                "tool": "get_ad_performance",
                "arguments": {"merchant_id": merchant_id, "days": 7},
                "reason": "取近 7 天整体指标",
            },
        ]
        self._execute_steps(ctx, merchant_id, ctx.query, steps)
        ctx.metric_lookup = {
            "latest": self._find_tool_data(ctx, "get_ad_performance", 1),
            "week7": self._find_tool_data(ctx, "get_ad_performance", 7),
        }

    @staticmethod
    def _find_tool_data(
        ctx: RunContext, tool: str, days: int
    ) -> Optional[Dict[str, Any]]:
        for observation in ctx.observations:
            if observation.get("tool") != tool or not observation.get("success"):
                continue
            window = (observation.get("data", {}).get("window", {}) or {}).get("days")
            if window == days:
                return observation.get("data")
        return None

    def _execute_steps(
        self, ctx: RunContext, merchant_id: str, query: str, steps: List[Dict[str, Any]]
    ) -> None:
        knowledge_service = KnowledgeService(self.db)
        for step in steps:
            if step["kind"] == "knowledge":
                items = knowledge_service.retrieve(
                    query=query,
                    industry=self._merchant_industry(ctx, knowledge_service, merchant_id),
                    top_k=self.profile.knowledge_top_k or 8,
                )
                known_ids = {item["knowledge_id"] for item in ctx.knowledge}
                items = [item for item in items if item["knowledge_id"] not in known_ids]
                ctx.knowledge.extend(items)
                ctx.observations.append(
                    {
                        "step": "knowledge",
                        "tool": None,
                        "success": True,
                        "summary": f"命中知识{len(items)}条",
                        "data": items,
                    }
                )
                self._emit("knowledge", {"items": len(items)})
                continue

            tool_name = step["tool"]
            started = perf_counter()
            try:
                result = self.tools.invoke(tool_name, step["arguments"])
                data = result["data"]
                ctx.observations.append(
                    {
                        "step": tool_name,
                        "tool": tool_name,
                        "success": True,
                        "summary": _summarize(tool_name, data),
                        "data": data,
                    }
                )
                self._emit(
                    "tool_call",
                    {"tool": tool_name, "success": True, "latency_ms": round((perf_counter() - started) * 1000, 2)},
                )
            except ToolError as exc:
                ctx.observations.append(
                    {
                        "step": tool_name,
                        "tool": tool_name,
                        "success": False,
                        "summary": f"工具失败：{exc}",
                        "error": exc.code,
                    }
                )
                self._emit(
                    "tool_call",
                    {
                        "tool": tool_name,
                        "success": False,
                        "error": exc.code,
                        "latency_ms": round((perf_counter() - started) * 1000, 2),
                    },
                )

    def _supplemental_plan(self, ctx: RunContext) -> List[Dict[str, Any]]:
        steps: List[Dict[str, Any]] = []
        merchant_id = ctx.merchant_id
        observed = {o.get("tool") for o in ctx.observations if o.get("success")}
        failed = {o.get("tool") for o in ctx.observations if not o.get("success")}

        if "get_ad_performance" in failed or not any(
            o.get("tool") == "get_ad_performance"
            and (o.get("data", {}).get("window", {}) or {}).get("days") == 30
            for o in ctx.observations
        ):
            steps.append(
                {
                    "kind": "tool",
                    "tool": "get_ad_performance",
                    "arguments": {"merchant_id": merchant_id, "days": 30},
                    "reason": "质检重试：补充 30 天长窗口趋势",
                }
            )
        if "get_product_performance" not in observed:
            steps.append(
                {
                    "kind": "tool",
                    "tool": "get_product_performance",
                    "arguments": {"merchant_id": merchant_id, "days": 14},
                    "reason": "质检重试：补充商品侧证据",
                }
            )
        if "get_recent_business_events" not in observed or not any(
            o.get("tool") == "get_recent_business_events"
            and o.get("data", {}).get("days") == 60
            for o in ctx.observations
        ):
            steps.append(
                {
                    "kind": "tool",
                    "tool": "get_recent_business_events",
                    "arguments": {"merchant_id": merchant_id, "days": 60},
                    "reason": "质检重试：拉长事件观察窗口",
                }
            )
        steps.append({"kind": "knowledge", "reason": "质检重试：补充知识证据"})
        return steps

    def _merchant_industry(self, ctx: RunContext, service: KnowledgeService, merchant_id: str) -> Optional[str]:
        for observation in ctx.observations:
            if observation.get("tool") == "get_shop_profile":
                return observation["data"].get("industry")
        from app.models.merchant import Merchant

        merchant = self.db.get(Merchant, merchant_id)
        return merchant.industry if merchant else None
