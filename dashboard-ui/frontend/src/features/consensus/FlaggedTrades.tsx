import { useConsensusCandidates } from '@/hooks/use-consensus';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type Column } from '@/components/shared/DataTable';
import { fmtNumber } from '@/lib/format';

interface EvidenceRating {
  source?: string;
  win_rate?: number;
  sample_size?: number;
}

interface PolyMatch {
  question?: string;
  liquidity?: number;
  match_score?: number;
  market_url?: string;
}

interface CandidateRow {
  ticker: string;
  direction: string;
  score: number;
  confirmations: number;
  sources_total: number;
  consensus_ratio: number;
  source_tag: string;
  evidence_ratings: EvidenceRating[];
  polymarket_matches: PolyMatch[];
  [key: string]: unknown;
}

function formatEvidence(r: CandidateRow): string {
  const list = Array.isArray(r.evidence_ratings) ? r.evidence_ratings : [];
  if (list.length === 0) return '—';
  return list
    .slice(0, 6)
    .map((x) => {
      const src = x.source ?? '';
      const wr = Number(x.win_rate ?? 0).toFixed(1);
      const n = Number(x.sample_size ?? 0);
      return `${src} (${wr}% / n=${n})`;
    })
    .join(', ');
}

function formatPolymarket(r: CandidateRow): React.ReactNode {
  const list = Array.isArray(r.polymarket_matches) ? r.polymarket_matches : [];
  if (list.length === 0) return <span className="text-muted-foreground">No match</span>;
  return (
    <span>
      {list.slice(0, 2).map((m, i) => {
        const q = m.question ?? 'market';
        const liq = Number(m.liquidity ?? 0).toFixed(0);
        const s = Number(m.match_score ?? 0).toFixed(0);
        const url = m.market_url ?? '';
        return (
          <span key={i} className="block text-xs">
            {url ? (
              <a href={url} target="_blank" rel="noopener noreferrer" className="text-primary underline">
                {q}
              </a>
            ) : (
              q
            )}
            {` (score ${s}, liq $${liq})`}
          </span>
        );
      })}
    </span>
  );
}

const columns: Column<CandidateRow>[] = [
  { key: 'ticker', header: 'Ticker', className: 'font-mono font-semibold' },
  { key: 'direction', header: 'Dir', render: (r) => <span className="uppercase">{r.direction}</span> },
  {
    key: 'score',
    header: 'Score',
    render: (r) => <span className="font-mono">{fmtNumber(r.score, 1)}</span>,
  },
  {
    key: 'confirmations',
    header: 'N/M',
    render: (r) => (
      <span className="font-mono">
        {r.confirmations}/{r.sources_total}
      </span>
    ),
  },
  {
    key: 'consensus_ratio',
    header: 'Ratio',
    render: (r) => <span className="font-mono">{fmtNumber(r.consensus_ratio, 2)}</span>,
  },
  { key: 'source_tag', header: 'Primary' },
  {
    key: 'evidence_ratings',
    header: 'Why Flagged',
    render: (r) => <span className="text-xs text-muted-foreground">{formatEvidence(r)}</span>,
  },
  {
    key: 'polymarket_matches',
    header: 'Polymarket Match',
    render: formatPolymarket,
  },
];

export function FlaggedTrades() {
  const { data, isLoading } = useConsensusCandidates(true);
  const rows = (Array.isArray(data) ? data : []) as CandidateRow[];

  return (
    <Card className="sm:col-span-2">
      <CardHeader>
        <CardTitle className="text-base">
          Flagged Consensus Trades
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
            limit={40}
            emptyMessage="No flagged consensus trades"
          />
        )}
      </CardContent>
    </Card>
  );
}
