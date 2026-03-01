import { useState, useEffect } from 'react';
import { useRiskControls, useRiskControlsMutation } from '@/hooks/use-controls';
import { ControlPanel, ControlRow } from '@/components/shared/ControlPanel';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';

interface ControlRecord {
  key: string;
  value: string;
  [key: string]: unknown;
}

function normalizeControls(raw: unknown): Record<string, string> {
  if (!raw) return {};
  if (Array.isArray(raw)) {
    const out: Record<string, string> = {};
    for (const r of raw as ControlRecord[]) {
      out[r.key] = String(r.value ?? '');
    }
    return out;
  }
  if (typeof raw === 'object') {
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
      out[k] = String(v ?? '');
    }
    return out;
  }
  return {};
}

export function BrainControls() {
  const { data: rawControls, isLoading } = useRiskControls();
  const saveMutation = useRiskControlsMutation();

  // Boolean fields
  const [enabled, setEnabled] = useState(false);
  const [notifySignal, setNotifySignal] = useState(false);
  const [notifyExec, setNotifyExec] = useState(false);
  const [grokEnabled, setGrokEnabled] = useState(true);
  const [grokAlphaEnabled, setGrokAlphaEnabled] = useState(true);

  // Numeric / string fields
  const [minTrade, setMinTrade] = useState('');
  const [winRate, setWinRate] = useState('');
  const [minTrades, setMinTrades] = useState('');
  const [minPnl, setMinPnl] = useState('');
  const [convergence, setConvergence] = useState('');
  const [convWindow, setConvWindow] = useState('');
  const [kelly, setKelly] = useState('');
  const [maxNotional, setMaxNotional] = useState('');
  const [daily, setDaily] = useState('');
  const [maxOpen, setMaxOpen] = useState('');
  const [grokMin, setGrokMin] = useState('70');
  const [grokBlock, setGrokBlock] = useState('30');
  const [grokBoost, setGrokBoost] = useState('1.3');
  const [grokAlphaBet, setGrokAlphaBet] = useState('15');
  const [grokAlphaEdge, setGrokAlphaEdge] = useState('20');

  const [statusMsg, setStatusMsg] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    if (!isLoading) {
      const c = normalizeControls(rawControls);
      setEnabled((c.tb_enabled ?? '0') === '1');
      setMinTrade(c.tb_min_trade_usdc ?? '');
      setWinRate(c.tb_min_wallet_win_rate ?? '');
      setMinTrades(c.tb_min_wallet_trades ?? '');
      setMinPnl(c.tb_min_wallet_pnl ?? '');
      setConvergence(c.tb_convergence_min ?? '');
      setConvWindow(c.tb_convergence_window_hours ?? '');
      setKelly(c.tb_kelly_fraction ?? '');
      setMaxNotional(c.tb_max_notional_per_trade ?? '');
      setDaily(c.tb_max_daily_exposure ?? '');
      setMaxOpen(c.tb_max_open_positions ?? '');
      setNotifySignal((c.tb_notify_on_signal ?? '0') === '1');
      setNotifyExec((c.tb_notify_on_execute ?? '0') === '1');
      setGrokEnabled((c.tb_grok_enabled ?? '1') === '1');
      setGrokMin(c.tb_grok_min_score ?? '70');
      setGrokBlock(c.tb_grok_block_below ?? '30');
      setGrokBoost(c.tb_grok_conviction_boost ?? '1.3');
      setGrokAlphaEnabled((c.tb_grok_alpha_enabled ?? '1') === '1');
      setGrokAlphaBet(c.tb_grok_alpha_bet_usd ?? '15');
      setGrokAlphaEdge(c.tb_grok_alpha_min_edge_pct ?? '20');
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
        tb_enabled: enabled ? '1' : '0',
        tb_min_trade_usdc: minTrade,
        tb_min_wallet_win_rate: winRate,
        tb_min_wallet_trades: minTrades,
        tb_min_wallet_pnl: minPnl,
        tb_convergence_min: convergence,
        tb_convergence_window_hours: convWindow,
        tb_kelly_fraction: kelly,
        tb_max_notional_per_trade: maxNotional,
        tb_max_daily_exposure: daily,
        tb_max_open_positions: maxOpen,
        tb_notify_on_signal: notifySignal ? '1' : '0',
        tb_notify_on_execute: notifyExec ? '1' : '0',
        tb_grok_enabled: grokEnabled ? '1' : '0',
        tb_grok_min_score: grokMin,
        tb_grok_block_below: grokBlock,
        tb_grok_conviction_boost: grokBoost,
        tb_grok_alpha_enabled: grokAlphaEnabled ? '1' : '0',
        tb_grok_alpha_bet_usd: grokAlphaBet,
        tb_grok_alpha_min_edge_pct: grokAlphaEdge,
      });
      showStatus('Controls saved', true);
    } catch {
      showStatus('Save failed', false);
    }
  }

  return (
    <ControlPanel
      title="Brain Controls"
      span={2}
      onSave={handleSave}
      isSaving={saveMutation.isPending}
    >
      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading controls...</div>
      ) : (
        <>
          {/* Core */}
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Core</div>

          <ControlRow label="Brain Enabled" description="Master on/off for trader brain">
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </ControlRow>

          <ControlRow label="Min Trade ($)" description="Minimum trade size in USDC">
            <Input
              type="number"
              value={minTrade}
              onChange={(e) => setMinTrade(e.target.value)}
              className="w-24 text-right"
              min={0}
            />
          </ControlRow>

          {/* Wallet Thresholds */}
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide pt-2">
            Wallet Thresholds
          </div>

          <ControlRow label="Min Win Rate" description="Min wallet historical win rate (0–1)">
            <Input
              type="number"
              value={winRate}
              onChange={(e) => setWinRate(e.target.value)}
              className="w-24 text-right"
              min={0}
              max={1}
              step={0.01}
            />
          </ControlRow>

          <ControlRow label="Min Wallet Trades" description="Min number of trades wallet must have">
            <Input
              type="number"
              value={minTrades}
              onChange={(e) => setMinTrades(e.target.value)}
              className="w-24 text-right"
              min={0}
            />
          </ControlRow>

          <ControlRow label="Min Wallet PnL ($)" description="Min wallet historical PnL">
            <Input
              type="number"
              value={minPnl}
              onChange={(e) => setMinPnl(e.target.value)}
              className="w-24 text-right"
            />
          </ControlRow>

          {/* Convergence */}
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide pt-2">
            Convergence
          </div>

          <ControlRow label="Convergence Min" description="Min number of wallets to trigger">
            <Input
              type="number"
              value={convergence}
              onChange={(e) => setConvergence(e.target.value)}
              className="w-24 text-right"
              min={1}
            />
          </ControlRow>

          <ControlRow label="Conv Window (hrs)" description="Lookback window in hours">
            <Input
              type="number"
              value={convWindow}
              onChange={(e) => setConvWindow(e.target.value)}
              className="w-24 text-right"
              min={1}
            />
          </ControlRow>

          {/* Position Sizing */}
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide pt-2">
            Position Sizing
          </div>

          <ControlRow label="Kelly Fraction" description="Kelly criterion fraction (0–1)">
            <Input
              type="number"
              value={kelly}
              onChange={(e) => setKelly(e.target.value)}
              className="w-24 text-right"
              min={0}
              max={1}
              step={0.05}
            />
          </ControlRow>

          <ControlRow label="Max Notional ($)" description="Max notional per trade">
            <Input
              type="number"
              value={maxNotional}
              onChange={(e) => setMaxNotional(e.target.value)}
              className="w-24 text-right"
              min={0}
            />
          </ControlRow>

          <ControlRow label="Max Daily Exposure ($)" description="Max daily exposure">
            <Input
              type="number"
              value={daily}
              onChange={(e) => setDaily(e.target.value)}
              className="w-24 text-right"
              min={0}
            />
          </ControlRow>

          <ControlRow label="Max Open Positions" description="Max concurrent open positions">
            <Input
              type="number"
              value={maxOpen}
              onChange={(e) => setMaxOpen(e.target.value)}
              className="w-24 text-right"
              min={0}
            />
          </ControlRow>

          {/* Notifications */}
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide pt-2">
            Notifications
          </div>

          <ControlRow label="Notify on Signal">
            <Switch checked={notifySignal} onCheckedChange={setNotifySignal} />
          </ControlRow>

          <ControlRow label="Notify on Execute">
            <Switch checked={notifyExec} onCheckedChange={setNotifyExec} />
          </ControlRow>

          {/* Grok */}
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide pt-2">
            Grok Scoring
          </div>

          <ControlRow label="Grok Enabled" description="Enable Grok sentiment scoring">
            <Switch checked={grokEnabled} onCheckedChange={setGrokEnabled} />
          </ControlRow>

          <ControlRow label="Grok Min Score" description="Min score to allow trade">
            <Input
              type="number"
              value={grokMin}
              onChange={(e) => setGrokMin(e.target.value)}
              className="w-24 text-right"
              min={0}
              max={100}
            />
          </ControlRow>

          <ControlRow label="Grok Block Below" description="Block trades scoring below this">
            <Input
              type="number"
              value={grokBlock}
              onChange={(e) => setGrokBlock(e.target.value)}
              className="w-24 text-right"
              min={0}
              max={100}
            />
          </ControlRow>

          <ControlRow label="Conviction Boost" description="Size multiplier when Grok is high">
            <Input
              type="number"
              value={grokBoost}
              onChange={(e) => setGrokBoost(e.target.value)}
              className="w-24 text-right"
              min={1}
              step={0.1}
            />
          </ControlRow>

          {/* Grok Alpha */}
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide pt-2">
            Grok Alpha Bets
          </div>

          <ControlRow label="Alpha Enabled" description="Enable Grok-driven alpha bets">
            <Switch checked={grokAlphaEnabled} onCheckedChange={setGrokAlphaEnabled} />
          </ControlRow>

          <ControlRow label="Alpha Bet ($)" description="USD bet size for alpha trades">
            <Input
              type="number"
              value={grokAlphaBet}
              onChange={(e) => setGrokAlphaBet(e.target.value)}
              className="w-24 text-right"
              min={0}
            />
          </ControlRow>

          <ControlRow label="Alpha Min Edge (%)" description="Min edge % to trigger alpha bet">
            <Input
              type="number"
              value={grokAlphaEdge}
              onChange={(e) => setGrokAlphaEdge(e.target.value)}
              className="w-24 text-right"
              min={0}
              max={100}
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
