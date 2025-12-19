"""
jupiter_adapter.py - Jupiter DEX adapter with execution-grade safety

Implements the hardening from ChatGPT analysis:
1. Single-flight execution (one order per symbol/side at a time)
2. Idempotency via position state tracking
3. Entry gating with freshness, cooldowns, and liquidity checks
4. Exit priority over entries
5. Graceful shutdown with position flattening

Usage:
    from jupiter_adapter import JupiterAdapter, JupiterConfig
    from solana_client import SolanaClient
    
    adapter = JupiterAdapter(config, solana_client)
    
    # Check if we can enter
    if adapter.can_enter("SOL/USDC"):
        result = await adapter.enter("SOL/USDC", price, size)
    
    # Exits have priority
    if adapter.should_exit("SOL/USDC", current_price):
        result = await adapter.exit("SOL/USDC", current_price, reason)
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

import httpx
from loguru import logger

# Import our hardened client
from solana_client import SolanaClient, TxResult, TxOutcome


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass(frozen=True)
class JupiterConfig:
    """Jupiter adapter configuration."""
    
    # API settings
    base_url: str = "https://quote-api.jup.ag/v6"
    http_timeout: float = 30.0
    
    # Slippage escalation ladder (bps per attempt)
    # Attempt 1: base slippage
    # Attempt 2: same slippage, just retry
    # Attempt 3: modest bump + priority fee
    # Attempt 4: larger bump, still capped
    slippage_bps_attempt_1: int = 50   # 0.50%
    slippage_bps_attempt_2: int = 50   # 0.50% (retry)
    slippage_bps_attempt_3: int = 100  # 1.00% (modest bump)
    slippage_bps_attempt_4: int = 150  # 1.50% (larger bump)
    slippage_bps_max: int = 200        # 2.00% hard cap
    
    # Priority fee escalation (lamports)
    priority_fee_attempt_1: int = 0        # auto
    priority_fee_attempt_2: int = 0        # auto
    priority_fee_attempt_3: int = 50000    # 0.00005 SOL
    priority_fee_attempt_4: int = 100000   # 0.0001 SOL
    
    # Attempt ladder settings
    max_attempts: int = 4
    attempt_delay_seconds: float = 2.0  # Delay between attempts
    
    # Retry settings
    max_quote_retries: int = 3
    retry_delay_base: float = 1.0
    
    # Cooldown settings (from ChatGPT analysis)
    failure_cooldown_seconds: float = 120.0  # 2 min cooldown after max_attempts failures
    failure_threshold: int = 4  # Number of failures before cooldown
    
    # Price freshness
    price_ttl_seconds: float = 10.0
    
    # Liquidity checks
    max_price_impact_bps: int = 100  # 1% max price impact
    
    # SOL reserve for fees
    min_sol_reserve: float = 0.10  # Keep 0.1 SOL for tx fees
    
    def get_slippage_for_attempt(self, attempt: int) -> int:
        """Get slippage bps for a given attempt number (1-indexed)."""
        slippages = [
            self.slippage_bps_attempt_1,
            self.slippage_bps_attempt_2,
            self.slippage_bps_attempt_3,
            self.slippage_bps_attempt_4,
        ]
        idx = min(attempt - 1, len(slippages) - 1)
        return min(slippages[idx], self.slippage_bps_max)
    
    def get_priority_fee_for_attempt(self, attempt: int) -> Optional[int]:
        """Get priority fee for a given attempt number (1-indexed). None = auto."""
        fees = [
            self.priority_fee_attempt_1,
            self.priority_fee_attempt_2,
            self.priority_fee_attempt_3,
            self.priority_fee_attempt_4,
        ]
        idx = min(attempt - 1, len(fees) - 1)
        fee = fees[idx]
        return fee if fee > 0 else None  # None means "auto"


class PositionState(Enum):
    """
    Position state machine.
    
    States:
    - FLAT: No position
    - OPEN: Have position
    - EXIT_ONLY: Have position, only exits allowed (after repeated failures)
    
    CRITICAL: Inflight status is tracked by inflight_*_signature, NOT by state.
    If inflight_buy_signature is set -> entry tx may still land
    If inflight_sell_signature is set -> exit tx may still land
    
    State transitions happen ONLY after confirm-or-reconcile:
    - SUCCESS on entry: FLAT -> OPEN
    - SUCCESS on exit: OPEN -> FLAT
    - FAILURE: no change
    - UNKNOWN: no change (signature preserved blocks new attempts)
    """
    FLAT = "flat"
    OPEN = "open"
    EXIT_ONLY = "exit_only"


@dataclass
class PairState:
    """
    Per-pair state tracking for idempotency and cooldowns.
    
    Phase 2/3 additions:
    - inflight_exit_intent_id: Tracks pending exit for single-flight protection
    - Only one exit can be inflight per token at a time
    """
    pair: str
    position_state: PositionState = PositionState.FLAT
    
    # Position data
    entry_price: Optional[float] = None
    entry_time: Optional[datetime] = None
    size_base: Optional[float] = None
    
    # In-flight tracking (per side) - Phase 3: single-flight protection
    inflight_buy_signature: Optional[str] = None
    inflight_buy_intent_id: Optional[str] = None
    inflight_sell_signature: Optional[str] = None
    inflight_sell_intent_id: Optional[str] = None
    
    # Per-side cooldowns (explicit timestamps as per Phase 1)
    buy_cooldown_until: Optional[datetime] = None
    sell_cooldown_until: Optional[datetime] = None
    
    # Per-side failure tracking
    buy_consecutive_failures: int = 0
    sell_consecutive_failures: int = 0
    
    # Current attempt tracking (for ladder)
    current_buy_attempt: int = 0
    current_sell_attempt: int = 0
    
    # Last trade tracking
    last_entry_time: Optional[datetime] = None
    last_exit_time: Optional[datetime] = None
    
    def is_buy_in_cooldown(self) -> bool:
        """Check if BUY is in failure cooldown."""
        if self.buy_cooldown_until is None:
            return False
        return datetime.now(timezone.utc) < self.buy_cooldown_until
    
    def is_sell_in_cooldown(self) -> bool:
        """Check if SELL is in failure cooldown."""
        if self.sell_cooldown_until is None:
            return False
        return datetime.now(timezone.utc) < self.sell_cooldown_until
    
    def record_buy_failure(self, cooldown_threshold: int, cooldown_seconds: float) -> None:
        """Record a BUY failure and potentially trigger cooldown."""
        self.buy_consecutive_failures += 1
        
        if self.buy_consecutive_failures >= cooldown_threshold:
            self.buy_cooldown_until = datetime.now(timezone.utc) + \
                                      __import__('datetime').timedelta(seconds=cooldown_seconds)
            self.current_buy_attempt = 0  # Reset attempt counter
            logger.warning(
                f"BUY_COOLDOWN_START | {self.pair} | failures={self.buy_consecutive_failures} | "
                f"until={self.buy_cooldown_until.isoformat()}"
            )
    
    def record_sell_failure(self, cooldown_threshold: int, cooldown_seconds: float) -> None:
        """Record a SELL failure and potentially trigger cooldown."""
        self.sell_consecutive_failures += 1
        
        if self.sell_consecutive_failures >= cooldown_threshold:
            self.sell_cooldown_until = datetime.now(timezone.utc) + \
                                       __import__('datetime').timedelta(seconds=cooldown_seconds)
            self.current_sell_attempt = 0  # Reset attempt counter
            logger.warning(
                f"SELL_COOLDOWN_START | {self.pair} | failures={self.sell_consecutive_failures} | "
                f"until={self.sell_cooldown_until.isoformat()}"
            )
    
    def reset_buy_failures(self) -> None:
        """Reset BUY failure counter on success."""
        self.buy_consecutive_failures = 0
        self.buy_cooldown_until = None
        self.current_buy_attempt = 0
    
    def reset_sell_failures(self) -> None:
        """Reset SELL failure counter on success."""
        self.sell_consecutive_failures = 0
        self.sell_cooldown_until = None
        self.current_sell_attempt = 0
    
    def has_inflight(self, side: Optional[str] = None) -> bool:
        """Check if there's an in-flight tx for this pair."""
        if side == "BUY":
            return self.inflight_buy_signature is not None
        elif side == "SELL":
            return self.inflight_sell_signature is not None
        else:
            return self.inflight_buy_signature is not None or self.inflight_sell_signature is not None
    
    def has_inflight_exit(self) -> bool:
        """
        Phase 3: Check if there's an inflight exit for this token.
        
        This prevents double-selling when first tx lands late.
        """
        return self.inflight_sell_signature is not None or \
               self.position_state == PositionState.EXITING_INFLIGHT


@dataclass
class TradeResult:
    """
    Result of a trade execution.
    
    CRITICAL: outcome is a 3-state enum, NOT binary success.
    - SUCCESS: Confirmed on-chain or reconciled_success
    - FAILURE: Definitive failure (simulation failed, reconciled_failure)
    - UNKNOWN: Timeout, RPC ambiguity - tx may still land
    """
    outcome: str  # "SUCCESS", "FAILURE", "UNKNOWN"
    pair: str
    side: str  # "BUY" or "SELL"
    signature: Optional[str] = None
    price: Optional[float] = None
    size: Optional[float] = None
    error: Optional[str] = None
    tx_result: Optional[TxResult] = None
    
    # Attempt info
    attempt_number: int = 1
    slippage_bps_used: int = 0
    priority_fee_used: Optional[int] = None
    
    # Quote data
    quote_in_amount: Optional[int] = None
    quote_out_amount: Optional[int] = None
    price_impact_bps: Optional[int] = None
    
    @property
    def success(self) -> bool:
        """Backward compat - but prefer checking outcome directly."""
        return self.outcome == "SUCCESS"
    
    @property
    def is_unknown(self) -> bool:
        """True if outcome is uncertain - tx may still land."""
        return self.outcome == "UNKNOWN"


# =============================================================================
# TOKEN REGISTRY (inline for standalone use)
# =============================================================================

@dataclass(frozen=True)
class TokenInfo:
    """Token metadata."""
    symbol: str
    mint: str
    decimals: int


# Standard Solana tokens
TOKENS: Dict[str, TokenInfo] = {
    "SOL": TokenInfo("SOL", "So11111111111111111111111111111111111111112", 9),
    "USDC": TokenInfo("USDC", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 6),
    "USDT": TokenInfo("USDT", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", 6),
    "JUP": TokenInfo("JUP", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", 6),
    "BONK": TokenInfo("BONK", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", 5),
    "WIF": TokenInfo("WIF", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", 6),
    "TRUMP": TokenInfo("TRUMP", "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN", 6),
    "POPCAT": TokenInfo("POPCAT", "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr", 9),
    "MEW": TokenInfo("MEW", "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP5", 5),
}


def get_token(symbol: str) -> TokenInfo:
    """Get token info by symbol."""
    if symbol not in TOKENS:
        raise ValueError(f"Unknown token: {symbol}")
    return TOKENS[symbol]


def parse_pair(pair: str) -> Tuple[TokenInfo, TokenInfo]:
    """Parse pair string into base and quote tokens."""
    base_sym, quote_sym = pair.split("/")
    return get_token(base_sym), get_token(quote_sym)


# =============================================================================
# JUPITER ADAPTER
# =============================================================================

class JupiterAdapter:
    """
    Jupiter DEX adapter with execution-grade safety.
    
    Key safety features:
    1. Single-flight: One order per symbol/side at a time
    2. State machine: FLAT -> ENTERING -> OPEN -> EXITING -> FLAT
    3. Cooldowns: After N failures, pause trading for that pair
    4. Exit priority: Exits always processed before entries
    5. Reconciliation: Uses SolanaClient's confirm-or-reconcile
    """
    
    def __init__(
        self,
        config: JupiterConfig,
        solana_client: SolanaClient,
    ):
        self.config = config
        self.solana = solana_client
        
        self._client: Optional[httpx.AsyncClient] = None
        self._pair_states: Dict[str, PairState] = {}
        self._exit_only_mode: bool = False  # Global exit-only mode
        
        logger.info(f"JUPITER_ADAPTER | init | slippage={config.slippage_bps}bps")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with IPv4 transport."""
        if self._client is None or self._client.is_closed:
            # Try to use IPv4 transport if network_bootstrap is available
            try:
                from network_bootstrap import create_ipv4_transport
                transport = create_ipv4_transport()
                self._client = httpx.AsyncClient(
                    timeout=self.config.http_timeout,
                    transport=transport,
                )
            except ImportError:
                self._client = httpx.AsyncClient(timeout=self.config.http_timeout)
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    def _get_pair_state(self, pair: str) -> PairState:
        """Get or create pair state."""
        if pair not in self._pair_states:
            self._pair_states[pair] = PairState(pair=pair)
        return self._pair_states[pair]
    
    # =========================================================================
    # GATING CHECKS (from ChatGPT analysis)
    # =========================================================================
    
    def can_enter(self, pair: str) -> Tuple[bool, Optional[str]]:
        """
        Check if entry is allowed for a pair.
        
        CRITICAL: Single-flight protection.
        If inflight_buy_signature is set (from UNKNOWN outcome), block new entry.
        """
        state = self._get_pair_state(pair)
        
        # Check global exit-only mode
        if self._exit_only_mode:
            return False, "exit_only_mode"
        
        # Can't enter if position exists
        if state.position_state == PositionState.OPEN:
            return False, "position_open"
        
        if state.position_state == PositionState.EXIT_ONLY:
            return False, "pair_exit_only"
        
        # CRITICAL: If there's an inflight buy signature, block
        # This is set when outcome=UNKNOWN and preserved until resolved
        if state.inflight_buy_signature is not None:
            return False, f"inflight_buy:{state.inflight_buy_signature[:16] if len(state.inflight_buy_signature or '') > 16 else state.inflight_buy_signature}..."
        
        # Check BUY cooldown
        if state.is_buy_in_cooldown():
            return False, f"buy_cooldown_until:{state.buy_cooldown_until.isoformat()}"
        
        return True, None
    
    def can_exit(self, pair: str) -> Tuple[bool, Optional[str]]:
        """
        Check if exit is allowed for a pair.
        
        CRITICAL: Single-flight protection for exits.
        If inflight_sell_signature is set (from UNKNOWN outcome), block new exit.
        This prevents double-selling when first tx may still land.
        """
        state = self._get_pair_state(pair)
        
        # Can't exit if no position
        if state.position_state == PositionState.FLAT:
            return False, "no_position"
        
        if state.position_state == PositionState.ENTERING_INFLIGHT:
            return False, "still_entering"
        
        # CRITICAL: If there's an inflight sell signature, block
        # This is set when outcome=UNKNOWN and preserved until resolved
        if state.inflight_sell_signature is not None:
            return False, f"inflight_sell:{state.inflight_sell_signature[:16] if len(state.inflight_sell_signature or '') > 16 else state.inflight_sell_signature}..."
        
        # Check SELL cooldown
        if state.is_sell_in_cooldown():
            return False, f"sell_cooldown_until:{state.sell_cooldown_until.isoformat()}"
        
        return True, None
    
    # =========================================================================
    # QUOTE API
    # =========================================================================
    
    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: Optional[int] = None,
    ) -> Optional[dict]:
        """
        Get quote from Jupiter with retry logic.
        
        Args:
            input_mint: Input token mint
            output_mint: Output token mint
            amount: Amount in smallest unit
            slippage_bps: Slippage in basis points (uses config default if None)
            
        Returns:
            Quote response or None on failure
        """
        if slippage_bps is None:
            slippage_bps = self.config.slippage_bps
        
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": str(slippage_bps),
        }
        
        client = await self._get_client()
        
        for attempt in range(self.config.max_quote_retries):
            try:
                resp = await client.get(f"{self.config.base_url}/quote", params=params)
                
                if resp.status_code == 429:
                    logger.warning(f"JUPITER_QUOTE | rate_limited | attempt={attempt + 1}")
                    if attempt < self.config.max_quote_retries - 1:
                        await asyncio.sleep(self.config.retry_delay_base * (2 ** attempt))
                        continue
                    return None
                
                if resp.status_code >= 500:
                    logger.warning(f"JUPITER_QUOTE | server_error | status={resp.status_code}")
                    if attempt < self.config.max_quote_retries - 1:
                        await asyncio.sleep(self.config.retry_delay_base * (2 ** attempt))
                        continue
                    return None
                
                resp.raise_for_status()
                data = resp.json()
                
                # Validate response
                required = ["inAmount", "outAmount", "routePlan"]
                if not all(f in data for f in required):
                    logger.error(f"JUPITER_QUOTE | invalid_response | missing fields")
                    return None
                
                logger.debug(
                    f"JUPITER_QUOTE | success | in={data['inAmount']} out={data['outAmount']}"
                )
                return data
                
            except httpx.TimeoutException:
                logger.warning(f"JUPITER_QUOTE | timeout | attempt={attempt + 1}")
                if attempt < self.config.max_quote_retries - 1:
                    await asyncio.sleep(self.config.retry_delay_base)
                    continue
                return None
                
            except Exception as e:
                logger.error(f"JUPITER_QUOTE | error | {type(e).__name__}: {e}")
                return None
        
        return None
    
    async def get_swap_transaction(
        self,
        quote_response: dict,
        user_pubkey: str,
        priority_fee_lamports: Optional[int] = None,
    ) -> Optional[bytes]:
        """
        Get swap transaction from Jupiter.
        
        Args:
            quote_response: Quote from get_quote()
            user_pubkey: User's wallet public key
            priority_fee_lamports: Priority fee in lamports (None = auto)
            
        Returns:
            Transaction bytes or None on failure
        """
        payload = {
            "quoteResponse": quote_response,
            "userPublicKey": user_pubkey,
            "wrapAndUnwrapSol": True,
            "prioritizationFeeLamports": priority_fee_lamports if priority_fee_lamports else "auto",
        }
        
        client = await self._get_client()
        
        try:
            resp = await client.post(f"{self.config.base_url}/swap", json=payload)
            
            if resp.status_code == 429:
                logger.warning("JUPITER_SWAP | rate_limited")
                return None
            
            if resp.status_code >= 500:
                logger.warning(f"JUPITER_SWAP | server_error | status={resp.status_code}")
                return None
            
            resp.raise_for_status()
            data = resp.json()
            
            if "swapTransaction" not in data:
                logger.error("JUPITER_SWAP | missing swapTransaction")
                return None
            
            tx_bytes = base64.b64decode(data["swapTransaction"])
            fee_info = f"priority={priority_fee_lamports}" if priority_fee_lamports else "priority=auto"
            logger.debug(f"JUPITER_SWAP | success | size={len(tx_bytes)} bytes | {fee_info}")
            return tx_bytes
            
        except httpx.TimeoutException:
            logger.warning("JUPITER_SWAP | timeout")
            return None
        except Exception as e:
            logger.error(f"JUPITER_SWAP | error | {type(e).__name__}: {e}")
            return None
    
    # =========================================================================
    # EXECUTE WITH LADDER (Phase 1 - deterministic attempt ladder)
    # =========================================================================
    
    async def execute_with_ladder(
        self,
        pair: str,
        side: str,
        input_mint: str,
        output_mint: str,
        amount_in: int,
        token_mint_for_reconcile: str,
        expected_delta: float,
    ) -> TradeResult:
        """
        Execute trade with deterministic attempt ladder.
        
        CRITICAL SEMANTICS:
        - SUCCESS: advance state, clear inflight
        - FAILURE: consume attempt, maybe retry, maybe cooldown
        - UNKNOWN: do NOT consume attempt, do NOT advance state, preserve inflight
        """
        state = self._get_pair_state(pair)
        
        attempt = 1
        while attempt <= self.config.max_attempts:
            slippage_bps = self.config.get_slippage_for_attempt(attempt)
            priority_fee = self.config.get_priority_fee_for_attempt(attempt)
            
            logger.info(
                f"LADDER_ATTEMPT | {pair} | {side} | attempt={attempt}/{self.config.max_attempts} | "
                f"slippage={slippage_bps}bps | priority={priority_fee or 'auto'}"
            )
            
            # Get quote
            quote = await self.get_quote(
                input_mint=input_mint,
                output_mint=output_mint,
                amount=amount_in,
                slippage_bps=slippage_bps,
            )
            
            if quote is None:
                logger.warning(f"LADDER_QUOTE_FAILED | {pair} | {side} | attempt={attempt}")
                attempt += 1  # Quote failure is definitive, consume attempt
                if attempt <= self.config.max_attempts:
                    await asyncio.sleep(self.config.attempt_delay_seconds)
                continue
            
            # Check price impact
            price_impact = float(quote.get("priceImpactPct", 0)) * 100
            if price_impact > self.config.max_price_impact_bps:
                logger.warning(
                    f"LADDER_PRICE_IMPACT | {pair} | {side} | impact={price_impact:.0f}bps"
                )
                return TradeResult(
                    outcome="FAILURE",
                    pair=pair,
                    side=side,
                    error=f"price_impact:{price_impact:.0f}bps",
                    attempt_number=attempt,
                    slippage_bps_used=slippage_bps,
                    price_impact_bps=int(price_impact),
                )
            
            # Get swap transaction
            tx_bytes = await self.get_swap_transaction(
                quote, 
                self.solana.pubkey,
                priority_fee_lamports=priority_fee,
            )
            
            if tx_bytes is None:
                logger.warning(f"LADDER_SWAP_FAILED | {pair} | {side} | attempt={attempt}")
                attempt += 1  # Swap build failure is definitive
                if attempt <= self.config.max_attempts:
                    await asyncio.sleep(self.config.attempt_delay_seconds)
                continue
            
            # Set inflight BEFORE execute (we have tx, about to submit)
            if side == "BUY":
                state.inflight_buy_signature = "pending"
            else:
                state.inflight_sell_signature = "pending"
            
            # Execute with confirm-or-reconcile
            tx_result = await self.solana.execute_with_reconcile(
                tx_bytes=tx_bytes,
                pair=pair,
                side=side,
                token_mint=token_mint_for_reconcile,
                expected_delta=expected_delta,
            )
            
            # Update inflight with actual signature
            if tx_result.signature:
                if side == "BUY":
                    state.inflight_buy_signature = tx_result.signature
                else:
                    state.inflight_sell_signature = tx_result.signature
            
            # Classify outcome into 3 states
            if tx_result.is_success:
                # SUCCESS - confirmed or reconciled_success
                logger.info(f"LADDER_SUCCESS | {pair} | {side} | attempt={attempt}")
                return TradeResult(
                    outcome="SUCCESS",
                    pair=pair,
                    side=side,
                    signature=tx_result.signature,
                    tx_result=tx_result,
                    attempt_number=attempt,
                    slippage_bps_used=slippage_bps,
                    priority_fee_used=priority_fee,
                    quote_in_amount=int(quote["inAmount"]),
                    quote_out_amount=int(quote["outAmount"]),
                )
            
            elif tx_result.outcome == TxOutcome.LANDED_UNCONFIRMED:
                # Reconciliation shows tx landed - treat as SUCCESS
                logger.warning(f"LADDER_LANDED_UNCONFIRMED | {pair} | {side} | treating as SUCCESS")
                return TradeResult(
                    outcome="SUCCESS",
                    pair=pair,
                    side=side,
                    signature=tx_result.signature,
                    tx_result=tx_result,
                    attempt_number=attempt,
                    slippage_bps_used=slippage_bps,
                    priority_fee_used=priority_fee,
                )
            
            elif tx_result.is_safe_to_retry:
                # FAILURE - definitive, can retry
                logger.warning(f"LADDER_FAILURE | {pair} | {side} | attempt={attempt} | retrying")
                # Clear inflight since this attempt definitively failed
                if side == "BUY":
                    state.inflight_buy_signature = None
                else:
                    state.inflight_sell_signature = None
                attempt += 1  # Consume attempt
                if attempt <= self.config.max_attempts:
                    await asyncio.sleep(self.config.attempt_delay_seconds)
                continue
            
            else:
                # UNKNOWN - timeout, RPC ambiguity
                # DO NOT consume attempt, DO NOT clear inflight
                logger.error(
                    f"LADDER_UNKNOWN | {pair} | {side} | attempt={attempt} | "
                    f"outcome={tx_result.outcome.value} | PRESERVING INFLIGHT"
                )
                return TradeResult(
                    outcome="UNKNOWN",
                    pair=pair,
                    side=side,
                    signature=tx_result.signature,
                    error=f"unknown_outcome:{tx_result.outcome.value}",
                    tx_result=tx_result,
                    attempt_number=attempt,
                    slippage_bps_used=slippage_bps,
                )
        
        # All attempts exhausted (only reached via FAILURE path)
        if side == "BUY":
            state.record_buy_failure(
                self.config.failure_threshold,
                self.config.failure_cooldown_seconds,
            )
            state.inflight_buy_signature = None
        else:
            state.record_sell_failure(
                self.config.failure_threshold,
                self.config.failure_cooldown_seconds,
            )
            state.inflight_sell_signature = None
        
        return TradeResult(
            outcome="FAILURE",
            pair=pair,
            side=side,
            error="all_attempts_exhausted",
            attempt_number=self.config.max_attempts,
            slippage_bps_used=self.config.get_slippage_for_attempt(self.config.max_attempts),
        )
    
    # =========================================================================
    # TRADE EXECUTION WITH SAFETY
    # =========================================================================
    
    async def enter(
        self,
        pair: str,
        price: float,
        notional: float,
    ) -> TradeResult:
        """
        Execute entry trade.
        
        CRITICAL SEMANTICS:
        - State does NOT transition on submit
        - State transitions ONLY after execute_with_reconcile returns
        - SUCCESS -> FLAT to OPEN
        - FAILURE -> stays FLAT
        - UNKNOWN -> stays FLAT, inflight preserved, next tick re-checks
        """
        state = self._get_pair_state(pair)
        
        # Check gating
        can, reason = self.can_enter(pair)
        if not can:
            logger.info(f"ENTRY_BLOCKED | {pair} | {reason}")
            return TradeResult(
                outcome="FAILURE",
                pair=pair,
                side="BUY",
                error=reason,
            )
        
        # Parse tokens
        base_token, quote_token = parse_pair(pair)
        size_base = notional / price
        amount_in = int(notional * (10 ** quote_token.decimals))
        
        # NO STATE TRANSITION HERE - state stays FLAT until resolution
        logger.info(f"ENTRY_SUBMITTING | {pair} | state remains FLAT until confirmed")
        
        # Execute with ladder
        result = await self.execute_with_ladder(
            pair=pair,
            side="BUY",
            input_mint=quote_token.mint,
            output_mint=base_token.mint,
            amount_in=amount_in,
            token_mint_for_reconcile=base_token.mint,
            expected_delta=size_base,
        )
        
        # State transitions ONLY here, based on outcome
        if result.outcome == "SUCCESS":
            # Confirmed or reconciled_success -> advance to OPEN
            state.position_state = PositionState.OPEN
            state.entry_price = price
            state.entry_time = datetime.now(timezone.utc)
            state.size_base = size_base
            state.last_entry_time = datetime.now(timezone.utc)
            state.reset_buy_failures()
            # Clear inflight on SUCCESS
            state.inflight_buy_signature = None
            state.inflight_buy_intent_id = None
            
            result.price = price
            result.size = size_base
            
            logger.info(f"STATE_TRANSITION | {pair} | FLAT -> OPEN | ENTRY_SUCCESS")
            
        elif result.outcome == "FAILURE":
            # Definitive failure -> stays FLAT
            # inflight already cleared in execute_with_ladder
            logger.info(f"STATE_NO_CHANGE | {pair} | stays FLAT | ENTRY_FAILURE")
            
        elif result.outcome == "UNKNOWN":
            # UNKNOWN -> NO state change, inflight preserved
            # The tx may still land - cannot assume FLAT or OPEN
            logger.warning(
                f"STATE_NO_CHANGE | {pair} | stays FLAT | ENTRY_UNKNOWN | "
                f"inflight_sig={state.inflight_buy_signature} | next tick will re-check"
            )
            # DO NOT clear inflight - single-flight must block until resolved
        
        return result
    
    async def exit(
        self,
        pair: str,
        price: float,
        reason: str,
    ) -> TradeResult:
        """
        Execute exit trade.
        
        CRITICAL SEMANTICS:
        - State does NOT transition on submit
        - State transitions ONLY after execute_with_reconcile returns
        - SUCCESS -> OPEN to FLAT (position closed)
        - FAILURE -> stays OPEN (still have position)
        - UNKNOWN -> stays OPEN, inflight preserved, BLOCKS new exit (single-flight)
        """
        state = self._get_pair_state(pair)
        
        # Single-flight check - blocks if exit already inflight
        can, gate_reason = self.can_exit(pair)
        if not can:
            logger.info(f"EXIT_BLOCKED | {pair} | {gate_reason}")
            return TradeResult(
                outcome="FAILURE",
                pair=pair,
                side="SELL",
                error=gate_reason,
            )
        
        # Parse tokens
        base_token, quote_token = parse_pair(pair)
        size_base = state.size_base or 0
        amount_in = int(size_base * (10 ** base_token.decimals))
        
        # Calculate PnL
        entry_price = state.entry_price or price
        pnl_pct = ((price - entry_price) / entry_price) * 100
        
        # NO STATE TRANSITION HERE - state stays OPEN until resolution
        logger.info(f"EXIT_SUBMITTING | {pair} | state remains OPEN until confirmed")
        
        # Execute with ladder
        result = await self.execute_with_ladder(
            pair=pair,
            side="SELL",
            input_mint=base_token.mint,
            output_mint=quote_token.mint,
            amount_in=amount_in,
            token_mint_for_reconcile=base_token.mint,
            expected_delta=-size_base,
        )
        
        # State transitions ONLY here, based on outcome
        if result.outcome == "SUCCESS":
            # Confirmed or reconciled_success -> position closed
            state.position_state = PositionState.FLAT
            state.entry_price = None
            state.entry_time = None
            state.size_base = None
            state.last_exit_time = datetime.now(timezone.utc)
            state.reset_sell_failures()
            # Clear inflight on SUCCESS
            state.inflight_sell_signature = None
            state.inflight_sell_intent_id = None
            
            result.price = price
            result.size = size_base
            
            logger.info(
                f"STATE_TRANSITION | {pair} | OPEN -> FLAT | EXIT_SUCCESS | "
                f"pnl={pnl_pct:.2f}% | reason={reason}"
            )
            
        elif result.outcome == "FAILURE":
            # Definitive failure -> still have position
            # inflight already cleared in execute_with_ladder
            if state.sell_consecutive_failures >= self.config.failure_threshold:
                state.position_state = PositionState.EXIT_ONLY
                logger.warning(f"STATE_TRANSITION | {pair} | OPEN -> EXIT_ONLY | too many failures")
            else:
                logger.info(f"STATE_NO_CHANGE | {pair} | stays OPEN | EXIT_FAILURE")
            
        elif result.outcome == "UNKNOWN":
            # UNKNOWN -> NO state change, inflight PRESERVED
            # The sell tx may still land - CANNOT fire another sell
            # This is the critical single-flight protection
            logger.warning(
                f"STATE_NO_CHANGE | {pair} | stays OPEN | EXIT_UNKNOWN | "
                f"inflight_sig={state.inflight_sell_signature} | "
                f"BLOCKING new exits until resolved"
            )
            # DO NOT clear inflight_sell_signature
            # can_exit() will return False while this is set
        
        return result
    
    # =========================================================================
    # INFLIGHT RESOLUTION (for UNKNOWN outcomes)
    # =========================================================================
    
    async def resolve_unknown_exits(self) -> List[Tuple[str, str]]:
        """
        Resolve UNKNOWN exit outcomes from previous ticks.
        
        Called every tick to re-check signatures that were left pending.
        If inflight_sell_signature is set, we poll status and reconcile.
        
        Returns:
            List of (pair, resolution) where resolution is "SUCCESS" or "FAILURE"
        """
        resolutions = []
        
        for pair, state in self._pair_states.items():
            sig = state.inflight_sell_signature
            if sig is None or sig == "pending":
                continue
            
            logger.info(f"RESOLVE_UNKNOWN | {pair} | checking sig={sig[:16]}...")
            
            # Check signature status
            status = await self.solana.get_signature_status(sig)
            
            if status is None:
                # Still not found - keep waiting
                logger.debug(f"RESOLVE_UNKNOWN | {pair} | not found yet")
                continue
            
            if status.get("confirmed") or status.get("finalized"):
                # SUCCESS - the exit landed
                state.position_state = PositionState.FLAT
                state.entry_price = None
                state.entry_time = None
                state.size_base = None
                state.last_exit_time = datetime.now(timezone.utc)
                state.inflight_sell_signature = None
                state.reset_sell_failures()
                
                logger.info(f"RESOLVE_UNKNOWN | {pair} | EXIT_SUCCESS (late confirm) | sig={sig[:16]}...")
                resolutions.append((pair, "SUCCESS"))
                
            elif status.get("error"):
                # FAILURE - exit did not land, can retry
                state.inflight_sell_signature = None
                
                logger.info(f"RESOLVE_UNKNOWN | {pair} | EXIT_FAILURE | error={status['error']}")
                resolutions.append((pair, "FAILURE"))
        
        return resolutions
    
    async def resolve_unknown_entries(self) -> List[Tuple[str, str]]:
        """
        Resolve UNKNOWN entry outcomes from previous ticks.
        """
        resolutions = []
        
        for pair, state in self._pair_states.items():
            sig = state.inflight_buy_signature
            if sig is None or sig == "pending":
                continue
            
            logger.info(f"RESOLVE_UNKNOWN | {pair} | checking sig={sig[:16]}...")
            
            status = await self.solana.get_signature_status(sig)
            
            if status is None:
                continue
            
            if status.get("confirmed") or status.get("finalized"):
                # SUCCESS - entry landed, but we don't have price/size info
                # This is a problem - we need to reconcile from chain
                state.position_state = PositionState.OPEN
                state.inflight_buy_signature = None
                # Note: entry_price and size_base are unknown here
                # Would need balance reconciliation to determine actual position
                
                logger.warning(
                    f"RESOLVE_UNKNOWN | {pair} | ENTRY_SUCCESS (late confirm) | "
                    f"WARNING: position size unknown, needs balance check"
                )
                resolutions.append((pair, "SUCCESS"))
                
            elif status.get("error"):
                state.inflight_buy_signature = None
                logger.info(f"RESOLVE_UNKNOWN | {pair} | ENTRY_FAILURE")
                resolutions.append((pair, "FAILURE"))
        
        return resolutions
    
    # =========================================================================
    # SHUTDOWN FLATTENING
    # =========================================================================
    
    async def flatten_all(
        self, 
        price_oracle=None,
        keep_sol_reserve: bool = True,
    ) -> List[TradeResult]:
        """
        Flatten all positions for shutdown.
        
        Order:
        1. Stop new entries (exit_only_mode)
        2. Resolve any UNKNOWN outcomes first
        3. Exit all non-SOL positions
        4. Exit SOL last, keeping 0.1 SOL reserve
        """
        logger.warning("=" * 60)
        logger.warning("FLATTEN_ALL | SHUTDOWN INITIATED")
        logger.warning("=" * 60)
        
        # Step 1: Stop new entries
        self._exit_only_mode = True
        logger.warning("FLATTEN_ALL | exit_only_mode=True")
        
        # Step 2: Resolve any UNKNOWN outcomes
        await self.resolve_unknown_entries()
        await self.resolve_unknown_exits()
        
        results = []
        sol_position = None
        
        # Step 3: Exit all non-SOL positions
        for pair, state in list(self._pair_states.items()):
            if state.position_state not in (PositionState.OPEN, PositionState.EXIT_ONLY):
                continue
            
            # Skip if inflight (UNKNOWN not yet resolved)
            if state.inflight_sell_signature:
                logger.warning(f"FLATTEN_ALL | {pair} | skipping, exit still inflight")
                continue
            
            if pair.startswith("SOL/"):
                sol_position = (pair, state)
                continue
            
            price = state.entry_price or 0
            if price_oracle and hasattr(price_oracle, 'get_cached_price'):
                cached = price_oracle.get_cached_price(pair)
                if cached:
                    price = cached.price
            
            if price > 0:
                result = await self.exit(pair, price, reason="shutdown")
                results.append(result)
        
        # Step 4: Exit SOL last with reserve
        if sol_position:
            pair, state = sol_position
            sol_balance = await self.solana.get_sol_balance()
            
            if keep_sol_reserve and sol_balance:
                reserve = self.config.min_sol_reserve
                if sol_balance <= reserve:
                    logger.warning(f"FLATTEN_ALL | SOL <= reserve, not selling")
                else:
                    price = state.entry_price or 0
                    if price > 0:
                        result = await self.exit(pair, price, reason="shutdown_sol")
                        results.append(result)
        
        success_count = sum(1 for r in results if r.outcome == "SUCCESS")
        logger.warning(f"FLATTEN_ALL | COMPLETE | {success_count}/{len(results)} succeeded")
        
        return results
    
    async def process_exits_first(
        self,
        pairs: List[str],
        price_oracle,
        check_exit_fn,
    ) -> List[TradeResult]:
        """
        Process exits before entries (Phase 1 - exit-first rule).
        
        If inventory exists, process SELL intents before any BUY intents.
        If strategy signals buy while position is non-flat and exit pending, ignore buy.
        
        Args:
            pairs: List of pairs to check
            price_oracle: Price oracle for current prices
            check_exit_fn: Function(pair, price) -> Optional[str] returning exit reason
            
        Returns:
            List of exit TradeResults
        """
        results = []
        
        for pair in pairs:
            state = self._get_pair_state(pair)
            
            # Only check exits for open positions
            if state.position_state not in (PositionState.OPEN, PositionState.EXIT_ONLY):
                continue
            
            # Get current price
            price_point = await price_oracle.get_price(pair) if price_oracle else None
            if not price_point:
                continue
            
            price = price_point.price if hasattr(price_point, 'price') else price_point
            
            # Check if we should exit
            exit_reason = check_exit_fn(pair, price)
            
            if exit_reason:
                logger.info(f"EXIT_FIRST | {pair} | reason={exit_reason}")
                result = await self.exit(pair, price, reason=exit_reason)
                results.append(result)
        
        return results
    
    # =========================================================================
    # STATE QUERIES
    # =========================================================================
    
    def get_position(self, pair: str) -> Optional[dict]:
        """Get current position for a pair."""
        state = self._get_pair_state(pair)
        
        if state.position_state not in (PositionState.OPEN, PositionState.EXIT_ONLY):
            return None
        
        return {
            "pair": pair,
            "entry_price": state.entry_price,
            "entry_time": state.entry_time.isoformat() if state.entry_time else None,
            "size_base": state.size_base,
            "state": state.position_state.value,
        }
    
    def get_all_positions(self) -> List[dict]:
        """Get all open positions."""
        positions = []
        for pair in self._pair_states:
            pos = self.get_position(pair)
            if pos:
                positions.append(pos)
        return positions
    
    def is_exit_only_mode(self) -> bool:
        """Check if adapter is in global exit-only mode."""
        return self._exit_only_mode
    
    def set_exit_only_mode(self, enabled: bool) -> None:
        """Set global exit-only mode."""
        self._exit_only_mode = enabled
        logger.warning(f"EXIT_ONLY_MODE | {'enabled' if enabled else 'disabled'}")
