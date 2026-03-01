import { useExecutionLearning } from '@/hooks/use-learning';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { statusClass } from '@/lib/format';

interface Row {
  ticker: string;
  source_tag: string;
  venue: string;
  order_status: string;
  [key: string]: unknown;
}

const columns: Column<Row>[] = [
  { key: 'ticker', header: 'Ticker' },
  { key: 'source_tag', header: 'Source' },
  { key: 'venue', header: 'Venue' },
  {
    key: 'order_status',
    header: 'Order',
    render: (r) => (
      <span className={statusClass(r.order_status)}>{r.order_status ?? '—'}</span>
    ),
  },
];

export function ExecutionLearning() {
  const { data, isLoading } = useExecutionLearning();

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">Execution Learning</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={(data ?? []) as Row[]}
            columns={columns}
            limit={20}
            emptyMessage="No execution data"
          />
        )}
      </CardContent>
    </Card>
  );
}
