import { usePortfolioSnapshot } from '@/hooks/use-portfolio';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fmtUsd, pnlClass } from '@/lib/format';

interface AlpacaVenueSnapshot {
  ok: boolean;
  error?: string;
  equity?: number;
  cash?: number;
  buying_power?: number;
  day_pnl?: number;
  positions?: unknown[];
}

interface PortfolioSnapshot {
  alpaca?: AlpacaVenueSnapshot;
  [key: string]: unknown;
}

export function AlpacaOverview() {
  const { data, isLoading } = usePortfolioSnapshot();
  const snapshot = data as PortfolioSnapshot | null | undefined;
  const a = snapshot?.alpaca;

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">Account Overview</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="text-sm text-muted-foreground">Loading...</div>
        )}
        {!isLoading && (!a || !a.ok) && (
          <p className="text-sm text-destructive">
            Alpaca offline{a?.error ? `: ${a.error}` : ''}
          </p>
        )}
        {!isLoading && a && a.ok && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="space-y-0.5">
              <p className="text-xs text-muted-foreground">Equity</p>
              <p className="text-lg font-bold font-mono">{fmtUsd(a.equity)}</p>
            </div>
            <div className="space-y-0.5">
              <p className="text-xs text-muted-foreground">Cash</p>
              <p className="text-lg font-bold font-mono">{fmtUsd(a.cash)}</p>
            </div>
            <div className="space-y-0.5">
              <p className="text-xs text-muted-foreground">Buying Power</p>
              <p className="text-lg font-bold font-mono">{fmtUsd(a.buying_power)}</p>
            </div>
            <div className="space-y-0.5">
              <p className="text-xs text-muted-foreground">Day PnL</p>
              <p className={`text-lg font-bold font-mono ${pnlClass(a.day_pnl ?? null)}`}>
                {fmtUsd(a.day_pnl ?? null)}
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
