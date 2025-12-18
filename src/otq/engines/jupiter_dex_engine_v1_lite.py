"""
Kyzlo Labs V1-Lite: Jupiter DEX Engine
REBUILD following REBUILD_JUPITER_ENGINE_PART1.md specification

Core Principles:
1. FAIL CLOSED - If something is wrong, STOP. Do not guess or use defaults.
2. NO ENV READS AFTER BOOT - Load .env once, build config, never read env again.
3. JUPITER ROUTES - Jupiter picks the route. You sign and send. No manual routing.
4. BASE58 ONLY - Private key must be base58 that decodes to exactly 64 bytes.
5. PRICE VALIDITY - If price is stale or missing, do NOT trade.
"""

from __future__ import annotations

import asyncio
import base58
import base64
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

import httpx
from dotenv import load_dotenv
from loguru import logger
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
import os


# =============================================================================
# PHASE 2: Keypair Loading (BASE58 ONLY - NO EXCEPTIONS)
# =============================================================================

def load_keypair_or_exit(private_key_b58: str) -> Keypair:
    """
    Load keypair from base58 private key.
    
    ACCEPTS: Base58 string decoding to exactly 64 bytes.
    REJECTS: Everything else.
    ON FAILURE: Exits process with error code 1.
    
    Policy:
    - NEVER LOG: The key bytes or decoded value
    - NO FALLBACK: Exit immediately on any validation failure
    """
    if not private_key_b58 or not isinstance(private_key_b58, str):
        print("FATAL: SOLANA_PRIVATE_KEY is empty or not set", file=sys.stderr)
        sys.exit(1)
    
    private_key_b58 = private_key_b58.strip()
    
    # Must be base58 characters only
    b58_chars = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
    if not all(c in b58_chars for c in private_key_b58):
        print("FATAL: SOLANA_PRIVATE_KEY contains invalid characters (must be base58)", file=sys.stderr)
        sys.exit(1)
    
    try:
        key_bytes = base58.b58decode(private_key_b58)
    except Exception as e:
        print(f"FATAL: Failed to decode SOLANA_PRIVATE_KEY as base58: {e}", file=sys.stderr)
        sys.exit(1)
    
    if len(key_bytes) != 64:
        print(f"FATAL: SOLANA_PRIVATE_KEY decoded to {len(key_bytes)} bytes, expected 64", file=sys.stderr)
        sys.exit(1)
    
    try:
        keypair = Keypair.from_bytes(key_bytes)
    except Exception as e:
        print(f"FATAL: Failed to create keypair: {e}", file=sys.stderr)
        sys.exit(1)
    
    return keypair


# =============================================================================
# PHASE 3: Configuration (SINGLE SOURCE OF TRUTH)
# =============================================================================

@dataclass(frozen=True)
class EngineConfig:
    """
    Immutable config. Built once at boot.
    
    Policy:
    - Frozen after initialization (no runtime modifications)
    - All runtime code reads from this config only
    - NEVER call os.getenv() anywhere else in codebase
    """
    wallet_pubkey: str
    rpc_url: str
    helius_api_key: str
    pairs: tuple  # Immutable tuple, not list
    tick_interval_seconds: float = 30.0
    price_ttl_seconds: float = 10.0
    confirm_timeout_seconds: float = 60.0
    http_timeout_seconds: float = 30.0
    min_sol_reserve: float = 0.05
    max_consecutive_errors: int = 5
    slippage_bps: int = 75
    dry_run: bool = True
    
    def __post_init__(self):
        if not self.rpc_url:
            raise ValueError("rpc_url is required")
        if not self.pairs:
            raise ValueError("pairs cannot be empty")


def load_config_or_exit() -> tuple[EngineConfig, Keypair]:
    """
    THE ONLY FUNCTION THAT CALLS os.getenv().
    
    Returns: (EngineConfig, Keypair)
    Exits on missing required values.
    
    Policy:
    - Load .env ONCE at boot
    - Build frozen EngineConfig dataclass
    - NEVER call os.getenv() anywhere else in codebase
    - All runtime code reads from config only
    - Grep test: os.getenv appears ONLY in this function
    """
    load_dotenv()
    
    private_key = os.getenv("SOLANA_PRIVATE_KEY", "").strip()
    if not private_key:
        print("FATAL: SOLANA_PRIVATE_KEY not set", file=sys.stderr)
        sys.exit(1)
    
    rpc_url = os.getenv("SOLANA_RPC_URL", "").strip()
    if not rpc_url:
        print("FATAL: SOLANA_RPC_URL not set", file=sys.stderr)
        sys.exit(1)
    
    keypair = load_keypair_or_exit(private_key)
    
    pairs_str = os.getenv("JUP_PAIRS", "SOL/USDC").strip()
    pairs = tuple(p.strip() for p in pairs_str.split(",") if p.strip())
    
    config = EngineConfig(
        wallet_pubkey=str(keypair.pubkey()),
        rpc_url=rpc_url,
        helius_api_key=os.getenv("HELIUS_API_KEY", "").strip(),
        pairs=pairs,
        tick_interval_seconds=float(os.getenv("TICK_INTERVAL", "30")),
        price_ttl_seconds=float(os.getenv("PRICE_TTL", "10")),
        confirm_timeout_seconds=float(os.getenv("CONFIRM_TIMEOUT", "60")),
        http_timeout_seconds=float(os.getenv("HTTP_TIMEOUT", "30")),
        min_sol_reserve=float(os.getenv("MIN_SOL_RESERVE", "0.05")),
        max_consecutive_errors=int(os.getenv("MAX_CONSECUTIVE_ERRORS", "5")),
        slippage_bps=int(os.getenv("JUP_SLIPPAGE_BPS", "75")),
        dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
    )
    
    return config, keypair


# =============================================================================
# PHASE 4: Price Oracle (FAIL-CLOSED)
# =============================================================================

class PriceSource(Enum):
    """Source of price data."""
    HELIUS = "helius"
    JUPITER = "jupiter"
    NONE = "none"


class FeedStatus(Enum):
    """Health status of a price feed."""
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


class WhyNot(Enum):
    """Reasons why a trade did not happen - for full traceability."""
    # Price issues
    PRICE_FETCH_FAILED = "price_fetch_failed"
    PRICE_STALE = "price_stale"
    PRICE_INVALID_SCHEMA = "price_invalid_schema"
    PRICE_OUT_OF_BOUNDS = "price_out_of_bounds"
    
    # Position issues
    POSITION_ALREADY_OPEN = "position_already_open"
    MAX_POSITIONS_REACHED = "max_positions_reached"
    TRADE_INFLIGHT = "trade_inflight"
    
    # Signal issues
    SIGNAL_FLAT = "signal_flat"
    RSI_NOT_OVERSOLD = "rsi_not_oversold"
    INSUFFICIENT_HISTORY = "insufficient_history"
    
    # Risk issues
    ENGINE_PAUSED = "engine_paused"
    SOL_RESERVE_LOW = "sol_reserve_low"
    CONSECUTIVE_ERRORS = "consecutive_errors"
    
    # Execution issues
    QUOTE_FAILED = "quote_failed"
    SWAP_TX_FAILED = "swap_tx_failed"
    TX_FAILED = "tx_failed"
    
    # Success (not really "why not" but completes the picture)
    TRADE_EXECUTED = "trade_executed"


@dataclass
class WhyNotRecord:
    """Records why a trade did or did not happen for a pair."""
    pair: str
    timestamp: datetime
    reason: WhyNot
    details: dict
    
    def to_log_line(self) -> str:
        """Format for logging."""
        ts = self.timestamp.strftime("%H:%M:%S")
        detail_str = " | ".join(f"{k}={v}" for k, v in self.details.items())
        return f"WHY_NOT | {ts} | {self.pair} | {self.reason.value} | {detail_str}"


@dataclass
class PricePoint:
    """
    Immutable price data point with validation.
    
    Policy:
    - Every price has: value, timestamp, source, age_seconds
    - Price VALID only if: age <= TTL AND price > 0
    - NEVER assume decimals - get from token registry
    """
    pair: str
    price: float
    timestamp: datetime
    source: PriceSource
    decimals_base: int
    decimals_quote: int
    
    @property
    def age_seconds(self) -> float:
        """Calculate age of price in seconds."""
        now = datetime.now(timezone.utc)
        return (now - self.timestamp).total_seconds()
    
    def is_valid(self, ttl_seconds: float) -> bool:
        """Check if price is valid (within TTL and positive)."""
        return self.age_seconds <= ttl_seconds and self.price > 0


class PriceOracle:
    """
    Fail-closed price oracle with full validation.
    
    Policy:
    1. Helius PRIMARY (if API key provided)
    2. Jupiter /price SECONDARY fallback
    3. Every price has: value, timestamp, source, age_seconds
    4. Price VALID only if: age <= TTL AND price > 0
    5. If no valid price: DO NOT TRADE (pause engine)
    6. NEVER assume decimals - get from token registry
    """
    
    HELIUS_URL = "https://mainnet.helius-rpc.com"
    JUPITER_PRICE_URL = "https://api.jup.ag/price/v2"
    
    # Sanity bounds per pair (very wide, just catching garbage)
    PRICE_BOUNDS = {
        "SOL/USDC": (1.0, 10000.0),
        "JUP/USDC": (0.001, 1000.0),
        "BONK/USDC": (0.0000001, 0.01),
        "WIF/USDC": (0.001, 1000.0),
        "TRUMP/USDC": (0.01, 10000.0),
        "POPCAT/USDC": (0.001, 1000.0),
        "MEW/USDC": (0.0001, 100.0),
    }
    
    def __init__(
        self,
        helius_api_key: str,
        http_timeout: float,
        price_ttl: float,
    ):
        self.helius_api_key = helius_api_key
        self.price_ttl = price_ttl
        self.http_timeout = http_timeout
        self._cache: Dict[str, PricePoint] = {}
        self.helius_status = FeedStatus.UNKNOWN
        self.jupiter_status = FeedStatus.UNKNOWN
        self._helius_backoff_until: float = 0
        self._jupiter_backoff_until: float = 0
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.http_timeout)
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    def _validate_helius_response(self, data: dict, mint: str) -> tuple[bool, str]:
        """Validate Helius response schema."""
        if data is None:
            return False, "response_null"
        if "result" not in data:
            return False, "missing_result"
        if data["result"] is None:
            return False, "result_null"
        if "token_info" not in data["result"]:
            return False, "missing_token_info"
        if "price_info" not in data["result"]["token_info"]:
            return False, "missing_price_info"
        if "price_per_token" not in data["result"]["token_info"]["price_info"]:
            return False, "missing_price_per_token"
        return True, "ok"
    
    def _validate_jupiter_response(self, data: dict, mint: str) -> tuple[bool, str]:
        """Validate Jupiter response schema."""
        if data is None:
            return False, "response_null"
        if "data" not in data:
            return False, "missing_data"
        if not isinstance(data["data"], dict):
            return False, "data_not_dict"
        if mint not in data["data"]:
            return False, "mint_not_in_data"
        if "price" not in data["data"][mint]:
            return False, "missing_price"
        return True, "ok"
    
    def _validate_price_bounds(self, price: float, pair: str) -> tuple[bool, str]:
        """Validate price is within reasonable bounds."""
        if price <= 0:
            return False, f"price_not_positive:{price}"
        if not math.isfinite(price):
            return False, f"price_not_finite:{price}"
        
        if pair in self.PRICE_BOUNDS:
            low, high = self.PRICE_BOUNDS[pair]
            if price < low:
                return False, f"price_below_min:{price}<{low}"
            if price > high:
                return False, f"price_above_max:{price}>{high}"
        
        return True, "ok"
    
    async def _fetch_helius_validated(self, base_mint: str, pair: str) -> tuple[Optional[float], Optional[str]]:
        """Fetch and validate price from Helius."""
        try:
            client = await self._get_client()
            
            url = f"{self.HELIUS_URL}/?api-key={self.helius_api_key}"
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAsset",
                "params": {"id": base_mint},
            }
            
            resp = await client.post(url, json=payload)
            
            if resp.status_code == 429:
                self._helius_backoff_until = asyncio.get_event_loop().time() + 60
                self.helius_status = FeedStatus.DOWN
                return None, "http_429_rate_limited"
            
            if resp.status_code >= 500:
                self.helius_status = FeedStatus.DOWN
                return None, f"http_{resp.status_code}"
            
            resp.raise_for_status()
            data = resp.json()
            
            is_valid, schema_reason = self._validate_helius_response(data, base_mint)
            if not is_valid:
                return None, f"schema:{schema_reason}"
            
            price = float(data["result"]["token_info"]["price_info"]["price_per_token"])
            
            is_valid, bounds_reason = self._validate_price_bounds(price, pair)
            if not is_valid:
                return None, f"bounds:{bounds_reason}"
            
            self.helius_status = FeedStatus.UP
            return price, None
            
        except httpx.TimeoutException:
            self.helius_status = FeedStatus.DOWN
            return None, "timeout"
        except Exception as e:
            self.helius_status = FeedStatus.DOWN
            return None, f"error:{type(e).__name__}"
    
    async def _fetch_jupiter_validated(
        self, 
        base_mint: str, 
        quote_mint: str, 
        pair: str
    ) -> tuple[Optional[float], Optional[str]]:
        """Fetch and validate price from Jupiter."""
        try:
            client = await self._get_client()
            
            params = {"ids": base_mint, "vsToken": quote_mint}
            resp = await client.get(self.JUPITER_PRICE_URL, params=params)
            
            if resp.status_code == 429:
                self._jupiter_backoff_until = asyncio.get_event_loop().time() + 60
                self.jupiter_status = FeedStatus.DOWN
                return None, "http_429_rate_limited"
            
            if resp.status_code >= 500:
                self.jupiter_status = FeedStatus.DOWN
                return None, f"http_{resp.status_code}"
            
            resp.raise_for_status()
            data = resp.json()
            
            is_valid, schema_reason = self._validate_jupiter_response(data, base_mint)
            if not is_valid:
                return None, f"schema:{schema_reason}"
            
            price = float(data["data"][base_mint]["price"])
            
            is_valid, bounds_reason = self._validate_price_bounds(price, pair)
            if not is_valid:
                return None, f"bounds:{bounds_reason}"
            
            self.jupiter_status = FeedStatus.UP
            return price, None
            
        except httpx.TimeoutException:
            self.jupiter_status = FeedStatus.DOWN
            return None, "timeout"
        except Exception as e:
            self.jupiter_status = FeedStatus.DOWN
            return None, f"error:{type(e).__name__}"
    
    async def get_price(
        self,
        pair: str,
        base_mint: str,
        quote_mint: str,
        base_decimals: int,
        quote_decimals: int,
    ) -> tuple[Optional[PricePoint], Optional[str]]:
        """
        Get price for a pair with fail-closed validation.
        
        Returns:
            Tuple of (PricePoint or None, why_not_reason or None)
            
        If PricePoint is None, why_not_reason explains why.
        """
        # Check cache first
        cached = self._cache.get(pair)
        if cached and cached.is_valid(self.price_ttl):
            return cached, None
        
        now = asyncio.get_event_loop().time()
        why_not = None
        
        # Try Helius first
        if self.helius_api_key and now >= self._helius_backoff_until:
            price, helius_why = await self._fetch_helius_validated(base_mint, pair)
            if price is not None:
                point = PricePoint(
                    pair=pair,
                    price=price,
                    timestamp=datetime.now(timezone.utc),
                    source=PriceSource.HELIUS,
                    decimals_base=base_decimals,
                    decimals_quote=quote_decimals,
                )
                self._cache[pair] = point
                return point, None
            else:
                why_not = f"helius:{helius_why}"
        
        # Try Jupiter as fallback
        if now >= self._jupiter_backoff_until:
            price, jup_why = await self._fetch_jupiter_validated(base_mint, quote_mint, pair)
            if price is not None:
                point = PricePoint(
                    pair=pair,
                    price=price,
                    timestamp=datetime.now(timezone.utc),
                    source=PriceSource.JUPITER,
                    decimals_base=base_decimals,
                    decimals_quote=quote_decimals,
                )
                self._cache[pair] = point
                return point, None
            else:
                why_not = f"jupiter:{jup_why}" if why_not is None else f"{why_not},jupiter:{jup_why}"
        
        # Both failed - return stale cache if available
        if cached:
            age = cached.age_seconds
            return cached, f"stale_cache:age={age:.1f}s"
        
        return None, why_not or "no_price_sources"


# =============================================================================
# PHASE 5: Jupiter Client (QUOTE + SWAP ONLY)
# =============================================================================

class JupiterClient:
    """
    Jupiter DEX client for quotes and swaps.
    
    Policy:
    1. Jupiter picks the route - NO manual routing
    2. GET /quote - returns route and amounts
    3. POST /swap - returns transaction to sign
    4. Validate response schema before using
    5. On schema error: return None (abort trade, don't crash)
    """
    
    BASE_URL = "https://quote-api.jup.ag/v6"
    
    # Required fields in responses
    REQUIRED_QUOTE_FIELDS = ["inAmount", "outAmount", "routePlan"]
    REQUIRED_SWAP_FIELDS = ["swapTransaction"]
    
    def __init__(self, http_timeout: float):
        self.http_timeout = http_timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.http_timeout)
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    def _validate_quote_response(self, data: dict) -> bool:
        """Validate quote response has required fields."""
        if data is None:
            return False
        for field in self.REQUIRED_QUOTE_FIELDS:
            if field not in data:
                logger.warning(f"JUPITER_QUOTE | missing field: {field}")
                return False
        return True
    
    def _validate_swap_response(self, data: dict) -> bool:
        """Validate swap response has required fields."""
        if data is None:
            return False
        for field in self.REQUIRED_SWAP_FIELDS:
            if field not in data:
                logger.warning(f"JUPITER_SWAP | missing field: {field}")
                return False
        return True
    
    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int,
    ) -> Optional[dict]:
        """
        Get quote from Jupiter.
        
        Policy:
        - Retry up to 3x with exponential backoff
        - Validate required fields
        - Return None on failure (don't crash)
        
        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount in smallest unit (lamports/decimals)
            slippage_bps: Slippage tolerance in basis points
            
        Returns:
            Quote response dict or None on failure
        """
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": str(slippage_bps),
        }
        
        client = await self._get_client()
        
        # Retry up to 3 times with exponential backoff
        for attempt in range(3):
            try:
                resp = await client.get(f"{self.BASE_URL}/quote", params=params)
                
                if resp.status_code == 429:
                    logger.warning(f"JUPITER_QUOTE | rate limited (attempt {attempt + 1}/3)")
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)  # 1s, 2s
                        continue
                    return None
                
                if resp.status_code >= 500:
                    logger.warning(f"JUPITER_QUOTE | server error {resp.status_code} (attempt {attempt + 1}/3)")
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return None
                
                resp.raise_for_status()
                data = resp.json()
                
                if not self._validate_quote_response(data):
                    logger.error("JUPITER_QUOTE | invalid response schema")
                    return None
                
                logger.debug(f"JUPITER_QUOTE | success | in={data['inAmount']} out={data['outAmount']}")
                return data
                
            except httpx.TimeoutException:
                logger.warning(f"JUPITER_QUOTE | timeout (attempt {attempt + 1}/3)")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
            except Exception as e:
                logger.error(f"JUPITER_QUOTE | error: {type(e).__name__}: {e}")
                return None
        
        return None
    
    async def get_swap_transaction(
        self,
        quote_response: dict,
        user_pubkey: str,
    ) -> Optional[bytes]:
        """
        Get swap transaction from Jupiter.
        
        Policy:
        - POST with wrapAndUnwrapSol=True, prioritizationFeeLamports="auto"
        - Validate swapTransaction exists
        - Return decoded bytes or None
        
        Args:
            quote_response: Quote response from get_quote()
            user_pubkey: User's wallet public key
            
        Returns:
            Transaction bytes or None on failure
        """
        payload = {
            "quoteResponse": quote_response,
            "userPublicKey": user_pubkey,
            "wrapAndUnwrapSol": True,
            "prioritizationFeeLamports": "auto",
        }
        
        client = await self._get_client()
        
        try:
            resp = await client.post(f"{self.BASE_URL}/swap", json=payload)
            
            if resp.status_code == 429:
                logger.warning("JUPITER_SWAP | rate limited")
                return None
            
            if resp.status_code >= 500:
                logger.warning(f"JUPITER_SWAP | server error {resp.status_code}")
                return None
            
            resp.raise_for_status()
            data = resp.json()
            
            if not self._validate_swap_response(data):
                logger.error("JUPITER_SWAP | invalid response schema")
                return None
            
            # Decode base64 transaction
            tx_b64 = data["swapTransaction"]
            tx_bytes = base64.b64decode(tx_b64)
            
            logger.debug(f"JUPITER_SWAP | success | tx_size={len(tx_bytes)} bytes")
            return tx_bytes
            
        except httpx.TimeoutException:
            logger.warning("JUPITER_SWAP | timeout")
            return None
        except Exception as e:
            logger.error(f"JUPITER_SWAP | error: {type(e).__name__}: {e}")
            return None


# =============================================================================
# PHASE 6: Transaction Executor
# =============================================================================

class TxResult(Enum):
    """Transaction execution result classification."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    BLOCKHASH_EXPIRED = "blockhash_expired"
    SIMULATION_FAILED = "simulation_failed"


@dataclass
class ExecutionResult:
    """Result of transaction execution."""
    status: TxResult
    signature: str
    error: Optional[str] = None


class TransactionExecutor:
    """
    Transaction executor with fail-closed error classification.
    
    Policy:
    1. Deserialize VersionedTransaction from bytes
    2. Sign with keypair
    3. Send via RPC with Confirmed commitment
    4. Wait for confirmation with timeout
    5. On blockhash expired: return BLOCKHASH_EXPIRED (do NOT retry)
    6. Classify all errors for risk manager
    
    Error Classification:
    - "blockhash" in error -> BLOCKHASH_EXPIRED
    - "simulation" in error -> SIMULATION_FAILED
    - no signature returned -> FAILED
    - confirmation timeout -> TIMEOUT
    - on-chain error -> FAILED
    """
    
    def __init__(
        self,
        rpc_url: str,
        keypair: Keypair,
        confirm_timeout: float,
    ):
        self.rpc_url = rpc_url
        self.keypair = keypair
        self.confirm_timeout = confirm_timeout
        self._client: Optional[AsyncClient] = None
    
    async def _get_client(self) -> AsyncClient:
        """Get or create RPC client."""
        if self._client is None:
            self._client = AsyncClient(self.rpc_url)
        return self._client
    
    async def close(self):
        """Close RPC client."""
        if self._client:
            await self._client.close()
    
    def _classify_error(self, error_msg: str) -> TxResult:
        """Classify error message to TxResult."""
        error_lower = error_msg.lower()
        
        if "blockhash" in error_lower:
            return TxResult.BLOCKHASH_EXPIRED
        if "simulation" in error_lower:
            return TxResult.SIMULATION_FAILED
        
        return TxResult.FAILED
    
    async def execute(self, tx_bytes: bytes) -> ExecutionResult:
        """
        Execute a transaction.
        
        Args:
            tx_bytes: Serialized VersionedTransaction bytes
            
        Returns:
            ExecutionResult with status and signature
        """
        try:
            # Deserialize transaction
            try:
                tx = VersionedTransaction.from_bytes(tx_bytes)
            except Exception as e:
                logger.error(f"TX_DESERIALIZE | error: {e}")
                return ExecutionResult(
                    status=TxResult.FAILED,
                    signature="",
                    error=f"deserialize_failed: {e}",
                )
            
            # Sign transaction
            try:
                tx = VersionedTransaction(tx.message, [self.keypair])
            except Exception as e:
                logger.error(f"TX_SIGN | error: {e}")
                return ExecutionResult(
                    status=TxResult.FAILED,
                    signature="",
                    error=f"sign_failed: {e}",
                )
            
            # Send transaction
            client = await self._get_client()
            try:
                resp = await client.send_transaction(tx, opts={"skip_preflight": False})
                
                if hasattr(resp, "value"):
                    signature = str(resp.value)
                else:
                    logger.error("TX_SEND | no signature in response")
                    return ExecutionResult(
                        status=TxResult.FAILED,
                        signature="",
                        error="no_signature_returned",
                    )
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"TX_SEND | error: {error_msg}")
                
                # Classify the error
                status = self._classify_error(error_msg)
                
                return ExecutionResult(
                    status=status,
                    signature="",
                    error=error_msg,
                )
            
            # Wait for confirmation
            try:
                start_time = asyncio.get_event_loop().time()
                
                while True:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed > self.confirm_timeout:
                        logger.warning(f"TX_CONFIRM | timeout after {elapsed:.1f}s | sig={signature}")
                        return ExecutionResult(
                            status=TxResult.TIMEOUT,
                            signature=signature,
                            error=f"confirmation_timeout:{elapsed:.1f}s",
                        )
                    
                    # Check signature status
                    status_resp = await client.get_signature_statuses([signature])
                    
                    if status_resp.value and status_resp.value[0]:
                        status_info = status_resp.value[0]
                        
                        # Check for errors
                        if status_info.err:
                            error_msg = str(status_info.err)
                            logger.error(f"TX_FAILED | sig={signature} | error={error_msg}")
                            
                            # Classify the error
                            tx_status = self._classify_error(error_msg)
                            
                            return ExecutionResult(
                                status=tx_status,
                                signature=signature,
                                error=error_msg,
                            )
                        
                        # Check confirmation level
                        if status_info.confirmation_status:
                            conf_level = str(status_info.confirmation_status)
                            if conf_level in ["confirmed", "finalized"]:
                                logger.info(f"TX_SUCCESS | sig={signature} | conf={conf_level}")
                                return ExecutionResult(
                                    status=TxResult.SUCCESS,
                                    signature=signature,
                                )
                    
                    # Wait before next check
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"TX_CONFIRM | error: {error_msg} | sig={signature}")
                
                # Classify the error
                status = self._classify_error(error_msg)
                
                return ExecutionResult(
                    status=status,
                    signature=signature,
                    error=error_msg,
                )
        
        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"TX_EXECUTE | unexpected error: {e}")
            return ExecutionResult(
                status=TxResult.FAILED,
                signature="",
                error=f"unexpected: {e}",
            )


# =============================================================================
# PHASE 7: Engine States
# =============================================================================

class EngineState(Enum):
    """
    Engine operational state.
    
    Transition Rules:
    - RUNNING -> PAUSED_PRICE_FEED: No valid price for any active pair
    - RUNNING -> PAUSED_SOL_RESERVE: SOL < min_sol_reserve
    - RUNNING -> PAUSED_EXEC_ERRORS: consecutive_errors >= max
    - PAUSED_* -> RUNNING: Manual unpause only (V1-Lite)
    - ANY -> STOPPED: Shutdown signal
    """
    RUNNING = "running"
    PAUSED_PRICE_FEED = "paused_price_feed"
    PAUSED_SOL_RESERVE = "paused_sol_reserve"
    PAUSED_EXEC_ERRORS = "paused_exec_errors"
    STOPPED = "stopped"


@dataclass
class PairState:
    """
    Per-pair state tracking to prevent double trades.
    
    Policy:
    - inflight=True while trade is executing
    - Prevents concurrent trades on same pair
    - Tracks last trade time for rate limiting
    """
    pair: str
    inflight: bool = False
    last_trade_time: Optional[datetime] = None


# =============================================================================
# PHASE 8: Engine Class - Main Implementation
# =============================================================================

class JupiterDexEngine:
    """
    Jupiter DEX Engine V1-Lite
    
    Main trading engine that integrates price oracle, Jupiter client, and strategy.
    Implements fail-closed design with strict validation at every step.
    """
    
    def __init__(self, cfg: EngineConfig, keypair: Keypair):
        """
        Initialize engine with config and keypair.
        
        Sets up:
        - PriceOracle (Helius + Jupiter fallback)
        - JupiterClient (quote/swap API)
        - TransactionExecutor (tx lifecycle)
        - JupiterMRStrategy (mean reversion signals)
        - State tracking (engine state, pair states, prices, SOL balance)
        """
        self.cfg = cfg
        self.keypair = keypair
        
        # Initialize price oracle
        self.price_oracle = PriceOracle(
            helius_api_key=cfg.helius_api_key,
            http_timeout=cfg.http_timeout_seconds,
            price_ttl=cfg.price_ttl_seconds,
        )
        
        # Initialize Jupiter client
        self.jupiter = JupiterClient(http_timeout=cfg.http_timeout_seconds)
        
        # Initialize transaction executor
        self.tx_executor = TransactionExecutor(
            rpc_url=cfg.rpc_url,
            keypair=keypair,
            confirm_timeout=cfg.confirm_timeout_seconds,
        )
        
        # Initialize strategy
        # ==============================================================================
        # STRATEGY SELECTOR: Choose ONE strategy below
        # ==============================================================================
        # Option 1: RSI Bands (Conservative Scalper, $10/trade, Phase 1 TP +0.35%, SL -0.85%, 15min forced exit)
        from otq.strategies.jupiter_rsi_bands_strategy import JupiterRSIBandsStrategy, JupiterRSIBandsConfig
        self.strategy = JupiterRSIBandsStrategy(JupiterRSIBandsConfig(pairs=list(cfg.pairs)))
        
        # Option 2: Jupiter MR (Mean Reversion, $10/trade, TP +0.45%, SL -0.60%, 25min hard exit, RSI >=48 exit)
        # from otq.strategies.jupiter_mr_strategy import JupiterMRStrategy, JupiterMRConfig
        # self.strategy = JupiterMRStrategy(JupiterMRConfig(pairs=list(cfg.pairs)))
        # ==============================================================================
        
        # Engine state management
        self.state = EngineState.RUNNING
        self.pause_reason: Optional[str] = None
        self._consecutive_errors = 0
        self._tick_lock = asyncio.Lock()
        
        # Pair state tracking
        self._pair_states = {p: PairState(pair=p) for p in cfg.pairs}
        
        # Cache for prices and balances
        self._prices: Dict[str, PricePoint] = {}
        self._sol_balance: float = 0.0
        
        # WHY_NOT tracking - one record per pair per tick
        self._why_not: Dict[str, WhyNotRecord] = {}
        
        logger.info(
            f"ENGINE_INIT | wallet={cfg.wallet_pubkey} | "
            f"pairs={cfg.pairs} | dry_run={cfg.dry_run}"
        )
    
    async def _check_sol_reserve(self) -> bool:
        """
        Check wallet SOL balance via RPC.
        
        Returns:
            True if balance >= min_sol_reserve, False otherwise
            
        Updates:
            - self._sol_balance
            - self.state (pauses on low balance)
        """
        try:
            client = await self.tx_executor._get_client()
            from solders.pubkey import Pubkey
            result = await client.get_balance(Pubkey.from_string(self.cfg.wallet_pubkey))
            self._sol_balance = result.value / 1e9
            
            if self._sol_balance < self.cfg.min_sol_reserve:
                logger.warning(
                    f"SOL_RESERVE | {self._sol_balance:.4f} < {self.cfg.min_sol_reserve}"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"SOL_CHECK | error: {e}")
            return False
    
    async def _update_all_prices(self) -> bool:
        """
        Update prices for ALL pairs and record to strategy.
        
        CRITICAL: This must update prices for ALL pairs, not just those with can_enter.
        This ensures RSI calculations stay current even for pairs with open positions.
        
        Returns:
            True if all prices are valid within TTL, False otherwise
        """
        from otq.config.solana_tokens import get_token
        
        all_valid = True
        
        for pair in self.cfg.pairs:
            base_sym, quote_sym = pair.split("/")
            base_token = get_token(base_sym)
            quote_token = get_token(quote_sym)
            
            price_point, why_not = await self.price_oracle.get_price(
                pair=pair,
                base_mint=base_token.mint,
                quote_mint=quote_token.mint,
                base_decimals=base_token.decimals,
                quote_decimals=quote_token.decimals,
            )
            
            if price_point is None:
                self._record_why_not(pair, WhyNot.PRICE_FETCH_FAILED, reason=why_not)
                all_valid = False
                logger.warning(f"PRICE_FAILED | {pair} | {why_not}")
                
            elif not price_point.is_valid(self.cfg.price_ttl_seconds):
                self._record_why_not(
                    pair, 
                    WhyNot.PRICE_STALE, 
                    age=price_point.age_seconds,
                    ttl=self.cfg.price_ttl_seconds
                )
                all_valid = False
                logger.warning(f"PRICE_STALE | {pair} | age={price_point.age_seconds:.1f}s")
                
            else:
                self._prices[pair] = price_point
                # CRITICAL: Always record to strategy for RSI updates
                self.strategy.record_price(pair, price_point.price)
                logger.debug(
                    f"PRICE | {pair} | {price_point.price:.6f} | "
                    f"{price_point.source.value} | age={price_point.age_seconds:.1f}s"
                )
        
        return all_valid
    
    def _record_why_not(
        self,
        pair: str,
        reason: WhyNot,
        **details
    ) -> None:
        """
        Record why a trade did not happen for this pair.
        Called throughout tick to track decision points.
        Later reasons overwrite earlier ones (most specific wins).
        """
        record = WhyNotRecord(
            pair=pair,
            timestamp=datetime.now(timezone.utc),
            reason=reason,
            details=details,
        )
        self._why_not[pair] = record
    
    async def tick(self) -> dict:
        """
        Main tick method - orchestrates one trading cycle.
        
        Order of operations (CRITICAL - follow exactly):
        1. Acquire tick lock
        2. Check if paused -> Skip if paused
        3. Check SOL reserve -> Pause if low
        4. Poll prices for ALL pairs
        5. Record prices to strategy for ALL pairs (CRITICAL for RSI updates)
        6. Check price validity -> Pause if invalid
        7. For each pair WITH position: check exits
        8. For each pair WITHOUT position: check entries
        9. Execute trades (one at a time, confirm before next)
        10. Update error tracking
        11. Release tick lock
        
        Returns:
            dict with timestamp, state, trades, errors, duration
        """
        async with self._tick_lock:
            tick_start = asyncio.get_event_loop().time()
            result = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "state": self.state.value,
                "trades": [],
                "errors": [],
            }
            
            # 1. Check if paused
            if self.state != EngineState.RUNNING:
                result["skipped"] = True
                result["reason"] = self.pause_reason
                return result
            
            # 2. Check SOL reserve
            if not await self._check_sol_reserve():
                self.state = EngineState.PAUSED_SOL_RESERVE
                self.pause_reason = f"sol={self._sol_balance:.4f}"
                return result
            
            # 3 & 4 & 5. Poll prices, record to strategy, check validity
            prices_valid = await self._update_all_prices()
            
            if not prices_valid:
                self.state = EngineState.PAUSED_PRICE_FEED
                self.pause_reason = "price_invalid"
                return result
            
            # 6. Check exits for open positions
            for pair, pos in list(self.strategy.positions.items()):
                if self._pair_states[pair].inflight:
                    continue
                price_point = self._prices.get(pair)
                if not price_point:
                    continue
                exit_reason = self.strategy.check_exit(pair, price_point.price)
                if exit_reason:
                    trade = await self._execute_exit(pair, pos, price_point, exit_reason)
                    result["trades"].append(trade)
            
            # 7. Check entries for flat pairs
            for pair in self.cfg.pairs:
                # Check inflight
                if self._pair_states[pair].inflight:
                    self._record_why_not(pair, WhyNot.TRADE_INFLIGHT)
                    continue
                
                # Check can_enter (position already open?)
                if not self.strategy.can_enter(pair):
                    if pair in self.strategy.positions:
                        self._record_why_not(pair, WhyNot.POSITION_ALREADY_OPEN)
                    else:
                        self._record_why_not(
                            pair, 
                            WhyNot.MAX_POSITIONS_REACHED,
                            current=len(self.strategy.positions),
                            max=self.strategy.config.max_concurrent_positions
                        )
                    continue
                
                # Check price available
                price_point = self._prices.get(pair)
                if not price_point:
                    # Already recorded in _update_all_prices
                    continue
                
                # Generate signal
                from otq.strategies.jupiter_mr_strategy import DexSignal
                signal, rsi = self.strategy.generate_entry_signal(pair)
                
                if signal == DexSignal.FLAT:
                    # Determine specific reason
                    prices = list(self.strategy.price_history.get(pair, []))
                    if len(prices) < self.strategy.config.rsi_period + 1:
                        self._record_why_not(
                            pair, 
                            WhyNot.INSUFFICIENT_HISTORY,
                            have=len(prices),
                            need=self.strategy.config.rsi_period + 1
                        )
                    elif math.isnan(rsi):
                        self._record_why_not(pair, WhyNot.INSUFFICIENT_HISTORY, rsi="nan")
                    else:
                        self._record_why_not(
                            pair, 
                            WhyNot.RSI_NOT_OVERSOLD,
                            rsi=round(rsi, 2),
                            threshold=self.strategy.config.rsi_oversold
                        )
                    continue
                
                # Signal is LONG - attempt entry
                trade = await self._execute_entry(pair, price_point, rsi)
                result["trades"].append(trade)
                
                if trade.get("success"):
                    self._record_why_not(pair, WhyNot.TRADE_EXECUTED, side="LONG")
                elif trade.get("error") == "quote_failed":
                    self._record_why_not(pair, WhyNot.QUOTE_FAILED)
                elif trade.get("error") == "swap_tx_failed":
                    self._record_why_not(pair, WhyNot.SWAP_TX_FAILED)
                else:
                    self._record_why_not(
                        pair, 
                        WhyNot.TX_FAILED, 
                        status=trade.get("tx_status"),
                        error=trade.get("tx_error")
                    )
            
            # Update error tracking
            if result["errors"]:
                self._consecutive_errors += len(result["errors"])
                if self._consecutive_errors >= self.cfg.max_consecutive_errors:
                    self.state = EngineState.PAUSED_EXEC_ERRORS
                    self.pause_reason = f"errors={self._consecutive_errors}"
            
            result["duration_ms"] = (asyncio.get_event_loop().time() - tick_start) * 1000
            
            # Log WHY_NOT for all pairs
            for pair in self.cfg.pairs:
                if pair in self._why_not:
                    record = self._why_not[pair]
                    logger.info(record.to_log_line())
            
            # Clear for next tick
            self._why_not.clear()
            
            return result
    
    async def _execute_entry(self, pair: str, price_point: PricePoint, rsi: float) -> dict:
        """
        Execute entry trade for a pair.
        
        Steps:
        1. Set inflight flag
        2. Calculate size and amount
        3. Get quote from Jupiter
        4. Get swap transaction
        5. Execute transaction
        6. Update strategy on success
        7. Clear inflight flag in finally block
        
        Args:
            pair: Trading pair (e.g., "SOL/USDC")
            price_point: Current validated price
            rsi: RSI value from strategy
            
        Returns:
            dict with trade details and success status
        """
        self._pair_states[pair].inflight = True
        
        try:
            base_sym, quote_sym = pair.split("/")
            from otq.config.solana_tokens import get_token
            base_token = get_token(base_sym)
            quote_token = get_token(quote_sym)
            
            notional = self.strategy.config.notional_per_trade
            size_base = notional / price_point.price
            amount_in = int(notional * (10 ** quote_token.decimals))
            
            result = {
                "action": "ENTRY",
                "pair": pair,
                "price": price_point.price,
                "price_source": price_point.source.value,
                "price_age": price_point.age_seconds,
                "size": size_base,
                "notional": notional,
                "rsi": rsi,
                "slippage_bps": self.cfg.slippage_bps,
                "success": False,
            }
            
            logger.info(f"ENTRY_SIGNAL | {pair} | price={price_point.price:.4f} | rsi={rsi:.1f}")
            
            if self.cfg.dry_run:
                logger.info(f"[DRY_RUN] ENTRY | {pair}")
                result["dry_run"] = True
                result["success"] = True
                self.strategy.open_position(pair, price_point.price, size_base)
                return result
            
            # Get quote
            quote = await self.jupiter.get_quote(
                input_mint=quote_token.mint,
                output_mint=base_token.mint,
                amount=amount_in,
                slippage_bps=self.cfg.slippage_bps,
            )
            if quote is None:
                result["error"] = "quote_failed"
                self._consecutive_errors += 1
                return result
            
            result["quote_out"] = quote.get("outAmount")
            
            # Get swap transaction
            tx_bytes = await self.jupiter.get_swap_transaction(quote, self.cfg.wallet_pubkey)
            if tx_bytes is None:
                result["error"] = "swap_tx_failed"
                self._consecutive_errors += 1
                return result
            
            # Execute
            exec_result = await self.tx_executor.execute(tx_bytes)
            result["signature"] = exec_result.signature
            result["tx_status"] = exec_result.status.value
            result["tx_error"] = exec_result.error
            
            if exec_result.status == TxResult.SUCCESS:
                result["success"] = True
                self.strategy.open_position(pair, price_point.price, size_base)
                self._consecutive_errors = 0
                logger.info(f"ENTRY_FILLED | {pair} | sig={exec_result.signature}")
            else:
                self._consecutive_errors += 1
                logger.error(f"ENTRY_FAILED | {pair} | {exec_result.status.value}")
            
            return result
            
        finally:
            self._pair_states[pair].inflight = False
            self._pair_states[pair].last_trade_time = datetime.now(timezone.utc)
    
    async def _execute_exit(self, pair: str, position, price_point: PricePoint, reason: str) -> dict:
        """
        Execute exit trade for a position.
        
        Steps:
        1. Set inflight flag
        2. Calculate PnL and amount
        3. Get quote from Jupiter
        4. Get swap transaction
        5. Execute transaction
        6. Close position on success
        7. Clear inflight flag in finally block
        
        Args:
            pair: Trading pair
            position: Current position object
            price_point: Current validated price
            reason: Exit reason from strategy
            
        Returns:
            dict with trade details and success status
        """
        self._pair_states[pair].inflight = True
        
        try:
            base_sym, quote_sym = pair.split("/")
            from otq.config.solana_tokens import get_token
            base_token = get_token(base_sym)
            quote_token = get_token(quote_sym)
            
            pnl_pct = ((price_point.price - position.entry_price) / position.entry_price) * 100
            amount_in = int(position.size_base * (10 ** base_token.decimals))
            
            result = {
                "action": "EXIT",
                "pair": pair,
                "price": price_point.price,
                "entry_price": position.entry_price,
                "size": position.size_base,
                "pnl_pct": pnl_pct,
                "reason": reason,
                "success": False,
            }
            
            logger.info(f"EXIT_SIGNAL | {pair} | pnl={pnl_pct:.2f}% | reason={reason}")
            
            if self.cfg.dry_run:
                logger.info(f"[DRY_RUN] EXIT | {pair}")
                result["dry_run"] = True
                result["success"] = True
                self.strategy.close_position(pair)
                return result
            
            # Get quote
            quote = await self.jupiter.get_quote(
                input_mint=base_token.mint,
                output_mint=quote_token.mint,
                amount=amount_in,
                slippage_bps=self.cfg.slippage_bps,
            )
            if quote is None:
                result["error"] = "quote_failed"
                self._consecutive_errors += 1
                return result
            
            # Get swap transaction
            tx_bytes = await self.jupiter.get_swap_transaction(quote, self.cfg.wallet_pubkey)
            if tx_bytes is None:
                result["error"] = "swap_tx_failed"
                self._consecutive_errors += 1
                return result
            
            # Execute
            exec_result = await self.tx_executor.execute(tx_bytes)
            result["signature"] = exec_result.signature
            result["tx_status"] = exec_result.status.value
            
            if exec_result.status == TxResult.SUCCESS:
                result["success"] = True
                self.strategy.close_position(pair)
                self._consecutive_errors = 0
                logger.info(f"EXIT_FILLED | {pair} | sig={exec_result.signature} | pnl={pnl_pct:.2f}%")
            else:
                self._consecutive_errors += 1
                logger.error(f"EXIT_FAILED | {pair} | {exec_result.status.value}")
            
            return result
            
        finally:
            self._pair_states[pair].inflight = False
            self._pair_states[pair].last_trade_time = datetime.now(timezone.utc)
    
    async def run(self):
        """
        Main loop - runs tick at configured intervals.
        
        Handles:
        - KeyboardInterrupt for graceful shutdown
        - Tick timing to maintain interval
        - Engine state transitions
        """
        logger.info(f"ENGINE_START | state={self.state.value}")
        
        try:
            while self.state != EngineState.STOPPED:
                tick_start = asyncio.get_event_loop().time()
                
                result = await self.tick()
                self._log_tick(result)
                
                elapsed = asyncio.get_event_loop().time() - tick_start
                sleep_time = max(0, self.cfg.tick_interval_seconds - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
        except KeyboardInterrupt:
            logger.info("ENGINE_INTERRUPT")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Gracefully shutdown all components."""
        self.state = EngineState.STOPPED
        await self.price_oracle.close()
        await self.jupiter.close()
        await self.tx_executor.close()
        logger.info("ENGINE_SHUTDOWN")
    
    def _log_tick(self, result: dict):
        """Log tick summary."""
        if result.get("skipped"):
            logger.debug(f"TICK_SKIP | {result.get('reason')}")
            return
        for t in result.get("trades", []):
            status = "OK" if t.get("success") else "FAIL"
            logger.info(f"TRADE | {t.get('action')} | {t.get('pair')} | {status}")
        logger.debug(f"TICK | {result.get('duration_ms', 0):.0f}ms | errors={self._consecutive_errors}")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def main():
    """Main entry point for the Jupiter DEX Engine."""
    cfg, keypair = load_config_or_exit()
    engine = JupiterDexEngine(cfg, keypair)
    await engine.run()


if __name__ == "__main__":
    asyncio.run(main())

