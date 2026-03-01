import { usePnlBreakdown } from '@/hooks/use-portfolio';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtUsd, fmtNumber, pnlClass } from '@/lib/format';

interface ClosedTrade {
  ticker: string;
  entry_side: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  pnl_pct: number;
  pnl_percent: number;
  [key: string]: unknown;
}

const columns: Column<ClosedTrade>[] = [
  { key: 'ticker', header: 'Ticker' },
  { key: 'entry_side', header: 'Side' },
  {
    key: 'entry_price',
    header: 'Entry',
    render: (r) => <span className="font-mono">{fmtUsd(r.entry_price)}</span>,
  },
  {
    key: 'exit_price',
    header: 'Exit',
    render: (r) => <span className="font-mono">{fmtUsd(r.exit_price)}</span>,
  },
  {
    key: 'pnl',
    header: 'PnL',
    render: (r) => (
      <span className={`font-mono ${pnlClass(r.pnl)}`}>{fmtUsd(r.pnl)}</span>
    ),
  },
  {
    key: 'pnl_pct',
    header: 'PnL%',
    render: (r) => {
      const pct = r.pnl_pct ?? r.pnl_percent ?? 0;
      return (
        <span className={pnlClass(pct)}>{fmtNumber(pct, 2)}%</span>
      );
    },
  },
];

export function AlpacaClosedTrades() {
  const { data, isLoading } = usePnlBreakdown(120);
  const trades = (data ?? []) as ClosedTrade[];

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">Closed Trades</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={trades}
            columns={columns}
            limit={40}
            emptyMessage="No closed trades"
          />
        )}
      </CardContent>
    </Card>
  );
}
