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
  fmtDateTime,
} from '@/components/common';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { api, type ConversationSummary } from '@/lib/api';
import { cn } from '@/lib/utils';

export default function ConversationsPage() {
  const [merchantId, setMerchantId] = useState('M001');
  const [activeId, setActiveId] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ['conversations', merchantId],
    queryFn: () => api.listConversations(merchantId),
  });
  const detailQuery = useQuery({
    queryKey: ['conversation', activeId],
    queryFn: () => api.getConversation(activeId!),
    enabled: activeId !== null,
  });

  const conversations: ConversationSummary[] = listQuery.data ?? [];
  const active = activeId ?? conversations[0]?.conversation_id ?? null;

  return (
    <div className="space-y-4">
      <PageHeader title="对话历史" description="商家与经营顾问的全部真实会话，助手消息保留意图、归因、动作等结构化 meta" />
      <LabelBanner label="SYNTHETIC" note="对话由合成商家场景产生。" />
      <MerchantSelect merchantId={merchantId} onChange={(id) => { setMerchantId(id); setActiveId(null); }} />

      {listQuery.isLoading && <LoadingCard />}
      {listQuery.isError && <ErrorCard error={listQuery.error} />}

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <Card>
          <CardContent className="p-2">
            {conversations.length === 0 && <div className="p-4 text-xs text-muted-foreground">暂无会话，先去 AI 经营顾问发起对话</div>}
            {conversations.map((conversation) => (
              <button
                key={conversation.conversation_id}
                onClick={() => setActiveId(conversation.conversation_id)}
                className={cn(
                  'w-full rounded-md px-3 py-2 text-left text-xs hover:bg-muted',
                  active === conversation.conversation_id && 'bg-primary/10',
                )}
              >
                <div className="truncate font-medium">
                  {conversation.title || conversation.conversation_id}
                </div>
                <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                  {conversation.conversation_id} · {fmtDateTime(conversation.updated_at)}
                </div>
              </button>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-4">
            {!active && <EmptyState text="选择左侧会话查看消息" />}
            {active && detailQuery.isLoading && <LoadingCard />}
            {active && detailQuery.isError && <ErrorCard error={detailQuery.error} />}
            {detailQuery.data?.messages.map((message) => {
              const meta = (message.meta ?? {}) as {
                intent?: { intent: string; confidence: number };
                needs_clarification?: boolean;
                quality_retried?: boolean;
                label?: string;
              };
              return (
                <div key={message.message_id} className={cn('flex', message.role === 'user' ? 'justify-end' : 'justify-start')}>
                  <div
                    className={cn(
                      'max-w-[85%] rounded-lg px-3 py-2 text-sm',
                      message.role === 'user'
                        ? 'bg-primary text-primary-foreground'
                        : 'border bg-white',
                    )}
                  >
                    {message.role === 'assistant' && meta.intent && (
                      <div className="mb-1.5 flex flex-wrap gap-1">
                        <Badge variant="secondary">
                          {meta.intent.intent} · {meta.intent.confidence}
                        </Badge>
                        {meta.needs_clarification && <Badge variant="destructive">已澄清</Badge>}
                        {meta.quality_retried && <Badge>补证重试</Badge>}
                      </div>
                    )}
                    <div className="whitespace-pre-wrap leading-6">{message.content}</div>
                    <div className={cn('mt-1 text-[10px]', message.role === 'user' ? 'text-primary-foreground/70' : 'text-muted-foreground')}>
                      {fmtDateTime(message.created_at)}
                    </div>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
