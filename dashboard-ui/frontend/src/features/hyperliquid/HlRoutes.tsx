import { useSignalRoutes } from '@/hooks/use-signals';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtTimestamp, pnlClass } from '@/lib/format';

interface RouteRow {
  routed_at?: string;
  ticker?: string;
  asset?: string;
  direction?: string;
  score?: number;
  preferred_venue?: string;
  reason?: string;
  [key: string]: unknown;
}

const columns: Column<RouteRow>[] = [
  {
    key: 'routed_at',
    header: 'Time',
    render: (r) => (
      <span className="text-xs font-mono">{fmtTimestamp(r.routed_at)}</span>
    ),
  },
  {
    key: 'ticker',
    header: 'Ticker',
    render: (r) => <span>{r.ticker ?? r.asset ?? '—'}</span>,
  },
  {
    key: 'direction',
    header: 'Dir',
    render: (r) => (
      <span
        className={
          String(r.direction ?? '').toLowerCase() === 'long'
            ? 'text-primary'
            : 'text-destructive'
        }
      >
        {r.direction ?? '—'}
      </span>
    ),
  },
  {
    key: 'score',
    header: 'Score',
    render: (r) => {
      const s = Number(r.score ?? 0);
      return <span className={pnlClass(s)}>{s.toFixed(1)}</span>;
    },
  },
  { key: 'preferred_venue', header: 'Venue' },
  {
    key: 'reason',
    header: 'Reason',
    render: (r) => (
      <span className="text-xs text-muted-foreground">
        {String(r.reason ?? '').slice(0, 80)}
      </span>
    ),
  },
];

export function HlRoutes() {
  const { data, isLoading } = useSignalRoutes();

  const cryptoRoutes = ((data ?? []) as RouteRow[]).filter(
    (r) => (r.preferred_venue ?? '').toLowerCase() === 'crypto',
  );

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">Signal Routes (Crypto)</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={cryptoRoutes}
            columns={columns}
            limit={40}
            emptyMessage="No crypto-routed signals"
          />
        )}
      </CardContent>
    </Card>
  );
}
