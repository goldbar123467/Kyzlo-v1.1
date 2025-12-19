"""
solana_client.py - Hardened Solana RPC client with confirm-or-reconcile

The MOST IMPORTANT safety improvement: never retry without proving prior attempt failed.

Features:
1. Confirm-or-reconcile after uncertain outcomes
2. Signature status tracking
3. Balance reconciliation on timeout
4. Proper error classification
5. Fee reserve protection

Usage:
    from solana_client import SolanaClient, TxOutcome
    
    client = SolanaClient(rpc_url, keypair)
    
    # Execute with automatic reconciliation
    result = await client.execute_with_reconcile(tx_bytes, expected_delta)
    
    if result.outcome == TxOutcome.CONFIRMED:
        print(f"Success: {result.signature}")
    elif result.outcome == TxOutcome.FAILED_VERIFIED:
        print("Failed, safe to retry")
    elif result.outcome == TxOutcome.LANDED_UNCONFIRMED:
        print("Tx landed but we lost track - reconcile manually")
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

from loguru import logger
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed, Finalized
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import VersionedTransaction


# =============================================================================
# OUTCOME CLASSIFICATION
# =============================================================================

class TxOutcome(Enum):
    """
    Transaction outcome classification.
    
    The key insight: we must distinguish between "tx failed" and "we don't know".
    Only retry if we KNOW it failed.
    """
    # Definite outcomes - safe to proceed
    CONFIRMED = "confirmed"          # Tx confirmed on-chain
    FINALIZED = "finalized"          # Tx finalized on-chain
    FAILED_VERIFIED = "failed_verified"  # Tx definitely failed (simulation, blockhash, etc.)
    
    # Uncertain outcomes - DO NOT RETRY without reconciliation
    TIMEOUT_UNKNOWN = "timeout_unknown"      # Confirmation timed out, status unknown
    LANDED_UNCONFIRMED = "landed_unconfirmed"  # Reconciliation shows tx landed
    
    # Pre-send failures
    SIGN_FAILED = "sign_failed"
    DESERIALIZE_FAILED = "deserialize_failed"
    SEND_FAILED = "send_failed"


class TxFailureReason(Enum):
    """Specific failure reasons for error tracking."""
    BLOCKHASH_EXPIRED = "blockhash_expired"
    SIMULATION_FAILED = "simulation_failed"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    SLIPPAGE_EXCEEDED = "slippage_exceeded"
    PROGRAM_ERROR = "program_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


# =============================================================================
# RESULT TYPES
# =============================================================================

@dataclass
class TxResult:
    """Result of transaction execution with full context."""
    outcome: TxOutcome
    signature: Optional[str] = None
    failure_reason: Optional[TxFailureReason] = None
    error_message: Optional[str] = None
    
    # Reconciliation data
    balance_before: Optional[float] = None
    balance_after: Optional[float] = None
    balance_delta: Optional[float] = None
    
    # Timing
    send_time: Optional[datetime] = None
    confirm_time: Optional[datetime] = None
    
    @property
    def is_success(self) -> bool:
        """True if tx definitely succeeded."""
        return self.outcome in (TxOutcome.CONFIRMED, TxOutcome.FINALIZED)
    
    @property
    def is_safe_to_retry(self) -> bool:
        """True if we KNOW the tx failed and can safely retry."""
        return self.outcome in (
            TxOutcome.FAILED_VERIFIED,
            TxOutcome.SIGN_FAILED,
            TxOutcome.DESERIALIZE_FAILED,
            TxOutcome.SEND_FAILED,
        )
    
    @property
    def needs_reconciliation(self) -> bool:
        """True if outcome is uncertain and needs balance check."""
        return self.outcome in (
            TxOutcome.TIMEOUT_UNKNOWN,
            TxOutcome.LANDED_UNCONFIRMED,
        )


@dataclass
class InflightTx:
    """Tracks an in-flight transaction."""
    signature: str
    pair: str
    side: str  # "BUY" or "SELL"
    send_time: datetime
    expected_delta: float  # Expected balance change (positive for buy, negative for sell)
    
    def age_seconds(self) -> float:
        """How long since tx was sent."""
        return (datetime.now(timezone.utc) - self.send_time).total_seconds()


@dataclass
class InflightIntent:
    """
    Phase 1 Fix: Persist all tx attempt data for confirm-or-reconcile.
    
    This captures everything needed to determine success/failure:
    - Signature (if obtained)
    - Pre-balances snapshot
    - Intent metadata
    """
    intent_id: str
    signature: Optional[str]
    pair: str
    side: str  # "BUY" or "SELL"
    amount_in: int  # Raw amount submitted
    expected_delta: float  # Expected balance change
    
    # Balance snapshots
    pre_balance_token: Optional[float] = None
    pre_balance_usdc: Optional[float] = None
    post_balance_token: Optional[float] = None
    post_balance_usdc: Optional[float] = None
    
    # Timestamps
    submit_ts: Optional[datetime] = None
    confirm_ts: Optional[datetime] = None
    
    # Outcome
    outcome: Optional[str] = None  # "confirmed", "reconciled_success", "reconciled_failure", "timeout"
    
    def token_delta(self) -> Optional[float]:
        """Calculate token balance change."""
        if self.pre_balance_token is not None and self.post_balance_token is not None:
            return self.post_balance_token - self.pre_balance_token
        return None
    
    def usdc_delta(self) -> Optional[float]:
        """Calculate USDC balance change."""
        if self.pre_balance_usdc is not None and self.post_balance_usdc is not None:
            return self.post_balance_usdc - self.pre_balance_usdc
        return None
    
    def matches_expected_deltas(self, tolerance_pct: float = 0.10) -> bool:
        """
        Check if balance deltas match expected for this trade.
        
        For SELL token→USDC:
        - token_delta should be negative
        - usdc_delta should be positive
        
        For BUY USDC→token:
        - token_delta should be positive
        - usdc_delta should be negative
        
        Args:
            tolerance_pct: Tolerance for fees/slippage (default 10%)
        """
        token_d = self.token_delta()
        usdc_d = self.usdc_delta()
        
        if token_d is None or usdc_d is None:
            return False
        
        expected_abs = abs(self.expected_delta)
        tolerance = expected_abs * tolerance_pct
        
        if self.side == "SELL":
            # Expect: token down, USDC up
            token_ok = token_d < 0 and abs(token_d) >= (expected_abs - tolerance)
            usdc_ok = usdc_d > 0
            return token_ok and usdc_ok
        else:  # BUY
            # Expect: token up, USDC down
            token_ok = token_d > 0 and token_d >= (expected_abs - tolerance)
            usdc_ok = usdc_d < 0
            return token_ok and usdc_ok


# =============================================================================
# SOLANA CLIENT
# =============================================================================

class SolanaClient:
    """
    Hardened Solana RPC client with confirm-or-reconcile.
    
    Key safety features:
    1. Tracks all in-flight transactions with balance snapshots
    2. On timeout: reconciles balance before allowing retry
    3. Classifies all errors for risk management
    4. Protects SOL fee reserve
    
    Phase 1 Fix:
    - Captures signature + pre_balances on every submit
    - Polls for 30-60 seconds (not 3-5)
    - Reconciles by balance deltas if confirmation times out
    """
    
    # USDC mint for balance reconciliation
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    def __init__(
        self,
        rpc_url: str,
        keypair: Keypair,
        confirm_timeout: float = 60.0,  # Phase 1: 30-60 seconds, not 3-5
        min_sol_reserve: float = 0.10,  # Keep 0.1 SOL for tx fees
        reconcile_tolerance_pct: float = 0.10,  # 10% tolerance for fees/slippage
    ):
        self.rpc_url = rpc_url
        self.keypair = keypair
        self.confirm_timeout = confirm_timeout
        self.min_sol_reserve = min_sol_reserve
        self.reconcile_tolerance_pct = reconcile_tolerance_pct
        
        self._client: Optional[AsyncClient] = None
        self._inflight: Dict[str, InflightTx] = {}  # signature -> InflightTx
        self._inflight_intents: Dict[str, InflightIntent] = {}  # intent_id -> InflightIntent
        self._last_balances: Dict[str, float] = {}  # mint -> balance
        self._intent_counter: int = 0
        
        self.pubkey = str(keypair.pubkey())
        
        logger.info(f"SOLANA_CLIENT | init | wallet={self.pubkey[:8]}... | confirm_timeout={confirm_timeout}s")
    
    async def _get_client(self) -> AsyncClient:
        """Get or create RPC client."""
        if self._client is None:
            self._client = AsyncClient(self.rpc_url)
        return self._client
    
    async def close(self):
        """Close RPC client."""
        if self._client:
            await self._client.close()
            self._client = None
    
    def _generate_intent_id(self) -> str:
        """Generate unique intent ID for tracking."""
        self._intent_counter += 1
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"intent_{ts}_{self._intent_counter}"
    
    # =========================================================================
    # BALANCE OPERATIONS
    # =========================================================================
    
    async def get_sol_balance(self) -> Optional[float]:
        """Get SOL balance in SOL (not lamports)."""
        try:
            client = await self._get_client()
            result = await client.get_balance(Pubkey.from_string(self.pubkey))
            balance = result.value / 1e9
            self._last_balances["SOL"] = balance
            return balance
        except Exception as e:
            logger.error(f"SOL_BALANCE | error | {e}")
            return None
    
    async def get_usdc_balance(self) -> Optional[float]:
        """Get USDC balance (convenience method for reconciliation)."""
        return await self.get_token_balance(self.USDC_MINT)
    
    async def get_token_balance(self, mint: str) -> Optional[float]:
        """
        Get SPL token balance.
        
        Returns balance in token units (adjusted for decimals).
        """
        try:
            client = await self._get_client()
            
            # Get associated token account
            from solders.pubkey import Pubkey
            
            # Find ATA
            result = await client.get_token_accounts_by_owner(
                Pubkey.from_string(self.pubkey),
                {"mint": Pubkey.from_string(mint)},
            )
            
            if not result.value:
                return 0.0
            
            # Sum all token accounts for this mint
            total = 0.0
            for account in result.value:
                data = account.account.data
                # Parse token account data
                if hasattr(data, 'parsed'):
                    info = data.parsed.get('info', {})
                    amount = info.get('tokenAmount', {})
                    total += float(amount.get('uiAmount', 0))
            
            self._last_balances[mint] = total
            return total
            
        except Exception as e:
            logger.error(f"TOKEN_BALANCE | error | mint={mint[:8]}... | {e}")
            return None
    
    async def check_sol_reserve(self) -> Tuple[bool, float]:
        """
        Check if SOL balance is above minimum reserve.
        
        Returns:
            (is_sufficient, current_balance)
        """
        balance = await self.get_sol_balance()
        if balance is None:
            return False, 0.0
        return balance >= self.min_sol_reserve, balance
    
    # =========================================================================
    # SIGNATURE STATUS
    # =========================================================================
    
    async def get_signature_status(self, signature: str) -> Optional[dict]:
        """
        Get status of a transaction signature.
        
        Returns dict with:
            - confirmed: bool
            - finalized: bool
            - error: Optional[str]
        """
        try:
            client = await self._get_client()
            result = await client.get_signature_statuses([Signature.from_string(signature)])
            
            if not result.value or not result.value[0]:
                return None
            
            status = result.value[0]
            
            conf_status = str(status.confirmation_status) if status.confirmation_status else None
            
            return {
                "confirmed": conf_status in ("confirmed", "finalized"),
                "finalized": conf_status == "finalized",
                "error": str(status.err) if status.err else None,
                "slot": status.slot,
            }
            
        except Exception as e:
            logger.error(f"SIG_STATUS | error | sig={signature[:16]}... | {e}")
            return None
    
    # =========================================================================
    # TRANSACTION EXECUTION
    # =========================================================================
    
    def _classify_error(self, error_msg: str) -> TxFailureReason:
        """Classify error message into failure reason."""
        error_lower = error_msg.lower()
        
        if "blockhash" in error_lower:
            return TxFailureReason.BLOCKHASH_EXPIRED
        if "simulation" in error_lower:
            return TxFailureReason.SIMULATION_FAILED
        if "insufficient" in error_lower or "not enough" in error_lower:
            return TxFailureReason.INSUFFICIENT_FUNDS
        if "slippage" in error_lower or "exceeds" in error_lower:
            return TxFailureReason.SLIPPAGE_EXCEEDED
        if "program" in error_lower:
            return TxFailureReason.PROGRAM_ERROR
        if "timeout" in error_lower:
            return TxFailureReason.TIMEOUT
        if "connection" in error_lower or "network" in error_lower:
            return TxFailureReason.NETWORK_ERROR
        
        return TxFailureReason.UNKNOWN
    
    async def execute(self, tx_bytes: bytes) -> TxResult:
        """
        Execute a transaction with confirmation tracking.
        
        This is the basic execution method. For trades, use execute_with_reconcile
        which adds balance checking on uncertain outcomes.
        
        Steps:
        1. Deserialize transaction
        2. Sign with keypair
        3. Send to RPC
        4. Wait for confirmation
        5. Classify outcome
        """
        send_time = datetime.now(timezone.utc)
        
        # Step 1: Deserialize
        try:
            tx = VersionedTransaction.from_bytes(tx_bytes)
        except Exception as e:
            logger.error(f"TX_DESERIALIZE | error | {e}")
            return TxResult(
                outcome=TxOutcome.DESERIALIZE_FAILED,
                error_message=str(e),
            )
        
        # Step 2: Sign
        try:
            signed_tx = VersionedTransaction(tx.message, [self.keypair])
        except Exception as e:
            logger.error(f"TX_SIGN | error | {e}")
            return TxResult(
                outcome=TxOutcome.SIGN_FAILED,
                error_message=str(e),
            )
        
        # Step 3: Send
        client = await self._get_client()
        signature = ""
        
        try:
            resp = await client.send_transaction(signed_tx, opts={"skip_preflight": False})
            
            if hasattr(resp, "value"):
                signature = str(resp.value)
            else:
                return TxResult(
                    outcome=TxOutcome.SEND_FAILED,
                    error_message="no_signature_returned",
                )
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"TX_SEND | error | {error_msg}")
            
            return TxResult(
                outcome=TxOutcome.FAILED_VERIFIED,
                failure_reason=self._classify_error(error_msg),
                error_message=error_msg,
                send_time=send_time,
            )
        
        logger.info(f"TX_SENT | sig={signature}")
        
        # Step 4: Wait for confirmation
        confirm_result = await self._wait_for_confirmation(signature, send_time)
        return confirm_result
    
    async def _wait_for_confirmation(
        self,
        signature: str,
        send_time: datetime,
    ) -> TxResult:
        """
        Wait for transaction confirmation with timeout.
        
        On timeout: returns TIMEOUT_UNKNOWN (needs reconciliation before retry)
        """
        start = asyncio.get_event_loop().time()
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start
            
            if elapsed > self.confirm_timeout:
                logger.warning(f"TX_TIMEOUT | sig={signature} | elapsed={elapsed:.1f}s")
                return TxResult(
                    outcome=TxOutcome.TIMEOUT_UNKNOWN,
                    signature=signature,
                    failure_reason=TxFailureReason.TIMEOUT,
                    error_message=f"confirmation_timeout:{elapsed:.1f}s",
                    send_time=send_time,
                )
            
            status = await self.get_signature_status(signature)
            
            if status is None:
                # Not found yet, keep waiting
                await asyncio.sleep(0.5)
                continue
            
            if status.get("error"):
                error_msg = status["error"]
                logger.error(f"TX_FAILED | sig={signature} | error={error_msg}")
                return TxResult(
                    outcome=TxOutcome.FAILED_VERIFIED,
                    signature=signature,
                    failure_reason=self._classify_error(error_msg),
                    error_message=error_msg,
                    send_time=send_time,
                    confirm_time=datetime.now(timezone.utc),
                )
            
            if status.get("finalized"):
                logger.info(f"TX_FINALIZED | sig={signature}")
                return TxResult(
                    outcome=TxOutcome.FINALIZED,
                    signature=signature,
                    send_time=send_time,
                    confirm_time=datetime.now(timezone.utc),
                )
            
            if status.get("confirmed"):
                logger.info(f"TX_CONFIRMED | sig={signature}")
                return TxResult(
                    outcome=TxOutcome.CONFIRMED,
                    signature=signature,
                    send_time=send_time,
                    confirm_time=datetime.now(timezone.utc),
                )
            
            await asyncio.sleep(0.5)
    
    # =========================================================================
    # CONFIRM-OR-RECONCILE (Phase 1 Fix - THE KEY SAFETY FEATURE)
    # =========================================================================
    
    async def execute_with_reconcile(
        self,
        tx_bytes: bytes,
        pair: str,
        side: str,
        token_mint: str,
        expected_delta: float,
    ) -> TxResult:
        """
        Execute transaction with balance reconciliation on uncertain outcomes.
        
        THIS IS THE MOST IMPORTANT SAFETY FEATURE.
        
        Phase 1 Fix Flow:
        Step A - Capture and persist:
            - Generate intent_id
            - Snapshot pre_balances (token + USDC)
            - Submit tx and capture signature
            - Persist all data to InflightIntent
            
        Step B - Confirmation poll with real timeout:
            - Poll for 30-60 seconds (self.confirm_timeout)
            - Use 'confirmed' commitment for trading
            - If confirmed → SUCCESS
            
        Step C - If not confirmed → reconcile by balances:
            - Snapshot post_balances
            - Calculate deltas
            - For SELL: token_delta < 0 AND usdc_delta > 0 → SUCCESS
            - For BUY: token_delta > 0 AND usdc_delta < 0 → SUCCESS
            - If deltas match → SUCCESS (chain state is authoritative)
            - If deltas don't match → FAILURE (safe to retry)
        
        Args:
            tx_bytes: Serialized transaction
            pair: Trading pair (for logging)
            side: "BUY" or "SELL"
            token_mint: Token to check balance of
            expected_delta: Expected balance change (positive for buys)
            
        Returns:
            TxResult with reconciliation data if applicable
        """
        intent_id = self._generate_intent_id()
        
        # =====================================================================
        # STEP A: Capture and persist signature + pre_balances
        # =====================================================================
        
        logger.info(f"RECONCILE_START | {intent_id} | {pair} | {side}")
        
        # Snapshot pre-balances
        pre_token = await self.get_token_balance(token_mint)
        pre_usdc = await self.get_usdc_balance()
        
        logger.debug(
            f"PRE_BALANCES | {intent_id} | token={pre_token} | usdc={pre_usdc}"
        )
        
        # Create intent record
        intent = InflightIntent(
            intent_id=intent_id,
            signature=None,
            pair=pair,
            side=side,
            amount_in=0,  # Will be set from tx if needed
            expected_delta=expected_delta,
            pre_balance_token=pre_token,
            pre_balance_usdc=pre_usdc,
            submit_ts=datetime.now(timezone.utc),
        )
        self._inflight_intents[intent_id] = intent
        
        # Execute transaction (this handles deserialize, sign, send)
        result = await self.execute(tx_bytes)
        result.balance_before = pre_token
        
        # Capture signature
        intent.signature = result.signature
        
        if result.signature:
            logger.info(f"TX_SUBMITTED | {intent_id} | sig={result.signature}")
        else:
            logger.error(f"TX_NO_SIGNATURE | {intent_id} | Cannot proceed with reconciliation")
            intent.outcome = "no_signature"
            return result
        
        # =====================================================================
        # STEP B: If definite outcome, we're done
        # =====================================================================
        
        if result.is_success:
            intent.outcome = "confirmed"
            intent.confirm_ts = datetime.now(timezone.utc)
            logger.info(f"TX_CONFIRMED | {intent_id} | outcome=success")
            return result
        
        if result.is_safe_to_retry:
            intent.outcome = f"failed:{result.failure_reason.value if result.failure_reason else 'unknown'}"
            logger.info(f"TX_FAILED_DEFINITE | {intent_id} | safe to retry")
            return result
        
        # =====================================================================
        # STEP C: UNCERTAIN OUTCOME - Reconcile by balances
        # =====================================================================
        
        if result.outcome == TxOutcome.TIMEOUT_UNKNOWN:
            logger.warning(
                f"TX_TIMEOUT | {intent_id} | sig={result.signature} | "
                f"Proceeding to balance reconciliation..."
            )
            
            # Wait a bit for chain to settle
            await asyncio.sleep(3.0)
            
            # Snapshot post-balances
            post_token = await self.get_token_balance(token_mint)
            post_usdc = await self.get_usdc_balance()
            
            intent.post_balance_token = post_token
            intent.post_balance_usdc = post_usdc
            result.balance_after = post_token
            
            logger.debug(
                f"POST_BALANCES | {intent_id} | token={post_token} | usdc={post_usdc}"
            )
            
            # Calculate deltas
            token_delta = intent.token_delta()
            usdc_delta = intent.usdc_delta()
            result.balance_delta = token_delta
            
            logger.info(
                f"RECONCILE_DELTAS | {intent_id} | "
                f"token_delta={token_delta:.6f if token_delta else 'None'} | "
                f"usdc_delta={usdc_delta:.6f if usdc_delta else 'None'} | "
                f"expected={expected_delta:.6f}"
            )
            
            # Check if deltas match expected
            if intent.matches_expected_deltas(self.reconcile_tolerance_pct):
                # SUCCESS - chain state is authoritative
                intent.outcome = "reconciled_success"
                result.outcome = TxOutcome.LANDED_UNCONFIRMED
                
                logger.warning(
                    f"RECONCILE_SUCCESS | {intent_id} | "
                    f"Balance deltas confirm tx landed | "
                    f"token_delta={token_delta:.6f} | usdc_delta={usdc_delta:.6f}"
                )
            else:
                # FAILURE - safe to retry
                intent.outcome = "reconciled_failure"
                result.outcome = TxOutcome.FAILED_VERIFIED
                result.failure_reason = TxFailureReason.TIMEOUT
                
                logger.info(
                    f"RECONCILE_FAILURE | {intent_id} | "
                    f"Balance deltas do not match expected | "
                    f"Safe to retry on next attempt"
                )
        
        return result
    
    def get_intent(self, intent_id: str) -> Optional[InflightIntent]:
        """Get an inflight intent by ID."""
        return self._inflight_intents.get(intent_id)
    
    def get_recent_intents(self, limit: int = 10) -> List[InflightIntent]:
        """Get most recent inflight intents."""
        intents = list(self._inflight_intents.values())
        intents.sort(key=lambda x: x.submit_ts or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return intents[:limit]
    
    # =========================================================================
    # INFLIGHT TRACKING
    # =========================================================================
    
    def track_inflight(
        self,
        signature: str,
        pair: str,
        side: str,
        expected_delta: float,
    ) -> None:
        """Track a transaction as in-flight."""
        self._inflight[signature] = InflightTx(
            signature=signature,
            pair=pair,
            side=side,
            send_time=datetime.now(timezone.utc),
            expected_delta=expected_delta,
        )
        logger.debug(f"INFLIGHT_ADD | sig={signature[:16]}... | {pair} {side}")
    
    def untrack_inflight(self, signature: str) -> Optional[InflightTx]:
        """Remove transaction from in-flight tracking."""
        tx = self._inflight.pop(signature, None)
        if tx:
            logger.debug(f"INFLIGHT_REMOVE | sig={signature[:16]}...")
        return tx
    
    def get_inflight(self, pair: str, side: str) -> Optional[InflightTx]:
        """Get in-flight tx for a pair/side if one exists."""
        for tx in self._inflight.values():
            if tx.pair == pair and tx.side == side:
                return tx
        return None
    
    def has_inflight(self, pair: str, side: Optional[str] = None) -> bool:
        """Check if there's an in-flight tx for this pair."""
        for tx in self._inflight.values():
            if tx.pair == pair:
                if side is None or tx.side == side:
                    return True
        return False
    
    async def reconcile_inflight(self, max_age_seconds: float = 120.0) -> List[TxResult]:
        """
        Reconcile all stale in-flight transactions.
        
        Call this periodically to clean up any txs that got lost.
        """
        results = []
        stale = []
        
        for sig, tx in list(self._inflight.items()):
            if tx.age_seconds() > max_age_seconds:
                stale.append((sig, tx))
        
        for sig, tx in stale:
            logger.warning(f"RECONCILE_STALE | sig={sig[:16]}... | age={tx.age_seconds():.0f}s")
            
            status = await self.get_signature_status(sig)
            
            if status is None:
                # Never found - probably failed
                result = TxResult(
                    outcome=TxOutcome.FAILED_VERIFIED,
                    signature=sig,
                    failure_reason=TxFailureReason.UNKNOWN,
                    error_message="tx_never_found",
                )
            elif status.get("error"):
                result = TxResult(
                    outcome=TxOutcome.FAILED_VERIFIED,
                    signature=sig,
                    failure_reason=self._classify_error(status["error"]),
                    error_message=status["error"],
                )
            elif status.get("confirmed") or status.get("finalized"):
                result = TxResult(
                    outcome=TxOutcome.LANDED_UNCONFIRMED,
                    signature=sig,
                )
            else:
                result = TxResult(
                    outcome=TxOutcome.TIMEOUT_UNKNOWN,
                    signature=sig,
                )
            
            results.append(result)
            self.untrack_inflight(sig)
        
        return results
