import { useRiskControls } from '@/hooks/use-overview';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { fmtUsd, fmtPct } from '@/lib/format';

interface RiskData {
  max_position_size_usd?: number;
  max_portfolio_risk_pct?: number;
  max_drawdown_pct?: number;
  daily_loss_limit_usd?: number;
  max_leverage?: number;
  stop_loss_pct?: number;
  take_profit_pct?: number;
  cooldown_minutes?: number;
  min_confidence?: number;
  [key: string]: unknown;
}

function LimitRow({ label, value, warn }: {
  label: string;
  value: string;
  warn?: boolean;
}) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn(
        'text-sm font-mono font-medium',
        warn ? 'text-chart-3' : '',
      )}>
        {value}
      </span>
    </div>
  );
}

export function SignalControls() {
  const { data, isLoading } = useRiskControls();
  const risk = (data ?? {}) as RiskData;

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Risk Controls</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Loading...</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Risk Controls</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <LimitRow label="Max Position" value={fmtUsd(risk.max_position_size_usd)} />
          <LimitRow label="Portfolio Risk" value={fmtPct(risk.max_portfolio_risk_pct)} />
          <LimitRow label="Max Drawdown" value={fmtPct(risk.max_drawdown_pct)} />
          <LimitRow label="Daily Loss Limit" value={fmtUsd(risk.daily_loss_limit_usd)} />
        </div>

        <Separator />

        <div className="space-y-1">
          <LimitRow label="Max Leverage" value={`${risk.max_leverage ?? 0}x`} />
          <LimitRow label="Stop Loss" value={fmtPct(risk.stop_loss_pct)} />
          <LimitRow label="Take Profit" value={fmtPct(risk.take_profit_pct)} />
          <LimitRow label="Cooldown" value={`${risk.cooldown_minutes ?? 0}m`} />
          <LimitRow label="Min Confidence" value={fmtPct(risk.min_confidence)} />
        </div>
      </CardContent>
    </Card>
  );
}
