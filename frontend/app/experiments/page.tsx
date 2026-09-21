'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FlaskConical, Loader2, Trophy } from 'lucide-react';
import { useState } from 'react';

import {
  EmptyState,
  ErrorCard,
  LabelBanner,
  LoadingCard,
  PageHeader,
  fmtDateTime,
  fmtNum,
  fmtPct,
  fmtSignedPct,
} from '@/components/common';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  api,
  type Experiment,
  type ExperimentResultComparison,
} from '@/lib/api';
import { cn } from '@/lib/utils';

function isComparison(results: Experiment['results']): results is ExperimentResultComparison {
  return !!results && 'ranking' in results;
}

export default function ExperimentsPage() {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<number | null>(null);

  const listQuery = useQuery({
    queryKey: ['experiments'],
    queryFn: api.listExperiments,
  });
  const createMutation = useMutation({
    mutationFn: () => api.createExperiment({ name: `A/B 实验 ${new Date().toLocaleString('zh-CN', { hour12: false })}` }),
    onSuccess: (result) => {
      setActiveId(result.id);
      void queryClient.invalidateQueries({ queryKey: ['experiments'] });
      void queryClient.invalidateQueries({ queryKey: ['experiment'] });
    },
  });

  const items = listQuery.data?.items ?? [];
  const active = activeId ?? items[0]?.id ?? null;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Experiment（A/B）"
        description="RunProfile 驱动的真实管线 A/B：memory/knowledge Top-K、记忆排序权重、质检阈值实时生效；model/temperature/prompt_version 为录制维度"
      />
      <LabelBanner label="Demo/Simulation Metrics" note="相同 21 case × 多变体顺序执行（含冷启动预热），指标差异来自真实管线行为。" />

      <Button disabled={createMutation.isPending} onClick={() => createMutation.mutate()}>
        {createMutation.isPending ? (
          <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
        ) : (
          <FlaskConical className="mr-1.5 h-4 w-4" />
        )}
        运行默认 5 变体 × 21 case 实验
      </Button>
      {createMutation.isError && <span className="ml-2 text-xs text-destructive">{createMutation.error.message}</span>}

      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        <Card>
          <CardContent className="p-2">
            {items.length === 0 && <div className="p-4 text-xs text-muted-foreground">暂无实验</div>}
            {items.map((item) => (
              <button
                key={item.id}
                onClick={() => setActiveId(item.id)}
                className={cn(
                  'w-full rounded-md px-3 py-2 text-left text-xs hover:bg-muted',
                  active === item.id && 'bg-primary/10',
                )}
              >
                <div className="truncate font-medium">{item.name}</div>
                <div className="mt-1 flex items-center gap-2 text-muted-foreground">
                  <span>#{item.id}</span>
                  <span>{item.variant_count} 变体 × {item.case_count} case</span>
                </div>
                <div className="mt-0.5 flex items-center gap-1 text-muted-foreground">
                  {item.winner ? (
                    <>
                      <Trophy className="h-3 w-3 text-amber-500" /> {item.winner}
                    </>
                  ) : (
                    item.status
                  )}
                  <span className="ml-auto">{fmtDateTime(item.created_at)}</span>
                </div>
              </button>
            ))}
          </CardContent>
        </Card>

        <div>
          {!active && <EmptyState text="发起或选择一次实验" />}
          {active && <ExperimentDetailPanel experimentId={active} />}
        </div>
      </div>
    </div>
  );
}

function ExperimentDetailPanel({ experimentId }: { experimentId: number }) {
  const query = useQuery({
    queryKey: ['experiment', experimentId],
    queryFn: () => api.getExperiment(experimentId),
  });
  if (query.isLoading) return <LoadingCard text="实验运行中（每变体真实执行 21 个 case，请稍候）…" />;
  if (query.isError) return <ErrorCard error={query.error} />;
  const experiment = query.data!;
  if (!isComparison(experiment.results)) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">实验状态：{experiment.status}</CardContent>
      </Card>
    );
  }
  const comparison = experiment.results;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            排名
            {comparison.ranking.map((name, index) => (
              <Badge key={name} variant={index === 0 ? 'success' : 'secondary'}>
                {index + 1}. {name}
              </Badge>
            ))}
          </CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-muted-foreground">{comparison.note}</CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>变体指标对比（baseline = {comparison.baseline}）</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr>
                <th className="px-2 py-1">变体</th>
                <th className="px-2">通过</th>
                <th className="px-2">成功率</th>
                <th className="px-2">工具准确</th>
                <th className="px-2">幻觉</th>
                <th className="px-2">重试率</th>
                <th className="px-2">延迟均值</th>
                <th className="px-2">Token</th>
              </tr>
            </thead>
            <tbody>
              {comparison.variants.map((variant) => {
                const delta = comparison.deltas_vs_baseline[variant.variant_name];
                return (
                  <tr key={variant.variant_name} className="border-t">
                    <td className="px-2 py-1.5 font-medium">
                      {variant.variant_name}
                      {variant.variant_name === comparison.winner && (
                        <Trophy className="ml-1 inline h-3 w-3 text-amber-500" />
                      )}
                    </td>
                    <td className="px-2">{variant.passed}/{variant.total}</td>
                    <td className="px-2">{fmtPct(variant.task_success_rate)}</td>
                    <td className="px-2">{fmtPct(variant.tool_accuracy ?? null)}</td>
                    <td className="px-2">{fmtPct(variant.hallucination_rate)}</td>
                    <td className="px-2">
                      {fmtPct(variant.retry_rate)}
                      {delta && <Delta value={delta.retry_rate} percent />}
                    </td>
                    <td className="px-2">
                      {fmtNum(variant.latency_avg_ms, 1)}ms
                      {delta && <Delta value={delta.latency_avg_ms} suffix="ms" />}
                    </td>
                    <td className="px-2">
                      {fmtNum(variant.token_proxy_total)}
                      {delta && <Delta value={delta.token_proxy_total} signed />}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <div className="grid gap-3 lg:grid-cols-2">
        {comparison.variants.map((variant) => {
          const run = experiment.runs?.find((item) => item.variant_name === variant.variant_name);
          return (
            <Card key={variant.variant_name}>
              <CardHeader>
                <CardTitle className="text-xs">{variant.variant_name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5 text-[11px] text-muted-foreground">
                <DimensionRow label="生效维度" value={variant.applied_dimensions ?? run?.config ?? {}} />
                <DimensionRow label="录制维度（真实 LLM 接入后生效）" value={variant.recorded_dimensions ?? {}} />
                <div>case 数：{run?.cases.length ?? 0} · 逐 case 已持久化</div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function Delta({ value, percent, signed, suffix }: { value: number | null; percent?: boolean; signed?: boolean; suffix?: string }) {
  if (value === null || value === undefined || value === 0) return null;
  const good = value < 0;
  const text = percent ? fmtSignedPct(value * 100) : `${value > 0 ? '+' : ''}${fmtNum(value, signed ? 0 : 1)}${suffix ?? ''}`;
  return (
    <span className={cn('ml-1', good ? 'text-success' : 'text-destructive')}>
      ({text})
    </span>
  );
}

function DimensionRow({ label, value }: { label: string; value: Record<string, unknown> }) {
  const entries = Object.entries(value);
  return (
    <div>
      <div>{label}</div>
      <code className="block rounded bg-muted/50 px-2 py-1 font-mono text-[10px]">
        {entries.length === 0 ? '{}' : entries.map(([key, val]) => `${key}=${String(val)}`).join('  ')}
      </code>
    </div>
  );
}
