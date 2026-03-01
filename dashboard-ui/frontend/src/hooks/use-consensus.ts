import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchApi, postApi } from '@/lib/api-client';

const INTERVAL = 30_000;

export function useTrustPanel() {
  return useQuery({
    queryKey: ['trust-panel'],
    queryFn: () => fetchApi('/api/trust-panel', null),
    refetchInterval: INTERVAL,
  });
}

export function useSourceRatings() {
  return useQuery({
    queryKey: ['source-ratings'],
    queryFn: () => fetchApi('/api/source-ratings', []),
    refetchInterval: INTERVAL,
  });
}

export function useSourceHorizonRatings() {
  return useQuery({
    queryKey: ['source-horizon-ratings'],
    queryFn: () => fetchApi('/api/source-horizon-ratings', []),
    refetchInterval: INTERVAL,
  });
}

export function useConsensusCandidates(flaggedOnly = true) {
  return useQuery({
    queryKey: ['consensus-candidates', flaggedOnly],
    queryFn: () =>
      fetchApi(
        `/api/consensus-candidates?flagged_only=${flaggedOnly ? '1' : '0'}`,
        [],
      ),
    refetchInterval: INTERVAL,
  });
}

export function useXConsensus() {
  return useQuery({
    queryKey: ['x-consensus'],
    queryFn: () => fetchApi('/api/x-consensus', null),
    refetchInterval: INTERVAL,
  });
}

export function useXConsensusSettingsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (settings: { x_consensus_min_hits: number }) =>
      postApi('/api/x-consensus-settings', settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['x-consensus'] });
    },
  });
}

export function useXDiscovery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { action: 'approve' | 'reject'; handle: string }) =>
      postApi('/api/x-discovery', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tracked-sources'] });
    },
  });
}
