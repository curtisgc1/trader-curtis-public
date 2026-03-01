import { useKellySignals } from '@/hooks/use-signals';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/shared/EmptyState';
import { fmtPct, fmtNumber, fmtUsd } from '@/lib/format';
import { cn } from '@/lib/utils';

interface KellyRow {
  ticker?: string;
  asset?: string;
  direction?: string;
  win_probability?: number;
  payout_ratio?: number;
  kelly_fraction?: number;
  recommended_size_usd?: number;
  edge?: number;
  source?: string;
  updated_at?: string;
  [key: string]: unknown;
}

function kellyColor(fraction: number): string {
  if (fraction >= 0.15) return 'text-primary';
  if (fraction >= 0.05) return 'text-chart-3';
  return 'text-muted-foreground';
}

function KellyCard({ row }: { row: KellyRow }) {
  const ticker = row.ticker ?? row.asset ?? '—';
  const dir = String(row.direction ?? '').toLowerCase();
  const winProb = row.win_probability ?? 0;
  const payout = row.payout_ratio ?? 0;
  const kelly = row.kelly_fraction ?? 0;
  const sizeUsd = row.recommended_size_usd;
  const edge = row.edge;

  return (
    <Card>
      <CardContent className="pt-4 space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-mono font-semibold">{ticker}</span>
          <Badge
            variant={dir === 'long' || dir === 'buy' ? 'default' : 'destructive'}
            className="text-xs uppercase"
          >
            {row.direction ?? '—'}
          </Badge>
        </div>

        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Win Prob</span>
            <span className="text-sm font-mono">{fmtPct(winProb * 100)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Payout</span>
            <span className="text-sm font-mono">{fmtNumber(payout, 2)}x</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Kelly f*</span>
            <span className={cn('text-sm font-mono font-bold', kellyColor(kelly))}>
              {fmtPct(kelly * 100)}
            </span>
          </div>
          {sizeUsd != null && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Size</span>
              <span className="text-sm font-mono">{fmtUsd(sizeUsd)}</span>
            </div>
          )}
        </div>

        {edge != null && (
          <div className="flex items-center justify-between border-t border-border pt-1">
            <span className="text-xs text-muted-foreground">Edge</span>
            <span className="text-xs font-mono">{fmtPct(edge * 100)}</span>
          </div>
        )}

        {row.source && (
          <div className="text-xs text-muted-foreground truncate">
            via {row.source}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function KellySignals() {
  const { data, isLoading } = useKellySignals();
  const rows = (Array.isArray(data) ? data : []) as KellyRow[];

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">
          Kelly Sizing
          {rows.length > 0 && (
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              ({rows.length})
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : rows.length === 0 ? (
          <EmptyState message="No Kelly signals" />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {rows.slice(0, 8).map((row, i) => (
              <KellyCard key={i} row={row} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
