import { usePortfolioSnapshot } from '@/hooks/use-portfolio';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { HlPositionCard, type Position } from './HlPositionCard';

interface HlData {
  positions?: Position[];
  [key: string]: unknown;
}

interface Snapshot {
  hyperliquid?: HlData;
  [key: string]: unknown;
}

export function HlPositions() {
  const { data, isLoading } = usePortfolioSnapshot();
  const snapshot = data as Snapshot | null;
  const positions = snapshot?.hyperliquid?.positions ?? [];

  return (
    <Card className="sm:col-span-3">
      <CardHeader>
        <CardTitle className="text-base">Perp Positions</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : positions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No perp positions</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {positions.map((p) => (
              <HlPositionCard key={p.coin} position={p} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
