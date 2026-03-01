import { usePortfolioSnapshot } from '@/hooks/use-overview';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { StatCard } from '@/components/shared/StatCard';
import { StatGrid } from '@/components/shared/StatGrid';
import { fmtUsd, pnlClass } from '@/lib/format';

interface PortfolioData {
  total_value?: number;
  total_equity?: number;
  open_positions?: number;
  unrealized_pnl?: number;
  realized_pnl_today?: number;
  margin_used?: number;
  margin_available?: number;
  cash?: number;
  venues?: Record<string, { value?: number; positions?: number }>;
  [key: string]: unknown;
}

export function PortfolioSummary() {
  const { data, isLoading } = usePortfolioSnapshot();
  const portfolio = (data ?? {}) as PortfolioData;

  if (isLoading) {
    return (
      <Card className="sm:col-span-3">
        <CardHeader>
          <CardTitle className="text-base">Portfolio Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Loading...</div>
        </CardContent>
      </Card>
    );
  }

  const totalValue = Number(portfolio.total_value ?? portfolio.total_equity ?? 0);
  const openPositions = Number(portfolio.open_positions ?? 0);
  const unrealizedPnl = Number(portfolio.unrealized_pnl ?? 0);
  const realizedToday = Number(portfolio.realized_pnl_today ?? 0);

  return (
    <Card className="sm:col-span-3">
      <CardHeader>
        <CardTitle className="text-base">Portfolio Summary</CardTitle>
      </CardHeader>
      <CardContent>
        <StatGrid columns={4}>
          <StatCard
            title="Total Value"
            value={fmtUsd(totalValue)}
          />
          <StatCard
            title="Open Positions"
            value={openPositions}
          />
          <StatCard
            title="Unrealized PnL"
            value={
              <span className={pnlClass(unrealizedPnl)}>
                {unrealizedPnl >= 0 ? '+' : ''}{fmtUsd(unrealizedPnl)}
              </span>
            }
          />
          <StatCard
            title="Realized Today"
            value={
              <span className={pnlClass(realizedToday)}>
                {realizedToday >= 0 ? '+' : ''}{fmtUsd(realizedToday)}
              </span>
            }
          />
        </StatGrid>

        {portfolio.venues && Object.keys(portfolio.venues).length > 0 && (
          <div className="mt-4 flex flex-wrap gap-4">
            {Object.entries(portfolio.venues).map(([venue, info]) => (
              <div key={venue} className="text-xs text-muted-foreground">
                <span className="font-medium">{venue}:</span>{' '}
                <span className="font-mono">{fmtUsd(info.value)}</span>{' '}
                ({info.positions ?? 0} pos)
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
