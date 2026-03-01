import { AlpacaOverview } from '@/features/alpaca/AlpacaOverview';
import { AlpacaPositions } from '@/features/alpaca/AlpacaPositions';
import { AlpacaControls } from '@/features/alpaca/AlpacaControls';
import { AlpacaOrders } from '@/features/alpaca/AlpacaOrders';
import { AlpacaRoutes } from '@/features/alpaca/AlpacaRoutes';
import { AlpacaClosedTrades } from '@/features/alpaca/AlpacaClosedTrades';
import { QuickTradeForm } from '@/components/shared/QuickTradeForm';

export function AlpacaPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Alpaca</h1>

      {/* Row 1: Account Overview (span-2) + Open Positions */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <AlpacaOverview />
        <AlpacaPositions />
      </div>

      {/* Row 2: Pre-Trade Controls + Quick Trade */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <AlpacaControls />
        <QuickTradeForm
          venue="alpaca"
          invalidateKeys={['alpaca-orders', 'portfolio-snapshot']}
        />
      </div>

      {/* Row 3: Execution Orders (span-2) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <AlpacaOrders />
      </div>

      {/* Row 4: Signal Routes (span-2) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <AlpacaRoutes />
      </div>

      {/* Row 5: Closed Trades (span-2) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <AlpacaClosedTrades />
      </div>
    </div>
  );
}
