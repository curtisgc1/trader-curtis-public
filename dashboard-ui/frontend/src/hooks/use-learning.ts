import { useQuery } from '@tanstack/react-query';
import { fetchApi } from '@/lib/api-client';

const INTERVAL = 30_000;

export interface LearningHealth {
  coverage_pct: number;
  tracked_coverage_pct: number;
  resolved_routes: number;
  eligible_routes: number;
  realized_routes: number;
}

export interface MemoryIntegrityData {
  approved_routes: number;
  linked_routes: number;
  resolved_routes: number;
  consistency_state: string;
  coverage_pct: number;
  tracked_pct: number;
  realized_routes: number;
  orphan_outcomes: number;
}

export function useLearningHealth() {
  return useQuery({
    queryKey: ['learning-health'],
    queryFn: () => fetchApi<LearningHealth | null>('/api/learning-health', null),
    refetchInterval: INTERVAL,
  });
}

export function useLearningMonitor() {
  return useQuery({
    queryKey: ['learning-monitor'],
    queryFn: () => fetchApi<Record<string, unknown> | null>('/api/learning-monitor', null),
    refetchInterval: INTERVAL,
  });
}

export function useMemoryIntegrity() {
  return useQuery({
    queryKey: ['memory-integrity'],
    queryFn: () => fetchApi<MemoryIntegrityData | null>('/api/memory-integrity', null),
    refetchInterval: INTERVAL,
  });
}

export function useTradeIntents() {
  return useQuery({
    queryKey: ['trade-intents'],
    queryFn: () =>
      fetchApi<Array<Record<string, unknown>>>('/api/trade-intents', []),
    refetchInterval: INTERVAL,
  });
}

export function useExecutionLearning() {
  return useQuery({
    queryKey: ['execution-learning'],
    queryFn: () =>
      fetchApi<Array<Record<string, unknown>>>('/api/execution-learning', []),
    refetchInterval: INTERVAL,
  });
}

export function useSourceLearning() {
  return useQuery({
    queryKey: ['source-learning'],
    queryFn: () =>
      fetchApi<Array<Record<string, unknown>>>('/api/source-learning', []),
    refetchInterval: INTERVAL,
  });
}

export function useStrategyLearning() {
  return useQuery({
    queryKey: ['strategy-learning'],
    queryFn: () =>
      fetchApi<Array<Record<string, unknown>>>('/api/strategy-learning', []),
    refetchInterval: INTERVAL,
  });
}

export function useInputFeatureStats(dimension?: string) {
  const qs = dimension ? `?dimension=${encodeURIComponent(dimension)}` : '';
  return useQuery({
    queryKey: ['input-feature-stats', dimension],
    queryFn: () =>
      fetchApi<Array<Record<string, unknown>>>(`/api/input-feature-stats${qs}`, []),
    refetchInterval: INTERVAL,
  });
}
