import { useState } from 'react';
import { TrustState } from '@/features/consensus/TrustState';
import { ConsensusControls } from '@/features/consensus/ConsensusControls';
import { FlaggedTrades } from '@/features/consensus/FlaggedTrades';
import { SourceRatings } from '@/features/consensus/SourceRatings';
import { AlignedSetups } from '@/features/consensus/AlignedSetups';

export function ConsensusPage() {
  const [alignedMode, setAlignedMode] = useState('all');

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Consensus</h1>

      {/* Row 1: Trust State + Master & Consensus Controls (span-2) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <TrustState />
        <ConsensusControls alignedMode={alignedMode} onAlignedModeChange={setAlignedMode} />
      </div>

      {/* Row 2: Flagged Trades (span-2) + Source Ratings */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <FlaggedTrades />
        <SourceRatings />
      </div>

      {/* Row 3: Aligned Setups (full width) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <AlignedSetups mode={alignedMode} />
      </div>
    </div>
  );
}
