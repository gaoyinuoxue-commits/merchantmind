'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Send, ShieldAlert, Sparkles, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { LabelBanner, MerchantSelect, PageHeader } from '@/components/common';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { api, type AgentAction, type AgentRunResponse } from '@/lib/api';

interface Turn {
  id: number;
  user: string;
  response?: AgentRunResponse;
  error?: string;
}

const SUGGESTED = [
  '为什么最近 ROI 一直下滑，帮我诊断',
  '最近流量成本上涨，要不要加预算？',
  '有没有素材疲劳最后失败的真实案例',
  '帮我把预算降低 20%',
];

export default function AdvisorPage() {
  const queryClient = useQueryClient();
  const [merchantId, setMerchantId] = useState('M001');
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [input, setInput] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setTurns([]);
    setConversationId(undefined);
  }, [merchantId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns]);

  const runMutation = useMutation({
    mutationFn: (message: string) =>
      api.runAgent({ merchant_id: merchantId, message, conversation_id: conversationId }),
    onSuccess: (response) => {
      setConversationId(response.conversation_id);
      setTurns((prev) => {
        const next = [...prev];
        const pending = next[next.length - 1];
        if (pending && !pending.response && !pending.error) pending.response = response;
        return next;
      });
      void queryClient.invalidateQueries({ queryKey: ['traces'] });
    },
    onError: (error: Error) => {
      setTurns((prev) => {
        const next = [...prev];
        const pending = next[next.length - 1];
        if (pending) pending.error = error.message;
        return next;
      });
    },
  });

  const actMutation = useMutation({
    mutationFn: (params: { action: AgentAction; confirmed: boolean }) =>
      api.executeAction({
        merchant_id: merchantId,
        action: params.action,
        confirmed: params.confirmed,
      }),
  });

  const feedbackMutation = useMutation({
    mutationFn: (params: { rating: number; traceId: string }) =>
      api.submitFeedback({ rating: params.rating, trace_id: params.traceId, merchant_id: merchantId }),
  });

  const send = (text: string) => {
    const message = text.trim();
    if (!message || runMutation.isPending) return;
    setTurns((prev) => [...prev, { id: Date.now(), user: message }]);
    setInput('');
    runMutation.mutate(message);
  };

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <PageHeader
        title="AI 经营顾问"
        description="真实 Agent 管线：意图识别 → 规划 → 记忆/知识召回 → 工具观察 → 双假设归因 → 动作建议 → 人类确认 → 再观察"
        badge="SYNTHETIC"
      />
      <LabelBanner label="Demo/Simulation Metrics" note="回答基于合成商家世界中真实入库的经营数据计算，非真实经营建议。" />

      <div className="flex items-center gap-3">
        <MerchantSelect merchantId={merchantId} onChange={setMerchantId} />
        {conversationId && (
          <span className="text-xs text-muted-foreground">
            会话 <span className="font-mono">{conversationId}</span>
          </span>
        )}
      </div>

      <Card className="min-h-[420px]">
        <CardContent className="space-y-4 p-4">
          {turns.length === 0 && (
            <div className="space-y-3 py-6">
              <p className="text-sm text-muted-foreground">试着问一个经营问题：</p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTED.map((question) => (
                  <button
                    key={question}
                    className="rounded-full border px-3 py-1.5 text-xs hover:border-primary hover:bg-primary/5"
                    onClick={() => send(question)}
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((turn) => (
            <div key={turn.id} className="space-y-3">
              <div className="flex justify-end">
                <div className="max-w-[80%] whitespace-pre-wrap rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
                  {turn.user}
                </div>
              </div>

              {!turn.response && !turn.error && runMutation.isPending && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> 正在诊断…
                </div>
              )}
              {turn.error && (
                <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
                  {turn.error}
                </div>
              )}

              {turn.response && <ResponseTurn turn={turn.response} onAction={actMutation} onFeedback={feedbackMutation} />}
            </div>
          ))}
          <div ref={bottomRef} />
        </CardContent>
      </Card>

      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          send(input);
        }}
      >
        <input
          className="h-10 flex-1 rounded-md border bg-white px-3 text-sm"
          placeholder="输入经营问题，例如：换季流量下滑是什么原因？"
          value={input}
          onChange={(event) => setInput(event.target.value)}
        />
        <Button type="submit" disabled={runMutation.isPending || !input.trim()}>
          <Send className="mr-1.5 h-4 w-4" /> 发送
        </Button>
      </form>
    </div>
  );
}

function ResponseTurn({
  turn,
  onAction,
  onFeedback,
}: {
  turn: AgentRunResponse;
  onAction: ReturnType<typeof useMutation<Record<string, unknown>, Error, { action: AgentAction; confirmed: boolean }>>;
  onFeedback: ReturnType<typeof useMutation<Record<string, unknown>, Error, { rating: number; traceId: string }>>;
}) {
  const diagnosis = turn.diagnosis as {
    primary_cause?: { title: string; confidence: number; explanation: string };
    quality_score?: number;
  } | null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="secondary">意图：{turn.intent.intent} · {turn.intent.confidence}</Badge>
        {turn.quality_retried && <Badge>已补证重试</Badge>}
        {turn.needs_clarification && <Badge variant="destructive">需要澄清</Badge>}
        <span className="font-mono text-muted-foreground">trace: {turn.trace_id}</span>
      </div>

      <div className="whitespace-pre-wrap rounded-lg border bg-white px-3 py-2 text-sm leading-6">
        {turn.reply}
      </div>

      {turn.needs_clarification && turn.clarification_question && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
          {turn.clarification_question}
        </div>
      )}

      {diagnosis?.primary_cause && (
        <div className="grid gap-2 text-xs sm:grid-cols-2">
          <Info title="主要归因">
            {diagnosis.primary_cause.title}（{diagnosis.primary_cause.confidence}）
          </Info>
          <Info title="证据质量分 quality_score">{diagnosis.quality_score ?? '—'}</Info>
        </div>
      )}

      {(turn.memory.length > 0 || turn.knowledge.length > 0) && (
        <div className="grid gap-2 text-xs sm:grid-cols-2">
          {turn.memory.length > 0 && (
            <Info title={`召回记忆 ${turn.memory.length} 条`}>
              {turn.memory.slice(0, 3).map((memory) => (
                <div key={memory.memory_id} className="truncate">
                  · [{memory.type}] {memory.content}
                </div>
              ))}
            </Info>
          )}
          {turn.knowledge.length > 0 && (
            <Info title={`引用知识 ${turn.knowledge.length} 条`}>
              {turn.knowledge.slice(0, 3).map((item) => (
                <div key={item.knowledge_id} className="truncate">
                  · {item.title}
                </div>
              ))}
            </Info>
          )}
        </div>
      )}

      {turn.actions.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-muted-foreground">建议动作（Action Loop）</div>
          {turn.actions.map((action, index) => (
            <ActionRow key={`${action.title}-${index}`} action={action} onAction={onAction} />
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>这条回答有帮助吗？</span>
        <Button
          variant="outline"
          size="sm"
          disabled={onFeedback.isPending}
          onClick={() => onFeedback.mutate({ rating: 5, traceId: turn.trace_id })}
        >
          <ThumbsUp className="mr-1 h-3.5 w-3.5" /> 有帮助
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={onFeedback.isPending}
          onClick={() => onFeedback.mutate({ rating: 2, traceId: turn.trace_id })}
        >
          <ThumbsDown className="mr-1 h-3.5 w-3.5" /> 不准确
        </Button>
        {onFeedback.isSuccess && <span className="text-success">反馈已记录（自动进入反馈闭环）</span>}
        {onFeedback.isError && <span className="text-destructive">{onFeedback.error.message}</span>}
      </div>
    </div>
  );
}

function Info({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border bg-muted/30 p-2.5">
      <div className="mb-1 font-medium text-muted-foreground">{title}</div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function ActionRow({
  action,
  onAction,
}: {
  action: AgentAction;
  onAction: ReturnType<typeof useMutation<Record<string, unknown>, Error, { action: AgentAction; confirmed: boolean }>>;
}) {
  const [state, setState] = useState<'idle' | 'confirming' | 'done'>('idle');
  const pending = onAction.isPending && onAction.variables?.action === action;
  const result = onAction.data;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-white p-2.5 text-xs">
      <Sparkles className="h-3.5 w-3.5 text-primary" />
      <span className="font-medium">{action.title}</span>
      <Badge variant={action.risk_level === 'high' ? 'destructive' : 'secondary'}>
        {action.risk_level}
      </Badge>
      <span className="text-muted-foreground">
        {action.requires_confirmation ? '需人类确认' : '可直接执行'}
      </span>
      <div className="ml-auto flex items-center gap-2">
        {state === 'done' && result ? (
          <span className="text-success">
            已执行：{JSON.stringify((result as { effect_summary?: unknown }).effect_summary ?? result).slice(0, 120)}
          </span>
        ) : action.requires_confirmation && state !== 'confirming' ? (
          <Button size="sm" variant="outline" onClick={() => setState('confirming')}>
            请求确认
          </Button>
        ) : (
          <>
            {action.requires_confirmation && <span className="text-amber-700">确认后将真实写库并推进模拟</span>}
            <Button
              size="sm"
              disabled={pending}
              onClick={() => {
                onAction.mutate(
                  { action, confirmed: action.requires_confirmation },
                  { onSuccess: () => setState('done') },
                );
              }}
            >
              {pending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : null}
              {action.requires_confirmation ? '确认执行' : '直接执行'}
            </Button>
            {action.requires_confirmation && (
              <Button size="sm" variant="ghost" onClick={() => setState('idle')}>
                取消
              </Button>
            )}
          </>
        )}
      </div>
      {onAction.isError && onAction.variables?.action === action && (
        <span className="w-full text-destructive">{onAction.error.message}</span>
      )}
    </div>
  );
}
