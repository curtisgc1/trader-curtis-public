import { useSignalRoutes } from '@/hooks/use-signals';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtTimestamp, fmtNumber } from '@/lib/format';

interface SignalRoute {
  routed_at: string;
  ticker: string;
  asset: string;
  direction: string;
  score: number;
  preferred_venue: string;
  reason: string;
  [key: string]: unknown;
}

const columns: Column<SignalRoute>[] = [
  {
    key: 'routed_at',
    header: 'Time',
    render: (r) => (
      <span className="font-mono text-xs">{fmtTimestamp(r.routed_at)}</span>
    ),
  },
  {
    key: 'ticker',
    header: 'Ticker',
    render: (r) => <span>{r.ticker || r.asset || '—'}</span>,
  },
  { key: 'direction', header: 'Dir' },
  {
    key: 'score',
    header: 'Score',
    render: (r) => (
      <span className="font-mono">{fmtNumber(r.score, 1)}</span>
    ),
  },
  { key: 'preferred_venue', header: 'Venue' },
  {
    key: 'reason',
    header: 'Reason',
    render: (r) => (
      <span className="text-muted-foreground">
        {(r.reason ?? '').slice(0, 60)}
      </span>
    ),
  },
];

export function AlpacaRoutes() {
  const { data, isLoading } = useSignalRoutes();
  const allRoutes = (data ?? []) as SignalRoute[];
  const routes = allRoutes.filter(
    (r) => (r.preferred_venue ?? '').toLowerCase() === 'stocks',
  );

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">Signal Routes (Stocks)</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={routes}
            columns={columns}
            limit={40}
            emptyMessage="No stock-routed signals"
          />
        )}
      </CardContent>
    </Card>
  );
}
