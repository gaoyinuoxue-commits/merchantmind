'use client';

import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Loader2 } from 'lucide-react';
import type { ReactNode } from 'react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { api, type MerchantSummary } from '@/lib/api';
import { cn } from '@/lib/utils';

export function LabelBanner({ label, note }: { label: string; note?: string }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
      <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
      <span className="font-medium">{label}</span>
      {note && <span className="text-amber-700">{note}</span>}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  badge,
}: {
  title: string;
  description?: string;
  badge?: string;
}) {
  return (
    <div className="mb-4">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold">{title}</h2>
        {badge && <Badge variant="secondary">{badge}</Badge>}
      </div>
      {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
    </div>
  );
}

export function LoadingCard({ text = '加载中…' }: { text?: string }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {text}
      </CardContent>
    </Card>
  );
}

export function ErrorCard({ error }: { error: unknown }) {
  return (
    <Card className="border-destructive/40">
      <CardContent className="p-4 text-sm text-destructive">
        {error instanceof Error ? error.message : '请求失败'}
      </CardContent>
    </Card>
  );
}

export function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
      {text}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: 'default' | 'good' | 'bad' | 'warn';
}) {
  const toneClass = {
    default: 'text-foreground',
    good: 'text-success',
    bad: 'text-destructive',
    warn: 'text-amber-600',
  }[tone];
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className={cn('mt-1 text-xl font-semibold', toneClass)}>
          {value === null || value === undefined || value === '' ? '—' : value}
        </div>
        {hint && <div className="mt-1 text-[11px] text-muted-foreground">{hint}</div>}
      </CardContent>
    </Card>
  );
}

export function MerchantSelect({
  merchantId,
  onChange,
  allowAll = false,
}: {
  merchantId: string;
  onChange: (id: string) => void;
  allowAll?: boolean;
}) {
  const { data } = useQuery({
    queryKey: ['merchants'],
    queryFn: api.listMerchants,
  });
  const merchants: MerchantSummary[] = data?.items ?? [];
  return (
    <select
      className="h-9 rounded-md border bg-white px-2 text-sm"
      value={merchantId}
      onChange={(event) => onChange(event.target.value)}
    >
      {allowAll && <option value="">全部商家</option>}
      {merchants.map((merchant) => (
        <option key={merchant.merchant_id} value={merchant.merchant_id}>
          {merchant.merchant_id} · {merchant.merchant_name}
        </option>
      ))}
    </select>
  );
}

export const fmtPct = (value: number | null | undefined, digits = 1) =>
  value === null || value === undefined ? '—' : `${(value * 100).toFixed(digits)}%`;

export const fmtNum = (value: number | null | undefined, digits = 0) =>
  value === null || value === undefined
    ? '—'
    : value.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits });

export const fmtSignedPct = (value: number | null | undefined, digits = 1) => {
  if (value === null || value === undefined) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}%`;
};

export const fmtDateTime = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, 'success' | 'destructive' | 'secondary' | 'default'> = {
    done: 'success',
    passed: 'success',
    fixed: 'success',
    ok: 'success',
    open: 'destructive',
    error: 'destructive',
    blocked: 'destructive',
    failed: 'destructive',
    in_review: 'default',
    confirmation_required: 'default',
    retry: 'default',
    wont_fix: 'secondary',
    ignored: 'secondary',
    clarified: 'secondary',
  };
  return <Badge variant={map[status] ?? 'secondary'}>{status}</Badge>;
}
