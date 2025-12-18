import aiohttp
from datetime import datetime
from decimal import Decimal
from typing import List

from ...ports.broker import BrokerPort, OrderAck, Account
from ...domain.models.order import Order, OrderStatus, OrderType, Side
from ...ports.telemetry import TelemetryPort


class AlpacaBrokerAdapter(BrokerPort):
    """Alpaca REST API adapter (paper/live based on base_url)."""

    def __init__(self, base_url: str, api_key: str, secret_key: str, telemetry: TelemetryPort):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.secret_key = secret_key
        self.telemetry = telemetry
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={"APCA-API-KEY-ID": self.api_key, "APCA-API-SECRET-KEY": self.secret_key}
            )

    async def submit_order(self, order: Order) -> OrderAck:
        await self._ensure_session()
        trace = self.telemetry.start_trace("alpaca_submit_order")
        payload = {
            "symbol": order.symbol,
            "qty": str(order.qty),
            "side": order.side.value.lower(),
            "type": order.order_type.value.lower(),
            "time_in_force": order.time_in_force.lower(),
        }
        if order.limit_price:
            payload["limit_price"] = str(order.limit_price)
        if order.stop_price:
            payload["stop_price"] = str(order.stop_price)

        async with self._session.post(f"{self.base_url}/v2/orders", json=payload) as resp:
            data = await resp.json()
            if resp.status != 200:
                trace.finish(success=False, error=data.get("message"))
                return OrderAck(order_id=order.id, venue_order_id="", status="REJECTED", message=data.get("message", ""))
            trace.finish(success=True)
            return OrderAck(order_id=order.id, venue_order_id=data["id"], status="SUBMITTED")

    async def cancel_order(self, order_id: str) -> bool:
        await self._ensure_session()
        async with self._session.delete(f"{self.base_url}/v2/orders/{order_id}") as resp:
            return resp.status in (200, 204)

    async def get_positions(self) -> List["Position"]:
        await self._ensure_session()
        async with self._session.get(f"{self.base_url}/v2/positions") as resp:
            data = await resp.json()
            from ...domain.models.position import Position

            return [
                Position(
                    symbol=p["symbol"],
                    quantity=Decimal(p["qty"]),
                    avg_entry_price=Decimal(p["avg_entry_price"]),
                    unrealized_pnl=Decimal(p["unrealized_pl"]),
                    realized_pnl=Decimal("0"),
                    last_updated=datetime.utcnow(),
                    account_id="alpaca",
                )
                for p in data
            ]

    async def get_account(self) -> Account:
        await self._ensure_session()
        async with self._session.get(f"{self.base_url}/v2/account") as resp:
            data = await resp.json()
            return Account(
                id=data["id"],
                buying_power=Decimal(data["buying_power"]),
                equity=Decimal(data["equity"]),
                cash=Decimal(data["cash"]),
            )

    async def get_open_orders(self) -> List[Order]:
        await self._ensure_session()
        async with self._session.get(f"{self.base_url}/v2/orders?status=open") as resp:
            data = await resp.json()
            return [
                Order(
                    id=o["client_order_id"] or o["id"],
                    symbol=o["symbol"],
                    side=Side(o["side"].upper()),
                    qty=Decimal(o["qty"]),
                    order_type=OrderType(o["type"].upper()),
                    status=OrderStatus(o["status"].upper()),
                    limit_price=Decimal(o["limit_price"]) if o.get("limit_price") else None,
                    stop_price=Decimal(o["stop_price"]) if o.get("stop_price") else None,
                    created_at=datetime.fromisoformat(o["created_at"].replace("Z", "+00:00")),
                    last_update_at=datetime.fromisoformat(o["updated_at"].replace("Z", "+00:00")),
                    account_id="alpaca",
                    venue_order_id=o["id"],
                )
                for o in data
            ]

