import { useHealthPulse, useMarketRegime } from '@/hooks/use-overview';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { HealthRing } from '@/components/shared/HealthRing';
import { cn } from '@/lib/utils';

interface PulseData {
  overall_score?: number;
  status?: string;
  uptime_pct?: number;
  latency_ms?: number;
  errors_1h?: number;
  last_heartbeat?: string;
  [key: string]: unknown;
}

interface RegimeData {
  regime?: string;
  confidence?: number;
  [key: string]: unknown;
}

function statusVariant(status: string | undefined) {
  if (!status) return 'secondary' as const;
  const s = status.toLowerCase();
  if (s === 'good' || s === 'healthy') return 'default' as const;
  if (s === 'warn' || s === 'degraded') return 'outline' as const;
  return 'destructive' as const;
}

function MetricRow({ label, value, valueClass }: {
  label: string;
  value: React.ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn('text-sm font-mono font-medium', valueClass)}>{value}</span>
    </div>
  );
}

export function HealthPulse() {
  const { data: pulseData, isLoading: pulseLoading } = useHealthPulse();
  const { data: regimeData } = useMarketRegime();
  const pulse = (pulseData ?? {}) as PulseData;
  const regime = (regimeData ?? {}) as RegimeData;

  if (pulseLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">System Health</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Loading...</div>
        </CardContent>
      </Card>
    );
  }

  const score = Number(pulse.overall_score ?? 0);
  const status = pulse.status ?? 'unknown';

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">System Health</CardTitle>
          <Badge variant={statusVariant(status)} className="text-xs">
            {status.toUpperCase()}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex justify-center">
          <HealthRing value={score} label="Health Score" size={96} />
        </div>
        <div className="space-y-1">
          <MetricRow label="Uptime" value={`${(pulse.uptime_pct ?? 0).toFixed(1)}%`} />
          <MetricRow label="Latency" value={`${pulse.latency_ms ?? 0}ms`} />
          <MetricRow
            label="Errors (1h)"
            value={pulse.errors_1h ?? 0}
            valueClass={Number(pulse.errors_1h ?? 0) > 0 ? 'text-destructive' : undefined}
          />
          {regime.regime && (
            <MetricRow
              label="Market Regime"
              value={regime.regime}
              valueClass="text-chart-3"
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
