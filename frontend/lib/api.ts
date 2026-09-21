async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    cache: 'no-store',
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') detail = body.detail;
      else if (body?.detail) detail = JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null as T;
  return res.json();
}

const json = (body: unknown) => ({ method: 'POST', body: JSON.stringify(body) });

export interface HealthResponse {
  status: 'ok' | 'degraded';
  service: string;
  version: string;
  environment: string;
  database: {
    status: 'up' | 'down';
    pgvector: string;
    message: string;
    server_version?: string | null;
  };
}

export interface MerchantSummary {
  merchant_id: string;
  merchant_name: string;
  industry: string;
  sub_industry?: string | null;
  business_stage: string;
  gmv_level?: string | null;
  city?: string | null;
  industries: { industry: string; sub_industry: string; is_primary: boolean }[];
  label: string;
}

export interface MerchantDetail extends MerchantSummary {
  performance: {
    date: string;
    gmv: number;
    ad_spend: number;
    impressions: number;
    clicks: number;
    ctr: number;
    cpm: number;
    conversions: number;
    cvr: number;
    roi: number;
  }[];
  campaigns: {
    campaign_id: string;
    campaign_name: string;
    objective: string;
    budget: number;
    status: string;
  }[];
  materials: {
    material_id: string;
    campaign_id: string;
    material_type: string;
    material_name: string;
    status: string;
  }[];
}

export interface SimulatorState {
  merchant_id: string;
  current_date?: string | null;
  last_7d: Record<string, number>;
  label: string;
}

export interface PerformanceRow {
  date: string;
  gmv: number;
  ad_spend: number;
  impressions: number;
  clicks: number;
  ctr: number;
  cpm: number;
  conversions: number;
  cvr: number;
  aov: number;
  roi: number;
}

export interface AdvanceResponse {
  merchant_id: string;
  from_date: string;
  to_date: string;
  days_added: number;
  performance: PerformanceRow[];
  events_emitted: Record<string, unknown>[];
  label: string;
}

export interface ConversationSummary {
  conversation_id: string;
  merchant_id: string;
  title?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  message_id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  meta?: Record<string, unknown> | null;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: Message[];
}

export interface MemoryItem {
  memory_id: string;
  merchant_id: string;
  type: string;
  content: string;
  importance: number;
  confidence: number;
  status: string;
  evidence_count: number;
  source: string;
  tags?: string[] | null;
  first_seen_at: string;
  updated_at: string;
}

export interface ScoredMemory extends MemoryItem {
  score: number;
  reasons?: string[] | null;
}

export interface MemoryConflict {
  id: number;
  memory_id: string;
  previous_memory_id: string;
  reason: string;
  resolution: string;
  created_at: string;
}

export interface KnowledgeItem {
  knowledge_id: string;
  slug: string;
  version: number;
  type: string;
  industry?: string | null;
  title: string;
  content: string;
  condition?: string | null;
  recommendation?: string | null;
  evidence?: string | null;
  status: string;
  source: string;
  merchant_count: number;
  quality_score: number;
  tags?: string[] | null;
  created_at: string;
  updated_at?: string;
}

export interface ScoredKnowledge extends KnowledgeItem {
  score: number;
  score_breakdown?: Record<string, number | string>;
}

export interface ToolSpec {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  permission: string;
  risk_level: string;
}

export interface ToolCallLog {
  id: number;
  tool_name: string;
  merchant_id?: string | null;
  trace_id?: string | null;
  arguments: Record<string, unknown>;
  result_summary?: string | null;
  latency_ms?: number | null;
  success: boolean;
  error?: string | null;
  created_at: string;
}

export interface AgentAction {
  title: string;
  risk_level: string;
  requires_confirmation: boolean;
  params: Record<string, unknown>;
}

export interface AgentRunResponse {
  conversation_id: string;
  reply: string;
  intent: { intent: string; confidence: number };
  plan?: Record<string, unknown> | null;
  observations: { tool?: string; stage?: string; summary?: string }[];
  memory: ScoredMemory[];
  knowledge: { knowledge_id: string; title: string; type: string; score: number }[];
  diagnosis: Record<string, unknown> | null;
  actions: AgentAction[];
  needs_clarification: boolean;
  clarification_question?: string | null;
  quality_retried: boolean;
  trace_id: string;
  label: string;
}

export interface TraceRun {
  trace_id: string;
  merchant_id?: string | null;
  conversation_id?: string | null;
  query: string;
  intent?: string | null;
  status: string;
  primary_cause?: string | null;
  quality_score?: number | null;
  needs_clarification: boolean;
  retry_count: number;
  tool_call_count: number;
  latency_ms?: number | null;
  created_at: string;
}

export interface TraceStage {
  span_type: string;
  name: string;
  status: string;
  latency_ms?: number | null;
}

export interface TraceSummary {
  trace_id: string;
  merchant_id?: string | null;
  query: string;
  intent?: string | null;
  status: string;
  decision: string;
  primary_cause?: string | null;
  confidence?: number | null;
  quality_score?: number | null;
  needs_clarification: boolean;
  retry_count: number;
  tool_call_count: number;
  failed_tools: string[];
  latency_ms?: number | null;
  created_at: string;
  analysis_summary: string;
  stages: TraceStage[];
  label: string;
}

export interface EvalRunSummary {
  eval_run_id: number;
  judge: string;
  total?: number;
  passed?: number;
  task_success_rate?: number;
  created_at: string;
  label: string;
}

export interface EvalCaseResult {
  case_result_id?: number;
  case_id: string;
  case_type: string;
  merchant_id: string;
  message: string;
  passed: boolean;
  metrics: Record<string, number | boolean | null>;
  prediction?: Record<string, unknown> | null;
  trace_id?: string | null;
  judge_score?: number | null;
  judged_by?: string | null;
  human_rating?: number | null;
  human_feedback?: string | null;
}

export interface EvalRunDetail {
  eval_run_id: number;
  judge: string;
  note?: string | null;
  created_at: string;
  metrics: {
    total: number;
    passed: number;
    task_success_rate: number;
    tool_accuracy?: number | null;
    cause_recall_at_3?: number | null;
    knowledge_recall_at_5?: number | null;
    hallucination_rate: number;
    retry_rate: number;
    latency_p50_ms?: number | null;
    latency_p95_ms?: number | null;
    latency_avg_ms?: number | null;
    token_proxy_total: number;
    by_type: Record<string, { total: number; passed: number; success_rate: number }>;
    human_rated: number;
    human_agreement_rate?: number | null;
  };
  cases: EvalCaseResult[];
  label: string;
}

export interface FeedbackItem {
  id: number;
  trace_id?: string | null;
  merchant_id?: string | null;
  conversation_id?: string | null;
  rating: number;
  helpful: boolean;
  comment?: string | null;
  created_at: string;
  label: string;
}

export interface Badcase {
  id: number;
  source: string;
  trace_id?: string | null;
  feedback_id?: number | null;
  eval_run_id?: number | null;
  case_id?: string | null;
  merchant_id?: string | null;
  title: string;
  error_type: string;
  affected_module: string;
  root_cause?: string | null;
  suggested_fix?: string | null;
  evidence?: Record<string, unknown> | null;
  status: string;
  severity: string;
  reporter?: string | null;
  occurrence_count: number;
  created_at: string;
  updated_at: string;
  resolved_at?: string | null;
  label: string;
}

export interface ExperimentListItem {
  id: number;
  name: string;
  status: string;
  case_count: number;
  variant_count: number;
  winner?: string | null;
  created_at: string;
  label: string;
}

export interface VariantRun {
  id: number;
  variant_name: string;
  config: Record<string, unknown>;
  total: number;
  passed: number;
  metrics: Record<string, number | null>;
  cases: Record<string, unknown>[];
}

export interface VariantSummary {
  variant_name: string;
  total: number;
  passed: number;
  task_success_rate: number;
  tool_accuracy?: number | null;
  hallucination_rate: number;
  retry_rate: number;
  latency_p50_ms?: number | null;
  latency_avg_ms?: number | null;
  token_proxy_total: number;
  applied_dimensions?: Record<string, unknown>;
  recorded_dimensions?: Record<string, unknown>;
}

export interface ExperimentResultComparison {
  baseline: string;
  winner: string;
  ranking: string[];
  deltas_vs_baseline: Record<string, Record<string, number | null>>;
  variants: VariantSummary[];
  metrics_legend: string[];
  note: string;
}

export interface Experiment {
  id: number;
  name: string;
  status: string;
  case_ids: string[];
  variants: Record<string, unknown>[];
  results: ExperimentResultComparison | { status: string } | null;
  runs?: VariantRun[];
  created_at: string;
  label: string;
}

export type ExperimentDetail = Experiment;

export interface MonitoringOverview {
  window_days: number;
  generated_at: string;
  label: string;
  monitoring: Record<string, number | null> & { label: string };
  ai_capability: Record<string, number | string | null> & { label: string };
  agent_usage: Record<string, number | null> & { label: string };
  business_kpi: {
    label: string;
    anchor_date?: string | null;
    window?: string;
    roi?: { recent: number | null; previous: number | null; change_pct: number | null };
    ctr?: { recent: number | null; previous: number | null; change_pct: number | null };
    cpm?: { recent: number | null; previous: number | null; change_pct: number | null };
    gmv_change_pct?: number | null;
    fatigued_materials?: number;
    fatigued_share?: number | null;
    resolution_minutes_avg?: number | null;
  };
}

const qs = (params: Record<string, string | number | undefined | null>) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : '';
};

export const api = {
  health: () => request<HealthResponse>('/api/health'),

  listMerchants: () =>
    request<{ items: MerchantSummary[]; label: string }>('/api/merchants'),
  getMerchant: (id: string) => request<MerchantDetail>(`/api/merchants/${id}`),

  simulatorState: (merchantId: string) =>
    request<SimulatorState>(`/api/simulator/state/${merchantId}`),
  simulatorAdvance: (body: {
    merchant_id: string;
    days: number;
    effects: Record<string, unknown>[];
  }) => request<AdvanceResponse>('/api/simulator/advance', json(body)),

  listConversations: (merchantId: string) =>
    request<ConversationSummary[]>(`/api/conversations?merchant_id=${merchantId}`),
  getConversation: (id: string) => request<ConversationDetail>(`/api/conversations/${id}`),

  listMemories: (merchantId: string, statusFilter?: string) =>
    request<MemoryItem[]>(`/api/memories?merchant_id=${merchantId}${qs({ status_filter: statusFilter })}`),
  recallMemory: (body: { merchant_id: string; query: string; top_k?: number }) =>
    request<ScoredMemory[]>('/api/memories/recall', json(body)),
  promoteMemory: (memoryId: string) =>
    request<MemoryItem>(`/api/memories/${memoryId}/promote`, { method: 'POST' }),
  listConflicts: (merchantId?: string) =>
    request<MemoryConflict[]>(`/api/memories/conflicts${qs({ merchant_id: merchantId })}`),

  listKnowledge: (filters: { status_filter?: string; ktype?: string; industry?: string } = {}) =>
    request<KnowledgeItem[]>(`/api/knowledge${qs(filters)}`),
  queryKnowledge: (body: { query: string; industry?: string; top_k?: number }) =>
    request<ScoredKnowledge[]>('/api/knowledge/query', json(body)),
  scanPatterns: () =>
    request<KnowledgeItem | null>('/api/knowledge/scan-patterns', { method: 'POST' }),
  proposeKnowledge: (body: Record<string, unknown>) =>
    request<KnowledgeItem>('/api/knowledge/propose', json(body)),
  verifyKnowledge: (id: string) =>
    request<KnowledgeItem>(`/api/knowledge/${id}/verify`, { method: 'POST' }),

  listTools: () => request<ToolSpec[]>('/api/tools'),
  recentToolCalls: (limit = 50) =>
    request<ToolCallLog[]>(`/api/tools/calls/recent?limit=${limit}`),
  invokeTool: (toolName: string, args: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/tools/${toolName}/invoke`, json({ arguments: args })),

  runAgent: (body: { merchant_id: string; message: string; conversation_id?: string }) =>
    request<AgentRunResponse>('/api/agent/run', json(body)),
  executeAction: (body: {
    merchant_id: string;
    action: AgentAction;
    confirmed: boolean;
    observe_days?: number;
  }) => request<Record<string, unknown>>('/api/agent/act', json(body)),

  listTraces: (params: { merchant_id?: string; limit?: number } = {}) =>
    request<{ items: TraceRun[]; label: string }>(`/api/traces${qs(params)}`),
  getTrace: (id: string) => request<TraceSummary>(`/api/traces/${id}`),

  createEvalRun: (judge: 'rule' | 'heuristic') =>
    request<EvalRunDetail>(`/api/eval/runs?judge=${judge}`, { method: 'POST' }),
  listEvalRuns: (limit = 20) =>
    request<{ items: EvalRunSummary[]; label: string }>(`/api/eval/runs?limit=${limit}`),
  getEvalRun: (id: number) => request<EvalRunDetail>(`/api/eval/runs/${id}`),
  recordHumanVerdict: (caseResultId: number, rating: number, feedback?: string) =>
    request<EvalCaseResult>(
      `/api/eval/cases/${caseResultId}/human`,
      json({ rating, feedback }),
    ),

  submitFeedback: (body: {
    rating: number;
    comment?: string;
    trace_id?: string;
    merchant_id?: string;
  }) => request<Record<string, unknown>>('/api/feedback', json(body)),
  listFeedback: (limit = 50) =>
    request<{ items: FeedbackItem[]; label: string }>(`/api/feedback?limit=${limit}`),
  listBadcases: (params: { status?: string; error_type?: string; limit?: number } = {}) =>
    request<{ items: Badcase[]; label: string }>(`/api/badcases${qs(params)}`),
  getBadcase: (id: number) => request<Badcase>(`/api/badcases/${id}`),
  updateBadcase: (
    id: number,
    body: { status?: string; root_cause?: string; suggested_fix?: string; severity?: string },
  ) => request<Badcase>(`/api/badcases/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

  createExperiment: (body: { name?: string; variants?: Record<string, unknown>[]; case_ids?: string[] }) =>
    request<ExperimentDetail>('/api/experiments', json(body)),
  listExperiments: () =>
    request<{ items: ExperimentListItem[]; label: string }>('/api/experiments'),
  getExperiment: (id: number) => request<ExperimentDetail>(`/api/experiments/${id}`),

  monitoringOverview: (windowDays = 30) =>
    request<MonitoringOverview>(`/api/monitoring/overview?window_days=${windowDays}`),
};
