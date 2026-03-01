import { usePolymarketMarkets } from '@/hooks/use-polymarket';
import { PolyPositionCard, type PolyMarket } from './PolyPositionCard';

export function PolyPositions() {
  const { data, isLoading } = usePolymarketMarkets();
  const markets = (data ?? []) as PolyMarket[];

  if (isLoading) {
    return (
      <div className="text-sm text-muted-foreground py-4">Loading positions...</div>
    );
  }

  if (!markets.length) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">
        No active positions
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {markets.map((m, i) => (
        <PolyPositionCard key={(m.market_id as string | undefined) ?? i} market={m} />
      ))}
    </div>
  );
}
