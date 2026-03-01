import { useQuantValidations } from '@/hooks/use-signals';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtNumber, fmtPct, fmtTimestamp } from '@/lib/format';
import { cn } from '@/lib/utils';

interface ValidationRow {
  ticker?: string;
  asset?: string;
  source?: string;
  source_tag?: string;
  validated_at?: string;
  passed?: boolean;
  pass?: boolean;
  win_rate?: number;
  ev?: number;
  expected_value?: number;
  sharpe?: number;
  sharpe_ratio?: number;
  regime_score?: number;
  regime?: string;
  sample_size?: number;
  reason?: string;
  gate_name?: string;
  [key: string]: unknown;
}

function isPassed(r: ValidationRow): boolean {
  return r.passed === true || r.pass === true;
}

const columns: Column<ValidationRow>[] = [
  {
    key: 'validated_at',
    header: 'Time',
    render: (r) => (
      <span className="text-xs font-mono">{fmtTimestamp(r.validated_at)}</span>
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
    key: 'source',
    header: 'Source',
    render: (r) => (
      <span className="text-xs">{r.source ?? r.source_tag ?? '—'}</span>
    ),
  },
  {
    key: 'gate_name',
    header: 'Gate',
    render: (r) => (
      <span className="text-xs">{r.gate_name ?? '—'}</span>
    ),
  },
  {
    key: 'passed',
    header: 'Result',
    render: (r) => {
      const pass = isPassed(r);
      return (
        <Badge
          variant={pass ? 'default' : 'destructive'}
          className="text-xs"
        >
          {pass ? 'PASS' : 'FAIL'}
        </Badge>
      );
    },
  },
  {
    key: 'win_rate',
    header: 'Win Rate',
    render: (r) => {
      const wr = r.win_rate;
      if (wr == null) return <span>—</span>;
      const pct = wr > 1 ? wr : wr * 100;
      return (
        <span className={cn('font-mono text-xs', pct >= 50 ? 'text-primary' : 'text-destructive')}>
          {fmtPct(pct)}
        </span>
      );
    },
  },
  {
    key: 'ev',
    header: 'EV',
    render: (r) => {
      const ev = r.ev ?? r.expected_value;
      if (ev == null) return <span>—</span>;
      return (
        <span className={cn('font-mono text-xs', ev > 0 ? 'text-primary' : 'text-destructive')}>
          {fmtNumber(ev, 3)}
        </span>
      );
    },
  },
  {
    key: 'sharpe',
    header: 'Sharpe',
    render: (r) => {
      const s = r.sharpe ?? r.sharpe_ratio;
      if (s == null) return <span>—</span>;
      return (
        <span className={cn('font-mono text-xs', s >= 1 ? 'text-primary' : s >= 0.5 ? 'text-chart-3' : 'text-destructive')}>
          {fmtNumber(s, 2)}
        </span>
      );
    },
  },
  {
    key: 'regime_score',
    header: 'Regime',
    render: (r) => {
      const score = r.regime_score;
      const label = r.regime;
      if (score == null && !label) return <span>—</span>;
      return (
        <span className="text-xs">
          {label ?? ''}{score != null ? ` (${fmtNumber(score, 1)})` : ''}
        </span>
      );
    },
  },
  {
    key: 'sample_size',
    header: 'N',
    render: (r) => (
      <span className="font-mono text-xs">{r.sample_size ?? '—'}</span>
    ),
  },
];

export function AdvancedDiagnostics() {
  const { data, isLoading } = useQuantValidations();
  const rows = (Array.isArray(data) ? data : []) as ValidationRow[];

  const passCount = rows.filter(isPassed).length;
  const failCount = rows.length - passCount;

  return (
    <Card className="sm:col-span-3">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">
            Quant Validations
            {rows.length > 0 && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                ({rows.length})
              </span>
            )}
          </CardTitle>
          {rows.length > 0 && (
            <div className="flex items-center gap-2">
              <Badge variant="default" className="text-xs">
                {passCount} pass
              </Badge>
              <Badge variant="destructive" className="text-xs">
                {failCount} fail
              </Badge>
            </div>
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
            limit={40}
            emptyMessage="No quant validations yet"
          />
        )}
      </CardContent>
    </Card>
  );
}
