import { useState, useEffect } from 'react';
import { useVenueMatrix } from '@/hooks/use-signals';
import { useVenueMatrixMutation } from '@/hooks/use-controls';
import { ControlPanel, ControlRow } from '@/components/shared/ControlPanel';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface VenueRow {
  venue: string;
  enabled?: number | boolean;
  mode?: string;
  min_score?: number;
  max_notional?: number;
  [key: string]: unknown;
}

export function HlControls() {
  const { data: venueMatrix } = useVenueMatrix();
  const mutation = useVenueMatrixMutation();

  const [enabled, setEnabled] = useState(false);
  const [mode, setMode] = useState('paper');
  const [minScore, setMinScore] = useState('0');
  const [maxNotional, setMaxNotional] = useState('0');

  // Seed from server data on load
  useEffect(() => {
    if (!venueMatrix) return;
    const rows = venueMatrix as VenueRow[];
    const crypto = rows.find(
      (v) => (v.venue ?? '').toLowerCase() === 'crypto',
    );
    if (!crypto) return;
    setEnabled(Number(crypto.enabled) === 1);
    setMode(String(crypto.mode ?? 'paper'));
    setMinScore(String(crypto.min_score ?? 0));
    setMaxNotional(String(crypto.max_notional ?? 0));
  }, [venueMatrix]);

  function handleSave() {
    mutation.mutate([
      {
        venue: 'crypto',
        enabled: enabled ? 1 : 0,
        mode,
        min_score: Number(minScore),
        max_notional: Number(maxNotional),
      },
    ]);
  }

  return (
    <ControlPanel
      title="Pre-Trade Controls (Crypto)"
      onSave={handleSave}
      isSaving={mutation.isPending}
    >
      <ControlRow
        label="Crypto Trading Enabled"
        description="Toggle crypto venue on/off"
      >
        <Switch
          checked={enabled}
          onCheckedChange={setEnabled}
        />
      </ControlRow>

      <ControlRow label="Mode" description="paper or live">
        <Select value={mode} onValueChange={setMode}>
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="paper">paper</SelectItem>
            <SelectItem value="live">live</SelectItem>
          </SelectContent>
        </Select>
      </ControlRow>

      <ControlRow label="Min Score" description="Minimum signal score to trade">
        <Input
          type="number"
          className="w-28 text-right"
          value={minScore}
          onChange={(e) => setMinScore(e.target.value)}
        />
      </ControlRow>

      <ControlRow label="Max Notional ($)" description="Per-trade notional cap">
        <Input
          type="number"
          className="w-28 text-right"
          value={maxNotional}
          onChange={(e) => setMaxNotional(e.target.value)}
        />
      </ControlRow>

      {mutation.isError && (
        <p className="text-xs text-destructive">
          {(mutation.error as Error).message}
        </p>
      )}
      {mutation.isSuccess && (
        <p className="text-xs text-primary">Saved</p>
      )}
    </ControlPanel>
  );
}
