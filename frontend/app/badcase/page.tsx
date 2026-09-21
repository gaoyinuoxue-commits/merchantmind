'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import {
  EmptyState,
  ErrorCard,
  LabelBanner,
  LoadingCard,
  PageHeader,
  StatusBadge,
  fmtDateTime,
} from '@/components/common';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api, type Badcase as BadcaseItem } from '@/lib/api';
import { cn } from '@/lib/utils';

const STATUS_TABS = ['', 'open', 'in_review', 'fixed', 'wont_fix', 'ignored'];
const FLOW: Record<string, { label: string; next: string }[]> = {
  open: [
    { label: '开始处理', next: 'in_review' },
    { label: '忽略', next: 'ignored' },
  ],
  in_review: [
    { label: '标记已修复', next: 'fixed' },
    { label: '不予修复', next: 'wont_fix' },
  ],
};

const SEVERITY_TONE: Record<string, 'destructive' | 'default' | 'secondary'> = {
  high: 'destructive',
  medium: 'default',
  low: 'secondary',
};

export default function BadcasePage() {
  const [status, setStatus] = useState('open');
  const [activeId, setActiveId] = useState<number | null>(null);

  const listQuery = useQuery({
    queryKey: ['badcases', status],
    queryFn: () => api.listBadcases({ status: status || undefined, limit: 100 }),
  });
  const items = listQuery.data?.items ?? [];
  const active = activeId ?? items[0]?.id ?? null;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Badcase / Feedback"
        description="评测失败与负反馈自动开单，按 Routing/Retrieval/Tool/Reasoning/Hallucination 分诊并给出责任模块与修复建议"
      />
      <LabelBanner label="SYNTHETIC" note="Badcase 与反馈均来自合成环境的评测和试用。" />

      <div className="flex flex-wrap gap-1 text-xs">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => {
              setStatus(tab);
              setActiveId(null);
            }}
            className={cn(
              'rounded-md border px-3 py-1',
              status === tab ? 'border-primary bg-primary/5 text-primary' : 'bg-white text-muted-foreground',
            )}
          >
            {tab || '全部'}
          </button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[420px_1fr]">
        <div className="space-y-2">
          {listQuery.isLoading && <LoadingCard />}
          {listQuery.isError && <ErrorCard error={listQuery.error} />}
          {items.length === 0 && !listQuery.isLoading && <EmptyState text="没有匹配的 Badcase" />}
          {items.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveId(item.id)}
              className={cn(
                'w-full rounded-md border bg-white p-3 text-left text-xs hover:border-primary/50',
                active === item.id && 'border-primary bg-primary/5',
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="destructive">{item.error_type}</Badge>
                <Badge variant={SEVERITY_TONE[item.severity] ?? 'secondary'}>{item.severity}</Badge>
                <StatusBadge status={item.status} />
                {item.occurrence_count > 1 && (
                  <Badge variant="secondary">×{item.occurrence_count}</Badge>
                )}
                <span className="ml-auto text-muted-foreground">#{item.id}</span>
              </div>
              <p className="mt-1.5 text-sm font-medium">{item.title}</p>
              <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                {item.affected_module} · {item.source} · {fmtDateTime(item.created_at)}
              </p>
            </button>
          ))}
        </div>

        <div className="space-y-4">
          {active !== null && <BadcaseDetail badcaseId={active} />}
          {active === null && <FeedbackPanel />}
        </div>
      </div>
    </div>
  );
}

function BadcaseDetail({ badcaseId }: { badcaseId: number }) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['badcase', badcaseId],
    queryFn: () => api.getBadcase(badcaseId),
  });
  const mutation = useMutation({
    mutationFn: (status: string) => api.updateBadcase(badcaseId, { status }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['badcases'] });
      void queryClient.invalidateQueries({ queryKey: ['badcase', badcaseId] });
    },
  });

  if (query.isLoading) return <LoadingCard />;
  if (query.isError) return <ErrorCard error={query.error} />;
  const item: BadcaseItem = query.data!;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            #{item.id} {item.title}
            <StatusBadge status={item.status} />
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-2 text-xs">
            <Badge variant="destructive">{item.error_type}</Badge>
            <Badge variant="secondary">{item.affected_module}</Badge>
            <Badge variant="outline">{item.severity}</Badge>
            <Badge variant="outline">来源 {item.source}</Badge>
            {item.case_id && <Badge variant="outline">case {item.case_id}</Badge>}
            <Badge variant="outline">出现 {item.occurrence_count} 次</Badge>
          </div>
          {item.root_cause && (
            <Section title="根因分析">
              <p className="text-muted-foreground">{item.root_cause}</p>
            </Section>
          )}
          {item.suggested_fix && (
            <Section title="修复建议">
              <p className="text-muted-foreground">{item.suggested_fix}</p>
            </Section>
          )}
          {item.evidence && Object.keys(item.evidence).length > 0 && (
            <Section title="证据">
              <pre className="max-h-56 overflow-auto rounded bg-muted/50 p-2 text-[11px] leading-5">
                {JSON.stringify(item.evidence, null, 2)}
              </pre>
            </Section>
          )}
          <div className="flex flex-wrap gap-2">
            {(FLOW[item.status] ?? []).map((action) => (
              <Button
                key={action.next}
                size="sm"
                variant="outline"
                disabled={mutation.isPending}
                onClick={() => mutation.mutate(action.next)}
              >
                {action.label}
              </Button>
            ))}
            {mutation.isError && <span className="self-center text-xs text-destructive">{mutation.error.message}</span>}
          </div>
          {item.resolved_at && (
            <p className="text-[11px] text-muted-foreground">解决时间：{fmtDateTime(item.resolved_at)}</p>
          )}
        </CardContent>
      </Card>
      <FeedbackPanel compact />
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-muted-foreground">{title}</div>
      {children}
    </div>
  );
}

function FeedbackPanel({ compact = false }: { compact?: boolean }) {
  const queryClient = useQueryClient();
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const [merchantId, setMerchantId] = useState('M001');

  const feedbackQuery = useQuery({
    queryKey: ['feedback'],
    queryFn: () => api.listFeedback(50),
  });
  const submitMutation = useMutation({
    mutationFn: () => api.submitFeedback({ rating, comment: comment || undefined, merchant_id: merchantId }),
    onSuccess: () => {
      setComment('');
      void queryClient.invalidateQueries({ queryKey: ['feedback'] });
      void queryClient.invalidateQueries({ queryKey: ['badcases'] });
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{compact ? '最近用户反馈' : '用户反馈闭环（rating ≤ 3 自动开 Badcase）'}</CardTitle>
      </CardHeader>
      <CardContent className={cn('space-y-3', compact && 'pt-0')}>
        {!compact && (
          <div className="space-y-2 rounded-md border p-3">
            <div className="flex items-center gap-3 text-xs">
              <label>商家</label>
              <input
                className="h-8 w-28 rounded-md border px-2 font-mono"
                value={merchantId}
                onChange={(event) => setMerchantId(event.target.value)}
              />
              <label>评分</label>
              <select
                className="h-8 rounded-md border px-2"
                value={rating}
                onChange={(event) => setRating(Number(event.target.value))}
              >
                {[5, 4, 3, 2, 1].map((value) => (
                  <option key={value} value={value}>
                    {value} 星
                  </option>
                ))}
              </select>
            </div>
            <textarea
              className="min-h-[60px] w-full rounded-md border p-2 text-sm"
              placeholder="反馈内容（可选）"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
            <Button size="sm" disabled={submitMutation.isPending} onClick={() => submitMutation.mutate()}>
              提交反馈
            </Button>
            {submitMutation.isSuccess && <span className="ml-2 text-xs text-success">已提交</span>}
            {submitMutation.isError && <span className="ml-2 text-xs text-destructive">{submitMutation.error.message}</span>}
          </div>
        )}
        <div className="space-y-1.5">
          {(feedbackQuery.data?.items ?? []).map((feedback) => (
            <div key={feedback.id} className="flex items-start gap-2 rounded-md border px-3 py-2 text-xs">
              <Badge variant={feedback.helpful ? 'success' : 'destructive'}>{feedback.rating}★</Badge>
              <div className="min-w-0 flex-1">
                <p className="truncate">{feedback.comment || '（无评论）'}</p>
                <p className="font-mono text-[10px] text-muted-foreground">
                  {feedback.merchant_id ?? '—'} · {fmtDateTime(feedback.created_at)}
                </p>
              </div>
            </div>
          ))}
          {feedbackQuery.data && feedbackQuery.data.items.length === 0 && (
            <EmptyState text="暂无反馈" />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
