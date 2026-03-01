import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { StatusPill } from './StatusPill';
import {
  LayoutDashboard,
  BarChart3,
  TrendingUp,
  DollarSign,
  Handshake,
  Radio,
  GraduationCap,
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/polymarket', label: 'Polymarket', icon: BarChart3 },
  { to: '/hyperliquid', label: 'Hyperliquid', icon: TrendingUp },
  { to: '/alpaca', label: 'Alpaca', icon: DollarSign },
  { to: '/consensus', label: 'Consensus', icon: Handshake },
  { to: '/signals', label: 'Signals', icon: Radio },
  { to: '/learning', label: 'Learning', icon: GraduationCap },
] as const;

export function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-56 flex-col border-r border-sidebar-border bg-sidebar">
      <div className="flex items-center gap-2 border-b border-sidebar-border px-4 py-4">
        <span className="text-lg font-bold text-sidebar-foreground">
          Trader Curtis
        </span>
        <StatusPill />
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-sidebar-accent text-sidebar-primary'
                  : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground',
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-sidebar-border px-4 py-3 text-xs text-muted-foreground">
        Auto-refresh: 30s
      </div>
    </aside>
  );
}
