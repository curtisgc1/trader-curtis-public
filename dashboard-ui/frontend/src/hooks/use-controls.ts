import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchApi, postApi } from '@/lib/api-client';

const INTERVAL = 30_000;

export function useRiskControls() {
  return useQuery({
    queryKey: ['risk-controls'],
    queryFn: () => fetchApi('/api/risk-controls', null),
    refetchInterval: INTERVAL,
  });
}

export function useRiskControlsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (updates: Record<string, unknown>) =>
      postApi('/api/risk-controls', { updates }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['risk-controls'] });
    },
  });
}

export function useActionMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: string) => postApi('/api/actions', { action }),
    onSuccess: () => {
      queryClient.invalidateQueries();
    },
  });
}

export function useTrackedSources() {
  return useQuery({
    queryKey: ['tracked-sources'],
    queryFn: () => fetchApi('/api/tracked-sources', []),
    refetchInterval: INTERVAL,
  });
}

export function useTrackedSourceUpsert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (source: Record<string, unknown>) =>
      postApi('/api/tracked-sources', source),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tracked-sources'] });
    },
  });
}

export function useInputSources() {
  return useQuery({
    queryKey: ['input-sources'],
    queryFn: () => fetchApi('/api/input-sources', []),
    refetchInterval: INTERVAL,
  });
}

export function useInputSourceUpsert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (source: Record<string, unknown>) =>
      postApi('/api/input-sources', source),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['input-sources'] });
    },
  });
}

export function useTickerTradeProfiles() {
  return useQuery({
    queryKey: ['ticker-trade-profiles'],
    queryFn: () => fetchApi('/api/ticker-trade-profiles', []),
    refetchInterval: INTERVAL,
  });
}

export function useTickerTradeProfileUpsert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (profile: Record<string, unknown>) =>
      postApi('/api/ticker-trade-profiles', profile),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ticker-trade-profiles'] });
    },
  });
}

export function usePositionProtection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      postApi('/api/position-protection', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolio-snapshot'] });
    },
  });
}

export function useVenueMatrixMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (updates: unknown[]) =>
      postApi('/api/venue-matrix', { updates }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['venue-matrix'] });
    },
  });
}

export function useHealthPulse() {
  return useQuery({
    queryKey: ['health-pulse'],
    queryFn: () => fetchApi('/api/health-pulse', null),
    refetchInterval: INTERVAL,
  });
}

export function useAgentAwareness() {
  return useQuery({
    queryKey: ['agent-awareness'],
    queryFn: () => fetchApi('/api/agent-awareness', null),
    refetchInterval: INTERVAL,
  });
}

export function useTradeClaimGuard() {
  return useQuery({
    queryKey: ['trade-claim-guard'],
    queryFn: () => fetchApi('/api/trade-claim-guard', null),
    refetchInterval: INTERVAL,
  });
}

export function useSourcePremiumBreakdown(sourceTag: string) {
  return useQuery({
    queryKey: ['source-premium-breakdown', sourceTag],
    queryFn: () =>
      fetchApi(
        `/api/source-premium-breakdown?source_tag=${encodeURIComponent(sourceTag)}`,
        null,
      ),
    enabled: sourceTag.length > 0,
  });
}

export function usePositionManagementIntents(limit = 120) {
  return useQuery({
    queryKey: ['position-management-intents', limit],
    queryFn: () =>
      fetchApi(`/api/position-management-intents?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}

export function useInputFeatureStats(dimension?: string) {
  const qs = dimension ? `?dimension=${encodeURIComponent(dimension)}` : '';
  return useQuery({
    queryKey: ['input-feature-stats', dimension],
    queryFn: () => fetchApi(`/api/input-feature-stats${qs}`, []),
    refetchInterval: INTERVAL,
  });
}
