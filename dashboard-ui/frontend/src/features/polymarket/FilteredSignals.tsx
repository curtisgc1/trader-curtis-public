import { useBrainSignals } from '@/hooks/use-polymarket';
import { SignalDrawer } from '@/components/shared/SignalDrawer';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { Badge } from '@/components/ui/badge';
import { fmtUsd } from '@/lib/format';

interface FilteredRow {
  detected_at?: string;
  wallet_address?: string;
  condition_id?: string;
  price?: number;
  size_usdc?: number;
  wallet_win_rate?: number;
  wallet_pnl?: number;
  notes?: string;
  action?: string;
  [key: string]: unknown;
}

const columns: Column<FilteredRow>[] = [
  {
    key: 'detected_at',
    header: 'Time',
    render: (r) => (
      <span className="font-mono text-xs">
        {(r.detected_at ?? '').replace('T', ' ').slice(0, 16)}
      </span>
    ),
  },
  {
    key: 'wallet_address',
    header: 'Wallet',
    render: (r) => (
      <span className="font-mono text-xs" title={r.wallet_address ?? ''}>
        {(r.wallet_address ?? '').slice(0, 10)}...
      </span>
    ),
  },
  {
    key: 'condition_id',
    header: 'Market',
    render: (r) => (
      <span className="font-mono text-xs" title={r.condition_id ?? ''}>
        {(r.condition_id ?? '').slice(0, 12)}...
      </span>
    ),
  },
  {
    key: 'price',
    header: 'Price',
    render: (r) => (
      <span className="font-mono text-xs">{Number(r.price ?? 0).toFixed(2)}</span>
    ),
  },
  {
    key: 'size_usdc',
    header: 'Size',
    render: (r) => <span className="font-mono text-xs">{fmtUsd(r.size_usdc as number | undefined)}</span>,
  },
  {
    key: 'wallet_win_rate',
    header: 'WR',
    render: (r) => {
      const wr = r.wallet_win_rate ?? 0;
      return (
        <span className="font-mono text-xs">
          {wr > 0 ? `${(wr * 100).toFixed(0)}%` : '-'}
        </span>
      );
    },
  },
  {
    key: 'wallet_pnl',
    header: 'PnL',
    render: (r) => {
      const pnl = r.wallet_pnl ?? 0;
      return (
        <span className="font-mono text-xs">
          {pnl > 0 ? fmtUsd(pnl) : '-'}
        </span>
      );
    },
  },
  {
    key: 'notes',
    header: 'Reason',
    render: (r) => <span className="text-xs">{r.notes ?? '—'}</span>,
  },
];

export function FilteredSignals() {
  const { data } = useBrainSignals(500);
  const allRows = (data ?? []) as FilteredRow[];
  const rows = allRows.filter((r) => r.action === 'filtered');

  return (
    <SignalDrawer
      title="Filtered Signals"
      span={2}
      badge={
        rows.length > 0 ? (
          <Badge variant="secondary" className="text-xs">
            {rows.length}
          </Badge>
        ) : undefined
      }
    >
      <DataTable
        data={rows}
        columns={columns}
        limit={100}
        emptyMessage="No filtered signals yet"
      />
    </SignalDrawer>
  );
}
