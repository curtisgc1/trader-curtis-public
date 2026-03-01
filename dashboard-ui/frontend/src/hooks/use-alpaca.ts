import { useQuery } from '@tanstack/react-query';
import { fetchApi } from '@/lib/api-client';

const INTERVAL = 30_000;

export function useAlpacaOrders(limit = 120) {
  return useQuery({
    queryKey: ['alpaca-orders', limit],
    queryFn: () => fetchApi(`/api/alpaca-orders?limit=${limit}`, []),
    refetchInterval: INTERVAL,
  });
}
