import { useSourceRatings } from '@/hooks/use-consensus';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtPct, pnlClass } from '@/lib/format';

interface SourceRatingRow {
  source: string;
  sample_size: number;
  win_rate: number;
  avg_pnl_pct: number;
  [key: string]: unknown;
}

const columns: Column<SourceRatingRow>[] = [
  { key: 'source', header: 'Source', className: 'font-mono' },
  { key: 'sample_size', header: 'Samples' },
  {
    key: 'win_rate',
    header: 'Win %',
    render: (r) => (
      <span className={pnlClass(r.win_rate - 50)}>{fmtPct(r.win_rate)}</span>
    ),
  },
  {
    key: 'avg_pnl_pct',
    header: 'Avg PnL%',
    render: (r) => (
      <span className={pnlClass(r.avg_pnl_pct)}>{fmtPct(r.avg_pnl_pct)}</span>
    ),
  },
];

export function SourceRatings() {
  const { data, isLoading } = useSourceRatings();
  const rows = (Array.isArray(data) ? data : []) as SourceRatingRow[];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Source Ratings</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={rows}
            columns={columns}
            limit={25}
            emptyMessage="No source ratings"
          />
        )}
      </CardContent>
    </Card>
  );
}
