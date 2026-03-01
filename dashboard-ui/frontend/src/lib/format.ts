export function fmtUsd(value: number | null | undefined, decimals = 2): string {
  if (value == null || isNaN(value)) return '—';
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(1)}k`;
  return `$${value.toFixed(decimals)}`;
}

export function fmtPct(value: number | null | undefined, decimals = 1): string {
  if (value == null || isNaN(value)) return '—';
  return `${value.toFixed(decimals)}%`;
}

export function fmtTimestamp(ts: string | null | undefined): string {
  if (!ts) return '—';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function fmtNumber(value: number | null | undefined, decimals = 2): string {
  if (value == null || isNaN(value)) return '—';
  return value.toFixed(decimals);
}

export function pnlClass(value: number | null | undefined): string {
  if (value == null || isNaN(value)) return 'text-muted-foreground';
  if (value > 0) return 'text-primary';
  if (value < 0) return 'text-destructive';
  return 'text-muted-foreground';
}

export function statusClass(status: string | null | undefined): string {
  if (!status) return 'text-muted-foreground';
  const s = status.toLowerCase();
  if (s === 'good' || s === 'active' || s === 'filled' || s === 'open') return 'text-primary';
  if (s === 'warn' || s === 'pending' || s === 'partial') return 'text-chart-3';
  return 'text-destructive';
}
