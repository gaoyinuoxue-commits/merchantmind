'use client';

import { useQuery } from '@tanstack/react-query';

import { ErrorCard, LabelBanner, LoadingCard, PageHeader, StatusBadge } from '@/components/common';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '@/lib/api';

const ENDPOINTS = [
  { method: 'GET', path: '/api/health', desc: 'API / PostgreSQL / pgvector 健康检查' },
  { method: 'GET', path: '/api/merchants', desc: '合成商家目录与经营详情' },
  { method: 'POST', path: '/api/simulator/advance', desc: '合成世界时间推进与效果注入' },
  { method: 'POST', path: '/api/agent/run · /api/agent/act', desc: 'Agent 诊断 Loop 与动作执行' },
  { method: 'GET', path: '/api/memories · /api/knowledge', desc: '记忆治理 / 召回与知识 RAG' },
  { method: 'GET', path: '/api/traces', desc: '端到端 Trace' },
  { method: 'POST', path: '/api/eval/runs', desc: '54 case 离线评测（rule / heuristic）' },
  { method: 'POST', path: '/api/feedback · /api/badcases', desc: '反馈闭环与自动分诊' },
  { method: 'POST', path: '/api/experiments', desc: 'RunProfile A/B 实验' },
  { method: 'GET', path: '/api/monitoring/overview', desc: '三层监控指标聚合' },
];

const LABEL_POLICY = [
  { label: 'SYNTHETIC', desc: '全部业务数据（商家、经营、对话、记忆、知识）均为合成生成' },
  { label: 'Demo/Simulation Metrics', desc: '在线监控、评测、实验指标来自合成环境真实运行，不代表线上表现' },
  { label: 'Synthetic Business Metrics', desc: 'ROI/CTR/GMV 等经营结果指标仅演示北极星指标设计' },
];

export default function SettingsPage() {
  const healthQuery = useQuery({ queryKey: ['health'], queryFn: api.health });

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <PageHeader title="Settings" description="环境信息、指标标注约定与 API 目录" />
      <LabelBanner label="Synthetic Environment" note="本部署不含任何真实商家数据。" />

      <Card>
        <CardHeader>
          <CardTitle>运行环境</CardTitle>
        </CardHeader>
        <CardContent>
          {healthQuery.isLoading && <LoadingCard />}
          {healthQuery.isError && <ErrorCard error={healthQuery.error} />}
          {healthQuery.data && (
            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <Info label="Backend">
                <StatusBadge status={healthQuery.data.status === 'ok' ? 'ok' : 'error'} />
                <span className="ml-2 font-mono text-xs">
                  {healthQuery.data.service} v{healthQuery.data.version}
                </span>
              </Info>
              <Info label="Environment">
                <span className="font-mono text-xs">{healthQuery.data.environment}</span>
              </Info>
              <Info label="PostgreSQL">
                <StatusBadge status={healthQuery.data.database.status === 'up' ? 'ok' : 'error'} />
                <span className="ml-2 font-mono text-xs">
                  {healthQuery.data.database.server_version}
                </span>
              </Info>
              <Info label="pgvector">
                <StatusBadge status={healthQuery.data.database.pgvector === 'installed' ? 'ok' : 'error'} />
                <span className="ml-2 font-mono text-xs">{healthQuery.data.database.pgvector}</span>
              </Info>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>指标标注约定</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {LABEL_POLICY.map((item) => (
            <div key={item.label} className="flex items-start gap-3 rounded-md border p-3 text-xs">
              <span className="shrink-0 rounded bg-amber-100 px-2 py-0.5 font-medium text-amber-800">
                {item.label}
              </span>
              <span className="text-muted-foreground">{item.desc}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>API 目录</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-left text-xs">
            <tbody>
              {ENDPOINTS.map((endpoint) => (
                <tr key={endpoint.path} className="border-b last:border-0">
                  <td className="w-16 py-2">
                    <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                      {endpoint.method}
                    </span>
                  </td>
                  <td className="py-2 font-mono text-[11px]">{endpoint.path}</td>
                  <td className="py-2 text-muted-foreground">{endpoint.desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function Info({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border p-3">
      <div className="mb-1.5 text-xs text-muted-foreground">{label}</div>
      <div className="flex items-center">{children}</div>
    </div>
  );
}
