import { useQuery } from '@tanstack/react-query';
import { fetchApi } from '@/lib/api-client';

const INTERVAL = 30_000;

export function usePortfolioSnapshot() {
  return useQuery({
    queryKey: ['portfolio-snapshot'],
    queryFn: () => fetchApi('/api/portfolio-snapshot', null),
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

export function useSummary() {
  return useQuery({
    queryKey: ['summary'],
    queryFn: () => fetchApi('/api/summary', null),
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

export function useSystemHealth() {
  return useQuery({
    queryKey: ['system-health'],
    queryFn: () => fetchApi('/api/system-health', { overall: 'unknown' }),
    refetchInterval: INTERVAL,
  });
}

export function usePerformanceCurve() {
  return useQuery({
    queryKey: ['performance-curve'],
    queryFn: () => fetchApi('/api/performance-curve', null),
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

export function useMarketRegime() {
  return useQuery({
    queryKey: ['market-regime'],
    queryFn: () => fetchApi('/api/market-regime', null),
    refetchInterval: INTERVAL,
  });
}

export function usePnlBreakdown(limit = 120) {
  return useQuery({
    queryKey: ['pnl-breakdown', limit],
    queryFn: () => fetchApi(`/api/pnl-breakdown?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}

export function useWalletConfig() {
  return useQuery({
    queryKey: ['wallet-config'],
    queryFn: () => fetchApi('/api/wallet-config', null),
    refetchInterval: INTERVAL,
  });
}
