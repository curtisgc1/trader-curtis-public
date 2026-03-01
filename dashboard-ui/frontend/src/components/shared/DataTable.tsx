import { cn } from '@/lib/utils';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { EmptyState } from './EmptyState';

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => React.ReactNode;
  className?: string;
  headerClassName?: string;
}

interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  limit?: number;
  emptyMessage?: string;
  className?: string;
  rowClassName?: (row: T) => string;
}

export function DataTable<T extends Record<string, unknown>>({
  data,
  columns,
  limit,
  emptyMessage = 'No data',
  className,
  rowClassName,
}: DataTableProps<T>) {
  const rows = limit ? data.slice(0, limit) : data;

  if (rows.length === 0) {
    return <EmptyState message={emptyMessage} />;
  }

  return (
    <div className={cn('overflow-x-auto', className)}>
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((col) => (
              <TableHead
                key={col.key}
                className={cn('text-xs text-muted-foreground', col.headerClassName)}
              >
                {col.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow key={i} className={rowClassName?.(row)}>
              {columns.map((col) => (
                <TableCell key={col.key} className={cn('text-sm', col.className)}>
                  {col.render
                    ? col.render(row)
                    : String(row[col.key] ?? '—')}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
