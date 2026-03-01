import { useCoreSignals } from '@/hooks/use-signals';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { StatCard } from '@/components/shared/StatCard';
import { StatGrid } from '@/components/shared/StatGrid';
import { HealthRing } from '@/components/shared/HealthRing';
import { Badge } from '@/components/ui/badge';
import { fmtNumber, fmtPct } from '@/lib/format';

interface CoreSignalData {
  total_signals?: number;
  active_signals?: number;
  avg_score?: number;
  win_rate?: number;
  avg_ev?: number;
  signal_health?: number;
  sources_online?: number;
  sources_total?: number;
  last_signal_age_min?: number;
  [key: string]: unknown;
}

export function CoreSignals() {
  const { data, isLoading } = useCoreSignals();
  const core = (data ?? {}) as CoreSignalData;

  if (isLoading) {
    return (
      <Card className="sm:col-span-3">
        <CardHeader>
          <CardTitle className="text-base">Core Signals</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Loading...</div>
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card className="sm:col-span-3">
        <CardHeader>
          <CardTitle className="text-base">Core Signals</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">No signal data</div>
        </CardContent>
      </Card>
    );
  }

  const health = core.signal_health ?? 0;
  const sourcesOnline = core.sources_online ?? 0;
  const sourcesTotal = core.sources_total ?? 0;
  const lastAge = core.last_signal_age_min ?? 0;
  const freshness = lastAge <= 5 ? 'Fresh' : lastAge <= 30 ? 'Stale' : 'Old';
  const freshnessVariant =
    lastAge <= 5 ? 'default' : lastAge <= 30 ? 'secondary' : 'destructive';

  return (
    <Card className="sm:col-span-3">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Core Signals</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={freshnessVariant as 'default' | 'secondary' | 'destructive'} className="text-xs">
              {freshness} ({fmtNumber(lastAge, 0)}m ago)
            </Badge>
            <span className="text-xs text-muted-foreground">
              {sourcesOnline}/{sourcesTotal} sources
            </span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-6">
          <HealthRing value={health} label="Signal Health" />
          <StatGrid columns={4} className="flex-1">
            <StatCard
              title="Total Signals"
              value={core.total_signals ?? 0}
              subtitle={`${core.active_signals ?? 0} active`}
            />
            <StatCard
              title="Avg Score"
              value={fmtNumber(core.avg_score, 1)}
            />
            <StatCard
              title="Win Rate"
              value={fmtPct(core.win_rate)}
            />
            <StatCard
              title="Avg EV"
              value={fmtNumber(core.avg_ev, 2)}
            />
          </StatGrid>
        </div>
      </CardContent>
    </Card>
  );
}
