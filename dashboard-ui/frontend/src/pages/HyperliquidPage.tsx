import { HlOverview } from '@/features/hyperliquid/HlOverview';
import { HlPositions } from '@/features/hyperliquid/HlPositions';
import { SpotBalances } from '@/features/hyperliquid/SpotBalances';
import { HlControls } from '@/features/hyperliquid/HlControls';
import { HlIntents, HlPositionManagement } from '@/features/hyperliquid/HlIntents';
import { HlRoutes } from '@/features/hyperliquid/HlRoutes';
import { QuickTradeForm } from '@/components/shared/QuickTradeForm';

const HL_SYMBOLS = [
  'BTC', 'ETH', 'SOL', 'DOGE', 'XRP',
  'AVAX', 'BNB', 'LTC', 'SUI', 'HYPE',
];

export function HyperliquidPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Hyperliquid</h1>

      {/* Row 1: Account Overview (full width) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <HlOverview />
      </div>

      {/* Row 2: Perp Positions (full width) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <HlPositions />
      </div>

      {/* Row 3: Spot Balances + Pre-Trade Controls + Quick Trade */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <SpotBalances />
        <HlControls />
        <QuickTradeForm
          venue="hyperliquid"
          symbols={HL_SYMBOLS}
          invalidateKeys={['hyperliquid-intents', 'portfolio-snapshot']}
        />
      </div>

      {/* Row 4: Trade Intents + Position Management + Signal Routes */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <HlIntents />
        <HlPositionManagement />
        <HlRoutes />
      </div>
    </div>
  );
}
