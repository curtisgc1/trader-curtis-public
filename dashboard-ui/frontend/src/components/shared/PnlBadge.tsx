import { cn } from '@/lib/utils';
import { fmtUsd, fmtPct, pnlClass } from '@/lib/format';
import { Badge } from '@/components/ui/badge';

interface PnlBadgeProps {
  value: number | null | undefined;
  mode?: 'usd' | 'pct';
  className?: string;
}

export function PnlBadge({ value, mode = 'usd', className }: PnlBadgeProps) {
  const display = mode === 'pct' ? fmtPct(value) : fmtUsd(value);
  const prefix = value != null && value > 0 ? '+' : '';

  return (
    <Badge
      variant="outline"
      className={cn(
        'font-mono text-xs',
        pnlClass(value),
        className,
      )}
    >
      {prefix}{display}
    </Badge>
  );
}
