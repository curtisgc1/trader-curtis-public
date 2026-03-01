import { useHyperliquidIntents } from '@/hooks/use-hyperliquid';
import { usePositionManagementIntents } from '@/hooks/use-controls';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtUsd, fmtTimestamp, statusClass, pnlClass } from '@/lib/format';

// ── Trade Intents ────────────────────────────────────────────────────────────

interface IntentRow {
  created_at?: string;
  symbol?: string;
  side?: string;
  qty?: number | string;
  notional?: number;
  status?: string;
  details?: unknown;
  [key: string]: unknown;
}

function formatDetails(raw: unknown): string {
  if (raw == null) return '';
  let obj: Record<string, unknown>;
  try {
    obj = typeof raw === 'string' ? (JSON.parse(raw) as Record<string, unknown>) : (raw as Record<string, unknown>);
  } catch {
    const s = String(raw);
    return s.length > 120 ? s.slice(0, 120) + '...' : s;
  }
  const parts: string[] = [];
  if (obj['action']) parts.push(String(obj['action']));
  if (obj['reason']) parts.push(String(obj['reason']));
  if (obj['error']) parts.push(`Error: ${obj['error']}`);
  if (parts.length) return parts.join(' · ');
  const fb = JSON.stringify(obj);
  return fb.length > 120 ? fb.slice(0, 120) + '...' : fb;
}

const intentColumns: Column<IntentRow>[] = [
  {
    key: 'created_at',
    header: 'Time',
    render: (r) => (
      <span className="text-xs font-mono">{fmtTimestamp(r.created_at)}</span>
    ),
  },
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
  { key: 'qty', header: 'Qty' },
  {
    key: 'notional',
    header: 'Notional',
    render: (r) => (
      <span className="font-mono">{fmtUsd(Number(r.notional ?? 0))}</span>
    ),
  },
  {
    key: 'status',
    header: 'Status',
    render: (r) => (
      <span className={statusClass(r.status)}>{r.status ?? '—'}</span>
    ),
  },
  {
    key: 'details',
    header: 'Details',
    render: (r) => (
      <span className="text-xs text-muted-foreground">
        {formatDetails(r.details)}
      </span>
    ),
  },
];

export function HlIntents() {
  const { data, isLoading } = useHyperliquidIntents(120);

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">Trade Intents</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={(data ?? []) as IntentRow[]}
            columns={intentColumns}
            limit={50}
            emptyMessage="No Hyperliquid trade intents"
          />
        )}
      </CardContent>
    </Card>
  );
}

// ── Position Management Intents ───────────────────────────────────────────────

interface PosMgmtRow {
  created_at?: string;
  symbol?: string;
  action?: string;
  side?: string;
  status?: string;
  reason?: string;
  pnl_pct?: number;
  [key: string]: unknown;
}

const posMgmtColumns: Column<PosMgmtRow>[] = [
  {
    key: 'created_at',
    header: 'Time',
    render: (r) => (
      <span className="text-xs font-mono">{fmtTimestamp(r.created_at)}</span>
    ),
  },
  { key: 'symbol', header: 'Symbol' },
  { key: 'action', header: 'Action' },
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
  {
    key: 'pnl_pct',
    header: 'PnL%',
    render: (r) => {
      const v = Number(r.pnl_pct ?? 0);
      return (
        <span className={pnlClass(v)}>
          {v >= 0 ? '+' : ''}{v.toFixed(2)}%
        </span>
      );
    },
  },
  {
    key: 'reason',
    header: 'Reason',
    render: (r) => (
      <span className="text-xs text-muted-foreground">
        {String(r.reason ?? '').slice(0, 80)}
      </span>
    ),
  },
];

export function HlPositionManagement() {
  const { data, isLoading } = usePositionManagementIntents(120);

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">Position Management</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={(data ?? []) as PosMgmtRow[]}
            columns={posMgmtColumns}
            limit={40}
            emptyMessage="No position management actions"
          />
        )}
      </CardContent>
    </Card>
  );
}
