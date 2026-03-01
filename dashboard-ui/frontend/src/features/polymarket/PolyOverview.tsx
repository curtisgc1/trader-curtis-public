import { usePolymarketOverview } from '@/hooks/use-polymarket';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { MarginBar } from '@/components/shared/MarginBar';
import { fmtUsd, pnlClass } from '@/lib/format';
import { cn } from '@/lib/utils';

interface PolyOverviewData {
  mode?: string;
  wallet?: string;
  daily_cap_usd?: number;
  daily_used_usd?: number;
  filled_live?: number;
  submitted_live?: number;
  pending_approval?: number;
  failed?: number;
  positions_count?: number;
  total_upnl?: number;
  [key: string]: unknown;
}

function StatRow({ label, value, valueClass }: { label: string; value: React.ReactNode; valueClass?: string }) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn('text-sm font-mono font-medium', valueClass)}>{value}</span>
    </div>
  );
}

export function PolyOverview() {
  const { data, isLoading } = usePolymarketOverview();
  const overview = (data ?? {}) as PolyOverviewData;

  if (isLoading) {
    return (
      <Card className="sm:col-span-3">
        <CardHeader>
          <CardTitle className="text-base">Account Overview</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Loading...</div>
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card className="sm:col-span-3">
        <CardHeader>
          <CardTitle className="text-base">Account Overview</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">No account data</div>
        </CardContent>
      </Card>
    );
  }

  const mode = (overview.mode ?? 'paper').toUpperCase();
  const isLive = mode === 'LIVE';
  const wallet = overview.wallet ?? '';
  const walletShort = wallet.length > 10
    ? `${wallet.slice(0, 6)}...${wallet.slice(-4)}`
    : wallet || '—';
  const cap = overview.daily_cap_usd ?? 0;
  const used = overview.daily_used_usd ?? 0;
  const remaining = Math.max(0, cap - used);
  const pct = cap > 0 ? Math.min(100, (used / cap) * 100) : 0;
  const posCount = overview.positions_count ?? 0;
  const totalUpnl = overview.total_upnl ?? 0;

  return (
    <Card className="sm:col-span-3">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Account Overview</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={isLive ? 'default' : 'secondary'} className="text-xs">
              {mode}
            </Badge>
            <span className="font-mono text-xs text-muted-foreground">{walletShort}</span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Daily cap bar */}
        <MarginBar usedPct={pct} label="Daily exposure" />

        {/* Primary stats row */}
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
          <StatRow label="Daily Cap" value={fmtUsd(cap)} />
          <StatRow label="Used Today" value={`${fmtUsd(used)} (${pct.toFixed(0)}%)`} />
          <StatRow label="Remaining" value={fmtUsd(remaining)} />
          <StatRow label="Open Markets" value={posCount} />
        </div>

        {/* Order stats row */}
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-5">
          <StatRow label="Filled Live" value={overview.filled_live ?? 0} />
          <StatRow label="Submitted" value={overview.submitted_live ?? 0} />
          <StatRow label="Pending Approval" value={overview.pending_approval ?? 0} />
          <StatRow label="Failed" value={overview.failed ?? 0} />
          <StatRow
            label="Total uPnL"
            value={`${totalUpnl >= 0 ? '+' : ''}${fmtUsd(totalUpnl)}`}
            valueClass={pnlClass(totalUpnl)}
          />
        </div>
      </CardContent>
    </Card>
  );
}
