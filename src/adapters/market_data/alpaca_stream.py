import asyncio
import json
from datetime import datetime
from decimal import Decimal
from typing import AsyncIterator, List, Optional

import websockets

from ...ports.market_data import MarketDataPort, Tick
from ...ports.telemetry import TelemetryPort


class AlpacaStreamAdapter(MarketDataPort):
    """Alpaca WebSocket for real-time trades/quotes."""

    def __init__(self, stream_url: str, api_key: str, secret_key: str, telemetry: TelemetryPort):
        self.stream_url = stream_url
        self.api_key = api_key
        self.secret_key = secret_key
        self.telemetry = telemetry
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._subscribed_symbols: List[str] = []
        self._last_snapshot = {}

    async def subscribe(self, symbols: List[str]) -> None:
        await self._connect()
        await self._authenticate()
        self._subscribed_symbols = symbols
        subscribe_msg = {
            "action": "subscribe",
            "trades": symbols,
            "quotes": symbols,
        }
        await self._ws.send(json.dumps(subscribe_msg))
        self._running = True

    async def stream(self) -> AsyncIterator[Tick]:
        while self._running:
            try:
                msg = await asyncio.wait_for(self._ws.recv(), timeout=30.0)
                for tick in self._parse_message(msg):
                    self._last_snapshot[tick.symbol] = tick
                    latency_ms = (datetime.utcnow() - tick.timestamp).total_seconds() * 1000
                    self.telemetry.record_latency("alpaca_tick", latency_ms)
                    yield tick
            except asyncio.TimeoutError:
                self.telemetry.log_structured("warning", "Alpaca stream timeout", {"venue": "alpaca"})
                await self._reconnect()
            except websockets.ConnectionClosed:
                self.telemetry.log_structured("error", "Alpaca connection closed", {"venue": "alpaca"})
                await self._reconnect()

    async def get_snapshot(self, symbol: str) -> "MarketState":
        from ...domain.models.market_state import MarketState

        tick = self._last_snapshot.get(symbol)
        if not tick:
            raise ValueError(f"No snapshot for {symbol}")
        return MarketState.from_tick(tick)

    async def disconnect(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()

    async def _connect(self):
        self._ws = await websockets.connect(self.stream_url)

    async def _authenticate(self):
        auth_msg = {"action": "auth", "key": self.api_key, "secret": self.secret_key}
        await self._ws.send(json.dumps(auth_msg))
        response = await self._ws.recv()
        data = json.loads(response)
        if not isinstance(data, list) or data[0].get("msg") != "authenticated":
            raise RuntimeError("Alpaca authentication failed")

    async def _reconnect(self):
        if self._ws:
            await self._ws.close()
        await asyncio.sleep(1)
        await self._connect()
        await self._authenticate()
        if self._subscribed_symbols:
            subscribe_msg = {
                "action": "subscribe",
                "trades": self._subscribed_symbols,
                "quotes": self._subscribed_symbols,
            }
            await self._ws.send(json.dumps(subscribe_msg))

    def _parse_message(self, msg: str) -> List[Tick]:
        data = json.loads(msg)
        ticks: List[Tick] = []
        if not isinstance(data, list):
            return ticks
        for item in data:
            msg_type = item.get("T")
            if msg_type == "t":  # Trade
                ticks.append(
                    Tick(
                        symbol=item["S"],
                        timestamp=datetime.fromisoformat(item["t"].replace("Z", "+00:00")),
                        price=Decimal(str(item["p"])),
                        size=Decimal(str(item["s"])),
                        bid=None,
                        ask=None,
                        exchange=item.get("x"),
                    )
                )
            elif msg_type == "q":  # Quote
                ticks.append(
                    Tick(
                        symbol=item["S"],
                        timestamp=datetime.fromisoformat(item["t"].replace("Z", "+00:00")),
                        price=(Decimal(str(item["bp"])) + Decimal(str(item["ap"]))) / 2,
                        size=Decimal(str(item["bs"])),
                        bid=Decimal(str(item["bp"])),
                        ask=Decimal(str(item["ap"])),
                        exchange=item.get("x"),
                    )
                )
        return ticks

