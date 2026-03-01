import { useInputFeatureStats } from '@/hooks/use-learning';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtPct, pnlClass } from '@/lib/format';

interface Row {
  outcome_type: string;
  dimension: string;
  dimension_value: string;
  sample_size: number;
  win_rate: number;
  avg_pnl_percent: number;
  [key: string]: unknown;
}

const columns: Column<Row>[] = [
  { key: 'outcome_type', header: 'Outcome' },
  { key: 'dimension', header: 'Dimension' },
  { key: 'dimension_value', header: 'Value' },
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
];

export function InputFeatureStats() {
  const { data, isLoading } = useInputFeatureStats();

  return (
    <Card className="sm:col-span-3">
      <CardHeader>
        <CardTitle className="text-base">Input Feature Stats</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={(data ?? []) as Row[]}
            columns={columns}
            limit={40}
            emptyMessage="No feature stats"
          />
        )}
      </CardContent>
    </Card>
  );
}
