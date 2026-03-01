import { useState } from 'react';
import { useIdLookup } from '@/hooks/use-overview';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

interface LookupResult {
  found?: boolean;
  type?: string;
  symbol?: string;
  venue?: string;
  status?: string;
  details?: Record<string, unknown>;
  [key: string]: unknown;
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-mono">{value}</span>
    </div>
  );
}

export function IdLookup() {
  const [query, setQuery] = useState('');
  const [committed, setCommitted] = useState('');
  const { data, isLoading } = useIdLookup(committed);
  const result = (data ?? {}) as LookupResult;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (trimmed.length > 0) {
      setCommitted(trimmed);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">ID Lookup</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form onSubmit={handleSubmit}>
          <Input
            placeholder="Route ID, trade ID, or symbol..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </form>
        {isLoading && committed && (
          <div className="text-sm text-muted-foreground">Searching...</div>
        )}
        {committed && !isLoading && result.found && (
          <div className="space-y-1">
            {result.type && <DetailRow label="Type" value={result.type} />}
            {result.symbol && <DetailRow label="Symbol" value={result.symbol} />}
            {result.venue && <DetailRow label="Venue" value={result.venue} />}
            {result.status && (
              <DetailRow
                label="Status"
                value={
                  <span className={cn(
                    result.status === 'open' ? 'text-primary' : 'text-muted-foreground',
                  )}>
                    {result.status}
                  </span>
                }
              />
            )}
            {result.details && Object.entries(result.details).map(([k, v]) => (
              <DetailRow key={k} label={k} value={String(v ?? '—')} />
            ))}
          </div>
        )}
        {committed && !isLoading && !result.found && (
          <div className="text-sm text-muted-foreground">No results found</div>
        )}
      </CardContent>
    </Card>
  );
}
