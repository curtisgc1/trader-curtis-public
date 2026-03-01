import type { ReactNode } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Loader2 } from 'lucide-react';

interface ControlPanelProps {
  title: string;
  children: ReactNode;
  onSave?: () => void;
  isSaving?: boolean;
  actions?: Array<{
    label: string;
    onClick: () => void;
    variant?: 'default' | 'destructive' | 'outline' | 'secondary';
    loading?: boolean;
  }>;
  className?: string;
  span?: 1 | 2 | 3;
}

const spanClass = {
  1: '',
  2: 'sm:col-span-2',
  3: 'sm:col-span-3',
} as const;

export function ControlPanel({
  title,
  children,
  onSave,
  isSaving,
  actions = [],
  className,
  span = 1,
}: ControlPanelProps) {
  return (
    <Card className={cn(spanClass[span], className)}>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {children}
        {(onSave || actions.length > 0) && (
          <div className="flex flex-wrap gap-2 pt-2">
            {onSave && (
              <Button onClick={onSave} disabled={isSaving} size="sm">
                {isSaving && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
                Save
              </Button>
            )}
            {actions.map((action) => (
              <Button
                key={action.label}
                variant={action.variant ?? 'outline'}
                size="sm"
                onClick={action.onClick}
                disabled={action.loading}
              >
                {action.loading && (
                  <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                )}
                {action.label}
              </Button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface ControlRowProps {
  label: string;
  children: ReactNode;
  description?: string;
}

export function ControlRow({ label, children, description }: ControlRowProps) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="space-y-0.5">
        <span className="text-sm font-medium">{label}</span>
        {description && (
          <p className="text-xs text-muted-foreground">{description}</p>
        )}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}
