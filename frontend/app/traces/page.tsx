'use client';

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import {
  EmptyState,
  ErrorCard,
  LabelBanner,
  LoadingCard,
  MerchantSelect,
  PageHeader,
  StatusBadge,
  fmtDateTime,
} from '@/components/common';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { api, type TraceRun, type TraceSummary } from '@/lib/api';
import { cn } from '@/lib/utils';

export default function TracesPage() {
  const [merchantId, setMerchantId] = useState('');
  const [activeId, setActiveId] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ['traces', merchantId],
    queryFn: () => api.listTraces({ merchant_id: merchantId || undefined, limit: 50 }),
    refetchInterval: 10_000,
  });
  const detailQuery = useQuery({
    queryKey: ['trace', activeId],
    queryFn: () => api.getTrace(activeId!),
    enabled: activeId !== null,
  });

  const runs: TraceRun[] = listQuery.data?.items ?? [];
  const active = activeId ?? runs[0]?.trace_id ?? null;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Trace"
        description="Agent 每次运行的端到端追踪：意图、工具调用、记忆/知识召回、Hook 校验、归因、动作与延迟"
      />
      <LabelBanner label="SYNTHETIC" note="Trace 来自合成环境中的真实 Agent 运行。" />
      <MerchantSelect merchantId={merchantId} onChange={setMerchantId} allowAll />

      {listQuery.isLoading && <LoadingCard />}
      {listQuery.isError && <ErrorCard error={listQuery.error} />}
      {runs.length === 0 && !listQuery.isLoading && <EmptyState text="暂无 Trace，先去经营顾问发起一次诊断" />}

      <div className="grid gap-4 lg:grid-cols-[420px_1fr]">
        <div className="space-y-2">
          {runs.map((run) => (
            <button
              key={run.trace_id}
              onClick={() => setActiveId(run.trace_id)}
              className={cn(
                'w-full rounded-md border bg-white p-3 text-left text-xs hover:border-primary/50',
                active === run.trace_id && 'border-primary bg-primary/5',
              )}
            >
              <div className="flex items-center gap-2">
                <StatusBadge status={run.status} />
                {run.intent && <Badge variant="secondary">{run.intent}</Badge>}
                <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                  {run.latency_ms ?? '—'}ms
                </span>
              </div>
              <p className="mt-1.5 line-clamp-2 text-sm">{run.query}</p>
              <div className="mt-1 text-[10px] text-muted-foreground">
                {run.merchant_id ?? '—'} · 工具 {run.tool_call_count} · 重试 {run.retry_count} ·{' '}
                {fmtDateTime(run.created_at)}
              </div>
            </button>
          ))}
        </div>

        <div>
          {!active && <EmptyState text="选择左侧 Trace 查看详情" />}
          {active && detailQuery.isLoading && <LoadingCard />}
          {active && detailQuery.isError && <ErrorCard error={detailQuery.error} />}
          {detailQuery.data && <TraceDetail trace={detailQuery.data} />}
        </div>
      </div>
    </div>
  );
}

function TraceDetail({ trace }: { trace: TraceSummary }) {
  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <StatusBadge status={trace.status} />
            <Badge variant="secondary">decision: {trace.decision}</Badge>
            {trace.failed_tools.length > 0 && (
              <Badge variant="destructive">失败工具：{trace.failed_tools.join(', ')}</Badge>
            )}
            <span className="font-mono text-muted-foreground">{trace.trace_id}</span>
          </div>
          <p className="mt-2 text-sm font-medium">{trace.query}</p>
          <p className="mt-1 text-xs text-muted-foreground">{trace.analysis_summary}</p>
        </div>

        <div className="grid gap-3 sm:grid-cols-4">
          <Metric label="质量分" value={trace.quality_score ?? '—'} />
          <Metric label="工具调用" value={trace.tool_call_count} />
          <Metric label="重试次数" value={trace.retry_count} />
          <Metric label="延迟" value={`${trace.latency_ms ?? '—'}ms`} />
        </div>

        <div>
          <div className="mb-2 text-xs font-medium text-muted-foreground">Span 时间线（{trace.stages.length}）</div>
          <div className="space-y-1.5">
            {trace.stages.map((stage, index) => (
              <div
                key={`${stage.span_type}-${index}`}
                className="flex items-center gap-3 rounded-md border bg-white px-3 py-2 text-xs"
              >
                <span className="w-5 text-center font-mono text-muted-foreground">{index + 1}</span>
                <Badge variant="outline">{stage.span_type}</Badge>
                <span className="flex-1 truncate">{stage.name}</span>
                <StatusBadge status={stage.status} />
                <span className="w-16 text-right font-mono text-muted-foreground">
                  {stage.latency_ms ?? '—'}ms
                </span>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}
