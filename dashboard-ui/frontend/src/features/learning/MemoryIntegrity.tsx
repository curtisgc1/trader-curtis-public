import { useMemoryIntegrity } from '@/hooks/use-learning';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

export function MemoryIntegrity() {
  const { data, isLoading } = useMemoryIntegrity();

  if (isLoading) {
    return (
      <Card className="sm:col-span-2">
        <CardHeader>
          <CardTitle className="text-base">Memory Integrity (30d)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground">Loading...</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">Memory Integrity (30d)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-xs">Approved</TableHead>
              <TableHead className="text-xs">Linked</TableHead>
              <TableHead className="text-xs">Resolved</TableHead>
              <TableHead className="text-xs">State</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell className="text-sm">{data?.approved_routes ?? 0}</TableCell>
              <TableCell className="text-sm">{data?.linked_routes ?? 0}</TableCell>
              <TableCell className="text-sm">{data?.resolved_routes ?? 0}</TableCell>
              <TableCell className="text-sm">{data?.consistency_state ?? 'unknown'}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-xs">Coverage</TableHead>
              <TableHead className="text-xs">Tracked</TableHead>
              <TableHead className="text-xs">Realized</TableHead>
              <TableHead className="text-xs">Orphans</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell className="text-sm">{data?.coverage_pct ?? 0}%</TableCell>
              <TableCell className="text-sm">{data?.tracked_pct ?? 0}%</TableCell>
              <TableCell className="text-sm">{data?.realized_routes ?? 0}</TableCell>
              <TableCell className="text-sm">{data?.orphan_outcomes ?? 0}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
