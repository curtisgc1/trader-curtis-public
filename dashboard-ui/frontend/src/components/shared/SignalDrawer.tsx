import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ReactNode } from 'react';

interface SignalDrawerProps {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  badge?: ReactNode;
  span?: 1 | 2 | 3;
  className?: string;
}

const spanClass = {
  1: '',
  2: 'sm:col-span-2',
  3: 'sm:col-span-3',
} as const;

export function SignalDrawer({
  title,
  children,
  defaultOpen = false,
  badge,
  span = 2,
  className,
}: SignalDrawerProps) {
  return (
    <Collapsible defaultOpen={defaultOpen} className={cn(spanClass[span], className)}>
      <Card>
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer select-none hover:bg-accent/50 transition-colors">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">{title}</CardTitle>
                {badge}
              </div>
              <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform duration-200 [[data-state=open]>&]:rotate-180" />
            </div>
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent>{children}</CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
