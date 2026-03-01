import { useTrustPanel } from '@/hooks/use-consensus';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface TrustPanel {
  state?: string;
  master_enabled?: boolean;
  consensus_enforce?: boolean;
  consensus_thresholds?: {
    min_confirmations?: number;
    min_ratio?: number;
    min_score?: number;
  };
  candidates_flagged?: number;
  candidates_total?: number;
  [key: string]: unknown;
}

function stateClass(state: string | undefined): string {
  if (state === 'good') return 'text-primary';
  if (state === 'warn') return 'text-chart-3';
  return 'text-destructive';
}

export function TrustState() {
  const { data, isLoading } = useTrustPanel();
  const panel = (data ?? {}) as TrustPanel;
  const th = panel.consensus_thresholds ?? {};

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Trust State</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">State</span>
              <span className={cn('text-sm font-semibold', stateClass(panel.state))}>
                {String(panel.state ?? 'unknown').toUpperCase()}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Master</span>
              <span className={cn('text-sm', panel.master_enabled ? 'text-primary' : 'text-muted-foreground')}>
                {panel.master_enabled ? 'ON' : 'OFF'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Consensus</span>
              <span className={cn('text-sm', panel.consensus_enforce ? 'text-primary' : 'text-muted-foreground')}>
                {panel.consensus_enforce ? 'ON' : 'OFF'}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Thresholds</span>
              <span className="text-sm font-mono">
                {th.min_confirmations ?? 0} / {th.min_ratio ?? 0} / {th.min_score ?? 0}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Flagged</span>
              <span className="text-sm font-mono">
                {panel.candidates_flagged ?? 0} / {panel.candidates_total ?? 0}
              </span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
