'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Play, Star } from 'lucide-react';
import { useState } from 'react';

import {
  EmptyState,
  ErrorCard,
  LabelBanner,
  LoadingCard,
  PageHeader,
  StatCard,
  fmtDateTime,
  fmtNum,
  fmtPct,
} from '@/components/common';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api, type EvalCaseResult, type EvalRunDetail } from '@/lib/api';
import { cn } from '@/lib/utils';

export default function EvaluationPage() {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<number | null>(null);

  const runsQuery = useQuery({
    queryKey: ['eval-runs'],
    queryFn: () => api.listEvalRuns(30),
  });

  const runMutation = useMutation({
    mutationFn: (judge: 'rule' | 'heuristic') => api.createEvalRun(judge),
    onSuccess: (result) => {
      setActiveId(result.eval_run_id);
      void queryClient.invalidateQueries({ queryKey: ['eval-runs'] });
      void queryClient.invalidateQueries({ queryKey: ['eval-run'] });
    },
  });

  const runs = runsQuery.data?.items ?? [];
  const active = activeId ?? runs[0]?.eval_run_id ?? null;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Evaluation"
        description="54 个 Ground Truth case 离线评测：RuleJudge 确定性判定 + Heuristic 结构代理评委，支持人工评分对齐"
      />
      <LabelBanner label="Demo/Simulation Metrics" note="评委为确定性规则与结构代理（非真实 LLM 打分），token 为代理估算。" />

      <div className="flex flex-wrap gap-2">
        <Button disabled={runMutation.isPending} onClick={() => runMutation.mutate('rule')}>
          {runMutation.isPending && runMutation.variables === 'rule' ? (
            <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-1.5 h-4 w-4" />
          )}
          运行 Rule 评测（54 case）
        </Button>
        <Button variant="outline" disabled={runMutation.isPending} onClick={() => runMutation.mutate('heuristic')}>
          {runMutation.isPending && runMutation.variables === 'heuristic' ? (
            <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-1.5 h-4 w-4" />
          )}
          运行 Heuristic 评委
        </Button>
        {runMutation.isError && <span className="self-center text-xs text-destructive">{runMutation.error.message}</span>}
      </div>

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <Card>
          <CardContent className="p-2">
            {runs.length === 0 && <div className="p-4 text-xs text-muted-foreground">暂无评测运行</div>}
            {runs.map((run) => (
              <button
                key={run.eval_run_id}
                onClick={() => setActiveId(run.eval_run_id)}
                className={cn(
                  'w-full rounded-md px-3 py-2 text-left text-xs hover:bg-muted',
                  active === run.eval_run_id && 'bg-primary/10',
                )}
              >
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">#{run.eval_run_id} {run.judge}</Badge>
                  <span className="text-muted-foreground">{fmtDateTime(run.created_at)}</span>
                </div>
                <div className="mt-1">
                  {run.passed ?? 0}/{run.total ?? 0} 通过 · {fmtPct(run.task_success_rate ?? null)}
                </div>
              </button>
            ))}
          </CardContent>
        </Card>

        <div>
          {!active && <EmptyState text="选择或发起一次评测" />}
          {active && <RunDetail runId={active} />}
        </div>
      </div>
    </div>
  );
}

function RunDetail({ runId }: { runId: number }) {
  const query = useQuery({
    queryKey: ['eval-run', runId],
    queryFn: () => api.getEvalRun(runId),
  });
  if (query.isLoading) return <LoadingCard />;
  if (query.isError) return <ErrorCard error={query.error} />;
  const run: EvalRunDetail = query.data!;
  const metrics = run.metrics;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Task Success" value={fmtPct(metrics.task_success_rate)} hint={`${metrics.passed}/${metrics.total}`} tone="good" />
        <StatCard label="Tool Accuracy" value={fmtPct(metrics.tool_accuracy ?? null)} />
        <StatCard label="Cause Recall@3" value={fmtPct(metrics.cause_recall_at_3 ?? null)} />
        <StatCard label="Knowledge Recall@5" value={fmtPct(metrics.knowledge_recall_at_5 ?? null)} />
        <StatCard label="幻觉率" value={fmtPct(metrics.hallucination_rate)} tone={metrics.hallucination_rate ? 'bad' : 'good'} />
        <StatCard label="重试率" value={fmtPct(metrics.retry_rate)} />
        <StatCard label="P50 / P95 延迟" value={`${metrics.latency_p50_ms ?? '—'} / ${metrics.latency_p95_ms ?? '—'}ms`} />
        <StatCard label="Token（代理）" value={fmtNum(metrics.token_proxy_total)} hint={`人工对齐 ${metrics.human_rated} 条`} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>分类型表现</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(metrics.by_type).map(([type, bucket]) => (
              <div key={type} className="rounded-md border px-3 py-2">
                <Badge variant="secondary">{type}</Badge>
                <div className="mt-1">
                  {bucket.passed}/{bucket.total} · {fmtPct(bucket.success_rate)}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>逐 Case 结果（{run.cases.length}）</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5">
          {run.cases.map((item) => (
            <CaseRow key={`${item.case_id}-${item.merchant_id}`} item={item} />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function CaseRow({ item }: { item: EvalCaseResult }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-md border bg-white px-3 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={item.passed ? 'success' : 'destructive'}>{item.passed ? 'PASS' : 'FAIL'}</Badge>
        <Badge variant="secondary">{item.case_type}</Badge>
        <span className="font-mono text-muted-foreground">{item.case_id}</span>
        <button className="text-primary hover:underline" onClick={() => setOpen((value) => !value)}>
          {open ? '收起' : '详情'}
        </button>
        <div className="ml-auto flex items-center gap-2">
          {item.judge_score !== null && item.judge_score !== undefined && (
            <span className="text-muted-foreground">评委分 {item.judge_score}</span>
          )}
          {item.human_rating && (
            <span className="flex items-center gap-0.5 text-amber-600">
              <Star className="h-3 w-3 fill-current" /> {item.human_rating}
            </span>
          )}
          <HumanRating item={item} />
        </div>
      </div>
      <p className="mt-1 text-muted-foreground">{item.message}</p>
      {open && (
        <pre className="mt-2 max-h-56 overflow-auto rounded bg-muted/50 p-2 text-[11px] leading-5">
          {JSON.stringify({ metrics: item.metrics, prediction: item.prediction, trace_id: item.trace_id }, null, 2)}
        </pre>
      )}
    </div>
  );
}

function HumanRating({ item }: { item: EvalCaseResult }) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (rating: number) => api.recordHumanVerdict(item.case_result_id!, rating),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['eval-run'] });
      void queryClient.invalidateQueries({ queryKey: ['eval-runs'] });
    },
  });
  if (item.case_result_id === undefined) return null;
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((rating) => (
        <button
          key={rating}
          disabled={mutation.isPending}
          onClick={() => mutation.mutate(rating)}
          className={cn(
            'text-sm leading-none',
            (item.human_rating ?? 0) >= rating ? 'text-amber-500' : 'text-muted-foreground/40',
          )}
          title="人工评分"
        >
          ★
        </button>
      ))}
      {mutation.isError && <span className="ml-1 text-destructive">{mutation.error.message}</span>}
    </div>
  );
}
