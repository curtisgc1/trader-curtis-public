import { useState, useEffect } from 'react';
import { useArbOverview } from '@/hooks/use-polymarket';
import { useRiskControlsMutation } from '@/hooks/use-controls';
import { ControlPanel, ControlRow } from '@/components/shared/ControlPanel';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { fmtUsd } from '@/lib/format';

interface ArbOverviewData {
  arb_enabled?: boolean;
  total_scanned?: number;
  executed?: number;
  partial?: number;
  avg_spread?: number;
  total_notional?: number;
  min_spread_pct?: number;
  max_per_leg?: number;
  [key: string]: unknown;
}

function StatItem({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-mono">{value}</span>
    </div>
  );
}

export function ArbScanner() {
  const { data, isLoading } = useArbOverview();
  const saveMutation = useRiskControlsMutation();

  const arb = (data ?? {}) as ArbOverviewData;

  const [arbEnabled, setArbEnabled] = useState(false);
  const [minSpread, setMinSpread] = useState('5');
  const [maxPerLeg, setMaxPerLeg] = useState('25');
  const [statusMsg, setStatusMsg] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    if (!isLoading && data) {
      setArbEnabled(!!arb.arb_enabled);
      setMinSpread(String(arb.min_spread_pct ?? 5));
      setMaxPerLeg(String(arb.max_per_leg ?? 25));
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
        tb_arb_enabled: arbEnabled ? '1' : '0',
        tb_arb_min_spread_pct: minSpread,
        tb_arb_max_per_leg: maxPerLeg,
      });
      showStatus('Saved arb settings', true);
    } catch {
      showStatus('Save failed', false);
    }
  }

  return (
    <ControlPanel
      title="Cross-Platform Arb Scanner"
      onSave={handleSave}
      isSaving={saveMutation.isPending}
    >
      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading...</div>
      ) : !data || arb.total_scanned === undefined ? (
        <div className="text-sm text-muted-foreground">No arb data</div>
      ) : (
        <>
          {/* Status summary */}
          <div className="space-y-0.5 rounded border border-border bg-muted/30 p-2">
            <StatItem
              label="Scanner"
              value={
                <span className={arb.arb_enabled ? 'text-primary' : 'text-destructive'}>
                  {arb.arb_enabled ? 'ON' : 'OFF'}
                </span>
              }
            />
            <StatItem label="Pairs Scanned (7d)" value={arb.total_scanned ?? 0} />
            <StatItem label="Executed" value={arb.executed ?? 0} />
            <StatItem label="Partial (unhedged)" value={arb.partial ?? 0} />
            <StatItem label="Avg Spread (net)" value={Number(arb.avg_spread ?? 0).toFixed(4)} />
            <StatItem label="Total Notional" value={fmtUsd(arb.total_notional ?? 0)} />
          </div>

          {/* Controls */}
          <ControlRow label="Arb Enabled" description="Enable cross-platform arb scanner">
            <Switch checked={arbEnabled} onCheckedChange={setArbEnabled} />
          </ControlRow>

          <ControlRow label="Min Spread %" description="Minimum spread threshold after fees">
            <Input
              type="number"
              value={minSpread}
              onChange={(e) => setMinSpread(e.target.value)}
              className="w-20 text-right"
              min={0}
              max={100}
              step={0.5}
            />
          </ControlRow>

          <ControlRow label="Max Per Leg ($)" description="Maximum USD per arb leg">
            <Input
              type="number"
              value={maxPerLeg}
              onChange={(e) => setMaxPerLeg(e.target.value)}
              className="w-20 text-right"
              min={1}
            />
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
