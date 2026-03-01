import { useMasterOverview } from '@/hooks/use-overview';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

interface MasterData {
  master_enabled?: boolean;
  mode?: string;
  auto_execute?: boolean;
  consensus_enforce?: boolean;
  risk_mode?: string;
  max_positions?: number;
  current_positions?: number;
  active_venues?: string[];
  paused_venues?: string[];
  [key: string]: unknown;
}

function ControlRow({ label, value, active }: {
  label: string;
  value: string;
  active?: boolean;
}) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn(
        'text-sm font-medium',
        active === true ? 'text-primary' : active === false ? 'text-destructive' : '',
      )}>
        {value}
      </span>
    </div>
  );
}

export function MasterControls() {
  const { data, isLoading } = useMasterOverview();
  const master = (data ?? {}) as MasterData;

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Master Controls</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Loading...</div>
        </CardContent>
      </Card>
    );
  }

  const enabled = master.master_enabled ?? false;
  const mode = (master.mode ?? 'paper').toUpperCase();
  const activeVenues = master.active_venues ?? [];
  const pausedVenues = master.paused_venues ?? [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Master Controls</CardTitle>
          <Badge
            variant={enabled ? 'default' : 'destructive'}
            className="text-xs"
          >
            {enabled ? 'ENABLED' : 'DISABLED'}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <ControlRow label="Mode" value={mode} />
          <ControlRow
            label="Auto Execute"
            value={master.auto_execute ? 'ON' : 'OFF'}
            active={master.auto_execute}
          />
          <ControlRow
            label="Consensus"
            value={master.consensus_enforce ? 'ON' : 'OFF'}
            active={master.consensus_enforce}
          />
          <ControlRow
            label="Risk Mode"
            value={(master.risk_mode ?? 'normal').toUpperCase()}
          />
          <ControlRow
            label="Positions"
            value={`${master.current_positions ?? 0} / ${master.max_positions ?? 0}`}
          />
        </div>

        {(activeVenues.length > 0 || pausedVenues.length > 0) && (
          <>
            <Separator />
            <div className="space-y-2">
              <span className="text-xs font-medium text-muted-foreground">Venues</span>
              <div className="flex flex-wrap gap-1.5">
                {activeVenues.map((v) => (
                  <Badge key={v} variant="default" className="text-xs">
                    {v}
                  </Badge>
                ))}
                {pausedVenues.map((v) => (
                  <Badge key={v} variant="secondary" className="text-xs line-through">
                    {v}
                  </Badge>
                ))}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
