'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Search } from 'lucide-react';
import { useState } from 'react';

import { EmptyState, ErrorCard, LabelBanner, LoadingCard, PageHeader, StatusBadge } from '@/components/common';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { api, type ScoredKnowledge } from '@/lib/api';
import { cn } from '@/lib/utils';

const TYPE_TABS = [
  { value: '', label: '全部类型' },
  { value: 'business_rule', label: '经营规则' },
  { value: 'diagnostic_rule', label: '诊断规则' },
  { value: 'industry_insight', label: '行业洞察' },
  { value: 'best_practice', label: '最佳实践' },
  { value: 'metric_definition', label: '指标定义' },
  { value: 'case', label: '真实案例' },
];

const STATUS_TABS = [
  { value: '', label: '全部状态' },
  { value: 'active', label: 'active' },
  { value: 'candidate', label: 'candidate' },
  { value: 'archived', label: 'archived' },
];

export default function KnowledgePage() {
  const [ktype, setKtype] = useState('');
  const [statusFilter, setStatusFilter] = useState('active');
  const [queryText, setQueryText] = useState('');
  const [submitted, setSubmitted] = useState('');

  const listQuery = useQuery({
    queryKey: ['knowledge', ktype, statusFilter],
    queryFn: () => api.listKnowledge({ ktype: ktype || undefined, status_filter: statusFilter || undefined }),
  });
  const ragQuery = useQuery({
    queryKey: ['knowledge-query', submitted],
    queryFn: () => api.queryKnowledge({ query: submitted, top_k: 8 }),
    enabled: submitted.length > 0,
  });

  return (
    <div className="space-y-4">
      <PageHeader
        title="Industry Knowledge（RAG）"
        description="58 条版本化行业知识：业务规则 / 诊断规则 / 洞察 / 最佳实践 / 指标定义 / 真实案例，支持语义检索与人工验证"
      />
      <LabelBanner label="SYNTHETIC" note="知识库为合成沉淀，检索结果由 pgvector 语义相似度 + 确定性 grounding 计算。" />

      <Card>
        <CardContent className="p-3">
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (queryText.trim()) setSubmitted(queryText.trim());
            }}
          >
            <input
              className="h-9 flex-1 rounded-md border bg-white px-3 text-sm"
              placeholder="RAG 语义检索：素材疲劳和预算失控有什么关系？"
              value={queryText}
              onChange={(event) => setQueryText(event.target.value)}
            />
            <Button type="submit">
              <Search className="mr-1.5 h-4 w-4" /> 检索
            </Button>
          </form>
        </CardContent>
      </Card>

      {submitted && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">检索结果（top 8）</h3>
            <Button size="sm" variant="ghost" onClick={() => setSubmitted('')}>
              清除检索
            </Button>
          </div>
          {ragQuery.isLoading && <LoadingCard />}
          {ragQuery.isError && <ErrorCard error={ragQuery.error} />}
          {(ragQuery.data ?? []).map((item: ScoredKnowledge) => (
            <Card key={item.knowledge_id}>
              <CardContent className="p-3">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <Badge variant="secondary">{item.type}</Badge>
                  <Badge variant="outline">score {item.score.toFixed(3)}</Badge>
                  <StatusBadge status={item.status} />
                  <span className="text-muted-foreground">{item.title}</span>
                </div>
                <p className="mt-1.5 line-clamp-3 text-sm text-muted-foreground">{item.content}</p>
              </CardContent>
            </Card>
          ))}
          {ragQuery.data && ragQuery.data.length === 0 && <EmptyState text="未检索到知识" />}
        </div>
      )}

      {!submitted && (
        <>
          <div className="flex flex-wrap gap-2 text-xs">
            {TYPE_TABS.map((tab) => (
              <button
                key={tab.value}
                onClick={() => setKtype(tab.value)}
                className={cn(
                  'rounded-md border px-2.5 py-1',
                  ktype === tab.value ? 'border-primary bg-primary/5 text-primary' : 'bg-white text-muted-foreground',
                )}
              >
                {tab.label}
              </button>
            ))}
            <span className="mx-1 w-px bg-border" />
            {STATUS_TABS.map((tab) => (
              <button
                key={tab.value}
                onClick={() => setStatusFilter(tab.value)}
                className={cn(
                  'rounded-md border px-2.5 py-1',
                  statusFilter === tab.value ? 'border-primary bg-primary/5 text-primary' : 'bg-white text-muted-foreground',
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {listQuery.isLoading && <LoadingCard />}
          {listQuery.isError && <ErrorCard error={listQuery.error} />}
          {listQuery.data && listQuery.data.length === 0 && <EmptyState text="该筛选下暂无知识" />}
          <div className="grid gap-2">
            {(listQuery.data ?? []).map((item) => (
              <KnowledgeRow key={item.knowledge_id} item={item} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function KnowledgeRow({ item }: { item: import('@/lib/api').KnowledgeItem }) {
  const queryClient = useQueryClient();
  const verifyMutation = useMutation({
    mutationFn: () => api.verifyKnowledge(item.knowledge_id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['knowledge'] }),
  });
  return (
    <Card>
      <CardContent className="p-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant="secondary">{item.type}</Badge>
          <StatusBadge status={item.status} />
          <span className="font-medium">{item.title}</span>
          <span className="ml-auto text-muted-foreground">
            v{item.version} · 质量 {item.quality_score} · {item.merchant_count} 商家佐证 · {item.source}
          </span>
        </div>
        <p className="mt-1.5 text-sm leading-6 text-muted-foreground">{item.content}</p>
        {item.recommendation && (
          <p className="mt-1 text-xs text-muted-foreground">建议：{item.recommendation}</p>
        )}
        <div className="mt-2 flex items-center justify-between">
          <span className="font-mono text-[10px] text-muted-foreground">{item.slug}</span>
          {item.status === 'candidate' && (
            <Button
              size="sm"
              variant="outline"
              disabled={verifyMutation.isPending}
              onClick={() => verifyMutation.mutate()}
            >
              <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> 验证发布
            </Button>
          )}
        </div>
        {verifyMutation.isError && <p className="mt-1 text-xs text-destructive">{verifyMutation.error.message}</p>}
      </CardContent>
    </Card>
  );
}
