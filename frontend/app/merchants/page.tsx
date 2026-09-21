'use client';

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { EmptyState, ErrorCard, LabelBanner, LoadingCard, PageHeader, StatusBadge, fmtNum } from '@/components/common';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api, type MerchantDetail } from '@/lib/api';
import { cn } from '@/lib/utils';

export default function MerchantsPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const listing = useQuery({ queryKey: ['merchants'], queryFn: api.listMerchants });

  if (listing.isLoading) return <LoadingCard text="加载合成商家…" />;
  if (listing.isError) return <ErrorCard error={listing.error} />;

  const merchants = listing.data?.items ?? [];
  const current = selected ?? merchants[0]?.merchant_id ?? null;

  return (
    <div className="space-y-4">
      <PageHeader
        title="商家中心"
        description="Synthetic Merchant World：商家档案、近 30 天经营曲线、投放计划与素材状态全部来自真实入库数据"
      />
      <LabelBanner label="SYNTHETIC" note="商家与经营数据均为合成生成，仅用于演示。" />

      <div className="flex flex-wrap gap-2">
        {merchants.map((merchant) => (
          <button
            key={merchant.merchant_id}
            onClick={() => setSelected(merchant.merchant_id)}
            className={cn(
              'rounded-md border px-3 py-2 text-left text-xs transition-colors',
              current === merchant.merchant_id
                ? 'border-primary bg-primary/5'
                : 'bg-white hover:border-primary/40',
            )}
          >
            <div className="font-medium">{merchant.merchant_name}</div>
            <div className="text-muted-foreground">
              {merchant.merchant_id} · {merchant.industry} · {merchant.business_stage}
            </div>
          </button>
        ))}
      </div>

      {current && <MerchantDetailPanel merchantId={current} />}
      {!current && <EmptyState text="暂无商家，请先运行 seed" />}
    </div>
  );
}

function MerchantDetailPanel({ merchantId }: { merchantId: string }) {
  const query = useQuery({
    queryKey: ['merchant', merchantId],
    queryFn: () => api.getMerchant(merchantId),
  });
  if (query.isLoading) return <LoadingCard />;
  if (query.isError) return <ErrorCard error={query.error} />;
  const merchant: MerchantDetail = query.data!;
  const chartData = merchant.performance.map((row) => ({
    date: row.date.slice(5),
    GMV: Math.round(row.gmv),
    广告花费: Math.round(row.ad_spend),
    ROI: Number(row.roi.toFixed(2)),
    CTRpct: Number((row.ctr * 100).toFixed(2)),
  }));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            {merchant.merchant_name}
            <Badge variant="secondary">{merchant.industry}</Badge>
            <Badge variant="outline">{merchant.business_stage}</Badge>
            {merchant.gmv_level && <Badge variant="outline">GMV {merchant.gmv_level}</Badge>}
            {merchant.city && <span className="text-xs text-muted-foreground">{merchant.city}</span>}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 lg:grid-cols-2">
          <ChartCard title="GMV / 广告花费（近 30 天，SYNTHETIC）">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" fontSize={10} interval={3} />
                <YAxis fontSize={10} tickFormatter={(v) => fmtNum(v as number)} />
                <Tooltip />
                <Legend />
                <Bar dataKey="GMV" fill="hsl(221 83% 53%)" />
                <Bar dataKey="广告花费" fill="hsl(24 95% 53%)" />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
          <ChartCard title="ROI / CTR%（近 30 天）">
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" fontSize={10} interval={3} />
                <YAxis fontSize={10} yAxisId="left" />
                <YAxis fontSize={10} yAxisId="right" orientation="right" unit="%" />
                <Tooltip />
                <Legend />
                <Line yAxisId="left" type="monotone" dataKey="ROI" stroke="hsl(142 71% 45%)" dot={false} />
                <Line yAxisId="right" type="monotone" dataKey="CTRpct" stroke="hsl(262 83% 58%)" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>投放计划（{merchant.campaigns.length}）</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-left text-xs">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="py-1">ID</th>
                  <th>名称</th>
                  <th>目标</th>
                  <th className="text-right">日预算</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {merchant.campaigns.map((campaign) => (
                  <tr key={campaign.campaign_id} className="border-t">
                    <td className="py-1.5 font-mono">{campaign.campaign_id}</td>
                    <td>{campaign.campaign_name}</td>
                    <td>{campaign.objective}</td>
                    <td className="text-right">{fmtNum(campaign.budget)}</td>
                    <td><StatusBadge status={campaign.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>素材（{merchant.materials.length}）</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-left text-xs">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="py-1">ID</th>
                  <th>名称</th>
                  <th>类型</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {merchant.materials.map((material) => (
                  <tr key={material.material_id} className="border-t">
                    <td className="py-1.5 font-mono">{material.material_id}</td>
                    <td>{material.material_name}</td>
                    <td>{material.material_type}</td>
                    <td><StatusBadge status={material.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border p-3">
      <div className="mb-2 text-xs font-medium text-muted-foreground">{title}</div>
      {children}
    </div>
  );
}
