import { LearningHealth } from '@/features/learning/LearningHealth';
import { MemoryIntegrity } from '@/features/learning/MemoryIntegrity';
import { SourceLearning } from '@/features/learning/SourceLearning';
import { StrategyLearning } from '@/features/learning/StrategyLearning';
import { ExecutionLearning } from '@/features/learning/ExecutionLearning';
import { TradeIntents } from '@/features/learning/TradeIntents';
import { InputFeatureStats } from '@/features/learning/InputFeatureStats';

export function LearningPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Learning</h1>

      {/* Row 1: Health + Memory Integrity */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <LearningHealth />
        <MemoryIntegrity />
      </div>

      {/* Row 2: Source Learning + Strategy Learning */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <SourceLearning />
        <StrategyLearning />
      </div>

      {/* Row 3: Execution Learning + Trade Intents */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <ExecutionLearning />
        <TradeIntents />
      </div>

      {/* Row 4: Input Feature Stats (full width) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <InputFeatureStats />
      </div>
    </div>
  );
}
