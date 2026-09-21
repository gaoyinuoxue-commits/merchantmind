'use client';

import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';

import { api, type HealthResponse } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

function StatusDot({ ok }: { ok: boolean }) {
  return ok ? (
    <CheckCircle2 className="h-4 w-4 text-success" />
  ) : (
    <XCircle className="h-4 w-4 text-destructive" />
  );
}

export function HealthPanel() {
  const { data, isLoading, isError, error, dataUpdatedAt } = useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 10_000,
  });

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在连接后端 /api/health …
        </CardContent>
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle>后端连接失败</CardTitle>
          <CardDescription>
            Frontend → Backend 链路异常，请确认 FastAPI 已在 http://localhost:8000 启动
          </CardDescription>
        </CardHeader>
        <CardContent className="text-xs text-muted-foreground">
          {error instanceof Error ? error.message : 'Unknown error'}
        </CardContent>
      </Card>
    );
  }

  const dbUp = data.database.status === 'up';
  const vectorReady = data.database.pgvector === 'installed';

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>Backend API</CardTitle>
            <CardDescription>FastAPI · uvicorn</CardDescription>
          </div>
          <StatusDot ok={data.status === 'ok'} />
        </CardHeader>
        <CardContent className="space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">状态</span>
            <Badge variant={data.status === 'ok' ? 'success' : 'secondary'}>
              {data.status}
            </Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">版本</span>
            <span className="font-mono">{data.version}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">环境</span>
            <span className="font-mono">{data.environment}</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>PostgreSQL</CardTitle>
            <CardDescription>业务数据 · Memory · Knowledge</CardDescription>
          </div>
          <StatusDot ok={dbUp} />
        </CardHeader>
        <CardContent className="space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">连接</span>
            <Badge variant={dbUp ? 'success' : 'destructive'}>
              {data.database.status}
            </Badge>
          </div>
          <div className="truncate text-muted-foreground" title={data.database.message}>
            {data.database.message}
          </div>
          {data.database.server_version && (
            <div className="truncate font-mono text-[11px] text-muted-foreground">
              {data.database.server_version}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>pgvector</CardTitle>
            <CardDescription>Embedding 向量检索</CardDescription>
          </div>
          <StatusDot ok={vectorReady} />
        </CardHeader>
        <CardContent className="space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">扩展</span>
            <Badge variant={vectorReady ? 'success' : 'secondary'}>
              {data.database.pgvector}
            </Badge>
          </div>
          <div className="text-muted-foreground">
            由后端启动时自动执行 CREATE EXTENSION IF NOT EXISTS vector
          </div>
        </CardContent>
      </Card>

      <p className="text-[11px] text-muted-foreground sm:col-span-2 lg:col-span-3">
        数据来自 GET /api/health（经 Next.js rewrite 同源代理到 FastAPI），每 10 秒刷新一次 ·
        最近刷新时间 {new Date(dataUpdatedAt).toLocaleTimeString('zh-CN')}
      </p>
    </div>
  );
}
