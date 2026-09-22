# MerchantMind — AI 商家经营诊断 Agent

> 面向电商商家的 AI 经营诊断 Agent。通过 **Synthetic Merchant World** 模拟真实商家经营环境，
> 结合 **Business Data、Merchant Memory、Industry Knowledge 与 Tool Calling**，
> 实现从问题理解、Context Planning、经营诊断到 Action 执行与结果反馈的 Agent 闭环，
> 并通过 **Trace、Evaluation、Badcase、Experiment** 持续优化 Agent 效果。

**项目阶段：Phase 1–20 已全部完成（全量 125 个 pytest 通过 · E2E 冒烟 11/11 · Docker 一键起栈 · 真实预训练深度模型 BGE 可插拔 · 指标直查 vs 归因诊断 · 可选真实生成式大模型）**

MerchantMind 不是 Chatbot，也不是 RAG Demo，而是一个 **Business Diagnosis Agent**：

```
Observe → Think → Act → Observe Again
```

---

## 目录

1. [项目背景](#1-项目背景) 2. [业务问题](#2-业务问题) 3. [为什么做 Merchant Diagnosis](#3-为什么做-merchant-diagnosis)
4. [为什么需要 Agent](#4-为什么需要-agent) 5. [为什么普通 RAG 不够](#5-为什么普通-rag-不够) 6. [Memory 与 RAG 的区别](#6-memory-与-rag-的区别)
7. [Event / Fact / Profile / Derived Insight](#7-event--fact--profile--derived-insight) 8. [Memory 如何自动生成](#8-memory-如何自动生成) 9. [Memory 如何避免污染](#9-memory-如何避免污染)
10. [Memory Conflict](#10-memory-conflict) 11. [Industry Knowledge](#11-industry-knowledge) 12. [Knowledge Candidate](#12-knowledge-candidate)
13. [Synthetic Merchant World](#13-synthetic-merchant-world) 14. [Decision Planner](#14-decision-planner) 15. [Tool Calling](#15-tool-calling)
16. [Hook](#16-hook) 17. [Uncertainty](#17-uncertainty) 18. [Action](#18-action) 19. [Agent Loop](#19-agent-loop)
20. [Trace](#20-trace) 21. [Evaluation](#21-evaluation) 22. [Badcase](#22-badcase) 23. [Experiment](#23-experiment)
24. [Monitoring](#24-monitoring) 25. [Business KPI](#25-business-kpi) 26. [技术架构](#26-技术架构) 27. [项目结构](#27-项目结构)
28. [本地启动（无 Docker）](#28-本地启动无-docker) 29. [Docker 启动](#29-docker-启动) 30. [本地预览与功能一览（Local Preview）](#30-本地预览与功能一览local-preview)
31. [当前局限](#31-当前局限) 32. [未来真实业务落地方案](#32-未来真实业务落地方案)

---

## 1. 项目背景

中小电商商家每天面对 GMV、ROI、CTR、CPM、CVR、素材、库存、季节性等大量信号，
"为什么 ROI 下降"这类问题需要跨广告、商品、素材、历史经营动作做多维归因。
人工分析门槛高、周期长；通用 Chatbot 缺少商家上下文，无法给出可追溯、可执行的诊断。

## 2. 业务问题

- 经营异常（ROI/CTR/CVR 下滑）的**归因链路长**，涉及多个数据源。
- 商家的**历史动作与偏好**散落在对话和事件里，无法被重复利用。
- 行业经验（如"女装素材 7 天后疲劳概率上升"）难以结构化地参与每次诊断。
- 诊断停留在"给建议"，缺少 **Action 执行 → 结果观测 → 再诊断** 的闭环与效果评估。

## 3. 为什么做 Merchant Diagnosis

经营诊断是一个**高频、高价值、上下文密集、需要工具取数**的决策场景：
它同时考验 LLM 的意图理解、结构化取数、证据归因、不确定性表达和行动编排，
比问答/文案类场景更能体现 Agent 的产品差异化。

## 4. 为什么需要 Agent

Agent ≠ Chatbot。MerchantMind 需要自主完成：

```
用户问题 → Intent → Decision Planner → Context Planning
        → Memory Retrieval + Knowledge RAG + Tool Calling
        → Evidence Aggregation → Diagnosis(Confidence)
        → Post-Hook 质检 → 回答 → Action 推荐/执行 → 再观测
```

这个过程包含**多步规划、多源取数、状态更新、工具调用与闭环反馈**，单次 LLM 调用无法完成。

## 5. 为什么普通 RAG 不够

普通 RAG 只回答"检索到的知识里怎么说"，但经营诊断还需要：

- **实时 Business Data**（必须通过 Tool 从数据库取，不能靠检索）；
- **商家个体 Memory**（与行业知识严格分离，带生命周期与冲突治理）；
- **Decision Planner**（决定取哪些数、调哪些工具、是否追问）；
- **Hooks / 风险控制 / 不确定性 / Action 闭环 / Evaluation**。

## 6. Memory 与 RAG 的区别

| 维度 | Merchant Memory | Industry Knowledge (RAG) |
|---|---|---|
| 回答的问题 | **这个**商家过去/现在是什么样 | **这个行业**通常是什么样 |
| 数据来源 | 对话抽取 + 事件 + 推导洞察 | 规则库 + 跨商家模式 + 人工审核 |
| 生命周期 | Candidate → Active → Superseded/Expired… | 版本化 v1/v2/v3，Candidate 需 Verified |
| 注入方式 | 规划后按权重召回，不全量注入 | Query Rewrite + 向量检索 + Rerank |

## 7. Event / Fact / Profile / Derived Insight

- **Event**：发生过什么（"8/20 把 Campaign A 预算 1000→2000"）。
- **Fact**：已确认的业务事实（"主营春季女装"）。
- **Profile**：长期稳定的特征/偏好/策略（"先小预算测试再放量"）。
- **Derived Insight**：基于 Data+Memory+Knowledge 的推导判断，**不能直接当 Fact**。

## 8. Memory 如何自动生成

`Conversation → 候选抽取 → 类型分类 → 重要性评估 → 置信度评估 → 去重 → 冲突检测 → 时效校验 → Governance → Write/Reject`（Phase 6 实现）。
不是每句话都写 Memory，只有长期有效、有业务价值、证据充分的信息才入库。

## 9. Memory 如何避免污染

- Candidate 先入候选表，经 Governance（长期性 / 重要性 / 证据数 / confidence）决定是否转正。
- 去重：相似 Memory 累加 `evidence_count`、更新 `last_seen_at` 与 confidence，而非新建。
- 召回加权：`0.35 语义 + 0.25 时近性 + 0.20 重要性 + 0.20 业务相关性`（Settings 可调），不全量注入。

## 10. Memory Conflict

新旧 Memory 冲突时**不覆盖**：记录 Old/New、冲突原因、时间戳、证据，
状态依据时间、证据数、confidence 在 `Candidate/Active/Superseded` 间流转（Phase 6）。

## 11. Industry Knowledge

类型：Business Rule / Diagnostic Rule / Industry Insight / Best Practice / Metric Definition / Case。
覆盖女装、美妆、食品、家居、3C；规划 50+ 条，包含条件、规则、推荐动作、证据、版本（Phase 8）。

## 12. Knowledge Candidate

多个商家出现相似问题 → Pattern Detection → Knowledge Candidate（Pending）。
单商家经验**不能**直接成为行业知识；只有人工/规则 **Verified** 后才转正并生成新版本。

## 13. Synthetic Merchant World

**禁止使用真实用户数据、禁止伪造真实线上指标。**
合成世界遵循 `业务规则 + 时间变化 + 事件驱动 + 少量随机噪声`，
而非 `random.uniform()`。例如：新素材 → 持续投放 → 素材疲劳 → CTR↓ → 提预算 → CPM↑ → ROI↓。
所有 Synthetic 数据**真实入库**，前端不允许 Mock。

## 14. Decision Planner

Planner 判断：是否需要 Business Data / Memory / Knowledge、需要哪些 Tool（可能多个）、是否追问、是否需要 Action。
例如"为什么最近 ROI 一直下降？"→ `performance_diagnosis` + 广告/素材/事件工具，无需 Action。

## 15. Tool Calling

Agent 不直接访问数据库：`Agent → Tool API → Service → Database`。
工具具备 `name / description / input_schema / output_schema / permission / risk_level`，
首批工具：`get_shop_profile`、`get_ad_performance`、`get_product_performance`、
`get_material_performance`、`get_historical_cases`、`get_recent_business_events`。所有调用进 Trace。

## 16. Hook

- **Pre-Hook**：校验 merchant_id / query / intent / 所需上下文。
- **Tool-Hook**：工具存在性、参数与日期合法性、商家归属。
- **Risk-Hook**：Read / Low / Medium / High Risk，高危 Action 必须人工确认。
- **Post-Hook**：事实/数字一致性、数据来源、业务规则、幻觉风险、完整性；
  `quality_score < 0.7` 允许 Retry Retrieval+Generation，最多 1 次。

## 17. Uncertainty

输出 Primary + Alternative Diagnosis 及各自 Confidence；`Confidence < 0.5` 时主动追问或声明证据不足，
禁止把所有结论说得同样确定。

## 18. Action

Agent 不只给建议，还支持分级 Action（Read Only / Low / Medium / High Risk）。
High Risk 必须 `Agent → Human Confirmation → Action`。Synthetic 环境只执行模拟动作，**不接真实广告账户**。

## 19. Agent Loop

`Action → Merchant Simulator → Business Data Change → Agent Observe → Evaluate Result`，
形成 Observe → Think → Act → Observe Again 的闭环。

## 20. Trace

Trace 记录 intent、planner、memory/knowledge 召回、tool calls/results、hooks、decision、
final answer、latency、token、retry 等；前端只展示 **Analysis Summary**，不展示完整 Chain of Thought。
可接 Langfuse，无 Langfuse 时落 PostgreSQL 本地 Trace（Phase 14）。

## 21. Evaluation

50–100 条带 Ground Truth（root_cause / expected_tools / expected_memory / expected_knowledge）的 Case。
指标：Memory/Knowledge Recall@K、Task Success、Tool Calling Accuracy/Success、
Correctness/Relevance/Completeness/Evidence/Actionability、Hallucination、P50/P95、Token、Retry Rate。
Rule Based + LLM-as-a-Judge（1–5 分）+ Human Spot Check（Phase 15）。

## 22. Badcase

失败自动建 Badcase（error_type / root_cause / affected_module / suggested_fix / status），
区分 Routing / Retrieval / Tool / Reasoning / Hallucination 错误，由不同模块分别修复（Phase 16）。

## 23. Experiment

支持 Model、Temperature、Memory/Knowledge Top-K、Prompt Version、Retry Threshold、
Ranking 权重等变量的 A/B，对比 Task Success、Quality、Hallucination、Latency、Token Cost（Phase 17）。
Prompt 与 Knowledge 均做版本化。

## 24. Monitoring

线上监控：Requests、Success、Tool Failure、Memory Write/Conflict、Retrieval Miss、
Hallucination、Latency、Token、Retry、Helpful Rate。Synthetic 环境明确标注 **Demo/Simulation Metrics**（Phase 18）。

## 25. Business KPI

三层指标：AI 能力（Recall/Tool Accuracy/Answer Quality）、Agent 使用（Success/Acceptance/Helpful/Follow-up）、
Business Outcome（ROI Improvement、CTR Improvement、低效素材减少、解决时长、执行率）——
最后一层在 Synthetic 环境中标注 **Synthetic Business Metrics**。

## 26. 技术架构

```
┌───────────────┐   /api/* rewrite    ┌─────────────────────────────────────────┐
│ Next.js 14    │ ───────────────────▶ │ FastAPI (Python)                        │
│ TS + Tailwind │                      │  api / agent / memory / knowledge /     │
│ React Query   │ ◀─────────────────── │  tools / hooks / actions / evaluation   │
│ Recharts      │        JSON          │  simulator / traces / monitoring        │
└───────────────┘                      └───────────────┬─────────────────────────┘
                                                       │ SQLAlchemy 2.0 / psycopg v3
                                              ┌────────▼─────────┐
                                              │ PostgreSQL 16    │
                                              │ + pgvector       │
                                              └──────────────────┘
LLM：OpenAI、DeepSeek、Qwen 或任意 OpenAI-compatible API（.env 配置，Key 仅存后端）
Embedding：本地确定性哈希(256) · 本地真实预训练 BGE-small-zh ONNX(512，随镜像) · OpenAI 兼容在线 API，三选一（见 §26.1）
Agent：自研 Orchestrator（不强依赖 LangChain/LangGraph）  Observability：Langfuse 或本地 Trace
```

### 26.1 深度模型与可插拔的语义层

本项目的"理解"与"检索"基于**真实的预训练深度模型**，而不是规则或哈希假向量；同时 embedding 与向量匹配方法都可以通过环境变量选择。

**① 本地预训练深度模型（离线、免联网、免 Key）**

- 模型为 BAAI/bge-small-zh-v1.5 的 int8 量化 ONNX：真实预训练的中文 BERT（4 层 Transformer、hidden 512、8 头注意力、词表 21128），单文件约 24MB，由 onnxruntime(CPU) 推理，已随 `COPY app` 打入后端镜像。
- 配套自实现的标准 BERT 中文 WordPiece 分词器（CJK 拆字、去 accent、标点拆分、longest-match `##` 子词）；模型输出经 masked mean pooling + L2 归一化得到 512 维语义向量。
- 语义实测：零字面重合的"投广告亏钱"与"投产比下滑"余弦 **0.512**，二者与无关句仅 0.311（宿主与容器内结果一致）。

**② 意图分类：迁移学习（冻结 BGE + 可训练 MLP 头）**

- 冻结上述 BGE 编码器，只训练一个 `512→128(ReLU+Dropout 0.2)→5 类 softmax` 的 MLP 分类头（numpy 手写反向传播、He 初始化、类别均衡权重、L2）。
- 在 33 条纯手写 hold-out 上准确率 **93.94%（31/33）**，同一测试集规则基线仅 **66.67%**；产物 `intent_dnn_weights.npz`，缺失时自动回退规则。
- `classify_with_backend` 支持 `rule | ml | dnn | hybrid`，由环境变量 `INTENT_CLASSIFIER_BACKEND` 切换，**默认 `rule`** 以保证 54 case 评测可复现。（`ml` 为原有的 TF-IDF + softmax 基线；`dnn` 为深度迁移模型。）

**③ Embedding provider 可插拔**

`get_embedder(provider)` 三选一：

- `local`（默认）：确定性哈希 256 维，零依赖、零回归；Merchant Memory 向量固定使用它；
- `bge`：上述本地真实预训练深度模型，512 维；
- `openai`：任意 OpenAI 兼容 `/embeddings`（默认 text-embedding-3-small，支持 `dimensions=512`），需配置 base_url/api_key。

**④ 向量匹配 / 检索策略可插拔**

知识库表在原 256 维列之外新增可空的 512 维 `embedding_deep` 列（HNSW cosine 索引）。`retrieve()` 按策略分发（环境变量 `KNOWLEDGE_RETRIEVAL_STRATEGY`）：

- `vector`（默认）：pgvector 余弦——存在 deep 向量时走 512 维列，否则回退 256 维本地列；
- `bm25`：纯词法检索，`k1=1.5、b=0.75`，idf 采用 BM25+ 形式，分词为拉丁词 + CJK bigram；
- `hybrid`：vector 与 bm25 通过 RRF（`k=60`）融合。

三种策略之后统一再做五因子精排（`0.55 semantic + 0.15 industry + 0.15 keyword + 0.10 type + 0.05 freshness`）；`score_breakdown.strategy` 标注本次实际使用的策略。

**⑤ 指标直查 vs 归因诊断（问"是多少"不再答非所问）**

- Agent 区分「取当前数值」与「分析下滑原因」：当问句是「现在 ROI 是多少 / 帮我查一下点击率 / 今天花了多少」这类**明确取数句式**时，只调用只读指标工具取最新当天与近 7 天数值并直接回答数字，不做记忆/知识 grounding 与归因；「为什么下滑 / 怎么提升 / 一般多少（问行业基准）/ X 怎么样（求分析）」仍走原诊断或咨询流程（保留记忆召回）。
- ROI 全系统统一为**毛利口径**：`ROI = GMV × 毛利率 ÷ 广告花费`，毛利率按行业（女装/家居 0.30、美妆 0.45、食品 0.25、3C 0.18），**ROI < 1 即投放亏损**；该口径在合成生成、Simulator、数据库物理列与工具重算之间完全一致（修复了此前工具重算漏乘毛利率、导致顾问答案与商家中心对不上的问题）。

**⑥ 生成式大模型（可选，让 Agent 真正"会回答"）**

- Agent 仍由确定性流程负责**取真实数据**（工具 / 记忆 / 知识），收集到的全部证据会打包成证据简报，交给 **OpenAI 兼容的真实生成式 LLM**（默认示例 DeepSeek，也支持 Qwen 兼容模式、火山方舟豆包、OpenAI、vLLM 等）针对问题**动态组织自然语言回答**——问趋势描述趋势、问数值报数值、问原因才归因，不再由固定模板答非所问。
- 开关与配置：`LLM_PROVIDER`（`local` 关闭 / 如 `deepseek` 开启）、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`；密钥只放在被 gitignore 的 `.env` 中。
- **优雅降级**：未配置密钥或调用失败时自动回退到原确定性模板，API 与评测零影响；默认 `LLM_PROVIDER=local`。

**⑦ 相关环境变量**

- `INTENT_CLASSIFIER_BACKEND=rule|ml|dnn|hybrid`
- `KNOWLEDGE_EMBEDDING_PROVIDER=local|bge|openai`
- `KNOWLEDGE_RETRIEVAL_STRATEGY=vector|bm25|hybrid`
- 生成式 LLM：`LLM_PROVIDER|LLM_BASE_URL|LLM_MODEL|LLM_API_KEY`；在线 embedding 另需 `OPENAI_EMBEDDING_MODEL`。

**边界**：预训练编码器与生成式 LLM 均为真实模型，但未引入 torch/transformers 等重依赖（BGE 仅 ONNX 运行时，LLM 走 OpenAI 兼容 HTTP）；工具选择与证据归因仍为确定性规划，确保数字真实可追溯；默认 provider=local + rule 保证现网与评测零回归。

### 26.2 运行时：一次请求的完整生命周期（Trace 逐步拆解）

Trace 页里看到的 `intent / memory / planner / tool_call / knowledge / diagnosis` **不是各自独立的 HTTP 接口，而是一次 `POST /api/agent/run` 请求内部顺序执行的 span**。一次典型的「性能诊断」会经过三大段共 11 步：

```text
【听懂问题】
 1 intent        意图识别 + 信号抽取（classify_with_backend）
 2 memory        记忆抽取：本句有没有值得长期记住的事实/偏好（有则先写入）
 3 memory        记忆召回：该商家历史记忆按多维打分取最相关几条
 4 planner       决策规划：按意图与信号动态生成"有序取证清单"
【全面取证】（按 plan 执行，结果统一进 ctx.observations）
 5 get_shop_profile            店铺画像：行业/阶段/当前日期（背景基线）
 6 get_ad_performance          近 7 天 ROI/CTR/CPM 及环比（定位异常）
 7 get_recent_business_events  近期调预算/上新/活动（解释拐点触发）
 8 get_material_performance    素材状态/疲劳度（判断是否素材问题）
 9 get_historical_cases        相似历史案例（类比佐证）
10 knowledge                   行业知识检索（规则与最佳实践）
【证据归因】
11 diagnosis      多候选根因各自按证据打分排序，输出主因（如 budget_cpm_spiral）
        ↓
   归因 + 全部证据打包交给生成式 LLM 组织成对题的自然语言回答（见 §26.1 ⑥）
```

取证清单**不是写死的**：Planner 依据信号动态增减（涉及素材/CTR 才查素材，涉及商品/CVR 才查商品）。同时 `run()` 中还有 3 条**提前返回分支**，保证不同问法走不同路径：

- 意图置信度过低 → PreHook 触发澄清，直接返回；
- 打招呼 → 直接返回；
- 命中「指标直查」（如"ROI 是多少"）→ 只取店铺画像 + 当天(days=1) + 近 7 天(days=7)，直接报数字，**不做记忆/知识 grounding 与归因**（见 §26.1 ⑤）。

归因后 PostHook 还会做质量质检：`quality_score` 过低则**自动补查再判一次**（最多 1 次）；核心工具取不到数据则触发澄清。这是 Agent 的自我纠错环节。

### 26.3 关键数据结构 IntentResult 与证据流向

所有意图后端（rule/ml/dnn/hybrid）输出统一为 `IntentResult`（`backend/app/agent/intent.py`）：

```python
@dataclass
class IntentResult:
    intent: str                              # 5 个意图标签之一
    confidence: float                        # 置信度 0~1
    signals: Dict[str, List[str]]            # metrics / domains 结构化信号

    def to_dict(self):                       # 落库/返回 JSON（置信度 round 4 位）
        return {"intent": self.intent,
                "confidence": round(self.confidence, 4),
                "signals": self.signals}
```

关键设计：**模型只负责判断意图类别，而"涉及哪个指标(roi/ctr…)、哪个业务域(素材/预算…)"由确定性规则抽取**（`extract_signals`），为后续工具编排提供可靠的细粒度参数。

Agent 取到的数据有 **4 个去向**：

| 数据 | 去向 | 作用 |
|---|---|---|
| 工具数据 | ① 归因引擎 `diagnose()` | 当证据，先算出**客观中立**的根因（不用 LLM，数字不被润色带偏） |
| 工具+记忆+知识+诊断 | ② 生成式 LLM | 打包成「证据简报」，让 LLM **严格基于证据**、针对真实问题作答（Grounding） |
| 记忆/知识/观察 | ③ HTTP 响应 → 前端 | 渲染「召回记忆 N 条 / 引用知识 N 条 / 调用工具 N 个」证据卡，可追溯 |
| 整套上下文 | ④ Trace 落库 | 事后可回看每一步输入输出与耗时，便于排查 Badcase |

### 26.4 模型分工：规则 / 本地小模型 / 云端 DeepSeek

系统里有三类"AI"，**本地小模型不是 DeepSeek**，分工明确：

| | 规则 | 本地小模型 **BGE** | 云端 **DeepSeek** |
|---|---|---|---|
| 本质 | 关键词 if 判断 | 开源预训练中文编码器（小版 BERT，约 24MB） | 生成式大模型（GPT 类） |
| 运行位置 | 本地进程 | **本地 / 容器内**，ONNX Runtime CPU 推理 | 远程服务器，HTTP 调用 |
| 成本 / 速度 | 免费 / 毫秒 | **免费 / 毫秒** | 按次收费 / 2–4 秒 |
| 职责 | 意图兜底、信号抽取 | 把句子变成向量 → 语义检索、意图 DNN 头 | **理解问题并生成最终自然语言回答** |

一句话：**BGE 管"听懂（语义）"，DeepSeek 管"表达（生成）"**。另有更轻的 `ml`（TF-IDF + softmax 逻辑回归）作为意图基线之一。

**数据库**：PostgreSQL 16 + pgvector。本地开发默认 `localhost:5432`；Docker 栈映射在宿主 `localhost:5433`；账户/库名均为 `merchantmind / merchantmind`，向量与业务数据同库存储。

### 26.5 设计取舍：为什么意图识别不直接交给生成式大模型

让 LLM 做意图识别通常也准，但这是**有意的工程取舍**（类似"让专家医生站门口做分诊"不划算）：

1. **慢**：意图是第一步，LLM 一次 2–4 秒，规则/小模型只要 1–2 毫秒；
2. **贵**：意图与生成各调一次，成本翻倍，而意图本地可零成本完成；
3. **不稳、难复现**：LLM 有随机性，意图一旦飘移，后续整条分支都乱；本地结果固定才能支撑 125 个稳定测试；
4. **依赖网络/Key**：断网或欠费时若连"听懂"都做不到，系统直接瘫痪；本地意图保证任何时候可用；
5. **需要可靠结构化参数**：下游要的是确定的"指标 + 业务域"字段，规则抽取可校验，LLM 自然语言还需再解析。

> 注意：意图 DNN 后端用的 BGE 本身也是预训练语言模型，只是"编码器"而非"生成式"模型。Function Calling 让 LLM "懂意图+选工具+填参数"一步完成是另一主流架构，更灵活但同样有上述代价；实践中常**混用**——简单高频走本地，拿不准的疑难句再升级给 LLM。

### 26.6 记忆召回 vs 知识库召回：机制并不相同

两者都叫"召回"，语义部分底层都用**余弦相似度 + HNSW 索引**，但向量、打分与可选项不同：

| 对比 | 记忆召回 | 知识库召回 |
|---|---|---|
| 向量 | **固定本地哈希 256 维** | BGE 512 维 或 本地 256 维（看 provider） |
| 打分 | **4 因素加权**：`0.35 语义 + 0.25 时效 + 0.20 重要性 + 0.20 词面` | 策略分发：`vector（纯余弦）/ bm25（纯词法）/ hybrid（RRF 融合）`，之后统一五因子精排 |
| 语义占比 | 仅 35% | vector 模式下 100% |
| 候选范围 | 该商家 + active | 全平台 + verified |
| 可切换 | 否（写死） | 是（环境变量切换） |

## 27. 项目结构

```text
merchantmind/
├── frontend/          # Next.js 14 + TS + Tailwind + React Query + Recharts
├── backend/app/
│   ├── api/           # 路由（Phase 1: /api/health）
│   ├── agent/         # orchestrator / planner / intent / reasoning / context
│   ├── memory/        # extractor / retriever / governance / conflict / ranking
│   ├── knowledge/     # retriever / candidate / versioning
│   ├── rag/  tools/  hooks/  actions/  evaluation/
│   ├── experiments/  simulator/  traces/  monitoring/
│   ├── models/  services/  config/  db/  schemas/
│   └── main.py
├── data/              # synthetic / conversations / knowledge / evaluation
├── scripts/  tests/  docs/
├── docker-compose.yml # db(pgvector/pgvector:pg16) + backend + frontend
├── .env.example
└── README.md
```

## 28. 本地启动（无 Docker）

要求：Python 3.9+、Node 18.18+（推荐 22）、PostgreSQL 16 + pgvector。

```bash
# 0. 环境变量
cp .env.example .env          # 默认指向 postgresql+psycopg://...@localhost:5432/merchantmind

# 1. 数据库（任选）
#    a) 已有 PostgreSQL：CREATE DATABASE merchantmind; CREATE EXTENSION vector;
#    b) Docker：docker compose up -d db

# 2. 后端
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head         # 建表（完整业务表结构，首个迁移内含 CREATE EXTENSION vector）
uvicorn app.main:app --reload --port 8000
# 后端启动时会自动 CREATE EXTENSION IF NOT EXISTS vector

# 2b. 种子数据（幂等；已存在数据时自动跳过，--force 强制重灌）
PYTHONPATH=. python scripts/seed_database.py --full --knowledge   # 完整合成世界 + 58 条行业知识

# 2c. 离线评测 / 端到端冒烟
PYTHONPATH=. python scripts/run_eval_once.py rule                 # 54 个 Ground Truth case
PYTHONPATH=. python scripts/e2e_smoke.py http://localhost:8000    # Observe→Think→Act 全链路 11 项断言

# 3. 前端
cd ../frontend
npm install
npm run dev                  # http://localhost:3000 （/api/* 自动代理到 8000）

# 4. 测试（DB 不可达时数据库相关用例自动 skip；MM_REQUIRE_DB=1 强制要求真实 PG）
cd ../backend && pytest
MM_REQUIRE_DB=1 pytest       # CI/本地有 PG 时使用，测试在独立的 *_test 库中运行并自动清理
```

常用迁移命令：`alembic current`、`alembic history`、`alembic downgrade base`（回滚全部）、
模型变更后 `alembic revision --autogenerate -m "..."`（需人工复核生成结果）。

健康检查：<http://localhost:8000/api/health>，返回示例：

```json
{
  "status": "ok",
  "service": "MerchantMind",
  "version": "0.1.0",
  "environment": "local",
  "database": { "status": "up", "pgvector": "installed", "message": "vector extension installed (0.8.0)" }
}
```

数据库不可用时 API 仍可服务，`status` 变为 `degraded` 且 `database.status=down`，不返回 5xx。

## 29. Docker 启动

```bash
cp .env.example .env
docker compose up --build
```

- db：[`pgvector/pgvector:pg16`](https://hub.docker.com/r/pgvector/pgvector)，带 `pg_isready` 健康检查，数据卷 `pgdata`
- backend：Python 3.12-slim（无 apt 依赖，psycopg 使用 binary wheel；onnxruntime 经 pip 安装，24MB BGE ONNX 模型随镜像），等待 db healthy 后启动；启动命令依次执行 `alembic upgrade head`（空库自动重放完整迁移链）→ `python scripts/seed_database.py --full --knowledge`（幂等灌入合成世界 + 58 条知识）→ uvicorn；带 `/api/health` HEALTHCHECK
- frontend：Node 22-alpine 多阶段构建（standalone），容器内把 `/api/*` 代理到 backend

重新灌种子（可选）：

```bash
docker compose exec backend PYTHONPATH=/app python scripts/seed_database.py --full --knowledge --force
```

访问：前端 <http://localhost:3000> · API <http://localhost:8000/api/health>

> 没有 Docker Desktop 时可用 [Colima](https://github.com/abiosoft/colima)（macOS，免 sudo）：
> `colima start --runtime docker --vm-type vz --mount none` 后照常 `docker compose up --build`。
> 若宿主机 5432 已被占用，在本地 `.env` 设置 `POSTGRES_PORT=5433`（仅影响宿主机映射端口）。

## 30. 本地预览与功能一览（Local Preview）

> 本项目当前**未托管公网在线 Demo**。请先按 [§28 本地启动](#28-本地启动无-docker) 或 [§29 Docker 启动](#29-docker-启动) 在本机把服务跑起来，再于浏览器访问本地地址 `http://localhost:3000` 预览。下面的功能一览用于说明启动后可看到的内容，该地址仅在本机有效、并非公网网址。

启动后，左侧 15 个页面全部对接真实 FastAPI（React Query + Recharts，无 Mock）：

- **AI 经营顾问**：选"花间女装旗舰店（M001）"提问"为什么最近 ROI 一直下滑，帮我诊断"，可看到
  意图 → 记忆/知识召回 → 双假设归因（含证据与 quality_score）→ 动作建议 → 人类确认 → 执行后推进世界再观察的完整 Loop，
  回答可一键好评/差评（差评自动开 Badcase）。
- **商家中心**：GMV/广告花费、ROI/CTR 曲线与计划、素材状态。
- **Merchant Simulator**：注入预算调整、流量成本上涨、上新素材等事件并推进世界。
- **Memory / Knowledge**：候选晋升、冲突列表、语义召回、知识候选挖掘/验证。
- **Trace**：每次 Agent 运行的 span 时间线、失败工具、质量分与延迟。
- **Evaluation**：一键跑 54 case Rule/Heuristic 评测并对单 case 人工评分。
- **Badcase**：失败自动分诊（Routing/Retrieval/Tool/Reasoning/Hallucination）与状态流转。
- **Experiment**：5 默认变体 × 21 case 真实管线 A/B（含冷启动预热、自动排名与 delta）。
- **Monitoring**：在线监控（Demo/Simulation Metrics）+ AI 能力/Agent 使用 + Synthetic Business Metrics 三层指标。
- **Action Center / Settings**：工具目录、调用审计与环境、标注约定。

非交互验收：

```bash
python scripts/e2e_smoke.py http://localhost:8000     # 11/11 PASS（含诊断→执行→评测→反馈→监控）
```

## 31. 当前局限

- 20 个 Phase 已全部完成：基础设施、19+ 张业务表与可逆 Alembic 迁移链（单 head `2eed261ea26`）、
  合成世界、Simulator、对话、记忆治理/召回、知识 RAG（58 条）、工具、Planner/Orchestrator、
  Hooks/双假因/Action Loop、Trace、54 case 评测、Badcase/反馈、A/B 实验、三层监控、15 页前端、
  真实预训练 BGE 深度模型、可插拔语义层与指标直查（§26.1）、
  Docker 一键栈；全量 125 个 pytest 绿灯，容器内空库重放迁移链 + seed + E2E 11/11 已验证。
- 语义层已使用真实预训练深度模型（本地 BGE-small-zh ONNX，见 §26.1）：意图 dnn 后端为“冻结 BGE + MLP 头”的迁移学习，
  知识 embedding 与向量匹配方法均可插拔（local/bge/openai × vector/bm25/hybrid）；默认仍走 local 哈希 + 规则意图以保证评测可复现。
- 生成式 LLM 为可插拔可选项（§26.1 ⑥）：配置 OpenAI 兼容密钥（如 DeepSeek）后最终自然语言回答由真实 LLM 生成；
  未配置时动作解析、规划、证据归因为确定性规则，评测评委为 Rule/Heuristic 结构代理，
  实验中 model/temperature/prompt_version 为录制维度，Token 为与上下文规模挂钩的代理估算。
- Synthetic 数据均为模拟，不代表真实业务；Monitoring/KPI 已显式标注 Demo/Simulation/Synthetic Metrics。
- 不连接任何真实广告账户或真实商家数据。

## 32. 未来真实业务落地方案

- 数据：接入广告平台 Marketing API（投放/素材/报表）、商品/订单库、客服会话，经用户授权并最小化权限。
- 写操作（改预算/暂停计划）默认走 Human-in-the-loop，配套审批流、审计日志与回滚。
- Memory/Knowledge 接入真实数据后需加租户隔离、PII 脱敏、保留期与删除权（合规）。
- Embedding/LLM 支持私有化部署与 VPC 内 OpenAI-compatible 网关；评测从 Synthetic Ground Truth 过渡到线上灰度 + 人工评审。

---

## Phase 路线图

Phase 1 基础设施 → 2 Schema → 3 Synthetic World → 4 Simulator → 5 Conversation →
6 Memory 治理 → 7 Memory 召回 → 8 Knowledge/RAG → 9 Tools → 10 Planner/Orchestrator →
11 Hooks/Uncertainty → 12 Diagnosis/Evidence → 13 Action/Loop → 14 Trace →
15 Evaluation → 16 Badcase/Feedback → 17 Experiment → 18 Monitoring/KPI → 19 完整前端 → 20 集成验收。

**状态：Phase 1–20 全部完成 ✅**（125 个 pytest 全绿、前端 tsc/next build 通过、Docker 三容器空库迁移链 + seed 自举、E2E 11/11；真实预训练 BGE 深度模型可插拔，支持指标直查，可选真实生成式 LLM，§26.1）

**每个 Phase 完成后运行代码、测试、检查数据库/API/前端，修复后才进入下一 Phase。**
