#!/usr/bin/env python3
"""
Real-time crypto spot prices via Binance WebSocket miniTicker streams.

Replaces slow CoinGecko HTTP polling with sub-second price updates.
Thread-safe price cache populated by a background WebSocket listener.
Tracks price history over configurable windows for momentum calculation.

Usage:
    from binance_ws_feed import start_feed, stop_feed, get_spot_price, get_price_change_pct

    start_feed()
    price = get_spot_price("BTC")
    change = get_price_change_pct("ETH", minutes=15)
    stop_feed()
"""

import asyncio
import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, Optional, Tuple

import websockets
from websockets.exceptions import ConnectionClosed

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"

TICKER_TO_SYMBOL = {
    "BTC": "btcusdt",
    "ETH": "ethusdt",
    "SOL": "solusdt",
    "DOGE": "dogeusdt",
    "XRP": "xrpusdt",
    "ADA": "adausdt",
    "AVAX": "avaxusdt",
    "DOT": "dotusdt",
    "LINK": "linkusdt",
    "BNB": "bnbusdt",
    "LTC": "ltcusdt",
}

SYMBOL_TO_TICKER: Dict[str, str] = {
    v.upper(): k for k, v in TICKER_TO_SYMBOL.items()
}

MAX_HISTORY_SECONDS = 20 * 60
HISTORY_SAMPLE_INTERVAL = 1.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _PriceCache:
    """Thread-safe cache holding latest prices and price history per ticker."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._prices: Dict[str, float] = {}
        self._updated_at: Dict[str, float] = {}
        self._history: Dict[str, Deque[Tuple[float, float]]] = {}
        self._last_sample_ts: Dict[str, float] = {}

    def update(self, ticker: str, price: float) -> None:
        now = time.monotonic()
        with self._lock:
            self._prices[ticker] = price
            self._updated_at[ticker] = now

            if ticker not in self._history:
                self._history[ticker] = deque()
                self._last_sample_ts[ticker] = 0.0

            last_sample = self._last_sample_ts[ticker]
            if now - last_sample >= HISTORY_SAMPLE_INTERVAL:
                self._history[ticker].append((now, price))
                self._last_sample_ts[ticker] = now

                cutoff = now - MAX_HISTORY_SECONDS
                hist = self._history[ticker]
                while hist and hist[0][0] < cutoff:
                    hist.popleft()

    def get_price(self, ticker: str) -> Optional[float]:
        with self._lock:
            return self._prices.get(ticker)

    def get_change_pct(self, ticker: str, minutes: int) -> Optional[float]:
        window_seconds = minutes * 60
        now = time.monotonic()
        with self._lock:
            hist = self._history.get(ticker)
            if not hist or len(hist) < 2:
                return None

            current_price = self._prices.get(ticker)
            if current_price is None:
                return None

            target_ts = now - window_seconds
            oldest_in_window: Optional[Tuple[float, float]] = None
            for ts, px in hist:
                if ts >= target_ts:
                    oldest_in_window = (ts, px)
                    break

            if oldest_in_window is None:
                return None

            old_price = oldest_in_window[1]
            if old_price <= 0:
                return None

            elapsed = now - oldest_in_window[0]
            if elapsed < window_seconds * 0.5:
                return None

            return ((current_price - old_price) / old_price) * 100.0

    def is_stale(self, ticker: str, max_age_seconds: float = 30.0) -> bool:
        with self._lock:
            updated = self._updated_at.get(ticker)
            if updated is None:
                return True
            return (time.monotonic() - updated) > max_age_seconds


_cache = _PriceCache()
_feed_thread: Optional[threading.Thread] = None
_feed_stop_event = threading.Event()
_feed_ready_event = threading.Event()
_feed_running = False


async def _ws_listener(stop_event: threading.Event, ready_event: threading.Event) -> None:
    streams = [f"{sym}@miniTicker" for sym in TICKER_TO_SYMBOL.values()]
    subscribe_msg = json.dumps({
        "method": "SUBSCRIBE",
        "params": streams,
        "id": 1,
    })

    reconnect_delay = 1.0
    max_reconnect_delay = 30.0

    while not stop_event.is_set():
        try:
            async with websockets.connect(
                BINANCE_WS_URL,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                await ws.send(subscribe_msg)

                ack = await asyncio.wait_for(ws.recv(), timeout=10)
                ack_data = json.loads(ack)
                if ack_data.get("id") == 1:
                    ready_event.set()

                reconnect_delay = 1.0

                while not stop_event.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    except asyncio.TimeoutError:
                        continue

                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    symbol = msg.get("s")
                    close_price_str = msg.get("c")
                    if symbol and close_price_str:
                        ticker = SYMBOL_TO_TICKER.get(symbol)
                        if ticker:
                            try:
                                price = float(close_price_str)
                                if price > 0:
                                    _cache.update(ticker, price)
                            except ValueError:
                                pass

        except ConnectionClosed:
            pass
        except Exception:
            pass

        if not stop_event.is_set():
            stop_event.wait(timeout=reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)


def _run_ws_loop(stop_event: threading.Event, ready_event: threading.Event) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_ws_listener(stop_event, ready_event))
    finally:
        loop.close()


def start_feed(timeout: float = 10.0) -> bool:
    """Start the Binance WebSocket feed in a background thread.

    Returns True if feed connected successfully within timeout, False otherwise.
    Calling start_feed() when already running is a no-op that returns True.
    """
    global _feed_thread, _feed_running

    if _feed_running and _feed_thread is not None and _feed_thread.is_alive():
        return True

    _feed_stop_event.clear()
    _feed_ready_event.clear()

    _feed_thread = threading.Thread(
        target=_run_ws_loop,
        args=(_feed_stop_event, _feed_ready_event),
        daemon=True,
        name="binance-ws-feed",
    )
    _feed_thread.start()

    connected = _feed_ready_event.wait(timeout=timeout)
    _feed_running = connected
    return connected


def stop_feed() -> None:
    """Stop the Binance WebSocket feed and wait for the thread to exit."""
    global _feed_thread, _feed_running

    _feed_stop_event.set()
    if _feed_thread is not None and _feed_thread.is_alive():
        _feed_thread.join(timeout=5.0)
    _feed_thread = None
    _feed_running = False


def is_feed_running() -> bool:
    """Check whether the WebSocket feed thread is alive and connected."""
    return _feed_running and _feed_thread is not None and _feed_thread.is_alive()


def get_spot_price(ticker: str) -> Optional[float]:
    """Get the latest spot price for a ticker (e.g. 'BTC', 'ETH').

    Returns None if the feed is not running, the ticker is unknown,
    or the cached price is stale (>30s old).
    """
    ticker = ticker.upper()
    if ticker not in TICKER_TO_SYMBOL:
        return None
    if not is_feed_running():
        return None
    if _cache.is_stale(ticker):
        return None
    return _cache.get_price(ticker)


def get_price_change_pct(ticker: str, minutes: int = 15) -> Optional[float]:
    """Get the price change percentage over the given window.

    Returns None if insufficient history is available (need at least 50%
    of the requested window filled with data).
    """
    ticker = ticker.upper()
    if ticker not in TICKER_TO_SYMBOL:
        return None
    if not is_feed_running():
        return None
    return _cache.get_change_pct(ticker, minutes)


def get_all_prices() -> Dict[str, float]:
    """Return a snapshot of all current prices. Useful for diagnostics."""
    result: Dict[str, float] = {}
    for ticker in TICKER_TO_SYMBOL:
        price = _cache.get_price(ticker)
        if price is not None:
            result[ticker] = price
    return result
