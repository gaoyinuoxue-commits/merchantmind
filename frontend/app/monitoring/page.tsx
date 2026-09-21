'use client';

import { useQuery } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import {
  ErrorCard,
  LabelBanner,
  LoadingCard,
  PageHeader,
  StatCard,
  fmtNum,
  fmtPct,
  fmtSignedPct,
} from '@/components/common';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api, type MonitoringOverview } from '@/lib/api';

export default function MonitoringPage() {
  const query = useQuery({
    queryKey: ['monitoring', 30],
    queryFn: () => api.monitoringOverview(30),
    refetchInterval: 15_000,
  });
  if (query.isLoading) return <LoadingCard text="聚合监控指标…" />;
  if (query.isError) return <ErrorCard error={query.error} />;
  const data: MonitoringOverview = query.data!;
  const m = data.monitoring;
  const capability = data.ai_capability;
  const usage = data.agent_usage;
  const business = data.business_kpi;

  const rateData = [
    { name: '成功率', value: toPercent(m.success_rate) },
    { name: '工具成功率', value: 100 - toPercent(m.tool_failure_rate) },
    { name: '检索命中率', value: 100 - toPercent(m.retrieval_miss_rate) },
    { name: '无重试率', value: 100 - toPercent(m.retry_rate) },
    { name: 'Helpful', value: toPercent(m.helpful_rate) },
  ];
  const latencyData = [
    { name: 'P50', value: num(m.latency_p50_ms) },
    { name: '平均', value: num(m.latency_avg_ms) },
    { name: 'P95', value: num(m.latency_p95_ms) },
  ];
  const businessBars = [
    {
      name: 'ROI',
      previous: business.roi?.previous ?? 0,
      recent: business.roi?.recent ?? 0,
    },
    {
      name: 'CTR%',
      previous: (business.ctr?.previous ?? 0) * 100,
      recent: (business.ctr?.recent ?? 0) * 100,
    },
    {
      name: 'CPM',
      previous: business.cpm?.previous ?? 0,
      recent: business.cpm?.recent ?? 0,
    },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Monitoring & KPI"
        description="三层指标体系：在线监控（Demo/Simulation Metrics）· AI 能力与 Agent 使用 · Business Outcome（Synthetic Business Metrics）"
        badge="30 天窗口"
      />
      <LabelBanner label="Demo/Simulation Metrics" note="在线/AI/使用层指标来自合成环境真实 Trace、评测、反馈表聚合。" />
      <LabelBanner label="Synthetic Business Metrics" note="经营结果指标由合成世界窗口对比计算，仅演示北极星指标设计，不代表真实业务。" />

      <section>
        <h3 className="mb-2 text-sm font-semibold">① 在线监控</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Requests" value={m.requests} hint={`成功 ${m.succeeded} · 澄清 ${m.clarifications} · 拦截 ${m.blocked_actions}`} />
          <StatCard label="Success Rate" value={fmtPct(m.success_rate as number | null)} tone="good" />
          <StatCard label="Tool Calls / 失败" value={`${m.tool_calls} / ${m.tool_failures}`} hint={fmtPct(m.tool_failure_rate as number | null)} tone={m.tool_failures ? 'bad' : 'good'} />
          <StatCard label="Memory 写入 / 冲突" value={`${m.memory_writes} / ${m.memory_conflicts}`} />
          <StatCard label="检索调用 / Miss" value={`${m.retrieval_calls} / ${m.retrieval_misses}`} hint={fmtPct(m.retrieval_miss_rate as number | null)} tone="warn" />
          <StatCard label="幻觉数 / 率" value={`${m.hallucinations} / ${fmtPct(m.hallucination_rate as number | null)}`} tone={m.hallucinations ? 'bad' : 'good'} />
          <StatCard label="重试次数 / 率" value={`${m.retries} / ${fmtPct(m.retry_rate as number | null)}`} />
          <StatCard label="Helpful Rate" value={fmtPct(m.helpful_rate as number | null)} hint={`${m.feedback_count} 条反馈`} />
          <StatCard label="Token（代理估算）" value={fmtNum(m.token_proxy_total)} />
          <StatCard label="P50 / P95 延迟" value={`${m.latency_p50_ms ?? '—'} / ${m.latency_p95_ms ?? '—'}ms`} />
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <ChartCard title="关键比率（%）">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={rateData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" fontSize={11} />
                <YAxis fontSize={10} unit="%" domain={[0, 100]} />
                <Tooltip />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {rateData.map((entry) => (
                    <Cell key={entry.name} fill={entry.value >= 90 ? 'hsl(142 71% 45%)' : 'hsl(24 95% 53%)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
          <ChartCard title="延迟分布（ms）">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={latencyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" fontSize={11} />
                <YAxis fontSize={10} />
                <Tooltip />
                <Bar dataKey="value" fill="hsl(221 83% 53%)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold">② AI 能力（最近一次评测）</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Task Success" value={fmtPct(capability.task_success_rate as number | null)} hint={`eval #${capability.eval_run_id ?? '—'} · ${capability.judge ?? '—'}`} tone="good" />
          <StatCard label="Tool Accuracy" value={fmtPct(capability.tool_accuracy as number | null)} />
          <StatCard label="Cause Recall@3" value={fmtPct(capability.cause_recall_at_3 as number | null)} />
          <StatCard label="Knowledge Recall@5" value={fmtPct(capability.knowledge_recall_at_5 as number | null)} />
          <StatCard label="Answer Quality（代理）" value={capability.answer_quality_proxy ?? '—'} hint="Heuristic 评委均分" />
          <StatCard label="幻觉率" value={fmtPct(capability.hallucination_rate as number | null)} tone="good" />
        </div>

        <h3 className="mb-2 mt-4 text-sm font-semibold">Agent 使用</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="会话数" value={usage.conversations} hint={`多轮 ${usage.multi_turn_conversations}`} />
          <StatCard label="Follow-up 率" value={fmtPct(usage.follow_up_rate as number | null)} />
          <StatCard label="动作请求 / 执行 / 拦截" value={`${usage.actions_requested} / ${usage.actions_executed} / ${usage.actions_blocked}`} />
          <StatCard label="执行率 / 人类确认率" value={`${fmtPct(usage.execution_rate as number | null)} / ${fmtPct(usage.human_confirmation_rate as number | null)}`} />
        </div>
      </section>

      <section>
        <div className="mb-2 flex items-center gap-2">
          <h3 className="text-sm font-semibold">③ Business Outcome</h3>
          <Badge variant="secondary">{business.window}</Badge>
          <span className="text-xs text-muted-foreground">锚点日期 {business.anchor_date}</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <CompareCard label="ROI" recent={business.roi?.recent} previous={business.roi?.previous} change={business.roi?.change_pct} digits={2} higherBetter />
          <CompareCard label="CTR" recent={business.ctr?.recent} previous={business.ctr?.previous} change={business.ctr?.change_pct} percent higherBetter />
          <CompareCard label="CPM" recent={business.cpm?.recent} previous={business.cpm?.previous} change={business.cpm?.change_pct} digits={1} higherBetter={false} />
          <StatCard label="GMV 环比变化" value={fmtSignedPct(business.gmv_change_pct)} tone={(business.gmv_change_pct ?? 0) >= 0 ? 'good' : 'bad'} />
          <StatCard label="低效（疲劳）素材" value={`${business.fatigued_materials}`} hint={`占比 ${fmtPct(business.fatigued_share)}`} tone="warn" />
          <StatCard label="平均解决时长" value={business.resolution_minutes_avg === null ? '—' : `${business.resolution_minutes_avg} 分钟`} />
        </div>
        <ChartCard title="近 7 天 vs 前 7 天（SYNTHETIC）">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={businessBars}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" fontSize={11} />
              <YAxis fontSize={10} />
              <Tooltip />
              <Legend />
              <Bar dataKey="previous" name="前 7 天" fill="hsl(220 9% 70%)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="recent" name="近 7 天" fill="hsl(221 83% 53%)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </section>
    </div>
  );
}

function toPercent(value: number | null | undefined): number {
  return value === null || value === undefined ? 0 : Math.round(value * 1000) / 10;
}
function num(value: number | null | undefined): number {
  return value ?? 0;
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="mt-3">
      <CardHeader>
        <CardTitle className="text-xs">{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function CompareCard({
  label,
  recent,
  previous,
  change,
  digits = 2,
  percent = false,
  higherBetter,
}: {
  label: string;
  recent: number | null | undefined;
  previous: number | null | undefined;
  change: number | null | undefined;
  digits?: number;
  percent?: boolean;
  higherBetter: boolean;
}) {
  const good = change === null || change === undefined ? undefined : higherBetter ? change >= 0 : change <= 0;
  const display = (value: number | null | undefined) =>
    value === null || value === undefined
      ? '—'
      : percent
        ? `${(value * 100).toFixed(digits)}%`
        : fmtNum(value, digits);
  return (
    <StatCard
      label={label}
      value={display(recent)}
      hint={`前窗口 ${display(previous)} · 环比 ${fmtSignedPct(change)}`}
      tone={good === undefined ? 'default' : good ? 'good' : 'bad'}
    />
  );
}
