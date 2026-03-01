import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchApi } from '@/lib/api-client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

interface SimRun {
  id: number;
  run_at: string;
  layer: string;
  contract: string;
  ticker: string;
  brier: number | null;
  edge_pct: number | null;
  n_paths: number | null;
  elapsed_ms: number | null;
}

interface SimResult {
  contract: string;
  ensemble_prob: number;
  market_price: number;
  edge_pct: number;
  brier: number;
  var_95: number;
  es_95: number;
  effective_n: number;
  elapsed_ms: number;
  error?: string;
}

function useSimulationHistory(limit = 20) {
  return useQuery<SimRun[]>({
    queryKey: ['simulation-history', limit],
    queryFn: () => fetchApi(`/api/simulation/history?limit=${limit}`, []),
    refetchInterval: 30_000,
  });
}

function edgeColor(edge: number | null): string {
  if (edge == null) return '';
  if (edge > 5) return 'text-green-400';
  if (edge > 0) return 'text-green-300';
  if (edge > -5) return 'text-orange-400';
  return 'text-red-400';
}

function brierBadge(brier: number | null) {
  if (brier == null) return null;
  const variant = brier < 0.15 ? 'default' : brier < 0.25 ? 'secondary' : 'destructive';
  return <Badge variant={variant}>{brier.toFixed(4)}</Badge>;
}

export function SimulationPanel() {
  const { data: history, isLoading } = useSimulationHistory();
  const queryClient = useQueryClient();

  const [contract, setContract] = useState('');
  const [prob, setProb] = useState('0.50');
  const [marketPrice, setMarketPrice] = useState('0.50');

  const runMutation = useMutation<SimResult, Error, void>({
    mutationFn: async () => {
      const params = new URLSearchParams({
        contract,
        prob,
        market_price: marketPrice,
      });
      const res = await fetch(`/api/simulation/run?${params}`);
      if (!res.ok) throw new Error(`Simulation failed: ${res.status}`);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['simulation-history'] });
    },
  });

  const result = runMutation.data;

  return (
    <div className="space-y-4">
      {/* Run Simulation Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Simulation Engine</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <div>
              <Label className="text-xs">Contract</Label>
              <Input
                value={contract}
                onChange={(e) => setContract(e.target.value)}
                placeholder="BTC_100K_2026"
                className="h-8 text-sm"
              />
            </div>
            <div>
              <Label className="text-xs">Prob Estimate</Label>
              <Input
                value={prob}
                onChange={(e) => setProb(e.target.value)}
                type="number"
                step="0.01"
                min="0.01"
                max="0.99"
                className="h-8 text-sm font-mono"
              />
            </div>
            <div>
              <Label className="text-xs">Market Price</Label>
              <Input
                value={marketPrice}
                onChange={(e) => setMarketPrice(e.target.value)}
                type="number"
                step="0.01"
                min="0.01"
                max="0.99"
                className="h-8 text-sm font-mono"
              />
            </div>
          </div>
          <Button
            onClick={() => runMutation.mutate()}
            disabled={!contract || runMutation.isPending}
            size="sm"
            className="w-full"
          >
            {runMutation.isPending ? 'Running...' : 'Run Ensemble Simulation'}
          </Button>

          {runMutation.isError && (
            <div className="text-xs text-red-400">{runMutation.error.message}</div>
          )}

          {result && !result.error && (
            <div className="grid grid-cols-4 gap-2 pt-2 border-t">
              <StatCell label="Ensemble P" value={result.ensemble_prob.toFixed(4)} />
              <StatCell
                label="Edge"
                value={`${result.edge_pct > 0 ? '+' : ''}${result.edge_pct.toFixed(2)}%`}
                className={edgeColor(result.edge_pct)}
              />
              <StatCell label="Brier" value={result.brier.toFixed(4)} />
              <StatCell label="VaR(95)" value={result.var_95.toFixed(4)} />
              <StatCell label="ES(95)" value={result.es_95.toFixed(4)} />
              <StatCell label="Eff. N" value={String(result.effective_n)} />
              <StatCell label="Time" value={`${result.elapsed_ms.toFixed(0)}ms`} />
            </div>
          )}
        </CardContent>
      </Card>

      {/* History Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Simulation Runs</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="text-sm text-muted-foreground">Loading...</div>
          ) : !history?.length ? (
            <div className="text-sm text-muted-foreground">No simulation runs yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="text-left py-1 pr-2">Time</th>
                    <th className="text-left py-1 pr-2">Layer</th>
                    <th className="text-left py-1 pr-2">Contract</th>
                    <th className="text-right py-1 pr-2">Edge</th>
                    <th className="text-right py-1 pr-2">Brier</th>
                    <th className="text-right py-1 pr-2">Paths</th>
                    <th className="text-right py-1">ms</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((run) => (
                    <tr key={run.id} className="border-b border-muted/30">
                      <td className="py-1 pr-2 font-mono text-muted-foreground">
                        {run.run_at?.slice(11, 19) ?? '-'}
                      </td>
                      <td className="py-1 pr-2">
                        <Badge variant="outline" className="text-[10px]">{run.layer}</Badge>
                      </td>
                      <td className="py-1 pr-2 font-mono">{run.contract || run.ticker || '-'}</td>
                      <td className={cn('py-1 pr-2 text-right font-mono', edgeColor(run.edge_pct))}>
                        {run.edge_pct != null ? `${run.edge_pct > 0 ? '+' : ''}${run.edge_pct.toFixed(2)}%` : '-'}
                      </td>
                      <td className="py-1 pr-2 text-right">{brierBadge(run.brier)}</td>
                      <td className="py-1 pr-2 text-right font-mono">
                        {run.n_paths?.toLocaleString() ?? '-'}
                      </td>
                      <td className="py-1 text-right font-mono text-muted-foreground">
                        {run.elapsed_ms != null ? `${run.elapsed_ms.toFixed(0)}` : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCell({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="text-center">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className={cn('text-sm font-mono font-medium', className)}>{value}</div>
    </div>
  );
}
