'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowUpCircle, Search } from 'lucide-react';
import { useState } from 'react';

import { EmptyState, ErrorCard, LabelBanner, LoadingCard, MerchantSelect, PageHeader, StatusBadge, fmtDateTime } from '@/components/common';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api, type ScoredMemory } from '@/lib/api';
import { cn } from '@/lib/utils';

const STATUS_TABS = [
  { value: '', label: '全部' },
  { value: 'candidate', label: '候选' },
  { value: 'active', label: '已生效' },
  { value: 'superseded', label: '已替代' },
];

type Tab = 'list' | 'recall' | 'conflicts';

export default function MemoryPage() {
  const [merchantId, setMerchantId] = useState('M001');
  const [tab, setTab] = useState<Tab>('list');
  const [statusFilter, setStatusFilter] = useState('');

  return (
    <div className="space-y-4">
      <PageHeader
        title="Merchant Memory"
        description="分层记忆治理：candidate → active 晋升、冲突检测与解决、HNSW 语义召回（pgvector 256 维）"
      />
      <LabelBanner label="SYNTHETIC" note="记忆从合成对话中抽取，不包含真实商家信息。" />
      <div className="flex flex-wrap items-center gap-3">
        <MerchantSelect merchantId={merchantId} onChange={setMerchantId} />
        <div className="flex gap-1 rounded-md border bg-white p-0.5 text-xs">
          {(
            [
              ['list', '记忆治理'],
              ['recall', '语义召回测试'],
              ['conflicts', '记忆冲突'],
            ] as [Tab, string][]
          ).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setTab(value)}
              className={cn('rounded px-3 py-1', tab === value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground')}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'list' && <ListTab merchantId={merchantId} statusFilter={statusFilter} setStatusFilter={setStatusFilter} />}
      {tab === 'recall' && <RecallTab merchantId={merchantId} />}
      {tab === 'conflicts' && <ConflictsTab merchantId={merchantId} />}
    </div>
  );
}

function ListTab({
  merchantId,
  statusFilter,
  setStatusFilter,
}: {
  merchantId: string;
  statusFilter: string;
  setStatusFilter: (value: string) => void;
}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['memories', merchantId, statusFilter],
    queryFn: () => api.listMemories(merchantId, statusFilter || undefined),
  });
  const promoteMutation = useMutation({
    mutationFn: api.promoteMemory,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['memories'] }),
  });

  return (
    <div className="space-y-3">
      <div className="flex gap-1 text-xs">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setStatusFilter(tab.value)}
            className={cn(
              'rounded-md border px-3 py-1',
              statusFilter === tab.value ? 'border-primary bg-primary/5 text-primary' : 'bg-white text-muted-foreground',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {query.isLoading && <LoadingCard />}
      {query.isError && <ErrorCard error={query.error} />}
      {query.data && query.data.length === 0 && <EmptyState text="暂无记忆，先在经营顾问中对话触发抽取" />}
      <div className="grid gap-2">
        {(query.data ?? []).map((memory) => (
          <Card key={memory.memory_id}>
            <CardContent className="flex flex-wrap items-start gap-3 p-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <Badge variant="secondary">{memory.type}</Badge>
                  <StatusBadge status={memory.status} />
                  <span className="text-muted-foreground">
                    重要性 {memory.importance} · 置信度 {memory.confidence} · 证据 {memory.evidence_count}
                  </span>
                </div>
                <p className="mt-1.5 text-sm">{memory.content}</p>
                <div className="mt-1 font-mono text-[10px] text-muted-foreground">
                  {memory.memory_id} · 更新 {fmtDateTime(memory.updated_at)}
                </div>
              </div>
              {memory.status === 'candidate' && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={promoteMutation.isPending}
                  onClick={() => promoteMutation.mutate(memory.memory_id)}
                >
                  <ArrowUpCircle className="mr-1 h-3.5 w-3.5" /> 晋升 active
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function RecallTab({ merchantId }: { merchantId: string }) {
  const [text, setText] = useState('');
  const [submitted, setSubmitted] = useState('');
  const query = useQuery({
    queryKey: ['memory-recall', merchantId, submitted],
    queryFn: () => api.recallMemory({ merchant_id: merchantId, query: submitted, top_k: 8 }),
    enabled: submitted.length > 0,
  });

  return (
    <div className="space-y-3">
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (text.trim()) setSubmitted(text.trim());
        }}
      >
        <input
          className="h-9 flex-1 rounded-md border bg-white px-3 text-sm"
          placeholder="输入查询，例如：这个商家预算波动大吗？"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <Button type="submit">
          <Search className="mr-1.5 h-4 w-4" /> 语义召回
        </Button>
      </form>
      {submitted && query.isLoading && <LoadingCard />}
      {query.isError && <ErrorCard error={query.error} />}
      <div className="grid gap-2">
        {(query.data ?? []).map((memory: ScoredMemory) => (
          <Card key={memory.memory_id}>
            <CardContent className="p-3">
              <div className="flex items-center gap-2 text-xs">
                <Badge variant="secondary">{memory.type}</Badge>
                <Badge variant="outline">score {memory.score.toFixed(3)}</Badge>
              </div>
              <p className="mt-1.5 text-sm">{memory.content}</p>
              {memory.reasons && memory.reasons.length > 0 && (
                <p className="mt-1 text-[11px] text-muted-foreground">打分因子：{memory.reasons.join('、')}</p>
              )}
            </CardContent>
          </Card>
        ))}
        {query.data && query.data.length === 0 && <EmptyState text="未召回到相关记忆" />}
      </div>
    </div>
  );
}

function ConflictsTab({ merchantId }: { merchantId: string }) {
  const query = useQuery({
    queryKey: ['memory-conflicts', merchantId],
    queryFn: () => api.listConflicts(merchantId),
  });
  return (
    <div className="space-y-2">
      {query.isLoading && <LoadingCard />}
      {query.isError && <ErrorCard error={query.error} />}
      {query.data && query.data.length === 0 && <EmptyState text="当前没有未解决的记忆冲突" />}
      {(query.data ?? []).map((conflict) => (
        <Card key={conflict.id}>
          <CardHeader className="pb-1">
            <CardTitle className="flex items-center gap-2 text-xs">
              <Badge variant={conflict.resolution === 'pending' ? 'destructive' : 'success'}>
                {conflict.resolution}
              </Badge>
              <span className="font-mono text-muted-foreground">{conflict.memory_id}</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {conflict.reason}
            <div className="mt-1 text-[11px] text-muted-foreground">{fmtDateTime(conflict.created_at)}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
