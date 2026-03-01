import { usePortfolioSnapshot } from '@/hooks/use-portfolio';
import { StatCard } from '@/components/shared/StatCard';
import { StatGrid } from '@/components/shared/StatGrid';
import { MarginBar } from '@/components/shared/MarginBar';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { fmtUsd, pnlClass } from '@/lib/format';

interface HlData {
  ok?: boolean;
  error?: string;
  network?: string;
  wallet?: string;
  perp_account_value?: number;
  account_value?: number;
  total_margin_used?: number;
  margin_ratio?: number;
  positions?: Array<{ unrealized_pnl?: number }>;
  [key: string]: unknown;
}

interface Snapshot {
  hyperliquid?: HlData;
  [key: string]: unknown;
}

export function HlOverview() {
  const { data, isLoading } = usePortfolioSnapshot();
  const snapshot = data as Snapshot | null;
  const hl = snapshot?.hyperliquid ?? {} as HlData;

  if (isLoading) {
    return (
      <Card className="sm:col-span-3">
        <CardContent className="py-6 text-sm text-muted-foreground">Loading...</CardContent>
      </Card>
    );
  }

  if (!hl.ok) {
    return (
      <Card className="sm:col-span-3">
        <CardContent className="py-6 text-sm text-destructive">
          Hyperliquid offline: {hl.error ?? 'unknown'}
        </CardContent>
      </Card>
    );
  }

  const accountValue = Number(hl.perp_account_value ?? hl.account_value ?? 0);
  const marginUsed = Number(hl.total_margin_used ?? 0);
  const available = accountValue - marginUsed;
  const marginRatio = Number(hl.margin_ratio ?? 0);
  const marginPct = marginRatio * 100;
  const positions = hl.positions ?? [];
  const totalPnl = positions.reduce(
    (sum, p) => sum + Number(p.unrealized_pnl ?? 0),
    0,
  );

  const network = hl.network ?? 'unknown';
  const walletShort = hl.wallet ? String(hl.wallet).slice(0, 10) + '...' : '—';

  return (
    <Card className="sm:col-span-3">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-base">Account Overview</CardTitle>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Badge variant={network === 'mainnet' ? 'default' : 'outline'}>
            {network}
          </Badge>
          <span className="font-mono">{walletShort}</span>
          <span>{positions.length} position{positions.length !== 1 ? 's' : ''}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <StatGrid columns={4}>
          <StatCard
            title="Account Value"
            value={fmtUsd(accountValue)}
          />
          <StatCard
            title="Margin Used"
            value={fmtUsd(marginUsed)}
            subtitle={`${marginPct.toFixed(1)}%`}
          />
          <StatCard
            title="Available"
            value={fmtUsd(available)}
          />
          <StatCard
            title="Total uPnL"
            value={
              <span className={pnlClass(totalPnl)}>
                {totalPnl >= 0 ? '+' : ''}{fmtUsd(totalPnl)}
              </span>
            }
          />
        </StatGrid>
        <MarginBar usedPct={marginPct} label="Margin utilization" />
      </CardContent>
    </Card>
  );
}
