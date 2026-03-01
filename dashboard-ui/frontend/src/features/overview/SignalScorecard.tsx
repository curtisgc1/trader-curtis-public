import { useSignalScorecard } from '@/hooks/use-overview';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtPct, fmtNumber, pnlClass } from '@/lib/format';

interface ScorecardRow {
  source?: string;
  accuracy?: number;
  weight?: number;
  trend?: string;
  sample_size?: number;
  avg_return?: number;
  [key: string]: unknown;
}

interface ScorecardData {
  sources?: ScorecardRow[];
  [key: string]: unknown;
}

function trendIcon(trend: string | undefined): string {
  if (!trend) return '—';
  const t = trend.toLowerCase();
  if (t === 'up' || t === 'improving') return '\u2191';
  if (t === 'down' || t === 'declining') return '\u2193';
  return '\u2192';
}

function trendClass(trend: string | undefined): string {
  if (!trend) return 'text-muted-foreground';
  const t = trend.toLowerCase();
  if (t === 'up' || t === 'improving') return 'text-primary';
  if (t === 'down' || t === 'declining') return 'text-destructive';
  return 'text-muted-foreground';
}

const columns: Column<ScorecardRow>[] = [
  { key: 'source', header: 'Source', className: 'font-mono' },
  {
    key: 'accuracy',
    header: 'Accuracy',
    render: (r) => (
      <span className={pnlClass((r.accuracy ?? 0) - 50)}>
        {fmtPct(r.accuracy)}
      </span>
    ),
  },
  {
    key: 'weight',
    header: 'Weight',
    render: (r) => fmtNumber(r.weight, 3),
  },
  { key: 'sample_size', header: 'Samples' },
  {
    key: 'avg_return',
    header: 'Avg Return',
    render: (r) => (
      <span className={pnlClass(r.avg_return)}>
        {fmtPct(r.avg_return)}
      </span>
    ),
  },
  {
    key: 'trend',
    header: 'Trend',
    render: (r) => (
      <span className={trendClass(r.trend)}>
        {trendIcon(r.trend)} {r.trend ?? '—'}
      </span>
    ),
  },
];

export function SignalScorecard() {
  const { data, isLoading } = useSignalScorecard();
  const scorecard = (data ?? {}) as ScorecardData;
  const rows = (scorecard.sources ?? (Array.isArray(data) ? data : [])) as ScorecardRow[];

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">Signal Scorecard</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={rows}
            columns={columns}
            limit={15}
            emptyMessage="No signal scores"
          />
        )}
      </CardContent>
    </Card>
  );
}
