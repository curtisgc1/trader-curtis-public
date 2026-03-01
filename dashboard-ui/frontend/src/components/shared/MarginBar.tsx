import { cn } from '@/lib/utils';

interface MarginBarProps {
  usedPct: number;
  label?: string;
  className?: string;
}

export function MarginBar({ usedPct, label, className }: MarginBarProps) {
  const clamped = Math.min(100, Math.max(0, usedPct));
  const color =
    clamped > 80 ? 'bg-destructive' : clamped > 60 ? 'bg-chart-3' : 'bg-primary';

  return (
    <div className={cn('space-y-1', className)}>
      {label && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{label}</span>
          <span className="font-mono">{clamped.toFixed(1)}%</span>
        </div>
      )}
      <div className="h-2 rounded-full bg-muted">
        <div
          className={cn('h-full rounded-full transition-all', color)}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
