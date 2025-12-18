from hypothesis import given, strategies as st

from src.application.services.order_state_machine import OrderStateMachine, InvalidTransition
from src.domain.models.order import Order, OrderStatus, OrderType, Side
from datetime import datetime
from decimal import Decimal
import uuid


def make_order(status: OrderStatus) -> Order:
    return Order(
        id=str(uuid.uuid4()),
        symbol="SPY",
        side=Side.BUY,
        qty=Decimal("10"),
        order_type=OrderType.MARKET,
        status=status,
        limit_price=None,
        stop_price=None,
        created_at=datetime.utcnow(),
        last_update_at=datetime.utcnow(),
        account_id="live",
    )


@given(
    current=st.sampled_from(list(OrderStatus)),
    target=st.sampled_from(list(OrderStatus)),
)
def test_order_fsm_transitions(current, target):
    fsm = OrderStateMachine()
    order = make_order(current)
    fsm.add_order(order)

    can = fsm.can_transition(order.id, target)
    if can:
        updated = fsm.transition(order.id, target)
        assert updated.status == target
    else:
        try:
            fsm.transition(order.id, target)
        except InvalidTransition:
            assert True
        else:
            assert False, f"Transition {current}->{target} should be invalid"

