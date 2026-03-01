import { useCounterfactualWins } from '@/hooks/use-signals';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { PnlBadge } from '@/components/shared/PnlBadge';
import { fmtTimestamp, fmtNumber, fmtUsd } from '@/lib/format';
import { cn } from '@/lib/utils';

interface MissedRow {
  signal_time?: string;
  ticker?: string;
  asset?: string;
  direction?: string;
  signal_score?: number;
  score?: number;
  source?: string;
  source_tag?: string;
  skip_reason?: string;
  reason?: string;
  hypothetical_pnl?: number;
  what_if_pnl?: number;
  pnl_usd?: number;
  peak_move_pct?: number;
  horizon_hours?: number;
  [key: string]: unknown;
}

function getPnl(r: MissedRow): number | null {
  const v = r.hypothetical_pnl ?? r.what_if_pnl ?? r.pnl_usd;
  return v != null ? Number(v) : null;
}

const columns: Column<MissedRow>[] = [
  {
    key: 'signal_time',
    header: 'Signal Time',
    render: (r) => (
      <span className="text-xs font-mono">{fmtTimestamp(r.signal_time)}</span>
    ),
  },
  {
    key: 'ticker',
    header: 'Ticker',
    render: (r) => (
      <span className="font-mono font-semibold">{r.ticker ?? r.asset ?? '—'}</span>
    ),
  },
  {
    key: 'direction',
    header: 'Dir',
    render: (r) => {
      const dir = String(r.direction ?? '').toLowerCase();
      return (
        <span
          className={cn(
            'uppercase text-xs font-medium',
            dir === 'long' || dir === 'buy' ? 'text-primary' : 'text-destructive',
          )}
        >
          {r.direction ?? '—'}
        </span>
      );
    },
  },
  {
    key: 'signal_score',
    header: 'Score',
    render: (r) => (
      <span className="font-mono">
        {fmtNumber(r.signal_score ?? r.score, 1)}
      </span>
    ),
  },
  {
    key: 'source',
    header: 'Source',
    render: (r) => (
      <span className="text-xs">{r.source ?? r.source_tag ?? '—'}</span>
    ),
  },
  {
    key: 'skip_reason',
    header: 'Why Skipped',
    render: (r) => (
      <span className="text-xs text-muted-foreground">
        {String(r.skip_reason ?? r.reason ?? '').slice(0, 60) || '—'}
      </span>
    ),
  },
  {
    key: 'hypothetical_pnl',
    header: 'What-If PnL',
    render: (r) => {
      const pnl = getPnl(r);
      return pnl != null ? <PnlBadge value={pnl} /> : <span>—</span>;
    },
  },
  {
    key: 'peak_move_pct',
    header: 'Peak Move',
    render: (r) => {
      const v = r.peak_move_pct;
      return v != null ? (
        <span className="font-mono text-xs">{fmtNumber(v, 1)}%</span>
      ) : (
        <span>—</span>
      );
    },
  },
];

export function MissedWins() {
  const { data, isLoading } = useCounterfactualWins();
  const rows = (Array.isArray(data) ? data : []) as MissedRow[];

  const totalMissed = rows.reduce((sum, r) => {
    const pnl = getPnl(r);
    return sum + (pnl != null && pnl > 0 ? pnl : 0);
  }, 0);

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">
            Missed Wins
            {rows.length > 0 && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                ({rows.length})
              </span>
            )}
          </CardTitle>
          {totalMissed > 0 && (
            <span className="text-sm font-mono text-chart-3">
              {fmtUsd(totalMissed)} left on table
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={rows}
            columns={columns}
            limit={30}
            emptyMessage="No missed wins — nice"
          />
        )}
      </CardContent>
    </Card>
  );
}
