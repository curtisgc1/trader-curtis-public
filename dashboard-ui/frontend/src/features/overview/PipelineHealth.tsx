import { usePipelineSignals } from '@/hooks/use-overview';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/shared/EmptyState';
import { fmtTimestamp } from '@/lib/format';

interface PipelineSignal {
  id?: string | number;
  symbol?: string;
  source?: string;
  status?: string;
  direction?: string;
  timestamp?: string;
  [key: string]: unknown;
}

function statusVariant(status: string | undefined) {
  if (!status) return 'secondary' as const;
  const s = status.toLowerCase();
  if (s === 'active' || s === 'filled' || s === 'executed') return 'default' as const;
  if (s === 'pending' || s === 'queued') return 'outline' as const;
  return 'destructive' as const;
}

export function PipelineHealth() {
  const { data, isLoading } = usePipelineSignals(10);
  const signals = (Array.isArray(data) ? data : []) as PipelineSignal[];

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Pipeline Health</CardTitle>
          <span className="text-xs text-muted-foreground">
            {signals.length} recent signal{signals.length !== 1 ? 's' : ''}
          </span>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : signals.length === 0 ? (
          <EmptyState message="No pipeline signals" />
        ) : (
          <div className="space-y-2">
            {signals.map((sig, i) => (
              <div
                key={sig.id ?? i}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-mono font-medium">
                    {sig.symbol ?? '—'}
                  </span>
                  {sig.direction && (
                    <span className="text-xs text-muted-foreground">
                      {sig.direction.toUpperCase()}
                    </span>
                  )}
                  {sig.source && (
                    <span className="text-xs text-muted-foreground">
                      via {sig.source}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    {fmtTimestamp(sig.timestamp)}
                  </span>
                  <Badge variant={statusVariant(sig.status)} className="text-xs">
                    {(sig.status ?? 'unknown').toUpperCase()}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
