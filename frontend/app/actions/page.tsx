'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, Wrench } from 'lucide-react';
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
import { api, type ToolSpec } from '@/lib/api';
import { cn } from '@/lib/utils';

export default function ActionsPage() {
  const [activeTool, setActiveTool] = useState<string | null>(null);

  const toolsQuery = useQuery({ queryKey: ['tools'], queryFn: api.listTools });
  const callsQuery = useQuery({
    queryKey: ['tool-calls'],
    queryFn: () => api.recentToolCalls(50),
    refetchInterval: 10_000,
  });
  const tools = toolsQuery.data ?? [];
  const active = activeTool ?? tools[0]?.name ?? null;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Action Center"
        description="Agent 可用工具目录与真实调用审计：每次 Tool Calling 都记录参数、结果摘要、延迟与成败；高风险动作经人类确认执行"
      />
      <LabelBanner label="SYNTHETIC" note="工具作用于合成世界，调用会真实写库（如预算调整、计划暂停）。" />

      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <div className="space-y-2">
          {toolsQuery.isLoading && <LoadingCard />}
          {toolsQuery.isError && <ErrorCard error={toolsQuery.error} />}
          {tools.map((tool) => (
            <button
              key={tool.name}
              onClick={() => setActiveTool(tool.name)}
              className={cn(
                'w-full rounded-md border bg-white p-3 text-left text-xs hover:border-primary/50',
                active === tool.name && 'border-primary bg-primary/5',
              )}
            >
              <div className="flex items-center gap-2">
                <Wrench className="h-3.5 w-3.5 text-primary" />
                <span className="font-mono font-medium">{tool.name}</span>
                <Badge variant={tool.risk_level === 'high' ? 'destructive' : 'secondary'} className="ml-auto">
                  {tool.risk_level}
                </Badge>
              </div>
              <p className="mt-1 text-muted-foreground">{tool.description}</p>
              <p className="mt-0.5 text-[10px] text-muted-foreground">permission: {tool.permission}</p>
            </button>
          ))}
        </div>

        <div className="space-y-4">
          {active && <ToolInvoker tool={tools.find((item) => item.name === active)!} />}
          <Card>
            <CardHeader>
              <CardTitle>最近调用（{callsQuery.data?.length ?? 0}）</CardTitle>
            </CardHeader>
            <CardContent>
              {callsQuery.isLoading && <LoadingCard />}
              {callsQuery.data && callsQuery.data.length === 0 && <EmptyState text="暂无工具调用，去经营顾问跑一次诊断" />}
              <div className="space-y-1.5">
                {(callsQuery.data ?? []).map((call) => (
                  <div key={call.id} className="rounded-md border px-3 py-2 text-xs">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono font-medium">{call.tool_name}</span>
                      <StatusBadge status={call.success ? 'ok' : 'error'} />
                      {call.merchant_id && <span className="text-muted-foreground">{call.merchant_id}</span>}
                      <span className="ml-auto font-mono text-muted-foreground">
                        {call.latency_ms ?? '—'}ms · {fmtDateTime(call.created_at)}
                      </span>
                    </div>
                    <p className="mt-1 truncate font-mono text-[10px] text-muted-foreground">
                      args: {JSON.stringify(call.arguments)}
                    </p>
                    {call.result_summary && (
                      <p className="mt-0.5 truncate text-muted-foreground">→ {call.result_summary}</p>
                    )}
                    {call.error && <p className="mt-0.5 text-destructive">{call.error}</p>}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ToolInvoker({ tool }: { tool: ToolSpec }) {
  const queryClient = useQueryClient();
  const [argsText, setArgsText] = useState('{}');
  const mutation = useMutation({
    mutationFn: () => api.invokeTool(tool.name, JSON.parse(argsText) as Record<string, unknown>),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['tool-calls'] }),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="font-mono">{tool.name}</span>
          <Badge variant="outline">{tool.permission}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-xs text-muted-foreground">{tool.description}</p>
        <div>
          <div className="mb-1 text-[11px] font-medium text-muted-foreground">入参 schema</div>
          <pre className="max-h-40 overflow-auto rounded bg-muted/50 p-2 text-[11px]">
            {JSON.stringify(tool.input_schema, null, 2)}
          </pre>
        </div>
        <textarea
          className="min-h-[80px] w-full rounded-md border p-2 font-mono text-xs"
          value={argsText}
          onChange={(event) => setArgsText(event.target.value)}
        />
        <div className="flex items-center gap-2">
          <Button size="sm" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
            <Play className="mr-1 h-3.5 w-3.5" /> 调用工具
          </Button>
          {mutation.isError && <span className="text-xs text-destructive">{mutation.error.message}</span>}
        </div>
        {mutation.data && (
          <pre className="max-h-60 overflow-auto rounded bg-muted/50 p-2 text-[11px]">
            {JSON.stringify(mutation.data, null, 2)}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}
