import { useArbOpportunities } from '@/hooks/use-polymarket';
import { SignalDrawer } from '@/components/shared/SignalDrawer';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { Badge } from '@/components/ui/badge';
import { fmtUsd } from '@/lib/format';
import { cn } from '@/lib/utils';

interface ArbRow {
  detected_at?: string;
  kalshi_ticker?: string;
  title?: string;
  similarity?: number;
  poly_price?: number;
  kalshi_price?: number;
  spread_after_fees?: number;
  action?: string;
  poly_size_usd?: number;
  kalshi_size_usd?: number;
  [key: string]: unknown;
}

const columns: Column<ArbRow>[] = [
  {
    key: 'detected_at',
    header: 'Time',
    render: (r) => (
      <span className="font-mono text-xs">
        {(r.detected_at ?? '').replace('T', ' ').slice(0, 16)}
      </span>
    ),
  },
  {
    key: 'kalshi_ticker',
    header: 'Kalshi',
    render: (r) => <span className="text-xs">{r.kalshi_ticker ?? '—'}</span>,
  },
  {
    key: 'title',
    header: 'Title',
    render: (r) => (
      <span className="text-xs" title={r.title ?? ''}>
        {(r.title ?? '').slice(0, 40)}
      </span>
    ),
  },
  {
    key: 'similarity',
    header: 'Sim%',
    render: (r) => <span className="font-mono text-xs">{r.similarity ?? 0}</span>,
  },
  {
    key: 'poly_price',
    header: 'P.Price',
    render: (r) => (
      <span className="font-mono text-xs">{Number(r.poly_price ?? 0).toFixed(2)}</span>
    ),
  },
  {
    key: 'kalshi_price',
    header: 'K.Price',
    render: (r) => (
      <span className="font-mono text-xs">{Number(r.kalshi_price ?? 0).toFixed(2)}</span>
    ),
  },
  {
    key: 'spread_after_fees',
    header: 'Net',
    render: (r) => (
      <span className="font-mono text-xs">{Number(r.spread_after_fees ?? 0).toFixed(3)}</span>
    ),
  },
  {
    key: 'action',
    header: 'Action',
    render: (r) => {
      const action = r.action ?? '';
      return (
        <span
          className={cn(
            'text-xs font-medium',
            action === 'executed' ? 'text-primary' : action === 'partial' ? 'text-destructive' : 'text-muted-foreground',
          )}
        >
          {action || '—'}
        </span>
      );
    },
  },
  {
    key: 'poly_size_usd',
    header: 'Leg $',
    render: (r) => {
      const action = r.action ?? '';
      const legUsd = action === 'executed' || action === 'partial'
        ? fmtUsd((r.poly_size_usd ?? 0) + (r.kalshi_size_usd ?? 0))
        : '-';
      return <span className="font-mono text-xs">{legUsd}</span>;
    },
  },
];

export function ArbOpportunities() {
  const { data } = useArbOpportunities(500);
  const rows = (data ?? []) as ArbRow[];

  return (
    <SignalDrawer
      title="Arb Opportunities"
      span={2}
      badge={
        rows.length > 0 ? (
          <Badge variant="secondary" className="text-xs">
            {rows.length}
          </Badge>
        ) : undefined
      }
    >
      <DataTable
        data={rows}
        columns={columns}
        limit={50}
        emptyMessage="No arb opportunities detected yet"
      />
    </SignalDrawer>
  );
}
