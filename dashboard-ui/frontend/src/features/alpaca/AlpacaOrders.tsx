import { useAlpacaOrders } from '@/hooks/use-alpaca';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtUsd, fmtTimestamp, statusClass } from '@/lib/format';

interface AlpacaOrder {
  created_at: string;
  ticker: string;
  direction: string;
  mode: string;
  notional: number;
  filled_price: number | null;
  order_status: string;
  [key: string]: unknown;
}

const columns: Column<AlpacaOrder>[] = [
  {
    key: 'created_at',
    header: 'Time',
    render: (r) => (
      <span className="font-mono text-xs">{fmtTimestamp(r.created_at)}</span>
    ),
  },
  { key: 'ticker', header: 'Ticker' },
  { key: 'direction', header: 'Dir' },
  { key: 'mode', header: 'Mode' },
  {
    key: 'notional',
    header: 'Notional',
    render: (r) => <span className="font-mono">{fmtUsd(r.notional)}</span>,
  },
  {
    key: 'filled_price',
    header: 'Fill Price',
    render: (r) => (
      <span className="font-mono">
        {r.filled_price != null ? fmtUsd(r.filled_price) : '—'}
      </span>
    ),
  },
  {
    key: 'order_status',
    header: 'Status',
    render: (r) => (
      <span className={statusClass(r.order_status)}>{r.order_status ?? '—'}</span>
    ),
  },
];

export function AlpacaOrders() {
  const { data, isLoading } = useAlpacaOrders(120);
  const orders = (data ?? []) as AlpacaOrder[];

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">Execution Orders</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={orders}
            columns={columns}
            limit={50}
            emptyMessage="No execution orders"
          />
        )}
      </CardContent>
    </Card>
  );
}
