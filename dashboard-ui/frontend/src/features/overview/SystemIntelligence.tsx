import { useSystemIntelligence } from '@/hooks/use-overview';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/shared/EmptyState';
import { fmtTimestamp } from '@/lib/format';

interface Insight {
  type?: string;
  title?: string;
  message?: string;
  severity?: string;
  timestamp?: string;
  [key: string]: unknown;
}

interface IntelligenceData {
  insights?: Insight[];
  [key: string]: unknown;
}

function severityVariant(severity: string | undefined) {
  if (!severity) return 'secondary' as const;
  const s = severity.toLowerCase();
  if (s === 'info' || s === 'low') return 'secondary' as const;
  if (s === 'warn' || s === 'medium') return 'outline' as const;
  if (s === 'critical' || s === 'high') return 'destructive' as const;
  return 'secondary' as const;
}

function InsightCard({ insight }: { insight: Insight }) {
  return (
    <div className="rounded-lg border border-border p-3 space-y-1.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {insight.type && (
            <Badge variant="outline" className="text-xs">
              {insight.type}
            </Badge>
          )}
          {insight.severity && (
            <Badge variant={severityVariant(insight.severity)} className="text-xs">
              {insight.severity}
            </Badge>
          )}
        </div>
        {insight.timestamp && (
          <span className="text-xs text-muted-foreground">
            {fmtTimestamp(insight.timestamp)}
          </span>
        )}
      </div>
      {insight.title && (
        <div className="text-sm font-medium">{insight.title}</div>
      )}
      {insight.message && (
        <div className="text-xs text-muted-foreground leading-relaxed">
          {insight.message}
        </div>
      )}
    </div>
  );
}

export function SystemIntelligence() {
  const { data, isLoading } = useSystemIntelligence();
  const intel = (data ?? {}) as IntelligenceData;
  const insights = intel.insights ?? (Array.isArray(data) ? data as Insight[] : []);

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">System Intelligence</CardTitle>
          {insights.length > 0 && (
            <span className="text-xs text-muted-foreground">
              {insights.length} insight{insights.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : insights.length === 0 ? (
          <EmptyState message="No insights available" />
        ) : (
          <div className="space-y-3">
            {insights.slice(0, 6).map((insight, i) => (
              <InsightCard key={insight.title ?? i} insight={insight} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
