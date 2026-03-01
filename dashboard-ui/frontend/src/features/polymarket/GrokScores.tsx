import { useGrokScores } from '@/hooks/use-polymarket';
import { SignalDrawer } from '@/components/shared/SignalDrawer';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface GrokScoreRow {
  scored_at?: string;
  question?: string;
  current_price?: number;
  grok_score?: number;
  grok_direction?: string;
  x_post_count?: number;
  rationale?: string;
  [key: string]: unknown;
}

const columns: Column<GrokScoreRow>[] = [
  {
    key: 'scored_at',
    header: 'Time',
    render: (r) => (
      <span className="font-mono text-xs">
        {(r.scored_at ?? '').replace('T', ' ').slice(0, 16)}
      </span>
    ),
  },
  {
    key: 'question',
    header: 'Market',
    render: (r) => (
      <span className="text-xs" title={r.question ?? ''}>
        {(r.question ?? '').slice(0, 50)}
      </span>
    ),
  },
  {
    key: 'current_price',
    header: 'Price',
    render: (r) => (
      <span className="font-mono text-xs">{Number(r.current_price ?? 0).toFixed(2)}</span>
    ),
  },
  {
    key: 'grok_score',
    header: 'Score',
    render: (r) => {
      const score = Number(r.grok_score ?? 0);
      return (
        <span
          className={cn(
            'font-mono text-xs font-semibold',
            score >= 70 ? 'text-primary' : score < 30 ? 'text-destructive' : 'text-muted-foreground',
          )}
        >
          {score}
        </span>
      );
    },
  },
  {
    key: 'grok_direction',
    header: 'Dir',
    render: (r) => <span className="text-xs">{r.grok_direction ?? '—'}</span>,
  },
  {
    key: 'x_post_count',
    header: 'Posts',
    render: (r) => <span className="font-mono text-xs">{r.x_post_count ?? 0}</span>,
  },
  {
    key: 'rationale',
    header: 'Rationale',
    render: (r) => (
      <span className="text-xs" title={r.rationale ?? ''}>
        {(r.rationale ?? '').slice(0, 80)}
      </span>
    ),
  },
];

export function GrokScores() {
  const { data } = useGrokScores(50);
  const rows = (data ?? []) as GrokScoreRow[];

  return (
    <SignalDrawer
      title="Grok Market Scores"
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
        emptyMessage="No Grok scores yet — scanner runs every 5 min"
      />
    </SignalDrawer>
  );
}
