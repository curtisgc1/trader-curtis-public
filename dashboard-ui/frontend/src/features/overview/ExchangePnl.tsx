import { useExchangePnl } from '@/hooks/use-overview';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PnlBadge } from '@/components/shared/PnlBadge';
import { EmptyState } from '@/components/shared/EmptyState';
import { fmtUsd } from '@/lib/format';

interface VenuePnl {
  venue?: string;
  realized_pnl?: number;
  unrealized_pnl?: number;
  total_pnl?: number;
  trade_count?: number;
  [key: string]: unknown;
}

interface ExchangePnlData {
  venues?: VenuePnl[];
  total_pnl?: number;
  [key: string]: unknown;
}

function VenueCard({ venue }: { venue: VenuePnl }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">{venue.venue ?? 'Unknown'}</span>
        <PnlBadge value={venue.total_pnl} />
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Realized</span>
          <span className="text-xs font-mono">{fmtUsd(venue.realized_pnl)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Unrealized</span>
          <span className="text-xs font-mono">{fmtUsd(venue.unrealized_pnl)}</span>
        </div>
        <div className="flex items-center justify-between col-span-2">
          <span className="text-xs text-muted-foreground">Trades</span>
          <span className="text-xs font-mono">{venue.trade_count ?? 0}</span>
        </div>
      </div>
    </div>
  );
}

export function ExchangePnl() {
  const { data, isLoading } = useExchangePnl();
  const pnlData = (data ?? {}) as ExchangePnlData;
  const venues = pnlData.venues ?? (Array.isArray(data) ? data as VenuePnl[] : []);

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Exchange P&L</CardTitle>
          {pnlData.total_pnl != null && <PnlBadge value={pnlData.total_pnl} />}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : venues.length === 0 ? (
          <EmptyState message="No exchange data" />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {venues.map((v, i) => (
              <VenueCard key={v.venue ?? i} venue={v} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
