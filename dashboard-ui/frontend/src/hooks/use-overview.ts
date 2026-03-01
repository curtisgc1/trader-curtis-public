import { useQuery } from '@tanstack/react-query';
import { fetchApi } from '@/lib/api-client';

const INTERVAL = 30_000;

export function useHealthPulse() {
  return useQuery({
    queryKey: ['health-pulse'],
    queryFn: () => fetchApi('/api/health-pulse', null),
    refetchInterval: INTERVAL,
  });
}

export function useExchangePnl() {
  return useQuery({
    queryKey: ['exchange-pnl'],
    queryFn: () => fetchApi('/api/exchange-pnl', null),
    refetchInterval: INTERVAL,
  });
}

export function useSignalScorecard() {
  return useQuery({
    queryKey: ['signal-scorecard'],
    queryFn: () => fetchApi('/api/signal-scorecard', null),
    refetchInterval: INTERVAL,
  });
}

export function usePipelineSignals(limit = 10) {
  return useQuery({
    queryKey: ['pipeline-signals', limit],
    queryFn: () => fetchApi(`/api/pipeline-signals?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}

export function useMasterOverview() {
  return useQuery({
    queryKey: ['master-overview'],
    queryFn: () => fetchApi('/api/master-overview', null),
    refetchInterval: INTERVAL,
  });
}

export function usePortfolioSnapshot() {
  return useQuery({
    queryKey: ['portfolio-snapshot'],
    queryFn: () => fetchApi('/api/portfolio-snapshot', null),
    refetchInterval: INTERVAL,
  });
}

export function useRiskControls() {
  return useQuery({
    queryKey: ['risk-controls'],
    queryFn: () => fetchApi('/api/risk-controls', null),
    refetchInterval: INTERVAL,
  });
}

export function usePerformanceCurve(days = 30) {
  return useQuery({
    queryKey: ['performance-curve', days],
    queryFn: () => fetchApi(`/api/performance-curve?days=${days}`, null),
    refetchInterval: INTERVAL,
  });
}

export function useSystemIntelligence() {
  return useQuery({
    queryKey: ['system-intelligence'],
    queryFn: () => fetchApi('/api/system-intelligence', null),
    refetchInterval: INTERVAL,
  });
}

export function useSourceScores(limit = 20) {
  return useQuery({
    queryKey: ['source-scores', limit],
    queryFn: () => fetchApi(`/api/source-scores?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}

export function useIdLookup(query: string) {
  return useQuery({
    queryKey: ['id-lookup', query],
    queryFn: () => fetchApi(`/api/id-lookup?q=${encodeURIComponent(query)}`, null),
    enabled: query.length > 0,
  });
}

export function useMarketRegime() {
  return useQuery({
    queryKey: ['market-regime'],
    queryFn: () => fetchApi('/api/market-regime', null),
    refetchInterval: INTERVAL,
  });
}
