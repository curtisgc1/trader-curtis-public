import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell } from '@/components/layout/AppShell';
import { OverviewPage } from '@/pages/OverviewPage';
import { PolymarketPage } from '@/pages/PolymarketPage';
import { HyperliquidPage } from '@/pages/HyperliquidPage';
import { AlpacaPage } from '@/pages/AlpacaPage';
import { ConsensusPage } from '@/pages/ConsensusPage';
import { SignalsPage } from '@/pages/SignalsPage';
import { LearningPage } from '@/pages/LearningPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 10_000,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="polymarket" element={<PolymarketPage />} />
            <Route path="hyperliquid" element={<HyperliquidPage />} />
            <Route path="alpaca" element={<AlpacaPage />} />
            <Route path="consensus" element={<ConsensusPage />} />
            <Route path="signals" element={<SignalsPage />} />
            <Route path="learning" element={<LearningPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
