import { usePerformanceCurve } from '@/hooks/use-overview';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState } from '@/components/shared/EmptyState';
import { fmtUsd, pnlClass } from '@/lib/format';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface CurvePoint {
  date?: string;
  value?: number;
  pnl?: number;
  cumulative_pnl?: number;
  [key: string]: unknown;
}

interface CurveData {
  points?: CurvePoint[];
  total_return?: number;
  [key: string]: unknown;
}

export function PerformanceCurve() {
  const { data, isLoading } = usePerformanceCurve(30);
  const curve = (data ?? {}) as CurveData;
  const points = curve.points ?? (Array.isArray(data) ? data as CurvePoint[] : []);

  if (isLoading) {
    return (
      <Card className="sm:col-span-2">
        <CardHeader>
          <CardTitle className="text-base">Performance (30d)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Loading...</div>
        </CardContent>
      </Card>
    );
  }

  if (points.length === 0) {
    return (
      <Card className="sm:col-span-2">
        <CardHeader>
          <CardTitle className="text-base">Performance (30d)</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState message="No performance data" />
        </CardContent>
      </Card>
    );
  }

  const values = points.map((p) => Number(p.cumulative_pnl ?? p.value ?? p.pnl ?? 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const barWidth = Math.max(2, Math.floor(100 / points.length));
  const lastValue = values[values.length - 1] ?? 0;

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Performance (30d)</CardTitle>
          <span className={cn('text-sm font-mono font-bold', pnlClass(lastValue))}>
            {lastValue >= 0 ? '+' : ''}{fmtUsd(lastValue)}
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <TooltipProvider>
          <div className="flex items-end gap-px" style={{ height: 120 }}>
            {points.map((point, i) => {
              const val = values[i];
              const normalized = ((val - min) / range) * 100;
              const height = Math.max(2, normalized);
              const isPositive = val >= 0;

              return (
                <Tooltip key={point.date ?? i}>
                  <TooltipTrigger asChild>
                    <div
                      className={cn(
                        'rounded-t-sm transition-all',
                        isPositive ? 'bg-primary/70 hover:bg-primary' : 'bg-destructive/70 hover:bg-destructive',
                      )}
                      style={{
                        height: `${height}%`,
                        width: `${barWidth}%`,
                        minWidth: 2,
                      }}
                    />
                  </TooltipTrigger>
                  <TooltipContent>
                    <div className="text-xs">
                      <div>{point.date ?? `Day ${i + 1}`}</div>
                      <div className={cn('font-mono', pnlClass(val))}>
                        {fmtUsd(val)}
                      </div>
                    </div>
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </div>
        </TooltipProvider>
        <div className="mt-2 flex justify-between text-xs text-muted-foreground">
          <span>{points[0]?.date ?? ''}</span>
          <span>{points[points.length - 1]?.date ?? ''}</span>
        </div>
      </CardContent>
    </Card>
  );
}
