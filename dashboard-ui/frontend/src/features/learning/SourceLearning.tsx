import { useSourceLearning } from '@/hooks/use-learning';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtPct, fmtNumber, pnlClass } from '@/lib/format';

interface Row {
  source_tag: string;
  sample_size: number;
  win_rate: number;
  avg_pnl_percent: number;
  sharpe_ratio: number;
  [key: string]: unknown;
}

const columns: Column<Row>[] = [
  { key: 'source_tag', header: 'Source' },
  { key: 'sample_size', header: 'N' },
  {
    key: 'win_rate',
    header: 'Win %',
    render: (r) => <span className={pnlClass(r.win_rate - 50)}>{fmtPct(r.win_rate)}</span>,
  },
  {
    key: 'avg_pnl_percent',
    header: 'Avg PnL%',
    render: (r) => (
      <span className={pnlClass(r.avg_pnl_percent)}>{fmtPct(r.avg_pnl_percent)}</span>
    ),
  },
  {
    key: 'sharpe_ratio',
    header: 'Sharpe',
    render: (r) => (
      <span className={pnlClass(r.sharpe_ratio)}>{fmtNumber(r.sharpe_ratio)}</span>
    ),
  },
];

export function SourceLearning() {
  const { data, isLoading } = useSourceLearning();

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">Source Learning</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={(data ?? []) as Row[]}
            columns={columns}
            limit={20}
            emptyMessage="No source learning data"
          />
        )}
      </CardContent>
    </Card>
  );
}
