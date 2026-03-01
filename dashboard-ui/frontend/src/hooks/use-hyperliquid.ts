import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchApi, postApi } from '@/lib/api-client';

const INTERVAL = 30_000;

export function useHyperliquidIntents(limit = 120) {
  return useQuery({
    queryKey: ['hyperliquid-intents', limit],
    queryFn: () => fetchApi(`/api/hyperliquid-intents?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}

export function useHyperliquidClosePosition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) =>
      postApi('/api/hyperliquid-close-position', { symbol }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolio-snapshot'] });
      queryClient.invalidateQueries({ queryKey: ['hyperliquid-intents'] });
    },
  });
}
