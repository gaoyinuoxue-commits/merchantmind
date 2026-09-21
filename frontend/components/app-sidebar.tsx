'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  BarChart3,
  BookOpen,
  Bot,
  Boxes,
  FlaskConical,
  Gauge,
  History,
  LayoutDashboard,
  LibraryBig,
  Settings,
  Store,
  Wand2,
  Workflow,
  Zap,
} from 'lucide-react';

import { cn } from '@/lib/utils';

const NAV_GROUPS: {
  label: string;
  items: { name: string; href: string; icon: React.ElementType }[];
}[] = [
  {
    label: '工作台',
    items: [
      { name: '系统状态', href: '/', icon: LayoutDashboard },
      { name: 'AI 经营顾问', href: '/advisor', icon: Bot },
      { name: '商家中心', href: '/merchants', icon: Store },
      { name: 'Merchant Simulator', href: '/simulator', icon: Wand2 },
      { name: '对话历史', href: '/conversations', icon: History },
    ],
  },
  {
    label: '记忆与知识',
    items: [
      { name: 'Memory', href: '/memory', icon: LibraryBig },
      { name: 'Industry Knowledge', href: '/knowledge', icon: BookOpen },
      { name: 'Knowledge Candidate', href: '/knowledge-candidates', icon: Boxes },
    ],
  },
  {
    label: '工程与评估',
    items: [
      { name: 'Trace', href: '/traces', icon: Workflow },
      { name: 'Evaluation', href: '/evaluation', icon: BarChart3 },
      { name: 'Badcase', href: '/badcase', icon: Activity },
      { name: 'Experiment', href: '/experiments', icon: FlaskConical },
      { name: 'Action Center', href: '/actions', icon: Zap },
      { name: 'Monitoring', href: '/monitoring', icon: Gauge },
      { name: 'Settings', href: '/settings', icon: Settings },
    ],
  },
];

export function AppSidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r bg-white">
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-sm font-bold text-primary-foreground">
          M
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold">MerchantMind</div>
          <div className="text-[11px] text-muted-foreground">AI 商家经营诊断 Agent</div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-4">
            <div className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              {group.label}
            </div>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
                return (
                  <li key={item.name}>
                    <Link
                      href={item.href}
                      className={cn(
                        'flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] transition-colors',
                        active
                          ? 'bg-primary/10 font-medium text-primary'
                          : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                      )}
                    >
                      <item.icon className="h-4 w-4 shrink-0" />
                      <span className="flex-1 truncate">{item.name}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t px-4 py-3 text-[11px] text-muted-foreground">
        Synthetic Environment · Phase 20
      </div>
    </aside>
  );
}
