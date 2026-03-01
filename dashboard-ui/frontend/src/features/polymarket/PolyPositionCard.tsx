import { cn } from '@/lib/utils';
import { fmtUsd, pnlClass } from '@/lib/format';

interface PolyOutcome {
  outcome?: string;
  net_shares?: number;
  avg_entry?: number;
  current_price?: number;
  net_notional?: number;
  current_value?: number;
  unrealized_pnl?: number;
  [key: string]: unknown;
}

export interface PolyMarket {
  question?: string;
  market_id?: string;
  market_url?: string;
  total_pnl?: number;
  total_exposure?: number;
  last_at?: string;
  outcomes?: PolyOutcome[];
  [key: string]: unknown;
}

function fmtEntryPct(v: number | undefined): string {
  const n = Number(v ?? 0) * 100;
  return Number.isFinite(n) ? `${n.toFixed(1)}%` : '—';
}

interface OutcomeRowProps {
  outcome: PolyOutcome;
}

function OutcomeRow({ outcome }: OutcomeRowProps) {
  const label = (outcome.outcome ?? '').toUpperCase();
  const isYes = label === 'YES';
  const oPnl = outcome.unrealized_pnl ?? 0;
  const shares = Math.abs(outcome.net_shares ?? 0);

  return (
    <div className="grid grid-cols-6 gap-2 rounded bg-muted/30 px-2 py-1.5 text-xs">
      <div>
        <span
          className={cn(
            'inline-block rounded px-1.5 py-0.5 text-[10px] font-bold uppercase',
            isYes
              ? 'bg-primary/20 text-primary'
              : 'bg-destructive/20 text-destructive',
          )}
        >
          {label}
        </span>
      </div>
      <div>
        <div className="text-muted-foreground">Shares</div>
        <div className="font-mono">{shares.toFixed(1)}</div>
      </div>
      <div>
        <div className="text-muted-foreground">Avg Entry</div>
        <div className="font-mono">{fmtEntryPct(outcome.avg_entry)}</div>
      </div>
      <div>
        <div className="text-muted-foreground">Current</div>
        <div className="font-mono">{fmtEntryPct(outcome.current_price)}</div>
      </div>
      <div>
        <div className="text-muted-foreground">Cost / Value</div>
        <div className="font-mono">
          {fmtUsd(Math.abs(outcome.net_notional ?? 0))} / {fmtUsd(outcome.current_value ?? 0)}
        </div>
      </div>
      <div>
        <div className="text-muted-foreground">P&amp;L</div>
        <div className={cn('font-mono font-semibold', pnlClass(oPnl))}>
          {oPnl >= 0 ? '+' : ''}{fmtUsd(oPnl)}
        </div>
      </div>
    </div>
  );
}

interface PolyPositionCardProps {
  market: PolyMarket;
}

export function PolyPositionCard({ market }: PolyPositionCardProps) {
  const question = market.question ?? market.market_id ?? 'Unknown market';
  const questionShort = question.length > 90 ? `${question.slice(0, 87)}...` : question;
  const pnl = market.total_pnl ?? 0;
  const lastAt = (market.last_at ?? '').replace('T', ' ').slice(0, 16);
  const outcomes = market.outcomes ?? [];

  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-card p-3 space-y-2',
        pnl >= 0 ? 'border-primary/20' : 'border-destructive/20',
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium leading-tight" title={question}>
          {questionShort}
        </span>
        {market.market_url && (
          <a
            href={market.market_url}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 text-xs text-muted-foreground hover:text-primary"
          >
            ↗
          </a>
        )}
      </div>

      {/* Outcome rows */}
      <div className="space-y-1">
        {outcomes.map((o, i) => (
          <OutcomeRow key={i} outcome={o} />
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Exposure {fmtUsd(market.total_exposure ?? 0)}</span>
        <span className={cn('font-semibold', pnlClass(pnl))}>
          P&amp;L {pnl >= 0 ? '+' : ''}{fmtUsd(pnl)}
        </span>
        <span>Last fill {lastAt || '—'}</span>
      </div>
    </div>
  );
}
