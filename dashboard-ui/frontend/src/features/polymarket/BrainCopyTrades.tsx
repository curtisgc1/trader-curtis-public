import { useBrainSignals } from '@/hooks/use-polymarket';
import { SignalDrawer } from '@/components/shared/SignalDrawer';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { Badge } from '@/components/ui/badge';
import { fmtUsd } from '@/lib/format';
import { cn } from '@/lib/utils';

interface BrainSignalRow {
  detected_at?: string;
  wallet_address?: string;
  condition_id?: string;
  side?: string;
  price?: number;
  size_usdc?: number;
  convergence_count?: number;
  action?: string;
  order_id?: string;
  [key: string]: unknown;
}

const columns: Column<BrainSignalRow>[] = [
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
    key: 'side',
    header: 'Side',
    render: (r) => <span className="text-xs">{r.side ?? '—'}</span>,
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
    key: 'convergence_count',
    header: 'Conv',
    render: (r) => <span className="text-xs">{r.convergence_count ?? 0}</span>,
  },
  {
    key: 'action',
    header: 'Action',
    render: (r) => {
      const action = r.action ?? '';
      return (
        <span
          className={cn(
            'text-xs font-medium',
            action === 'executed' || action === 'filled'
              ? 'text-primary'
              : action === 'skipped'
                ? 'text-destructive'
                : 'text-muted-foreground',
          )}
        >
          {action || '—'}
        </span>
      );
    },
  },
  {
    key: 'order_id',
    header: 'Order',
    render: (r) => (
      <span className="font-mono text-xs" title={r.order_id ?? ''}>
        {r.order_id ? `${r.order_id.slice(0, 8)}...` : '-'}
      </span>
    ),
  },
];

export function BrainCopyTrades() {
  const { data } = useBrainSignals(500);
  const allRows = (data ?? []) as BrainSignalRow[];
  const rows = allRows.filter((r) => r.action !== 'filtered');

  return (
    <SignalDrawer
      title="Brain Copy Trades"
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
        limit={50}
        emptyMessage="No brain signals yet — start trader_brain.py"
      />
    </SignalDrawer>
  );
}
