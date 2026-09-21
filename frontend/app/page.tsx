'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';

import { ErrorCard, LabelBanner, StatCard, fmtPct } from '@/components/common';
import { HealthPanel } from '@/components/health-panel';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '@/lib/api';

const QUICK_LINKS = [
  { href: '/advisor', title: 'AI 经营顾问', desc: '诊断 Loop：Observe → Think → Act' },
  { href: '/merchants', title: '商家中心', desc: '合成商家、投放计划、素材与经营曲线' },
  { href: '/monitoring', title: 'Monitoring', desc: '在线监控与三层 KPI' },
  { href: '/evaluation', title: 'Evaluation', desc: '54 case 离线评测与人工评分' },
  { href: '/experiments', title: 'Experiment', desc: 'RunProfile 驱动的 A/B 实验' },
  { href: '/badcase', title: 'Badcase', desc: '失败自动分诊与反馈闭环' },
];

export default function HomePage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['monitoring', 'overview', 30],
    queryFn: () => api.monitoringOverview(30),
    refetchInterval: 15_000,
  });
  const monitoring = data?.monitoring;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <section>
        <div className="mb-2 flex items-center gap-2">
          <h2 className="text-xl font-semibold">MerchantMind</h2>
          <Badge variant="secondary">v0.1.0 · Phase 20</Badge>
          <Badge variant="outline">Synthetic Environment</Badge>
        </div>
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
          面向电商商家的 AI 经营诊断 Agent。Synthetic Merchant World 提供真实入库的经营数据，结合
          Merchant Memory、Industry Knowledge 与 Tool Calling，跑通意图识别 → 规划 → 归因 →
          动作建议 → 人类确认 → 再观察的完整闭环，全程 Trace / 评测 / 实验 / 监控可观测。
        </p>
      </section>

      <LabelBanner
        label="Demo/Simulation Metrics"
        note="本环境全部为合成数据；经营结果类指标标注 Synthetic Business Metrics，不代表真实业务表现。"
      />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="请求数（30 天）"
          value={monitoring?.requests ?? (isLoading ? '…' : '—')}
          hint={`成功 ${monitoring?.succeeded ?? 0} · 澄清 ${monitoring?.clarifications ?? 0}`}
        />
        <StatCard
          label="成功率"
          value={monitoring ? fmtPct(monitoring.success_rate as number | null) : isLoading ? '…' : '—'}
          tone="good"
        />
        <StatCard
          label="工具失败率"
          value={monitoring ? fmtPct(monitoring.tool_failure_rate as number | null) : isLoading ? '…' : '—'}
          tone={(monitoring?.tool_failure_rate as number | null) ? 'bad' : 'good'}
        />
        <StatCard
          label="幻觉率 / P95 延迟"
          value={
            monitoring
              ? `${fmtPct(monitoring.hallucination_rate as number | null)} / ${monitoring.latency_p95_ms ?? '—'}ms`
              : isLoading
                ? '…'
                : '—'
          }
        />
        <StatCard
          label="记忆写入 / 冲突"
          value={monitoring ? `${monitoring.memory_writes} / ${monitoring.memory_conflicts}` : '—'}
        />
        <StatCard
          label="检索 Miss 率"
          value={monitoring ? fmtPct(monitoring.retrieval_miss_rate as number | null) : '—'}
          tone="warn"
        />
        <StatCard
          label="重试率"
          value={monitoring ? fmtPct(monitoring.retry_rate as number | null) : '—'}
        />
        <StatCard
          label="Helpful Rate"
          value={monitoring ? fmtPct(monitoring.helpful_rate as number | null) : '—'}
          hint={`${monitoring?.feedback_count ?? 0} 条反馈`}
        />
      </section>

      {isError && <ErrorCard error={error} />}

      <section>
        <h3 className="mb-3 text-sm font-semibold">系统状态</h3>
        <HealthPanel />
      </section>

      <section>
        <h3 className="mb-3 text-sm font-semibold">快捷入口</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {QUICK_LINKS.map((item) => (
            <Link key={item.href} href={item.href}>
              <Card className="h-full transition-colors hover:border-primary/50 hover:bg-primary/5">
                <CardHeader>
                  <CardTitle>{item.title}</CardTitle>
                </CardHeader>
                <CardContent className="text-xs text-muted-foreground">{item.desc}</CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
