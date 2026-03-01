import { cn } from '@/lib/utils';
import type { ReactNode } from 'react';

interface StatGridProps {
  children: ReactNode;
  columns?: 2 | 3 | 4;
  className?: string;
}

const colClass = {
  2: 'grid-cols-1 sm:grid-cols-2',
  3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
  4: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4',
} as const;

export function StatGrid({ children, columns = 3, className }: StatGridProps) {
  return (
    <div className={cn('grid gap-4', colClass[columns], className)}>
      {children}
    </div>
  );
}
