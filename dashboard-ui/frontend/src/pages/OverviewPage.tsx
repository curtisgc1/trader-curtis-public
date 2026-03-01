import { HealthPulse } from '@/features/overview/HealthPulse';
import { IdLookup } from '@/features/overview/IdLookup';
import { ExchangePnl } from '@/features/overview/ExchangePnl';
import { SignalScorecard } from '@/features/overview/SignalScorecard';
import { PipelineHealth } from '@/features/overview/PipelineHealth';
import { MasterControls } from '@/features/overview/MasterControls';
import { PortfolioSummary } from '@/features/overview/PortfolioSummary';
import { SignalControls } from '@/features/overview/SignalControls';
import { PerformanceCurve } from '@/features/overview/PerformanceCurve';
import { SystemIntelligence } from '@/features/overview/SystemIntelligence';
import { SourceHealth } from '@/features/overview/SourceHealth';

export function OverviewPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Mission Control</h1>

      {/* Row 1: Portfolio Summary (full width) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <PortfolioSummary />
      </div>

      {/* Row 2: Health Pulse + Master Controls + ID Lookup */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <HealthPulse />
        <MasterControls />
        <IdLookup />
      </div>

      {/* Row 3: Exchange P&L + Risk Controls */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <ExchangePnl />
        <SignalControls />
      </div>

      {/* Row 4: Performance Curve + Signal Scorecard (each span-2, wraps) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <PerformanceCurve />
        <SignalScorecard />
      </div>

      {/* Row 5: Pipeline Health + System Intelligence */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <PipelineHealth />
        <SystemIntelligence />
      </div>

      {/* Row 6: Source Health (span-2, wraps into next row area) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <SourceHealth />
      </div>
    </div>
  );
}
