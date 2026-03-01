import { useQuery } from '@tanstack/react-query';
import { fetchApi } from '@/lib/api-client';
import { cn } from '@/lib/utils';

interface SystemHealth {
  overall: string;
}

export function StatusPill() {
  const { data } = useQuery({
    queryKey: ['system-health'],
    queryFn: () => fetchApi<SystemHealth>('/api/system-health', { overall: 'unknown' }),
    refetchInterval: 30_000,
  });

  const status = data?.overall ?? 'unknown';

  const colorMap: Record<string, string> = {
    good: 'bg-primary/20 text-primary',
    warn: 'bg-chart-3/20 text-chart-3',
    bad: 'bg-destructive/20 text-destructive',
    offline: 'bg-destructive/20 text-destructive',
  };

  const dotMap: Record<string, string> = {
    good: 'bg-primary',
    warn: 'bg-chart-3',
    bad: 'bg-destructive',
    offline: 'bg-destructive',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium capitalize',
        colorMap[status] ?? 'bg-muted text-muted-foreground',
      )}
    >
      <span
        className={cn(
          'h-1.5 w-1.5 rounded-full animate-pulse',
          dotMap[status] ?? 'bg-muted-foreground',
        )}
      />
      {status}
    </span>
  );
}
