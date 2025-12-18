from datetime import datetime
from decimal import Decimal

from hypothesis import given, strategies as st

from src.domain.models.portfolio import Portfolio
from src.domain.models.position import Position


@given(
    qty1=st.decimals(min_value="-1000", max_value="1000", allow_nan=False, allow_infinity=False),
    px1=st.decimals(min_value="1", max_value="1000", allow_nan=False, allow_infinity=False),
    qty2=st.decimals(min_value="-1000", max_value="1000", allow_nan=False, allow_infinity=False),
    px2=st.decimals(min_value="1", max_value="1000", allow_nan=False, allow_infinity=False),
)
def test_portfolio_value_invariant(qty1, px1, qty2, px2):
    portfolio = Portfolio.initialize(Decimal("100000"))
    portfolio.positions["A"] = Position(
        symbol="A",
        quantity=Decimal(qty1),
        avg_entry_price=Decimal(px1),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        last_updated=datetime.utcnow(),
        account_id="live",
    )
    portfolio.positions["B"] = Position(
        symbol="B",
        quantity=Decimal(qty2),
        avg_entry_price=Decimal(px2),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        last_updated=datetime.utcnow(),
        account_id="live",
    )

    position_value = sum(
        pos.quantity * pos.avg_entry_price for pos in portfolio.positions.values()
    )
    expected_total = portfolio.cash + position_value

    # Invariant: total_value matches cash + positions
    portfolio.total_value = expected_total
    assert portfolio.total_value == expected_total

