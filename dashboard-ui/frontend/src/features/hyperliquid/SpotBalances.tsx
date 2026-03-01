import { usePortfolioSnapshot } from '@/hooks/use-portfolio';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtUsd } from '@/lib/format';

interface SpotBalance {
  coin?: string;
  token?: string;
  total?: number;
  balance?: number;
  [key: string]: unknown;
}

interface HlData {
  spot_balances?: SpotBalance[];
  spot_total_usdc?: number;
  [key: string]: unknown;
}

interface Snapshot {
  hyperliquid?: HlData;
  [key: string]: unknown;
}

interface Row extends SpotBalance {
  _token: string;
  _balance: number;
}

const columns: Column<Row>[] = [
  { key: '_token', header: 'Token' },
  {
    key: '_balance',
    header: 'Balance',
    render: (r) => <span className="font-mono">{fmtUsd(r._balance)}</span>,
  },
];

export function SpotBalances() {
  const { data, isLoading } = usePortfolioSnapshot();
  const snapshot = data as Snapshot | null;
  const hl = snapshot?.hyperliquid ?? {} as HlData;
  const rawBalances = hl.spot_balances ?? [];
  const usdcTotal = Number(hl.spot_total_usdc ?? 0);

  const rows: Row[] = rawBalances.map((b) => ({
    ...b,
    _token: String(b.coin ?? b.token ?? '?'),
    _balance: Number(b.total ?? b.balance ?? 0),
  }));

  // If no balances but there is USDC, show a single USDC row
  const displayRows: Row[] =
    rows.length === 0 && usdcTotal > 0
      ? [{ _token: 'USDC', _balance: usdcTotal }]
      : rows;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Spot Balances</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={displayRows}
            columns={columns}
            emptyMessage="No spot balances"
          />
        )}
      </CardContent>
    </Card>
  );
}
