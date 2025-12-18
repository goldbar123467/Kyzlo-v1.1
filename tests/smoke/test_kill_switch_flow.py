from datetime import datetime
from decimal import Decimal

import asyncio

from src.domain.events.signal import Signal
from src.domain.risk.kill_switch import KillSwitch
from src.domain.risk.pre_trade import PreTradeCheck
from src.domain.models.order import OrderStatus
from src.domain.models.portfolio import Portfolio
from src.domain.models.logical_account import LogicalAccount, AccountRole
from src.oms.order_manager import OrderManager
from src.application.services.order_state_machine import OrderStateMachine


class FakeRiskValidator:
    """Minimal risk gate honoring kill switch for this smoke test."""

    def __init__(self, kill_switch: KillSwitch):
        self.kill_switch = kill_switch

    def validate(self, signal, portfolio, market_state):
        if self.kill_switch.triggered:
            return PreTradeCheck(
                passed=False, reason=f"Kill switch: {self.kill_switch.reason}", rule_name="KILL_SWITCH"
            )
        return PreTradeCheck(passed=True, reason=None, rule_name="ALL")


class FakeEMSRouter:
    def __init__(self):
        self.canceled = []

    async def cancel_order(self, order):
        self.canceled.append(order.id)
        return True


def test_kill_switch_blocks_and_cancels():
    # Setup portfolio and account
    portfolio = Portfolio.initialize(Decimal("100000"))
    portfolio.accounts["live"] = LogicalAccount(
        id="live",
        role=AccountRole.LIVE,
        max_drawdown=Decimal("0.2"),
        max_leverage=Decimal("2"),
        capital_pct=Decimal("1.0"),
        initial_capital=Decimal("100000"),
    )

    kill_switch = KillSwitch()
    risk = FakeRiskValidator(kill_switch)
    fsm = OrderStateMachine()
    oms = OrderManager(fsm)

    # Create an open order
    sig = Signal(
        strategy_id="trend",
        symbol="SPY",
        target_position=Decimal("10"),
        confidence=0.9,
        timestamp=datetime.utcnow(),
        metadata={},
    )
    order = oms.create_order(sig, account_id="live")
    oms.transition_order(order.id, OrderStatus.PENDING)

    # Trigger kill switch
    kill_switch.trigger("test")

    # Validate new signal is blocked
    block = risk.validate(sig, portfolio, market_state=None)
    assert not block.passed
    assert block.rule_name == "KILL_SWITCH"

    # Ensure open orders get cancel requests
    router = FakeEMSRouter()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for o in oms.get_open_orders():
        # simulate cancel
        loop.run_until_complete(router.cancel_order(o))
        oms.transition_order(o.id, OrderStatus.CANCELED)
    loop.close()

    assert router.canceled == [order.id]
    assert all(o.status == OrderStatus.CANCELED for o in oms.get_open_orders()) or len(
        oms.get_open_orders()
    ) == 0

