import { useLearningHealth } from '@/hooks/use-learning';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtPct } from '@/lib/format';

interface HealthRow {
  coverage: string;
  tracked: string;
  resolved: string;
  realized: string;
  [key: string]: unknown;
}

const columns: Column<HealthRow>[] = [
  { key: 'coverage', header: 'Resolved %' },
  { key: 'tracked', header: 'Tracked %' },
  { key: 'resolved', header: 'Resolved' },
  { key: 'realized', header: 'Realized' },
];

export function LearningHealth() {
  const { data, isLoading } = useLearningHealth();

  const rows: HealthRow[] = data
    ? [
        {
          coverage: fmtPct(data.coverage_pct),
          tracked: fmtPct(data.tracked_coverage_pct),
          resolved: `${data.resolved_routes ?? 0}/${data.eligible_routes ?? 0}`,
          realized: String(data.realized_routes ?? 0),
        },
      ]
    : [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Learning Health (7d)</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable data={rows} columns={columns} emptyMessage="No health data" />
        )}
      </CardContent>
    </Card>
  );
}
