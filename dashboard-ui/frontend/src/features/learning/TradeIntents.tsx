import { useTradeIntents } from '@/hooks/use-learning';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { statusClass } from '@/lib/format';

interface Row {
  venue: string;
  symbol: string;
  side: string;
  status: string;
  [key: string]: unknown;
}

const columns: Column<Row>[] = [
  { key: 'venue', header: 'Venue' },
  { key: 'symbol', header: 'Symbol' },
  {
    key: 'side',
    header: 'Side',
    render: (r) => (
      <span
        className={
          r.side === 'buy' || r.side === 'long'
            ? 'text-primary'
            : 'text-destructive'
        }
      >
        {r.side ?? '—'}
      </span>
    ),
  },
  {
    key: 'status',
    header: 'Status',
    render: (r) => (
      <span className={statusClass(r.status)}>{r.status ?? '—'}</span>
    ),
  },
];

export function TradeIntents() {
  const { data, isLoading } = useTradeIntents();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Trade Intents</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={(data ?? []) as Row[]}
            columns={columns}
            limit={20}
            emptyMessage="No trade intents"
          />
        )}
      </CardContent>
    </Card>
  );
}
