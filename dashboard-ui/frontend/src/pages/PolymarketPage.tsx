import { PolyOverview } from '@/features/polymarket/PolyOverview';
import { PolyPositions } from '@/features/polymarket/PolyPositions';
import { BrainStatus } from '@/features/polymarket/BrainStatus';
import { ArbScanner } from '@/features/polymarket/ArbScanner';
import { BrainCopyTrades } from '@/features/polymarket/BrainCopyTrades';
import { ArbOpportunities } from '@/features/polymarket/ArbOpportunities';
import { GrokAlpha } from '@/features/polymarket/GrokAlpha';
import { GrokScores } from '@/features/polymarket/GrokScores';
import { FilteredSignals } from '@/features/polymarket/FilteredSignals';
import { BrainControls } from '@/features/polymarket/BrainControls';
import { SimulationPanel } from '@/features/polymarket/SimulationPanel';

export function PolymarketPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Polymarket</h1>

      {/* Row 1: Account Overview (span-3) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <PolyOverview />
      </div>

      {/* Row 2: Position Cards (dynamic grid) */}
      <PolyPositions />

      {/* Row 3: Brain Status + Arb Scanner */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <BrainStatus />
        <ArbScanner />
      </div>

      {/* Row 4: Brain Copy Trades + Arb Opportunities */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <BrainCopyTrades />
        <ArbOpportunities />
      </div>

      {/* Row 5: Grok Alpha Bets + Grok Market Scores */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <GrokAlpha />
        <GrokScores />
      </div>

      {/* Row 6: Filtered Signals + Brain Controls */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FilteredSignals />
        <BrainControls />
      </div>

      {/* Row 7: Simulation Engine */}
      <SimulationPanel />
    </div>
  );
}
