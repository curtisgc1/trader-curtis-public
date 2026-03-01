import { useState } from 'react';
import { useHyperliquidClosePosition } from '@/hooks/use-hyperliquid';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { MarginBar } from '@/components/shared/MarginBar';
import { fmtUsd, fmtNumber, pnlClass } from '@/lib/format';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface Position {
  coin: string;
  szi: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  leverage?: number;
  liquidation_price?: number;
  margin_used?: number;
  position_value?: number;
  cum_funding?: number;
  [key: string]: unknown;
}

interface HlPositionCardProps {
  position: Position;
}

export function HlPositionCard({ position: p }: HlPositionCardProps) {
  const closeMutation = useHyperliquidClosePosition();
  const [confirmed, setConfirmed] = useState(false);

  const szi = Number(p.szi ?? 0);
  const isLong = szi >= 0;
  const pnl = Number(p.unrealized_pnl ?? 0);
  const pnlPct = Number(p.unrealized_pnl_pct ?? 0);
  const lev = Number(p.leverage ?? 1).toFixed(1);
  const liqPrice = Number(p.liquidation_price ?? 0);
  const marginUsed = Number(p.margin_used ?? 0);
  const posValue = Number(p.position_value ?? 0);
  const funding = Number(p.cum_funding ?? 0);

  // Margin utilization percentage — use position's own margin_used vs position_value as proxy
  const marginPct = posValue > 0 ? (marginUsed / posValue) * 100 : 0;

  function handleClose() {
    if (!confirmed) {
      setConfirmed(true);
      return;
    }
    closeMutation.mutate(p.coin);
    setConfirmed(false);
  }

  return (
    <Card
      className={cn(
        'border',
        pnl >= 0
          ? 'border-primary/20 bg-primary/5'
          : 'border-destructive/20 bg-destructive/5',
      )}
    >
      <CardContent className="pt-4 space-y-3">
        {/* Header */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-base font-bold">{p.coin}</span>
          <Badge variant={isLong ? 'default' : 'destructive'}>
            {isLong ? 'LONG' : 'SHORT'}
          </Badge>
          <span className="text-xs text-muted-foreground">{lev}x</span>
          <span className="text-xs text-muted-foreground font-mono ml-auto">
            {fmtNumber(Math.abs(szi), 4)} {p.coin}
          </span>
          <span className="text-xs text-muted-foreground">
            Margin {fmtUsd(marginUsed)}
          </span>
        </div>

        {/* Prices */}
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div>
            <p className="text-muted-foreground mb-0.5">Entry</p>
            <p className="font-mono font-semibold">{fmtUsd(p.entry_price)}</p>
          </div>
          <div>
            <p className="text-muted-foreground mb-0.5">Mark</p>
            <p className="font-mono font-semibold">{fmtUsd(p.mark_price)}</p>
          </div>
          <div>
            <p className="text-muted-foreground mb-0.5">Liq Price</p>
            <p className={cn('font-mono font-semibold', liqPrice > 0 ? 'text-destructive' : 'text-muted-foreground')}>
              {liqPrice > 0 ? fmtUsd(liqPrice) : '—'}
            </p>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-2 text-xs">
          <div>
            <p className="text-muted-foreground mb-0.5">Pos Value</p>
            <p className="font-mono">{fmtUsd(posValue)}</p>
          </div>
          <div>
            <p className="text-muted-foreground mb-0.5">uPnL</p>
            <p className={cn('font-mono font-semibold', pnlClass(pnl))}>
              {pnl >= 0 ? '+' : ''}{fmtUsd(pnl)}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground mb-0.5">ROE%</p>
            <p className={cn('font-mono', pnlClass(pnlPct))}>
              {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
            </p>
          </div>
          <div>
            <p className="text-muted-foreground mb-0.5">Funding</p>
            <p className={cn('font-mono', pnlClass(-funding))}>
              {fmtUsd(-funding)}
            </p>
          </div>
        </div>

        {/* Margin bar */}
        <MarginBar usedPct={marginPct} />

        {/* Close button */}
        <div className="pt-1">
          <Button
            variant="destructive"
            size="sm"
            className="w-full"
            onClick={handleClose}
            disabled={closeMutation.isPending}
          >
            {closeMutation.isPending && (
              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
            )}
            {confirmed ? `Confirm close ${p.coin}?` : 'Close Position'}
          </Button>
          {confirmed && !closeMutation.isPending && (
            <button
              className="mt-1 w-full text-xs text-muted-foreground hover:text-foreground"
              onClick={() => setConfirmed(false)}
            >
              Cancel
            </button>
          )}
          {closeMutation.isError && (
            <p className="mt-1 text-xs text-destructive">
              {(closeMutation.error as Error).message}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
