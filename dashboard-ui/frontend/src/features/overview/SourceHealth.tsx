import { useSourceScores } from '@/hooks/use-overview';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtPct, fmtNumber, pnlClass } from '@/lib/format';
import { cn } from '@/lib/utils';

interface SourceRow {
  source?: string;
  score?: number;
  win_rate?: number;
  sample_size?: number;
  trend?: string;
  avg_pnl_pct?: number;
  [key: string]: unknown;
}

function trendIndicator(trend: string | undefined): string {
  if (!trend) return '—';
  const t = trend.toLowerCase();
  if (t === 'up' || t === 'improving' || t === 'rising') return '\u25B2';
  if (t === 'down' || t === 'declining' || t === 'falling') return '\u25BC';
  return '\u25C6';
}

function trendClass(trend: string | undefined): string {
  if (!trend) return 'text-muted-foreground';
  const t = trend.toLowerCase();
  if (t === 'up' || t === 'improving' || t === 'rising') return 'text-primary';
  if (t === 'down' || t === 'declining' || t === 'falling') return 'text-destructive';
  return 'text-chart-3';
}

function scoreClass(score: number | undefined): string {
  if (score == null) return 'text-muted-foreground';
  if (score >= 70) return 'text-primary';
  if (score >= 40) return 'text-chart-3';
  return 'text-destructive';
}

const columns: Column<SourceRow>[] = [
  { key: 'source', header: 'Source', className: 'font-mono' },
  {
    key: 'score',
    header: 'Score',
    render: (r) => (
      <span className={cn('font-mono font-bold', scoreClass(r.score))}>
        {fmtNumber(r.score, 1)}
      </span>
    ),
  },
  {
    key: 'win_rate',
    header: 'Win %',
    render: (r) => (
      <span className={pnlClass((r.win_rate ?? 0) - 50)}>
        {fmtPct(r.win_rate)}
      </span>
    ),
  },
  { key: 'sample_size', header: 'Samples' },
  {
    key: 'avg_pnl_pct',
    header: 'Avg PnL%',
    render: (r) => (
      <span className={pnlClass(r.avg_pnl_pct)}>
        {fmtPct(r.avg_pnl_pct)}
      </span>
    ),
  },
  {
    key: 'trend',
    header: 'Trend',
    render: (r) => (
      <span className={trendClass(r.trend)}>
        {trendIndicator(r.trend)}
      </span>
    ),
  },
];

export function SourceHealth() {
  const { data, isLoading } = useSourceScores(20);
  const rows = (Array.isArray(data) ? data : []) as SourceRow[];

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">Source Health</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={rows}
            columns={columns}
            limit={20}
            emptyMessage="No source scores"
          />
        )}
      </CardContent>
    </Card>
  );
}
