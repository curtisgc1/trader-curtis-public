import { useState, useEffect } from 'react';
import { useRiskControls, useRiskControlsMutation, useActionMutation } from '@/hooks/use-controls';
import { ControlPanel, ControlRow } from '@/components/shared/ControlPanel';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface ConsensusControlsProps {
  alignedMode: string;
  onAlignedModeChange: (mode: string) => void;
}

interface ControlRecord {
  key: string;
  value: string;
  [key: string]: unknown;
}

export function ConsensusControls({ alignedMode, onAlignedModeChange }: ConsensusControlsProps) {
  const { data: rawControls, isLoading } = useRiskControls();
  const saveMutation = useRiskControlsMutation();
  const actionMutation = useActionMutation();

  const controls: Record<string, string> = {};
  if (Array.isArray(rawControls)) {
    (rawControls as ControlRecord[]).forEach((r) => {
      controls[r.key] = String(r.value ?? '');
    });
  }

  const [master, setMaster] = useState(false);
  const [consensusEnforce, setConsensusEnforce] = useState(true);
  const [minConf, setMinConf] = useState('3');
  const [minRatio, setMinRatio] = useState('0.6');
  const [minScore, setMinScore] = useState('60');
  const [statusMsg, setStatusMsg] = useState<{ text: string; ok: boolean } | null>(null);

  // Sync local state when controls load
  useEffect(() => {
    if (!isLoading && Object.keys(controls).length > 0) {
      setMaster((controls.agent_master_enabled ?? '0') === '1');
      setConsensusEnforce((controls.consensus_enforce ?? '1') === '1');
      setMinConf(controls.consensus_min_confirmations ?? '3');
      setMinRatio(controls.consensus_min_ratio ?? '0.6');
      setMinScore(controls.consensus_min_score ?? '60');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading]);

  function showStatus(text: string, ok: boolean) {
    setStatusMsg({ text, ok });
    setTimeout(() => setStatusMsg(null), 3000);
  }

  async function handleSave() {
    try {
      await saveMutation.mutateAsync({
        agent_master_enabled: master ? '1' : '0',
        consensus_enforce: consensusEnforce ? '1' : '0',
        consensus_min_confirmations: minConf,
        consensus_min_ratio: minRatio,
        consensus_min_score: minScore,
      });
      showStatus('Controls saved', true);
    } catch {
      showStatus('Save failed', false);
    }
  }

  async function handleScan() {
    try {
      await actionMutation.mutateAsync('run_scan');
      showStatus('Scan triggered', true);
    } catch {
      showStatus('Scan trigger failed', false);
    }
  }

  async function handlePolyAlign() {
    try {
      await actionMutation.mutateAsync('run_poly_align');
      showStatus('Polymarket alignment triggered', true);
    } catch {
      showStatus('Polymarket alignment failed', false);
    }
  }

  return (
    <ControlPanel
      title="Master & Consensus Controls"
      span={2}
      onSave={handleSave}
      isSaving={saveMutation.isPending}
      actions={[
        {
          label: 'Scan',
          onClick: handleScan,
          variant: 'outline',
          loading: actionMutation.isPending,
        },
        {
          label: 'Build Poly Alignments',
          onClick: handlePolyAlign,
          variant: 'outline',
          loading: actionMutation.isPending,
        },
      ]}
    >
      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading controls...</div>
      ) : (
        <>
          <ControlRow label="Master On/Off" description="Enable or disable the master trading switch">
            <Switch checked={master} onCheckedChange={setMaster} />
          </ControlRow>

          <ControlRow label="Consensus Enforce" description="Require consensus before executing trades">
            <Switch checked={consensusEnforce} onCheckedChange={setConsensusEnforce} />
          </ControlRow>

          <ControlRow label="Min Confirmations">
            <Input
              type="number"
              value={minConf}
              onChange={(e) => setMinConf(e.target.value)}
              className="w-20 text-right"
              min={1}
              max={20}
            />
          </ControlRow>

          <ControlRow label="Min Ratio">
            <Input
              type="number"
              value={minRatio}
              onChange={(e) => setMinRatio(e.target.value)}
              className="w-24 text-right"
              min={0}
              max={1}
              step={0.05}
            />
          </ControlRow>

          <ControlRow label="Min Score">
            <Input
              type="number"
              value={minScore}
              onChange={(e) => setMinScore(e.target.value)}
              className="w-24 text-right"
              min={0}
              max={100}
            />
          </ControlRow>

          <ControlRow label="Aligned Mode">
            <Select value={alignedMode} onValueChange={onAlignedModeChange}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="strong">Strong</SelectItem>
                <SelectItem value="weak">Weak</SelectItem>
              </SelectContent>
            </Select>
          </ControlRow>

          {statusMsg && (
            <div className="pt-1">
              <Badge variant={statusMsg.ok ? 'default' : 'destructive'}>
                {statusMsg.text}
              </Badge>
            </div>
          )}
        </>
      )}
    </ControlPanel>
  );
}

// Re-export Label so it's not marked unused — it may be needed in future edits
export { Label };
