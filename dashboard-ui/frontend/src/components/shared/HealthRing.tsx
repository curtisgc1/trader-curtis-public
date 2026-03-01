import { cn } from '@/lib/utils';

interface HealthRingProps {
  value: number;
  max?: number;
  label: string;
  size?: number;
  className?: string;
}

export function HealthRing({
  value,
  max = 100,
  label,
  size = 80,
  className,
}: HealthRingProps) {
  const pct = Math.min(100, (value / max) * 100);
  const radius = (size - 8) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;

  const color =
    pct >= 70
      ? 'stroke-primary'
      : pct >= 40
        ? 'stroke-chart-3'
        : 'stroke-destructive';

  return (
    <div className={cn('flex flex-col items-center gap-1', className)}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={4}
          className="text-muted/50"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className={cn('transition-all duration-500', color)}
        />
      </svg>
      <span className="text-lg font-bold">{Math.round(pct)}%</span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}
