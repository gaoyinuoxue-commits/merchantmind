'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, ScanSearch } from 'lucide-react';
import { useState } from 'react';

import { EmptyState, ErrorCard, LabelBanner, LoadingCard, PageHeader, StatusBadge } from '@/components/common';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '@/lib/api';

const TYPES = [
  'business_rule',
  'diagnostic_rule',
  'industry_insight',
  'best_practice',
  'metric_definition',
  'case',
];

export default function KnowledgeCandidatesPage() {
  const queryClient = useQueryClient();
  const candidatesQuery = useQuery({
    queryKey: ['knowledge', 'candidate'],
    queryFn: () => api.listKnowledge({ status_filter: 'candidate' }),
  });

  const scanMutation = useMutation({
    mutationFn: api.scanPatterns,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['knowledge'] }),
  });

  return (
    <div className="space-y-4">
      <PageHeader
        title="Knowledge Candidate"
        description="知识候选池：从跨商家模式自动挖掘（propose_from_merchant_patterns）或人工提案，经验证后版本化发布"
      />
      <LabelBanner label="SYNTHETIC" note="候选知识在验证前不参与 Agent 归因 grounding。" />

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">待验证候选（{candidatesQuery.data?.length ?? 0}）</h3>
            <Button
              size="sm"
              variant="outline"
              disabled={scanMutation.isPending}
              onClick={() => scanMutation.mutate()}
            >
              <ScanSearch className="mr-1.5 h-4 w-4" />
              {scanMutation.isPending ? '挖掘中…' : '从商家模式挖掘'}
            </Button>
          </div>
          {scanMutation.isError && <ErrorCard error={scanMutation.error} />}
          {scanMutation.isSuccess && scanMutation.data === null && (
            <p className="text-xs text-muted-foreground">暂无可自动挖掘的新模式（当前商家证据不足）。</p>
          )}
          {scanMutation.isSuccess && scanMutation.data && (
            <p className="text-xs text-success">已生成候选：{scanMutation.data.title}</p>
          )}

          {candidatesQuery.isLoading && <LoadingCard />}
          {candidatesQuery.isError && <ErrorCard error={candidatesQuery.error} />}
          {candidatesQuery.data && candidatesQuery.data.length === 0 && (
            <EmptyState text="没有待验证候选，可点击右上角挖掘或手动提案" />
          )}
          {(candidatesQuery.data ?? []).map((item) => (
            <Card key={item.knowledge_id}>
              <CardContent className="p-3">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <Badge variant="secondary">{item.type}</Badge>
                  <StatusBadge status={item.status} />
                  <span className="font-medium">{item.title}</span>
                  <span className="ml-auto text-muted-foreground">
                    {item.merchant_count} 商家 · 质量 {item.quality_score}
                  </span>
                </div>
                <p className="mt-1.5 text-sm text-muted-foreground">{item.content}</p>
                <div className="mt-2 flex items-center justify-between">
                  <span className="font-mono text-[10px] text-muted-foreground">{item.slug} · v{item.version}</span>
                  <VerifyButton knowledgeId={item.knowledge_id} />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <ProposeForm />
      </div>
    </div>
  );
}

function VerifyButton({ knowledgeId }: { knowledgeId: string }) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => api.verifyKnowledge(knowledgeId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['knowledge'] }),
  });
  return (
    <Button size="sm" variant="outline" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
      <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> 验证发布
    </Button>
  );
}

function ProposeForm() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    slug: '',
    title: '',
    type: 'industry_insight',
    content: '',
    recommendation: '',
  });
  const mutation = useMutation({
    mutationFn: () =>
      api.proposeKnowledge({
        ...form,
        source: 'manual_proposal',
        quality_score: 0.6,
      }),
    onSuccess: () => {
      setForm({ slug: '', title: '', type: 'industry_insight', content: '', recommendation: '' });
      void queryClient.invalidateQueries({ queryKey: ['knowledge'] });
    },
  });

  const set = (key: keyof typeof form, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>人工提案候选</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <input
          className="h-9 w-full rounded-md border px-3 text-sm"
          placeholder="slug（小写字母/数字/下划线）"
          value={form.slug}
          onChange={(event) => set('slug', event.target.value)}
        />
        <input
          className="h-9 w-full rounded-md border px-3 text-sm"
          placeholder="标题"
          value={form.title}
          onChange={(event) => set('title', event.target.value)}
        />
        <select
          className="h-9 w-full rounded-md border px-2 text-sm"
          value={form.type}
          onChange={(event) => set('type', event.target.value)}
        >
          {TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
        <textarea
          className="min-h-[96px] w-full rounded-md border p-3 text-sm"
          placeholder="知识内容"
          value={form.content}
          onChange={(event) => set('content', event.target.value)}
        />
        <input
          className="h-9 w-full rounded-md border px-3 text-sm"
          placeholder="建议动作（可选）"
          value={form.recommendation}
          onChange={(event) => set('recommendation', event.target.value)}
        />
        <Button
          className="w-full"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          提交候选
        </Button>
        {mutation.isError && <p className="text-xs text-destructive">{mutation.error.message}</p>}
        {mutation.isSuccess && <p className="text-xs text-success">候选已提交，等待验证发布</p>}
      </CardContent>
    </Card>
  );
}
