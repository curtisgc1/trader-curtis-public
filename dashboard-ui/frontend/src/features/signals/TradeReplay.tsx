import { useSignalRoutes } from '@/hooks/use-signals';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtTimestamp, fmtNumber } from '@/lib/format';
import { cn } from '@/lib/utils';

interface RouteRow {
  routed_at?: string;
  ticker?: string;
  asset?: string;
  source?: string;
  source_tag?: string;
  direction?: string;
  score?: number;
  status?: string;
  preferred_venue?: string;
  venue?: string;
  reason?: string;
  [key: string]: unknown;
}

function statusVariant(status: string | undefined): 'default' | 'secondary' | 'destructive' | 'outline' {
  const s = (status ?? '').toLowerCase();
  if (s === 'filled' || s === 'executed' || s === 'routed') return 'default';
  if (s === 'pending' || s === 'queued') return 'secondary';
  if (s === 'rejected' || s === 'failed' || s === 'expired') return 'destructive';
  return 'outline';
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
    render: (r) => (
      <span className="font-mono font-semibold">{r.ticker ?? r.asset ?? '—'}</span>
    ),
  },
  {
    key: 'source',
    header: 'Source',
    render: (r) => (
      <span className="text-xs">{r.source ?? r.source_tag ?? '—'}</span>
    ),
  },
  {
    key: 'direction',
    header: 'Dir',
    render: (r) => {
      const dir = String(r.direction ?? '').toLowerCase();
      return (
        <span
          className={cn(
            'uppercase font-medium text-xs',
            dir === 'long' || dir === 'buy' ? 'text-primary' : 'text-destructive',
          )}
        >
          {r.direction ?? '—'}
        </span>
      );
    },
  },
  {
    key: 'score',
    header: 'Score',
    render: (r) => (
      <span className="font-mono">{fmtNumber(r.score, 1)}</span>
    ),
  },
  {
    key: 'status',
    header: 'Status',
    render: (r) => (
      <Badge variant={statusVariant(r.status)} className="text-xs">
        {r.status ?? '—'}
      </Badge>
    ),
  },
  {
    key: 'preferred_venue',
    header: 'Venue',
    render: (r) => (
      <span className="text-xs">{r.preferred_venue ?? r.venue ?? '—'}</span>
    ),
  },
  {
    key: 'reason',
    header: 'Reason',
    render: (r) => (
      <span className="text-xs text-muted-foreground">
        {String(r.reason ?? '').slice(0, 60)}
      </span>
    ),
  },
];

export function TradeReplay() {
  const { data, isLoading } = useSignalRoutes();
  const rows = (Array.isArray(data) ? data : []) as RouteRow[];

  return (
    <Card className="sm:col-span-3">
      <CardHeader>
        <CardTitle className="text-base">
          Signal Routes
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
        ) : (
          <DataTable
            data={rows}
            columns={columns}
            limit={50}
            emptyMessage="No signal routes yet"
          />
        )}
      </CardContent>
    </Card>
  );
}
