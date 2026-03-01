import { useState, useEffect } from 'react';
import { useVenueMatrix } from '@/hooks/use-signals';
import { useRiskControls, useRiskControlsMutation, useVenueMatrixMutation } from '@/hooks/use-controls';
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

interface VenueEntry {
  venue: string;
  enabled: number;
  mode: string;
  min_score: number;
  max_notional: number;
  [key: string]: unknown;
}

interface RiskControl {
  key: string;
  value: string;
  [key: string]: unknown;
}

function getControl(controls: RiskControl[], key: string, def: string): string {
  return controls.find((c) => c.key === key)?.value ?? def;
}

export function AlpacaControls() {
  const { data: venueData } = useVenueMatrix();
  const { data: riskData } = useRiskControls();
  const venueMutation = useVenueMatrixMutation();
  const riskMutation = useRiskControlsMutation();

  const venues = (venueData ?? []) as VenueEntry[];
  const riskControls = (riskData ?? []) as RiskControl[];

  const [enabled, setEnabled] = useState(false);
  const [mode, setMode] = useState('paper');
  const [minScore, setMinScore] = useState('0');
  const [maxNotional, setMaxNotional] = useState('0');
  const [allowShorts, setAllowShorts] = useState(true);
  const [highBeta, setHighBeta] = useState(true);
  const [consensusEnforce, setConsensusEnforce] = useState(true);
  const [alpacaMinRoute, setAlpacaMinRoute] = useState('60');
  const [pgKw, setPgKw] = useState(false);
  const [pgLiq, setPgLiq] = useState(false);
  const [pgMom, setPgMom] = useState(false);
  const [pgMin, setPgMin] = useState('0');

  // Populate from fetched data
  useEffect(() => {
    const stocks = venues.find(
      (v) => (v.venue ?? '').toLowerCase() === 'stocks',
    );
    if (stocks) {
      setEnabled(Number(stocks.enabled) === 1);
      setMode(stocks.mode ?? 'paper');
      setMinScore(String(stocks.min_score ?? 0));
      setMaxNotional(String(stocks.max_notional ?? 0));
    }
  }, [venues]);

  useEffect(() => {
    if (riskControls.length === 0) return;
    setAllowShorts(getControl(riskControls, 'allow_equity_shorts', '1') === '1');
    setHighBeta(getControl(riskControls, 'high_beta_only', '1') === '1');
    setConsensusEnforce(getControl(riskControls, 'consensus_enforce', '1') === '1');
    setAlpacaMinRoute(getControl(riskControls, 'alpaca_min_route_score', '60'));
    setPgKw(getControl(riskControls, 'premium_gate_kw_stocks', '0') === '1');
    setPgLiq(getControl(riskControls, 'premium_gate_liq_stocks', '0') === '1');
    setPgMom(getControl(riskControls, 'premium_gate_mom_stocks', '0') === '1');
    setPgMin(getControl(riskControls, 'premium_gate_stocks_min', '0'));
  }, [riskControls]);

  const isSaving = venueMutation.isPending || riskMutation.isPending;

  async function handleSave() {
    await venueMutation.mutateAsync([
      {
        venue: 'stocks',
        enabled: enabled ? 1 : 0,
        mode,
        min_score: Number(minScore),
        max_notional: Number(maxNotional),
      },
    ]);
    await riskMutation.mutateAsync({
      allow_equity_shorts: allowShorts ? '1' : '0',
      high_beta_only: highBeta ? '1' : '0',
      consensus_enforce: consensusEnforce ? '1' : '0',
      alpaca_min_route_score: alpacaMinRoute,
      premium_gate_kw_stocks: pgKw ? '1' : '0',
      premium_gate_liq_stocks: pgLiq ? '1' : '0',
      premium_gate_mom_stocks: pgMom ? '1' : '0',
      premium_gate_stocks_min: pgMin,
    });
  }

  return (
    <ControlPanel title="Pre-Trade Controls (Stocks)" onSave={handleSave} isSaving={isSaving}>
      <ControlRow label="Venue Enabled">
        <Switch checked={enabled} onCheckedChange={setEnabled} />
      </ControlRow>

      <ControlRow label="Mode">
        <Select value={mode} onValueChange={setMode}>
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="paper">Paper</SelectItem>
            <SelectItem value="live">Live</SelectItem>
          </SelectContent>
        </Select>
      </ControlRow>

      <ControlRow label="Min Score">
        <Input
          type="number"
          className="w-24"
          value={minScore}
          onChange={(e) => setMinScore(e.target.value)}
        />
      </ControlRow>

      <ControlRow label="Max Notional ($)">
        <Input
          type="number"
          className="w-24"
          value={maxNotional}
          onChange={(e) => setMaxNotional(e.target.value)}
        />
      </ControlRow>

      <ControlRow label="Allow Shorts">
        <Switch checked={allowShorts} onCheckedChange={setAllowShorts} />
      </ControlRow>

      <ControlRow label="High-Beta Only">
        <Switch checked={highBeta} onCheckedChange={setHighBeta} />
      </ControlRow>

      <ControlRow label="Consensus Enforce">
        <Switch checked={consensusEnforce} onCheckedChange={setConsensusEnforce} />
      </ControlRow>

      <ControlRow label="Alpaca Min Route Score">
        <Input
          type="number"
          className="w-24"
          value={alpacaMinRoute}
          onChange={(e) => setAlpacaMinRoute(e.target.value)}
        />
      </ControlRow>

      <div className="space-y-2 pt-1">
        <p className="text-xs font-medium text-muted-foreground">Premium Gates</p>
        <ControlRow label="KW Gate">
          <Switch checked={pgKw} onCheckedChange={setPgKw} />
        </ControlRow>
        <ControlRow label="Liquidity Gate">
          <Switch checked={pgLiq} onCheckedChange={setPgLiq} />
        </ControlRow>
        <ControlRow label="Momentum Gate">
          <Switch checked={pgMom} onCheckedChange={setPgMom} />
        </ControlRow>
        <ControlRow label="Gate Min Score">
          <Input
            type="number"
            className="w-24"
            value={pgMin}
            onChange={(e) => setPgMin(e.target.value)}
          />
        </ControlRow>
      </div>

      {(venueMutation.isError || riskMutation.isError) && (
        <p className="text-xs text-destructive">
          {(venueMutation.error as Error | null)?.message ??
            (riskMutation.error as Error | null)?.message}
        </p>
      )}
      {venueMutation.isSuccess && riskMutation.isSuccess && (
        <p className="text-xs text-primary">Saved</p>
      )}
    </ControlPanel>
  );
}
