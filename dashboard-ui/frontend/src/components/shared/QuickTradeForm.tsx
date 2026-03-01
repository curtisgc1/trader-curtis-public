import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { postApi } from '@/lib/api-client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2 } from 'lucide-react';


interface QuickTradeFormProps {
  venue: 'alpaca' | 'hyperliquid';
  symbols?: string[];
  invalidateKeys?: string[];
}

export function QuickTradeForm({
  venue,
  symbols,
  invalidateKeys = [],
}: QuickTradeFormProps) {
  const [symbol, setSymbol] = useState('');
  const [notional, setNotional] = useState('');
  const queryClient = useQueryClient();

  const endpoint =
    venue === 'alpaca'
      ? '/api/alpaca-quick-trade'
      : '/api/hyperliquid-quick-trade';

  const mutation = useMutation({
    mutationFn: (payload: { symbol: string; side: string; notional: number }) =>
      postApi(endpoint, payload),
    onSuccess: () => {
      for (const key of invalidateKeys) {
        queryClient.invalidateQueries({ queryKey: [key] });
      }
      setSymbol('');
      setNotional('');
    },
  });

  function submit(side: string) {
    const sym = symbol.trim().toUpperCase();
    const amt = parseFloat(notional);
    if (!sym || isNaN(amt) || amt <= 0) return;
    mutation.mutate({ symbol: sym, side, notional: amt });
  }

  const isAlpaca = venue === 'alpaca';
  const buyLabel = isAlpaca ? 'Buy' : 'Long';
  const sellLabel = isAlpaca ? 'Short' : 'Short';

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Quick Trade</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label className="text-xs">Symbol</Label>
          {symbols ? (
            <Select value={symbol} onValueChange={setSymbol}>
              <SelectTrigger>
                <SelectValue placeholder="Select..." />
              </SelectTrigger>
              <SelectContent>
                {symbols.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Input
              placeholder="AAPL"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
            />
          )}
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">Notional ($)</Label>
          <Input
            type="number"
            placeholder="100"
            value={notional}
            onChange={(e) => setNotional(e.target.value)}
          />
        </div>

        <div className="flex gap-2">
          <Button
            onClick={() => submit('buy')}
            disabled={mutation.isPending}
            className="flex-1 bg-primary/15 border border-primary/30 text-primary hover:bg-primary/25"
            variant="outline"
          >
            {mutation.isPending && (
              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
            )}
            {buyLabel}
          </Button>
          <Button
            onClick={() => submit('sell')}
            disabled={mutation.isPending}
            className="flex-1 bg-destructive/15 border border-destructive/30 text-destructive hover:bg-destructive/25"
            variant="outline"
          >
            {sellLabel}
          </Button>
          {isAlpaca && (
            <Button
              onClick={() => submit('close')}
              disabled={mutation.isPending}
              variant="outline"
              className="flex-1"
            >
              Close
            </Button>
          )}
        </div>

        {mutation.isError && (
          <p className="text-xs text-destructive">
            {(mutation.error as Error).message}
          </p>
        )}
        {mutation.isSuccess && (
          <p className="text-xs text-primary">Order submitted</p>
        )}
      </CardContent>
    </Card>
  );
}
