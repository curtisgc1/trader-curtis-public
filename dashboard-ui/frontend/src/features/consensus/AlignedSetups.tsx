import { usePolymarketAlignedSetups } from '@/hooks/use-polymarket';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtNumber, fmtUsd } from '@/lib/format';

interface AlignedSetupRow {
  ticker: string;
  direction: string;
  candidate_score: number;
  alpha_score: number;
  confirmations: number;
  sources_total: number;
  consensus_ratio: number;
  class_tag: string;
  market_url: string;
  question: string;
  market_slug: string;
  alignment_confidence: number;
  crowding_penalty: number;
  liquidity: number;
  match_score: number;
  [key: string]: unknown;
}

interface AlignedSetupsProps {
  mode: string;
}

const columns: Column<AlignedSetupRow>[] = [
  {
    key: 'ticker',
    header: 'Play',
    render: (r) => (
      <span className="font-mono font-semibold">
        {r.ticker} {String(r.direction).toUpperCase()}
      </span>
    ),
  },
  {
    key: 'candidate_score',
    header: 'Signal',
    render: (r) => <span className="font-mono">{fmtNumber(r.candidate_score, 2)}</span>,
  },
  {
    key: 'alpha_score',
    header: 'Alpha',
    render: (r) => <span className="font-mono">{fmtNumber(r.alpha_score, 3)}</span>,
  },
  {
    key: 'confirmations',
    header: 'Consensus',
    render: (r) => (
      <span className="font-mono">
        {r.confirmations}/{r.sources_total} ({fmtNumber(r.consensus_ratio, 2)})
      </span>
    ),
  },
  { key: 'class_tag', header: 'Class' },
  {
    key: 'market_url',
    header: 'Polymarket Market',
    render: (r) => {
      const label = r.question || r.market_slug || 'open market';
      if (r.market_url) {
        return (
          <a
            href={r.market_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline text-xs"
          >
            {label}
          </a>
        );
      }
      return <span className="text-xs">{label}</span>;
    },
  },
  {
    key: 'alignment_confidence',
    header: 'Align Conf',
    render: (r) => <span className="font-mono">{fmtNumber(r.alignment_confidence, 3)}</span>,
  },
  {
    key: 'crowding_penalty',
    header: 'Crowding',
    render: (r) => <span className="font-mono">{fmtNumber(r.crowding_penalty, 3)}</span>,
  },
  {
    key: 'liquidity',
    header: 'Liquidity',
    render: (r) => <span className="font-mono">{fmtUsd(r.liquidity, 0)}</span>,
  },
  {
    key: 'match_score',
    header: 'Match',
    render: (r) => <span className="font-mono">{fmtNumber(r.match_score, 1)}</span>,
  },
];

export function AlignedSetups({ mode }: AlignedSetupsProps) {
  const { data, isLoading } = usePolymarketAlignedSetups(mode);
  const rows = (Array.isArray(data) ? data : []) as AlignedSetupRow[];

  return (
    <Card className="sm:col-span-3">
      <CardHeader>
        <CardTitle className="text-base">
          High-Signal &rarr; Polymarket Aligned Bets
          {rows.length > 0 && (
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              ({rows.length})
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : (
          <DataTable
            data={rows}
            columns={columns}
            limit={35}
            emptyMessage="No aligned setups"
          />
        )}
      </CardContent>
    </Card>
  );
}
