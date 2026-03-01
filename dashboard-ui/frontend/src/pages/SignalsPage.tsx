import { CoreSignals } from '@/features/signals/CoreSignals';
import { TradeReplay } from '@/features/signals/TradeReplay';
import { KellySignals } from '@/features/signals/KellySignals';
import { MissedWins } from '@/features/signals/MissedWins';
import { AdvancedDiagnostics } from '@/features/signals/AdvancedDiagnostics';

export function SignalsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Signals</h1>

      {/* Row 1: Core signal overview (full width) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <CoreSignals />
      </div>

      {/* Row 2: Signal routes / trade replay (full width) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <TradeReplay />
      </div>

      {/* Row 3: Kelly sizing (span-2) + Missed wins (span-2, wraps below on narrow) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <KellySignals />
        <MissedWins />
      </div>

      {/* Row 4: Quant validations / diagnostics (full width) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <AdvancedDiagnostics />
      </div>
    </div>
  );
}
