from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Mapping, Optional, Tuple

from domain.events.signal import Signal as DomainSignal
from domain.models.logical_account import LogicalAccount
from domain.models.market_state import MarketState
from domain.models.portfolio import Portfolio
from domain.models.position import Position as DomainPosition
from domain.risk.pre_trade import PreTradeRules

from otq.domain.perps.health import MarginState
from otq.domain.perps.types import PerpsPosition, PositionSide, PriceSnapshot, PriceType
from otq.engines.perps_execution_engine import NormalizedPerpsSignal


def _d(v: Any) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


def _signed_delta_qty(sig: NormalizedPerpsSignal) -> Decimal:
    qty = _d(sig.qty)
    if sig.desired.upper() == "LONG":
        return qty
    if sig.desired.upper() == "SHORT":
        return -qty
    return Decimal("0")


def _position_to_domain(pos: Optional[PerpsPosition], *, account_id: str) -> Optional[DomainPosition]:
    if pos is None:
        return None

    signed_qty = Decimal(str(pos.qty))
    if pos.side == PositionSide.SHORT:
        signed_qty = -signed_qty

    return DomainPosition(
        symbol=pos.symbol,
        quantity=signed_qty,
        avg_entry_price=_d(pos.avg_entry_price),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        last_updated=datetime.now(timezone.utc),
        account_id=account_id,
    )


def _price_decimal(price: Optional[PriceSnapshot], *, prefer: PriceType = PriceType.ORACLE) -> Optional[Decimal]:
    if price is None:
        return None

    v = price.get(prefer)
    if v is None:
        # Fallback order (explicit + deterministic)
        v = price.oracle_price or price.mark_price or price.last_price or price.index_price

    return _d(v) if v is not None else None


@dataclass(frozen=True)
class PerpsPreTradeHookConfig:
    """Configuration for running `domain.risk.pre_trade.PreTradeRules` in perps.

    Notes:
    - `NormalizedPerpsSignal.qty` is treated as *delta* size (open intent size),
      which matches how `PreTradeRules.check_position_limit` is implemented.
    - This hook is intended to run for OPENS only; the engine already avoids
      calling it for reduce-only CLOSE/REDUCE paths.
    """

    account_id: str = "live"

    # Optional per-symbol limits
    max_position_size: Optional[Decimal] = None
    max_position_size_by_symbol: Optional[Mapping[str, Decimal]] = None

    max_notional: Optional[Decimal] = None
    max_notional_by_symbol: Optional[Mapping[str, Decimal]] = None

    # If True, run leverage check when portfolio/account are provided.
    enforce_leverage: bool = True

    # If True, run fat-finger check when market_state is provided.
    enforce_fat_finger: bool = False

    # Which price to use for notional/leverage.
    price_preference: PriceType = PriceType.ORACLE


PortfolioProvider = Callable[[Any, NormalizedPerpsSignal], Portfolio]
AccountProvider = Callable[[Any, NormalizedPerpsSignal, Portfolio], LogicalAccount]
MarketStateProvider = Callable[[Any, NormalizedPerpsSignal], MarketState]


def make_perps_pre_trade_hook(
    *,
    rules: Optional[PreTradeRules] = None,
    config: Optional[PerpsPreTradeHookConfig] = None,
    portfolio_provider: Optional[PortfolioProvider] = None,
    account_provider: Optional[AccountProvider] = None,
    market_state_provider: Optional[MarketStateProvider] = None,
) -> Callable[[Any, NormalizedPerpsSignal, Optional[PriceSnapshot], MarginState, Optional[PerpsPosition]], Tuple[bool, str]]:
    """Create a perps `pre_trade_hook` that evaluates existing `PreTradeRules`.

    The returned hook matches the perps engine hook signature.

    Returns:
        (passed, reason)
    """

    r = rules or PreTradeRules()
    cfg = config or PerpsPreTradeHookConfig()

    def _max_position_for(symbol: str) -> Optional[Decimal]:
        if cfg.max_position_size_by_symbol and symbol in cfg.max_position_size_by_symbol:
            return cfg.max_position_size_by_symbol[symbol]
        return cfg.max_position_size

    def _max_notional_for(symbol: str) -> Optional[Decimal]:
        if cfg.max_notional_by_symbol and symbol in cfg.max_notional_by_symbol:
            return cfg.max_notional_by_symbol[symbol]
        return cfg.max_notional

    def hook(
        raw_signal: Any,
        normalized: NormalizedPerpsSignal,
        price: Optional[PriceSnapshot],
        margin: MarginState,
        pos: Optional[PerpsPosition],
    ) -> Tuple[bool, str]:
        _ = margin  # reserved for future use (e.g., available collateral)

        desired = normalized.desired.upper()
        if desired not in {"LONG", "SHORT"}:
            return True, ""

        delta = _signed_delta_qty(normalized)

        domain_signal = DomainSignal(
            strategy_id=str(getattr(raw_signal, "strategy_id", "perps")),
            symbol=str(normalized.symbol),
            target_position=delta,
            confidence=float(getattr(raw_signal, "confidence", normalized.confidence or 1.0)),
            timestamp=getattr(raw_signal, "timestamp", datetime.now(timezone.utc)),
            metadata=dict(getattr(raw_signal, "metadata", {}) or {}),
            account_id=str(getattr(raw_signal, "account_id", cfg.account_id)),
        )

        domain_position = _position_to_domain(pos, account_id=domain_signal.account_id)

        # 1) Position limit
        max_pos = _max_position_for(domain_signal.symbol)
        if max_pos is not None:
            chk = r.check_position_limit(domain_signal, domain_position, _d(max_pos))
            if not chk.passed:
                return False, f"{chk.rule_name}: {chk.reason or 'blocked'}"

        # 2) Price-dependent checks require a price
        px = _price_decimal(price, prefer=cfg.price_preference)

        # 2a) Notional limit
        max_notional = _max_notional_for(domain_signal.symbol)
        if max_notional is not None:
            if px is None:
                return False, "NOTIONAL_LIMIT: missing_price"
            chk = r.check_notional_limit(domain_signal, px, _d(max_notional))
            if not chk.passed:
                return False, f"{chk.rule_name}: {chk.reason or 'blocked'}"

        # 2b) Leverage
        if cfg.enforce_leverage and (portfolio_provider is not None):
            if px is None:
                return False, "LEVERAGE: missing_price"
            portfolio = portfolio_provider(raw_signal, normalized)
            if account_provider is not None:
                account = account_provider(raw_signal, normalized, portfolio)
            else:
                # Default: resolve account_id from portfolio.accounts
                acct_id = domain_signal.account_id
                if acct_id not in portfolio.accounts:
                    return False, f"LEVERAGE: unknown_account_id={acct_id}"
                account = portfolio.accounts[acct_id]

            chk = r.check_leverage(domain_signal, portfolio, account, px)
            if not chk.passed:
                return False, f"{chk.rule_name}: {chk.reason or 'blocked'}"

        # 3) Fat finger (optional)
        if cfg.enforce_fat_finger and (market_state_provider is not None):
            ms = market_state_provider(raw_signal, normalized)
            chk = r.check_fat_finger(domain_signal, ms)
            if not chk.passed:
                return False, f"{chk.rule_name}: {chk.reason or 'blocked'}"

        return True, ""

    return hook
