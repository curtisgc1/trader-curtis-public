import { useGrokAlpha } from '@/hooks/use-polymarket';
import { SignalDrawer } from '@/components/shared/SignalDrawer';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface GrokAlphaRow {
  detected_at?: string;
  question?: string;
  market_price?: number;
  grok_confidence?: number;
  edge_pct?: number;
  direction?: string;
  status?: string;
  news_summary?: string;
  [key: string]: unknown;
}

const columns: Column<GrokAlphaRow>[] = [
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
    key: 'question',
    header: 'Market',
    render: (r) => (
      <span className="text-xs" title={r.question ?? ''}>
        {(r.question ?? '').slice(0, 40)}
      </span>
    ),
  },
  {
    key: 'market_price',
    header: 'Mkt%',
    render: (r) => (
      <span className="font-mono text-xs">
        {(Number(r.market_price ?? 0) * 100).toFixed(0)}%
      </span>
    ),
  },
  {
    key: 'grok_confidence',
    header: 'Grok%',
    render: (r) => (
      <span className="font-mono text-xs">{Number(r.grok_confidence ?? 0)}%</span>
    ),
  },
  {
    key: 'edge_pct',
    header: 'Edge',
    render: (r) => (
      <span className="font-mono text-xs">{Number(r.edge_pct ?? 0).toFixed(0)}%</span>
    ),
  },
  {
    key: 'direction',
    header: 'Dir',
    render: (r) => <span className="text-xs">{r.direction ?? '—'}</span>,
  },
  {
    key: 'status',
    header: 'Status',
    render: (r) => {
      const status = r.status ?? '';
      return (
        <span
          className={cn(
            'text-xs font-medium',
            status === 'executed' ? 'text-primary' : status === 'failed' ? 'text-destructive' : 'text-muted-foreground',
          )}
        >
          {status || '—'}
        </span>
      );
    },
  },
  {
    key: 'news_summary',
    header: 'News',
    render: (r) => (
      <span className="text-xs" title={r.news_summary ?? ''}>
        {(r.news_summary ?? '').slice(0, 80)}
      </span>
    ),
  },
];

export function GrokAlpha() {
  const { data } = useGrokAlpha(50);
  const rows = (data ?? []) as GrokAlphaRow[];

  return (
    <SignalDrawer
      title="Grok Alpha Bets"
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
        emptyMessage="No Grok alpha bets yet — scanner runs every 10 min"
      />
    </SignalDrawer>
  );
}
