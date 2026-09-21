'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { ErrorCard, LabelBanner, LoadingCard, MerchantSelect, PageHeader, fmtNum } from '@/components/common';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api, type AdvanceResponse, type PerformanceRow } from '@/lib/api';

const EFFECT_TYPES = [
  { value: 'budget_change', label: '调整预算（factor 倍数）' },
  { value: 'campaign_pause', label: '暂停计划' },
  { value: 'new_material', label: '上新素材' },
  { value: 'traffic_cost_increase', label: '流量成本上涨（spend_factor）' },
  { value: 'demand', label: '需求变化（factor）' },
];

interface EffectDraft {
  type: string;
  factor?: number;
  spend_factor?: number;
  ctr_factor?: number;
  campaign_id?: string;
  material_type?: string;
  material_name?: string;
}

export default function SimulatorPage() {
  const queryClient = useQueryClient();
  const [merchantId, setMerchantId] = useState('M001');
  const [days, setDays] = useState(7);
  const [effects, setEffects] = useState<EffectDraft[]>([]);
  const [lastResult, setLastResult] = useState<AdvanceResponse | null>(null);

  const stateQuery = useQuery({
    queryKey: ['simulator-state', merchantId],
    queryFn: () => api.simulatorState(merchantId),
  });

  const advanceMutation = useMutation({
    mutationFn: () =>
      api.simulatorAdvance({
        merchant_id: merchantId,
        days,
        effects: effects.map((effect) => {
          const cleaned: Record<string, unknown> = { type: effect.type };
          (['factor', 'spend_factor', 'ctr_factor'] as const).forEach((key) => {
            if (effect[key] !== undefined && Number.isFinite(effect[key])) cleaned[key] = effect[key];
          });
          (['campaign_id', 'material_type', 'material_name'] as const).forEach((key) => {
            if (effect[key]) cleaned[key] = effect[key];
          });
          return cleaned;
        }),
      }),
    onSuccess: (result) => {
      setLastResult(result);
      setEffects([]);
      void queryClient.invalidateQueries({ queryKey: ['simulator-state', merchantId] });
      void queryClient.invalidateQueries({ queryKey: ['merchant', merchantId] });
    },
  });

  const addEffect = () =>
    setEffects((prev) => [...prev, { type: 'budget_change', factor: 1.1 }]);

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <PageHeader
        title="Merchant Simulator"
        description="驱动合成世界时间前进并注入干预/外部事件，Agent 动作执行后同样通过该引擎观察后验效果（Observe Again）"
      />
      <LabelBanner label="SYNTHETIC" note="模拟结果由合成世界引擎基于真实入库数据计算，用于验证动作后验效果。" />

      <div className="flex flex-wrap items-center gap-3">
        <MerchantSelect merchantId={merchantId} onChange={setMerchantId} />
        {stateQuery.data?.current_date && (
          <span className="text-xs text-muted-foreground">
            世界当前日期：<span className="font-mono">{stateQuery.data.current_date}</span>
          </span>
        )}
      </div>

      {stateQuery.isLoading && <LoadingCard />}
      {stateQuery.isError && <ErrorCard error={stateQuery.error} />}
      {stateQuery.data && (
        <Card>
          <CardHeader>
            <CardTitle>最近 7 天窗口指标</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(stateQuery.data.last_7d).map(([key, value]) => (
                <div key={key} className="rounded-md border p-3">
                  <div className="text-xs text-muted-foreground">{key}</div>
                  <div className="mt-1 text-lg font-semibold">{fmtNum(value, 2)}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>注入效果 / 事件</CardTitle>
          <Button size="sm" variant="outline" onClick={addEffect}>
            <Plus className="mr-1 h-3.5 w-3.5" /> 添加效果
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {effects.length === 0 && (
            <p className="text-xs text-muted-foreground">不添加效果即纯时间推进（自然演化）。</p>
          )}
          {effects.map((effect, index) => (
            <div key={index} className="flex flex-wrap items-center gap-2 rounded-md border p-2 text-xs">
              <select
                className="h-8 rounded-md border px-2"
                value={effect.type}
                onChange={(event) =>
                  setEffects((prev) => prev.map((item, i) => (i === index ? { ...item, type: event.target.value } : item)))
                }
              >
                {EFFECT_TYPES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              {['budget_change', 'demand'].includes(effect.type) && (
                <NumberField label="factor" value={effect.factor} onChange={(v) => update(setEffects, index, 'factor', v, effects)} />
              )}
              {effect.type === 'traffic_cost_increase' && (
                <NumberField label="spend_factor" value={effect.spend_factor} onChange={(v) => update(setEffects, index, 'spend_factor', v, effects)} />
              )}
              {effect.type === 'new_material' && (
                <>
                  <input
                    className="h-8 w-32 rounded-md border px-2"
                    placeholder="material_type"
                    value={effect.material_type ?? ''}
                    onChange={(event) =>
                      setEffects((prev) => prev.map((item, i) => (i === index ? { ...item, material_type: event.target.value } : item)))
                    }
                  />
                  <input
                    className="h-8 w-40 rounded-md border px-2"
                    placeholder="material_name"
                    value={effect.material_name ?? ''}
                    onChange={(event) =>
                      setEffects((prev) => prev.map((item, i) => (i === index ? { ...item, material_name: event.target.value } : item)))
                    }
                  />
                </>
              )}
              {['campaign_pause', 'budget_change'].includes(effect.type) && (
                <input
                  className="h-8 w-32 rounded-md border px-2 font-mono"
                  placeholder="campaign_id"
                  value={effect.campaign_id ?? ''}
                  onChange={(event) =>
                    setEffects((prev) => prev.map((item, i) => (i === index ? { ...item, campaign_id: event.target.value } : item)))
                  }
                />
              )}
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setEffects((prev) => prev.filter((_, i) => i !== index))}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}

          <div className="flex items-center gap-3">
            <label className="text-xs text-muted-foreground">推进天数</label>
            <input
              type="number"
              min={1}
              max={30}
              className="h-8 w-20 rounded-md border px-2"
              value={days}
              onChange={(event) => setDays(Math.min(30, Math.max(1, Number(event.target.value) || 1)))}
            />
            <Button
              disabled={advanceMutation.isPending}
              onClick={() => advanceMutation.mutate()}
            >
              <Play className="mr-1.5 h-4 w-4" />
              {advanceMutation.isPending ? '推进中…' : '推进世界'}
            </Button>
            {advanceMutation.isError && (
              <span className="text-xs text-destructive">{advanceMutation.error.message}</span>
            )}
          </div>
        </CardContent>
      </Card>

      {lastResult && <ResultPanel result={lastResult} />}
    </div>
  );
}

function update(
  setter: React.Dispatch<React.SetStateAction<EffectDraft[]>>,
  index: number,
  key: 'factor' | 'spend_factor' | 'ctr_factor',
  value: number | undefined,
  effects: EffectDraft[],
) {
  setter(effects.map((item, i) => (i === index ? { ...item, [key]: value } : item)));
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value?: number;
  onChange: (value: number | undefined) => void;
}) {
  return (
    <label className="flex items-center gap-1 text-muted-foreground">
      {label}
      <input
        type="number"
        step={0.05}
        className="h-8 w-24 rounded-md border px-2 font-mono"
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value === '' ? undefined : Number(event.target.value))}
      />
    </label>
  );
}

function ResultPanel({ result }: { result: AdvanceResponse }) {
  const rows: PerformanceRow[] = result.performance;
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          推进结果：{result.from_date} → {result.to_date}（+{result.days_added} 天）
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {result.events_emitted.length > 0 && (
          <div>
            <div className="mb-1 text-xs font-medium text-muted-foreground">触发事件</div>
            <ul className="space-y-1 text-xs">
              {result.events_emitted.map((event, index) => (
                <li key={index} className="rounded bg-muted/50 px-2 py-1 font-mono">
                  {JSON.stringify(event)}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr>
                {['date', 'gmv', 'ad_spend', 'impressions', 'clicks', 'ctr', 'cpm', 'roi'].map((key) => (
                  <th key={key} className="px-2 py-1">{key}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.date} className="border-t">
                  <td className="px-2 py-1 font-mono">{row.date}</td>
                  <td className="px-2">{fmtNum(row.gmv, 0)}</td>
                  <td className="px-2">{fmtNum(row.ad_spend, 0)}</td>
                  <td className="px-2">{fmtNum(row.impressions)}</td>
                  <td className="px-2">{fmtNum(row.clicks)}</td>
                  <td className="px-2">{(row.ctr * 100).toFixed(2)}%</td>
                  <td className="px-2">{row.cpm.toFixed(1)}</td>
                  <td className="px-2">{row.roi.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
