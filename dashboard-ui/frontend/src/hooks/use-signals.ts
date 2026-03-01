import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchApi, postApi } from '@/lib/api-client';

const INTERVAL = 30_000;

export function useCoreSignals(lookbackHours = 72) {
  return useQuery({
    queryKey: ['core-signals', lookbackHours],
    queryFn: () =>
      fetchApi(`/api/core-signals?lookback_hours=${lookbackHours}`, []),
    refetchInterval: INTERVAL,
  });
}

export function useSignalRoutes() {
  return useQuery({
    queryKey: ['signal-routes'],
    queryFn: () => fetchApi('/api/signal-routes', []),
    refetchInterval: INTERVAL,
  });
}

export function usePipelineSignals() {
  return useQuery({
    queryKey: ['pipeline-signals'],
    queryFn: () => fetchApi('/api/pipeline-signals', []),
    refetchInterval: INTERVAL,
  });
}

export function useSignalReadiness() {
  return useQuery({
    queryKey: ['signal-readiness'],
    queryFn: () => fetchApi('/api/signal-readiness', null),
    refetchInterval: INTERVAL,
  });
}

export function useKellySignals() {
  return useQuery({
    queryKey: ['kelly-signals'],
    queryFn: () => fetchApi('/api/kelly-signals', []),
    refetchInterval: INTERVAL,
  });
}

export function useCounterfactualWins(horizonHours = 24, limit = 200) {
  return useQuery({
    queryKey: ['counterfactual-wins', horizonHours, limit],
    queryFn: () =>
      fetchApi(
        `/api/counterfactual-wins?horizon_hours=${horizonHours}&limit=${limit}`,
        [],
      ),
    refetchInterval: INTERVAL,
  });
}

export function useRecentTradeDecisions(limit = 20) {
  return useQuery({
    queryKey: ['recent-trade-decisions', limit],
    queryFn: () =>
      fetchApi(`/api/recent-trade-decisions?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}

export function useTradeExplain(identifier: string) {
  return useQuery({
    queryKey: ['trade-explain', identifier],
    queryFn: () =>
      fetchApi(`/api/trade-explain?identifier=${encodeURIComponent(identifier)}`, null),
    enabled: identifier.length > 0,
  });
}

export function useQuantValidations() {
  return useQuery({
    queryKey: ['quant-validations'],
    queryFn: () => fetchApi('/api/quant-validations', []),
    refetchInterval: INTERVAL,
  });
}

export function useChartLiquidity() {
  return useQuery({
    queryKey: ['chart-liquidity'],
    queryFn: () => fetchApi('/api/chart-liquidity', []),
    refetchInterval: INTERVAL,
  });
}

export function useBookmarkAlphaIdeas() {
  return useQuery({
    queryKey: ['bookmark-alpha-ideas'],
    queryFn: () => fetchApi('/api/bookmark-alpha-ideas', []),
    refetchInterval: INTERVAL,
  });
}

export function useBreakthroughEvents() {
  return useQuery({
    queryKey: ['breakthrough-events'],
    queryFn: () => fetchApi('/api/breakthrough-events', []),
    refetchInterval: INTERVAL,
  });
}

export function useAllocatorDecisions() {
  return useQuery({
    queryKey: ['allocator-decisions'],
    queryFn: () => fetchApi('/api/allocator-decisions', []),
    refetchInterval: INTERVAL,
  });
}

export function useSourceScores() {
  return useQuery({
    queryKey: ['source-scores'],
    queryFn: () => fetchApi('/api/source-scores', []),
    refetchInterval: INTERVAL,
  });
}

export function useBookmarkTheses() {
  return useQuery({
    queryKey: ['bookmark-theses'],
    queryFn: () => fetchApi('/api/bookmark-theses', []),
    refetchInterval: INTERVAL,
  });
}

export function useEventAlerts() {
  return useQuery({
    queryKey: ['event-alerts'],
    queryFn: () => fetchApi('/api/event-alerts', []),
    refetchInterval: INTERVAL,
  });
}

export function useExecutionOrders(limit = 120) {
  return useQuery({
    queryKey: ['execution-orders', limit],
    queryFn: () => fetchApi(`/api/execution-orders?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}

export function useSignalScorecard(lookbackDays?: number, minSamples?: number) {
  const params = new URLSearchParams();
  if (lookbackDays != null) params.set('lookback_days', String(lookbackDays));
  if (minSamples != null) params.set('min_samples', String(minSamples));
  const qs = params.toString();
  return useQuery({
    queryKey: ['signal-scorecard', lookbackDays, minSamples],
    queryFn: () => fetchApi(`/api/signal-scorecard${qs ? `?${qs}` : ''}`, null),
    refetchInterval: INTERVAL,
  });
}

export function useVenueMatrix() {
  return useQuery({
    queryKey: ['venue-matrix'],
    queryFn: () => fetchApi('/api/venue-matrix', []),
    refetchInterval: INTERVAL,
  });
}

export function useVenueReadiness() {
  return useQuery({
    queryKey: ['venue-readiness'],
    queryFn: () => fetchApi('/api/venue-readiness', null),
    refetchInterval: INTERVAL,
  });
}

export function useMissedOpportunities(lookbackDays = 7) {
  return useQuery({
    queryKey: ['missed-opportunities', lookbackDays],
    queryFn: () =>
      fetchApi(`/api/missed-opportunities?lookback_days=${lookbackDays}`, []),
    refetchInterval: INTERVAL,
  });
}

export function useIdLookup(id: string) {
  return useQuery({
    queryKey: ['id-lookup', id],
    queryFn: () =>
      fetchApi(`/api/id-lookup?id=${encodeURIComponent(id)}`, null),
    enabled: id.length > 0,
  });
}

export function useTradeFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      postApi('/api/trade-feedback', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recent-trade-decisions'] });
    },
  });
}

export function useCounterfactualFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      route_id: number;
      horizon_hours: number;
      feedback: string;
      notes: string;
    }) => postApi('/api/counterfactual-feedback', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['counterfactual-wins'] });
    },
  });
}

export function useSourceDecay(windowDays = 14, minLifetimeTrades = 10) {
  return useQuery({
    queryKey: ['source-decay', windowDays, minLifetimeTrades],
    queryFn: () =>
      fetchApi(
        `/api/source-decay?window_days=${windowDays}&min_lifetime_trades=${minLifetimeTrades}`,
        [],
      ),
    refetchInterval: INTERVAL,
  });
}

export function useWeightHistory(limit = 50) {
  return useQuery({
    queryKey: ['weight-history', limit],
    queryFn: () => fetchApi(`/api/weight-history?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}
