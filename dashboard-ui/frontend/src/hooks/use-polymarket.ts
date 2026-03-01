import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchApi, postApi } from '@/lib/api-client';

const INTERVAL = 30_000;

export function usePolymarketOverview() {
  return useQuery({
    queryKey: ['polymarket-overview'],
    queryFn: () => fetchApi('/api/polymarket-overview', null),
    refetchInterval: INTERVAL,
  });
}

export function usePolymarketMarkets() {
  return useQuery({
    queryKey: ['polymarket-markets'],
    queryFn: () => fetchApi('/api/polymarket-markets', []),
    refetchInterval: INTERVAL,
  });
}

export function usePolymarketCandidates() {
  return useQuery({
    queryKey: ['polymarket-candidates'],
    queryFn: () => fetchApi('/api/polymarket-candidates', []),
    refetchInterval: INTERVAL,
  });
}

export function useBrainSignals(limit = 100) {
  return useQuery({
    queryKey: ['brain-signals', limit],
    queryFn: () => fetchApi(`/api/brain-signals?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}

export function useBrainStatus() {
  return useQuery({
    queryKey: ['brain-status'],
    queryFn: () => fetchApi('/api/brain-status', null),
    refetchInterval: INTERVAL,
  });
}

export function useArbOverview() {
  return useQuery({
    queryKey: ['arb-overview'],
    queryFn: () => fetchApi('/api/arb-overview', null),
    refetchInterval: INTERVAL,
  });
}

export function useArbOpportunities(limit = 100) {
  return useQuery({
    queryKey: ['arb-opportunities', limit],
    queryFn: () => fetchApi(`/api/arb-opportunities?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}

export function useGrokScores(limit = 50) {
  return useQuery({
    queryKey: ['grok-scores', limit],
    queryFn: () => fetchApi(`/api/grok-scores?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}

export function useGrokAlpha(limit = 50) {
  return useQuery({
    queryKey: ['grok-alpha', limit],
    queryFn: () => fetchApi(`/api/grok-alpha?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}

export function usePolymarketOrders(limit = 120) {
  return useQuery({
    queryKey: ['polymarket-orders', limit],
    queryFn: () => fetchApi(`/api/polymarket-orders?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}

export function usePolymarketScorecard() {
  return useQuery({
    queryKey: ['polymarket-scorecard'],
    queryFn: () => fetchApi('/api/polymarket-scorecard', null),
    refetchInterval: INTERVAL,
  });
}

export function usePolymarketMmOverview() {
  return useQuery({
    queryKey: ['polymarket-mm-overview'],
    queryFn: () => fetchApi('/api/polymarket-mm-overview', null),
    refetchInterval: INTERVAL,
  });
}

export function usePolymarketMmSnapshots(readyOnly = false) {
  return useQuery({
    queryKey: ['polymarket-mm-snapshots', readyOnly],
    queryFn: () =>
      fetchApi(
        `/api/polymarket-mm-snapshots?ready_only=${readyOnly ? '1' : '0'}`,
        [],
      ),
    refetchInterval: INTERVAL,
  });
}

export function usePolymarketAlignedSetups(mode = 'all') {
  return useQuery({
    queryKey: ['polymarket-aligned-setups', mode],
    queryFn: () =>
      fetchApi(`/api/polymarket-aligned-setups?mode=${mode}`, []),
    refetchInterval: INTERVAL,
  });
}

export function useWeatherMarketProbs() {
  return useQuery({
    queryKey: ['weather-market-probs'],
    queryFn: () => fetchApi('/api/weather-market-probs', []),
    refetchInterval: INTERVAL,
  });
}

export function useTrackedPolyWallets() {
  return useQuery({
    queryKey: ['tracked-poly-wallets'],
    queryFn: () => fetchApi('/api/tracked-poly-wallets', []),
    refetchInterval: INTERVAL,
  });
}

export function usePolymarketWalletScores() {
  return useQuery({
    queryKey: ['polymarket-wallet-scores'],
    queryFn: () => fetchApi('/api/polymarket-wallet-scores', []),
    refetchInterval: INTERVAL,
  });
}

export function useFreshWhales(limit = 50) {
  return useQuery({
    queryKey: ['fresh-whales', limit],
    queryFn: () => fetchApi(`/api/fresh-whales?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}

export function usePolymarketApprove() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => postApi('/api/polymarket-approve', { ids }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['polymarket-candidates'] });
      queryClient.invalidateQueries({ queryKey: ['brain-signals'] });
    },
  });
}

export function useTrackedPolyWalletUpsert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (wallet: Record<string, unknown>) =>
      postApi('/api/tracked-poly-wallets', wallet),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tracked-poly-wallets'] });
    },
  });
}
