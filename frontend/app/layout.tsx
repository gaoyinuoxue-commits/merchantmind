import type { Metadata } from 'next';

import './globals.css';
import { Providers } from '@/components/providers';
import { AppSidebar } from '@/components/app-sidebar';

export const metadata: Metadata = {
  title: 'MerchantMind · AI 商家经营诊断 Agent',
  description:
    'Synthetic Merchant World 驱动的 AI 经营诊断 Agent：Memory + Knowledge + Tool Calling + Action Loop',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <Providers>
          <div className="flex min-h-screen bg-muted/40">
            <AppSidebar />
            <main className="flex-1 overflow-y-auto">
              <header className="flex h-14 items-center justify-between border-b bg-white px-6">
                <h1 className="text-sm font-medium text-muted-foreground">
                  MerchantMind 控制台 · Observe → Think → Act → Observe Again
                </h1>
                <span className="text-xs text-muted-foreground">
                  所有数据均为 Synthetic Demo Data
                </span>
              </header>
              <div className="p-6">{children}</div>
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
