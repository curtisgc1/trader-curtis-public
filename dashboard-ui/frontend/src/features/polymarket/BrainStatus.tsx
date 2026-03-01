import { useBrainStatus } from '@/hooks/use-polymarket';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { fmtTimestamp } from '@/lib/format';

interface BrainStatusData {
  brain_alive?: boolean;
  heartbeat_age_sec?: number;
  signals_seen?: number;
  trades_executed?: number;
  last_signal_at?: string;
  controls?: Record<string, string>;
  [key: string]: unknown;
}

function StatusRow({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: React.ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn('text-sm font-medium', valueClass)}>{value}</span>
    </div>
  );
}

export function BrainStatus() {
  const { data, isLoading } = useBrainStatus();
  const brain = (data ?? {}) as BrainStatusData;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Trader Brain Status</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : !data || brain.signals_seen === undefined ? (
          <div className="text-sm text-muted-foreground">No brain data</div>
        ) : (
          <div className="space-y-1">
            <StatusRow
              label="Process"
              value={
                <span>
                  <span className={brain.brain_alive ? 'text-primary' : 'text-destructive'}>
                    {brain.brain_alive ? 'LIVE' : 'DEAD'}
                  </span>
                  {' '}
                  <span className="text-xs text-muted-foreground">
                    ({brain.heartbeat_age_sec !== undefined && brain.heartbeat_age_sec >= 0
                      ? `${brain.heartbeat_age_sec}s ago`
                      : 'no heartbeat'})
                  </span>
                </span>
              }
            />
            <StatusRow
              label="Brain"
              value={brain.controls?.tb_enabled === '1' ? 'ON' : 'OFF'}
              valueClass={brain.controls?.tb_enabled === '1' ? 'text-primary' : 'text-destructive'}
            />
            <StatusRow label="Signals Seen" value={brain.signals_seen ?? 0} />
            <StatusRow label="Trades Executed" value={brain.trades_executed ?? 0} />
            <StatusRow
              label="Last Signal"
              value={brain.last_signal_at ? fmtTimestamp(brain.last_signal_at) : 'none'}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
