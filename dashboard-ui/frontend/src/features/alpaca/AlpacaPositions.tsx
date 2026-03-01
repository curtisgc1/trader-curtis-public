import { usePortfolioSnapshot } from '@/hooks/use-portfolio';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtUsd, fmtPct, pnlClass } from '@/lib/format';

interface Position {
  symbol: string;
  qty: number;
  side: string;
  market_value: number;
  unrealized_pl: number;
  unrealized_plpc: number;
  [key: string]: unknown;
}

interface AlpacaVenueSnapshot {
  ok: boolean;
  positions?: Position[];
}

interface PortfolioSnapshot {
  alpaca?: AlpacaVenueSnapshot;
  [key: string]: unknown;
}

const columns: Column<Position>[] = [
  { key: 'symbol', header: 'Symbol' },
  { key: 'qty', header: 'Qty' },
  { key: 'side', header: 'Side' },
  {
    key: 'market_value',
    header: 'Mkt Value',
    render: (r) => <span className="font-mono">{fmtUsd(r.market_value)}</span>,
  },
  {
    key: 'unrealized_pl',
    header: 'uPnL',
    render: (r) => (
      <span className={`font-mono ${pnlClass(r.unrealized_pl)}`}>
        {fmtUsd(r.unrealized_pl)}
      </span>
    ),
  },
  {
    key: 'unrealized_plpc',
    header: 'uPnL%',
    render: (r) => (
      <span className={pnlClass(r.unrealized_plpc)}>
        {fmtPct(r.unrealized_plpc * 100)}
      </span>
    ),
  },
];

export function AlpacaPositions() {
  const { data, isLoading } = usePortfolioSnapshot();
  const snapshot = data as PortfolioSnapshot | null | undefined;
  const positions = (snapshot?.alpaca?.positions ?? []) as Position[];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Open Positions</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={positions}
            columns={columns}
            emptyMessage="No open positions"
          />
        )}
      </CardContent>
    </Card>
  );
}
