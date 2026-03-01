import { cn } from '@/lib/utils';
import { Inbox } from 'lucide-react';

interface EmptyStateProps {
  message?: string;
  className?: string;
}

export function EmptyState({
  message = 'No data',
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 py-8 text-muted-foreground',
        className,
      )}
    >
      <Inbox className="h-8 w-8" />
      <p className="text-sm">{message}</p>
    </div>
  );
}
