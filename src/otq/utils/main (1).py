# src/otq/main.py
"""
OT-Tech-Quant (OTQ) Platform - Main Entry Point
================================================
Production-ready multi-strategy trading platform.

Strategies:
1. Intraday MR + Volume (QQQ/SPY) - otq paper / otq live
2. ETF Momentum Rotation (TQQQ/SQQQ/UVXY/GLD) - otq momentum
3. Pairs Statistical Arbitrage - otq pairs
4. Crypto MR (Bybit Perpetuals) - otq crypto
5. Run all strategies in parallel - otq all

Usage:
    otq paper                 # Intraday MR paper trading
    otq live                  # Intraday MR live trading
    otq momentum              # ETF Momentum Rotation
    otq pairs                 # Pairs StatArb
    otq crypto                # Crypto MR on Bybit
    otq all                   # All strategies in parallel
    otq analyze --symbol QQQ  # Analyze a symbol
    otq status                # Account status
"""

import argparse
import sys
import os
import time
import signal
import threading
import multiprocessing
import subprocess
from datetime import datetime, timedelta, time as dtime, timezone
from typing import Optional, Dict, List
from pathlib import Path
import tomllib

import pandas as pd
import numpy as np
from dotenv import load_dotenv
from loguru import logger

# Configure loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    "logs/live/otq_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="DEBUG"
)

# Load environment
load_dotenv()


# =============================================================================
# KYZLO CLI UI - PowerShell 5.1 Compatible (Blue Theme)
# =============================================================================

class KyzloUI:
    """Pretty CLI output for Kyzlo Labs trading platform."""
    
    # ANSI color codes (PowerShell 5.1 compatible)
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"
    DIM = "\033[90m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    
    # Box drawing characters
    BOX_H = "─"
    BOX_V = "│"
    BOX_TL = "┌"
    BOX_TR = "┐"
    BOX_BL = "└"
    BOX_BR = "┘"
    
    @classmethod
    def header(cls, mode: str = "MAINNET", wallet_balance: float = 0.0):
        """Print the Kyzlo Labs startup header."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode_color = cls.GREEN if mode == "MAINNET" else cls.YELLOW
        
        print(f"\n{cls.CYAN}{cls.BOLD}")
        print(f"  ╔═══════════════════════════════════════════════════════════════╗")
        print(f"  ║           {cls.BLUE}██╗  ██╗██╗   ██╗███████╗██╗      ██████╗{cls.CYAN}            ║")
        print(f"  ║           {cls.BLUE}██║ ██╔╝╚██╗ ██╔╝╚══███╔╝██║     ██╔═══██╗{cls.CYAN}           ║")
        print(f"  ║           {cls.BLUE}█████╔╝  ╚████╔╝   ███╔╝ ██║     ██║   ██║{cls.CYAN}           ║")
        print(f"  ║           {cls.BLUE}██╔═██╗   ╚██╔╝   ███╔╝  ██║     ██║   ██║{cls.CYAN}           ║")
        print(f"  ║           {cls.BLUE}██║  ██╗   ██║   ███████╗███████╗╚██████╔╝{cls.CYAN}           ║")
        print(f"  ║           {cls.BLUE}╚═╝  ╚═╝   ╚═╝   ╚══════╝╚══════╝ ╚═════╝{cls.CYAN}            ║")
        print(f"  ║                        {cls.WHITE}L A B S{cls.CYAN}                               ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════╣")
        print(f"  ║  {cls.WHITE}Jupiter DEX Mean-Reversion Engine{cls.CYAN}                           ║")
        print(f"  ║  {cls.DIM}Solana Mainnet │ V1-Lite{cls.CYAN}                                    ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════╣")
        print(f"  ║  {cls.WHITE}Mode:{cls.RESET}    {mode_color}{cls.BOLD}{mode:<12}{cls.RESET}{cls.CYAN}                                      ║")
        print(f"  ║  {cls.WHITE}Time:{cls.RESET}    {cls.DIM}{now}{cls.CYAN}                              ║")
        if wallet_balance > 0:
            print(f"  ║  {cls.WHITE}Wallet:{cls.RESET}  {cls.GREEN}${wallet_balance:,.2f} USDC{cls.CYAN}                                    ║")
        print(f"  ╚═══════════════════════════════════════════════════════════════╝{cls.RESET}\n")
    
    @classmethod
    def session_status(cls, pnl: float, pnl_pct: float, open_positions: int, rsi: float = None):
        """Display session P&L and status bar."""
        pnl_color = cls.GREEN if pnl >= 0 else cls.RED
        pnl_sign = "+" if pnl >= 0 else ""
        rsi_display = f"RSI: {rsi:.1f}" if rsi else "RSI: --"
        
        # RSI color coding
        if rsi:
            if rsi < 30:
                rsi_color = cls.GREEN  # Oversold
            elif rsi > 70:
                rsi_color = cls.RED    # Overbought
            else:
                rsi_color = cls.WHITE
        else:
            rsi_color = cls.DIM
        
        print(f"{cls.CYAN}┌─────────────────────────────────────────────────────────────────┐{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.WHITE}SESSION{cls.RESET}  {pnl_color}{pnl_sign}${pnl:,.2f} ({pnl_sign}{pnl_pct:.2f}%){cls.RESET}  {cls.DIM}│{cls.RESET}  {rsi_color}{rsi_display}{cls.RESET}  {cls.DIM}│{cls.RESET}  {cls.WHITE}Positions:{cls.RESET} {open_positions}  {cls.CYAN}│{cls.RESET}")
        print(f"{cls.CYAN}└─────────────────────────────────────────────────────────────────┘{cls.RESET}")
    
    @classmethod
    def trade_buy(cls, symbol: str, coin_amount: float, usd_value: float, price: float, rsi: float):
        """Display a BUY trade execution."""
        base = symbol.split('/')[0] if '/' in symbol else symbol
        print(f"\n{cls.CYAN}┌─────────────────────────────────────────────────────────────────┐{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.GREEN}{cls.BOLD}▲ BUY{cls.RESET}                                                          {cls.CYAN}│{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.WHITE}{symbol}{cls.RESET}                                                         {cls.CYAN}│{cls.RESET}")
        print(f"{cls.CYAN}├─────────────────────────────────────────────────────────────────┤{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.DIM}Amount:{cls.RESET}    {cls.WHITE}{coin_amount:,.6f} {base}{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.DIM}Value:{cls.RESET}     {cls.GREEN}${usd_value:,.2f} USDC{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.DIM}Price:{cls.RESET}     ${price:,.4f}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.DIM}RSI:{cls.RESET}       {cls.GREEN}{rsi:.1f}{cls.RESET} {cls.DIM}(oversold){cls.RESET}")
        print(f"{cls.CYAN}└─────────────────────────────────────────────────────────────────┘{cls.RESET}")
    
    @classmethod
    def trade_sell(cls, symbol: str, coin_amount: float, usd_value: float, price: float, 
                   rsi: float, entry_price: float, pnl_pct: float):
        """Display a SELL trade execution with P&L."""
        base = symbol.split('/')[0] if '/' in symbol else symbol
        pnl_color = cls.GREEN if pnl_pct >= 0 else cls.RED
        pnl_sign = "+" if pnl_pct >= 0 else ""
        pnl_usd = usd_value * (pnl_pct / 100)
        result_word = "WIN" if pnl_pct >= 0 else "LOSS"
        
        print(f"\n{cls.CYAN}┌─────────────────────────────────────────────────────────────────┐{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.RED}{cls.BOLD}▼ SELL{cls.RESET}                                                         {cls.CYAN}│{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.WHITE}{symbol}{cls.RESET}                                                         {cls.CYAN}│{cls.RESET}")
        print(f"{cls.CYAN}├─────────────────────────────────────────────────────────────────┤{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.DIM}Amount:{cls.RESET}    {cls.WHITE}{coin_amount:,.6f} {base}{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.DIM}Value:{cls.RESET}     {cls.WHITE}${usd_value:,.2f} USDC{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.DIM}Price:{cls.RESET}     ${price:,.4f}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.DIM}Entry:{cls.RESET}     ${entry_price:,.4f}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.DIM}RSI:{cls.RESET}       {cls.RED}{rsi:.1f}{cls.RESET} {cls.DIM}(overbought){cls.RESET}")
        print(f"{cls.CYAN}├─────────────────────────────────────────────────────────────────┤{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.WHITE}P&L:{cls.RESET}       {pnl_color}{cls.BOLD}{pnl_sign}{pnl_pct:.2f}%{cls.RESET}  ({pnl_color}{pnl_sign}${abs(pnl_usd):,.2f}{cls.RESET})  {pnl_color}{result_word}{cls.RESET}")
        print(f"{cls.CYAN}└─────────────────────────────────────────────────────────────────┘{cls.RESET}")
    
    @classmethod
    def signal(cls, symbol: str, signal_type: str, rsi: float, price: float):
        """Display a signal detection."""
        if signal_type.upper() == "BUY":
            sig_color = cls.GREEN
            arrow = "▲"
        elif signal_type.upper() == "SELL":
            sig_color = cls.RED
            arrow = "▼"
        else:
            sig_color = cls.YELLOW
            arrow = "●"
        
        print(f"{cls.DIM}[{datetime.now().strftime('%H:%M:%S')}]{cls.RESET} {sig_color}{arrow} {signal_type}{cls.RESET} {cls.WHITE}{symbol}{cls.RESET} @ ${price:,.4f}  {cls.DIM}RSI:{cls.RESET} {rsi:.1f}")
    
    @classmethod
    def tick(cls, pairs_status: list):
        """Display current tick status for all pairs."""
        now = datetime.now().strftime("%H:%M:%S")
        print(f"\n{cls.DIM}[{now}]{cls.RESET} {cls.CYAN}─────────────────────────────────────────────────{cls.RESET}")
        for pair in pairs_status:
            symbol = pair.get("symbol", "???")
            price = pair.get("price", 0)
            rsi = pair.get("rsi", 0)
            position = pair.get("position", None)
            
            # RSI color
            if rsi < 30:
                rsi_color = cls.GREEN
            elif rsi > 70:
                rsi_color = cls.RED
            else:
                rsi_color = cls.WHITE
            
            pos_indicator = f"{cls.GREEN}●{cls.RESET}" if position else f"{cls.DIM}○{cls.RESET}"
            print(f"  {pos_indicator} {cls.WHITE}{symbol:<12}{cls.RESET} ${price:>10,.4f}  {rsi_color}RSI {rsi:>5.1f}{cls.RESET}")
    
    @classmethod
    def error(cls, message: str):
        """Display an error message."""
        print(f"{cls.RED}{cls.BOLD}✗ ERROR:{cls.RESET} {cls.RED}{message}{cls.RESET}")
    
    @classmethod
    def success(cls, message: str):
        """Display a success message."""
        print(f"{cls.GREEN}{cls.BOLD}✓{cls.RESET} {cls.WHITE}{message}{cls.RESET}")
    
    @classmethod
    def info(cls, message: str):
        """Display an info message."""
        print(f"{cls.CYAN}ℹ{cls.RESET} {cls.DIM}{message}{cls.RESET}")
    
    @classmethod
    def waiting(cls, message: str = "Waiting for signals..."):
        """Display waiting status."""
        print(f"{cls.DIM}[{datetime.now().strftime('%H:%M:%S')}] {message}{cls.RESET}", end='\r')
    
    @classmethod
    def divider(cls):
        """Print a divider line."""
        print(f"{cls.CYAN}{'─' * 65}{cls.RESET}")
    
    @classmethod
    def shutdown(cls):
        """Display shutdown message."""
        print(f"\n{cls.CYAN}┌─────────────────────────────────────────────────────────────────┐{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.YELLOW}■ SHUTTING DOWN{cls.RESET}                                                {cls.CYAN}│{cls.RESET}")
        print(f"{cls.CYAN}│{cls.RESET}  {cls.DIM}Closing positions and saving state...{cls.RESET}                        {cls.CYAN}│{cls.RESET}")
        print(f"{cls.CYAN}└─────────────────────────────────────────────────────────────────┘{cls.RESET}\n")


# Export UI for use by engines
UI = KyzloUI


# =============================================================================
# OPTIONAL HYBRID MARKET DATA (Polygon primary, CoinGecko fallback)
# =============================================================================


def _load_market_data_config():
    """Read market_data flag and API overrides from config/settings.toml if present."""
    cfg_path = Path(__file__).resolve().parents[2] / "config" / "settings.toml"
    if not cfg_path.exists():
        return {"use_hybrid_market_data": False}
    try:
        with cfg_path.open("rb") as f:
            data = tomllib.load(f)
        md = data.get("market_data", {}) or {}
        cg = data.get("coingecko", {}) or {}
        poly = data.get("polygon", {}) or {}
        return {
            "use_hybrid_market_data": bool(md.get("use_hybrid_market_data", False)),
            "coingecko_api_key": cg.get("api_key"),
            "polygon_api_key": poly.get("api_key"),
            "polygon_base_url": poly.get("base_url", "https://api.polygon.io"),
        }
    except Exception as exc:  # pragma: no cover - config guard
        logger.warning(f"Could not parse settings.toml: {exc}")
        return {"use_hybrid_market_data": False}


def create_market_data_port():
    """
    Factory for MarketDataPort honoring market_data.use_hybrid_market_data.
    Returns None when hybrid flag is false to keep existing behavior unchanged.
    """
    cfg = _load_market_data_config()
    if not cfg.get("use_hybrid_market_data"):
        logger.info("Hybrid market data disabled; retaining existing feeds.")
        return None

    try:
        from src.adapters.market_data.alpha_vantage_adapter import AlphaVantageAdapter
        from src.adapters.market_data.coingecko_adapter import CoinGeckoMarketDataAdapter
        from src.application.services.hybrid_market_data import HybridMarketDataService
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(f"Hybrid market data enabled but adapters unavailable: {exc}") from exc

    coingecko_key = os.getenv("COINGECKO_API_KEY") or cfg.get("coingecko_api_key") or ""
    alpha_key = os.getenv("ALPHAVANTAGE_API_KEY") or cfg.get("alphavantage_api_key")

    # Hard rule: never call Polygon for crypto. Polygon adapter intentionally omitted.
    polygon = None
    coingecko = CoinGeckoMarketDataAdapter(
        api_key=coingecko_key,
        min_interval_seconds=12.0,
        backoff_base_seconds=5.0,
        cache_ttl=120,
    )
    alpha = AlphaVantageAdapter(api_key=alpha_key) if alpha_key else None
    svc = HybridMarketDataService(polygon, coingecko, alpha_vantage_adapter=alpha, enabled=True)
    if alpha:
        logger.info("Hybrid market data enabled: CoinGecko-only for crypto + Alpha Vantage for intraday equities backfill")
    else:
        logger.info("Hybrid market data enabled: CoinGecko-only (Polygon disabled for crypto); Alpha Vantage not configured")
    return svc


# =============================================================================
# STRATEGY IMPORTS
# =============================================================================

# Keep `otq.main` import-light so the coordinator/perps CLI can run without
# optional heavy dependencies (e.g. torch). Commands that require these
# strategies will validate availability at call time.
try:
    from otq.strategies.golden_cross import GoldenCrossStrategy
except Exception:  # pragma: no cover
    GoldenCrossStrategy = None  # type: ignore

try:
    from otq.strategies.intraday_mr_volume_pro import (
        IntradayMRVolumePro,
        IntradayMRVolumeProGPU,
        StrategyConfig,
        SignalType,
    )
except Exception:  # pragma: no cover
    IntradayMRVolumePro = None  # type: ignore
    IntradayMRVolumeProGPU = None  # type: ignore
    StrategyConfig = None  # type: ignore
    SignalType = None  # type: ignore

try:
    from otq.strategies.etf_momentum_rotation import (
        ETFMomentumRotation,
        MomentumConfig,
        MomentumSignal,
    )
except Exception:  # pragma: no cover
    ETFMomentumRotation = None  # type: ignore
    MomentumConfig = None  # type: ignore
    MomentumSignal = None  # type: ignore

try:
    from otq.strategies.pairs_statarb import (
        PairsStatArb,
        PairsConfig,
        PairSignal,
    )
except Exception:  # pragma: no cover
    PairsStatArb = None  # type: ignore
    PairsConfig = None  # type: ignore
    PairSignal = None  # type: ignore

try:
    from otq.strategies.crypto_mr_intraday import (
        CryptoMRIntraday,
        CryptoMRConfig,
        CryptoSignalType,
    )
except Exception:  # pragma: no cover
    CryptoMRIntraday = None  # type: ignore
    CryptoMRConfig = None  # type: ignore
    CryptoSignalType = None  # type: ignore

try:
    from otq.backtesting.engine import BacktestEngine
    from otq.analytics.tearsheet import TearsheetGenerator
except Exception:  # pragma: no cover
    BacktestEngine = None  # type: ignore
    TearsheetGenerator = None  # type: ignore


# =============================================================================
# BACKTEST COMMAND
# =============================================================================

def command_backtest(args):
    """Run strategy backtest."""
    import requests
    
    symbol = getattr(args, 'symbol', 'SPY')
    strategy_name = getattr(args, 'strategy', 'golden_cross')
    
    print(f"🏭 Initializing Backtest for {symbol}...")

    if strategy_name == "intraday_mr":
        if IntradayMRVolumeProGPU is None:
            print("❌ intraday_mr strategy unavailable (missing optional deps like torch)")
            return
        strategy = IntradayMRVolumeProGPU()
    else:
        if GoldenCrossStrategy is None:
            print("❌ golden_cross strategy unavailable (missing optional deps like torch)")
            return
        strategy = GoldenCrossStrategy()
    
    print(f"   📊 Strategy: {strategy.name}")

    poly_key = os.getenv("POLYGON_API_KEY")
    if not poly_key:
        print("❌ POLYGON_API_KEY not found")
        return
    
    end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
    
    print(f"   [DATA] Fetching {symbol} ({start_date} -> {end_date})...")
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}?adjusted=true&sort=asc&limit=5000&apiKey={poly_key}"
    
    try:
        resp = requests.get(url).json()
        if resp.get("status") != "OK":
            print(f"❌ Data Download Failed: {resp}")
            return
        
        df = pd.DataFrame(resp["results"])
        df['datetime'] = pd.to_datetime(df['t'], unit='ms')
        df.set_index('datetime', inplace=True)
        
    except Exception as e:
        print(f"❌ Critical Data Failure: {e}")
        return

    if BacktestEngine is None or TearsheetGenerator is None:
        print("❌ Backtesting components unavailable (missing optional deps)")
        return

    engine = BacktestEngine(strategy)
    results = engine.run(df)
    engine.report()
    
    tearsheet = TearsheetGenerator(results)
    tearsheet.generate("latest_backtest.png")
    
    print("✅ Backtest Complete.")


# =============================================================================
# INTRADAY MR LIVE TRADING ENGINE
# =============================================================================

class LiveTradingEngine:
    """Intraday MR + Volume Explosion live trading engine."""
    
    def __init__(self, paper: bool = True, reports_dir: str = "reports"):
        self.paper = paper
        self.reports_dir = reports_dir
        self.running = False
        self._shutdown_event = threading.Event()
        
        self._init_strategy()
        self._init_data_adapter()
        self._init_broker()
        self._init_reporter()
        
        self.regime_checked_today = False
        self.regime_valid = False
        self.last_signal_check = datetime.min
        
        mode = "PAPER" if paper else "🔴 LIVE"
        logger.info(f"LiveTradingEngine initialized in {mode} mode")
    
    class _MockIntradayDataAdapter:
        """Lightweight mock/EOD adapter to avoid live Polygon when unavailable."""

        def __init__(self, symbols):
            self.symbols = symbols

        def start(self, backfill_days: int = 1):
            logger.warning("Mock intraday data adapter active (no live bars).")

        def stop(self):
            return

        def fetch_vix_close(self):
            return 20.0

        def fetch_spy_daily_bars(self, days: int = 20):
            return pd.DataFrame()

        def get_bars_5min(self, symbol: str, n: int = 250):
            return pd.DataFrame()

        def get_bars_1min(self, symbol: str, n: int = 100):
            return pd.DataFrame()

        def get_latest_price(self, symbol: str):
            return None

        def get_latest_prices(self):
            return {}
    
    def _init_strategy(self):
        config = StrategyConfig(
            symbols=["QQQ", "SPY"],
            rsi_oversold=27.0,
            rsi_overbought=73.0,
            volume_multiplier=2.3,
            profit_target_pct=0.37,
            stop_loss_pct=0.41,
            max_hold_minutes=11,
            risk_per_trade_pct=4.0,
            max_concurrent_positions=4
        )
        self.strategy = IntradayMRVolumePro(config)
        logger.info(f"Strategy loaded: {self.strategy.name}")
    
    def _init_data_adapter(self):
        use_mock = os.getenv("OTQ_INTRADAY_DATA_MODE", "").lower() in {"mock", "eod"} or os.getenv("CODE_INTERPRETER")
        if use_mock:
            logger.warning("Using mock/EOD intraday data adapter (Polygon SIP disabled).")
            self.data_adapter = self._MockIntradayDataAdapter(self.strategy.config.symbols)
            return

        from otq.data.vendors.polygon_sip_adapter import PolygonSIPAdapter
        
        api_key = os.getenv("POLYGON_API_KEY")
        if not api_key:
            logger.warning("POLYGON_API_KEY missing; falling back to mock intraday data adapter.")
            self.data_adapter = self._MockIntradayDataAdapter(self.strategy.config.symbols)
            return
        
        try:
            self.data_adapter = PolygonSIPAdapter(
                api_key=api_key,
                symbols=self.strategy.config.symbols,
                on_bar_1min=self._on_bar_1min,
                on_bar_5min=self._on_bar_5min
            )
        except Exception as exc:
            logger.error(f"Polygon SIP adapter init failed; using mock adapter instead: {exc}")
            self.data_adapter = self._MockIntradayDataAdapter(self.strategy.config.symbols)
    
    def _init_broker(self):
        from otq.live.brokers.alpaca_pro_adapter import AlpacaProAdapter
        
        api_key = os.getenv("ALPACA_API_KEY")
        secret_key = os.getenv("ALPACA_SECRET_KEY")
        
        if not api_key or not secret_key:
            raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set")
        
        self.broker = AlpacaProAdapter(
            api_key=api_key,
            secret_key=secret_key,
            paper=self.paper
        )
    
    def _init_reporter(self):
        from otq.analytics.live_reporter import LiveReporter
        
        self.reporter = LiveReporter(
            reports_dir=self.reports_dir,
            strategy_name=self.strategy.name
        )
        self.reporter.load_state()
    
    def start(self):
        logger.info("=" * 60)
        logger.info("🚀 STARTING INTRADAY MR ENGINE")
        logger.info("=" * 60)
        
        self.running = True
        self.data_adapter.start(backfill_days=1)
        
        time.sleep(5)
        
        account = self.broker.get_account()
        logger.info(f"Account Equity: ${account.equity:,.2f}")
        
        self.reporter.start_new_day(account.equity)
        
        try:
            self._run_trading_loop()
        except KeyboardInterrupt:
            from otq.utils.shutdown import request_stop
            request_stop()
        finally:
            self.stop()
    
    def stop(self):
        logger.info("Stopping engine...")
        self.running = False
        self._shutdown_event.set()
        self.broker.close_all_positions()
        self.broker.cancel_all_orders()
        self.data_adapter.stop()
        self.reporter.end_of_day_reports(auto_push=not self.paper)
        self.reporter.save_state()
    
    def _run_trading_loop(self):
        while self.running and not self._shutdown_event.is_set():
            try:
                now = datetime.now()
                current_time = now.time()
                
                market_open = dtime(9, 30)
                market_close = dtime(16, 0)
                
                if current_time < market_open:
                    wait_seconds = (datetime.combine(now.date(), market_open) - now).total_seconds()
                    self._wait_interruptible(min(wait_seconds, 60))
                    continue
                
                if current_time >= market_close:
                    self.reporter.end_of_day_reports(auto_push=not self.paper)
                    self.reporter.save_state()
                    self.regime_checked_today = False
                    self.strategy.reset_daily_state()
                    next_open = datetime.combine(now.date() + timedelta(days=1), market_open)
                    wait_seconds = (next_open - now).total_seconds()
                    self._wait_interruptible(min(wait_seconds, 3600))
                    continue
                
                if not self.regime_checked_today and current_time >= market_open:
                    self._check_regime_filter()
                    self.regime_checked_today = True
                
                if not self.regime_valid:
                    self._wait_interruptible(300)
                    continue
                
                trading_start = dtime(9, 45)
                trading_end = dtime(15, 45)
                
                if trading_start <= current_time <= trading_end:
                    self._check_exits()
                    
                    if (now - self.last_signal_check).total_seconds() >= 60:
                        self._check_signals()
                        self.last_signal_check = now
                    
                    account = self.broker.get_account()
                    self.reporter.record_equity(now, account.equity)
                
                self._wait_interruptible(1)
                
            except Exception as e:
                logger.error(f"Error: {e}")
                self._wait_interruptible(10)
    
    def _check_regime_filter(self):
        vix_close = self.data_adapter.fetch_vix_close() or 20.0
        spy_daily = self.data_adapter.fetch_spy_daily_bars(days=20)
        
        if spy_daily.empty:
            self.regime_valid = True
            return
        
        is_valid, reason = self.strategy.check_daily_regime(vix_close, spy_daily)
        self.regime_valid = is_valid
        
        if is_valid:
            logger.info(f"✅ Regime filter PASSED: {reason}")
        else:
            logger.warning(f"❌ Regime filter FAILED: {reason}")
    
    def _check_signals(self):
        for symbol in self.strategy.config.symbols:
            try:
                bars_5min = self.data_adapter.get_bars_5min(symbol, n=250)
                bars_1min = self.data_adapter.get_bars_1min(symbol, n=100)
                
                if bars_5min.empty or bars_1min.empty:
                    continue
                
                account = self.broker.get_account()
                signal = self.strategy.generate_signal(
                    symbol=symbol,
                    bars_5min=bars_5min,
                    bars_1min=bars_1min,
                    current_time=datetime.now(),
                    current_equity=account.equity
                )
                
                if signal:
                    self._execute_signal(signal, account.equity)
                    
            except Exception as e:
                logger.error(f"Signal error for {symbol}: {e}")
    
    def _execute_signal(self, signal, current_equity: float):
        logger.info(f"🎯 SIGNAL: {signal.signal_type.name} {signal.symbol} @ ${signal.entry_price:.2f}")
        
        current_price = self.data_adapter.get_latest_price(signal.symbol) or signal.entry_price
        shares = self.strategy.calculate_position_size(signal, current_equity, current_price)
        
        if shares <= 0:
            return
        
        side = "buy" if signal.signal_type == SignalType.LONG else "sell"
        result = self.broker.submit_market_order(symbol=signal.symbol, qty=shares, side=side)
        
        if result.status.value == "filled":
            logger.info(f"✅ FILLED: {side.upper()} {shares} {signal.symbol} @ ${result.filled_avg_price:.2f}")
            self.strategy.open_position(signal, shares, result.filled_avg_price)
    
    def _check_exits(self):
        positions = self.strategy.get_positions()
        if not positions:
            return
        
        current_prices = self.data_adapter.get_latest_prices()
        exits = self.strategy.check_exits(current_prices, datetime.now())
        
        for symbol, reason in exits:
            self._execute_exit(symbol, reason)
    
    def _execute_exit(self, symbol: str, reason: str):
        position = self.strategy.get_positions().get(symbol)
        if not position:
            return
        
        logger.info(f"🚪 EXIT: {symbol} - {reason}")
        
        side = "sell" if position.side == SignalType.LONG else "buy"
        result = self.broker.submit_market_order(symbol=symbol, qty=position.shares, side=side)
        
        if result.status.value == "filled":
            if position.side == SignalType.LONG:
                pnl = (result.filled_avg_price - position.entry_price) * position.shares
            else:
                pnl = (position.entry_price - result.filled_avg_price) * position.shares
            
            self.reporter.record_trade(
                symbol=symbol,
                side=position.side.name.lower(),
                entry_price=position.entry_price,
                exit_price=result.filled_avg_price,
                shares=position.shares,
                entry_time=position.entry_time,
                exit_time=datetime.now(),
                exit_reason=reason
            )
            
            self.strategy.close_position(symbol)
            logger.info(f"   P&L: ${pnl:+,.2f}")
    
    def _on_bar_1min(self, symbol: str, bar):
        pass
    
    def _on_bar_5min(self, symbol: str, bar):
        pass
    
    def _wait_interruptible(self, seconds: float):
        self._shutdown_event.wait(timeout=seconds)


# =============================================================================
# ETF MOMENTUM ROTATION ENGINE
# =============================================================================

class MomentumTradingEngine:
    """ETF Momentum Rotation trading engine."""
    
    def __init__(self, paper: bool = True):
        self.paper = paper
        self.running = False
        self._shutdown_event = threading.Event()
        
        self.strategy = ETFMomentumRotation()
        self._init_broker()
        self._init_reporter()
        
        logger.info(f"MomentumTradingEngine initialized: {self.strategy.name}")
    
    def _init_broker(self):
        from otq.live.brokers.alpaca_pro_adapter import AlpacaProAdapter
        
        self.broker = AlpacaProAdapter(
            api_key=os.getenv("ALPACA_API_KEY"),
            secret_key=os.getenv("ALPACA_SECRET_KEY"),
            paper=self.paper
        )
    
    def _init_reporter(self):
        from otq.analytics.live_reporter import LiveReporter
        
        self.reporter = LiveReporter(
            reports_dir="reports/momentum",
            strategy_name=self.strategy.name
        )
        self.reporter.load_state()
    
    def start(self):
        logger.info("=" * 60)
        logger.info("🔄 STARTING ETF MOMENTUM ROTATION ENGINE")
        logger.info("=" * 60)
        
        self.running = True
        
        account = self.broker.get_account()
        logger.info(f"Account Equity: ${account.equity:,.2f}")
        self.reporter.start_new_day(account.equity)
        
        try:
            self._run_trading_loop()
        except KeyboardInterrupt:
            from otq.utils.shutdown import request_stop
            request_stop()
        finally:
            self.stop()
    
    def stop(self):
        self.running = False
        self._shutdown_event.set()
        self.reporter.end_of_day_reports(auto_push=not self.paper)
        self.reporter.save_state()
    
    def _run_trading_loop(self):
        import requests
        
        poly_key = os.getenv("POLYGON_API_KEY")
        
        while self.running and not self._shutdown_event.is_set():
            try:
                now = datetime.now()
                current_time = now.time()
                
                # Daily rebalance at 15:55
                rebalance_time = dtime(15, 55)
                
                if current_time >= rebalance_time and current_time < dtime(15, 56):
                    logger.info("Checking momentum signals...")
                    
                    # Fetch ETF data
                    etf_data = {}
                    for symbol in self.strategy.config.symbols:
                        df = self._fetch_daily_data(symbol, poly_key, days=300)
                        if not df.empty:
                            etf_data[symbol] = df
                    
                    # Fetch VIX
                    vix_df = self._fetch_daily_data("VIX", poly_key, days=5)
                    vix_close = vix_df['c'].iloc[-1] if not vix_df.empty else 20.0
                    
                    account = self.broker.get_account()
                    
                    signal = self.strategy.generate_signal(
                        etf_data=etf_data,
                        vix_close=vix_close,
                        current_time=now,
                        current_equity=account.equity
                    )
                    
                    if signal:
                        logger.info(f"Signal: {signal.target_etf.value} - {signal.reason}")
                        self._execute_rotation(signal, account.equity)
                    
                    self.reporter.record_equity(now, account.equity)
                    
                    # Sleep until next day
                    self._wait_interruptible(3600)
                else:
                    self._wait_interruptible(60)
                    
            except Exception as e:
                logger.error(f"Error: {e}")
                self._wait_interruptible(60)
    
    def _fetch_daily_data(self, symbol: str, api_key: str, days: int = 300) -> pd.DataFrame:
        import requests
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days + 50)).strftime('%Y-%m-%d')
        
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}?adjusted=true&sort=asc&limit=5000&apiKey={api_key}"
        
        try:
            resp = requests.get(url).json()
            if resp.get("status") == "OK" and resp.get("results"):
                df = pd.DataFrame(resp["results"])
                df['datetime'] = pd.to_datetime(df['t'], unit='ms')
                df.set_index('datetime', inplace=True)
                return df
        except Exception as e:
            logger.error(f"Failed to fetch {symbol}: {e}")
        
        return pd.DataFrame()
    
    def _execute_rotation(self, signal, equity: float):
        current_position = self.strategy.get_current_position()
        
        should_rebalance, reason = self.strategy.should_rebalance(signal, current_position)
        
        if not should_rebalance:
            logger.info(f"No rebalance needed: {reason}")
            return
        
        logger.info(f"Rebalancing: {reason}")
        
        # Close current position
        if current_position:
            result = self.broker.close_position(current_position.symbol)
            logger.info(f"Closed {current_position.symbol}")
        
        # Open new position
        if signal.target_etf != MomentumSignal.CASH:
            target_symbol = signal.target_etf.value
            current_price = self._get_current_price(target_symbol)
            
            if current_price:
                shares = self.strategy.calculate_target_shares(signal, equity, current_price)
                
                if shares > 0:
                    result = self.broker.submit_market_order(
                        symbol=target_symbol,
                        qty=shares,
                        side="buy"
                    )
                    
                    if result.status.value == "filled":
                        logger.info(f"Bought {shares} {target_symbol} @ ${result.filled_avg_price:.2f}")
                        self.strategy.update_position(
                            target_symbol, shares, result.filled_avg_price, signal.target_weight
                        )
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        try:
            positions = self.broker.get_positions()
            if symbol in positions:
                return positions[symbol].current_price
            
            # Fallback to fetching
            df = self._fetch_daily_data(symbol, os.getenv("POLYGON_API_KEY"), days=1)
            if not df.empty:
                return df['c'].iloc[-1]
        except Exception:
            pass
        return None
    
    def _wait_interruptible(self, seconds: float):
        self._shutdown_event.wait(timeout=seconds)


# =============================================================================
# PAIRS STATARB ENGINE
# =============================================================================

class PairsArbEngine:
    """Pairs Statistical Arbitrage trading engine."""
    
    def __init__(self, paper: bool = True):
        self.paper = paper
        self.running = False
        self._shutdown_event = threading.Event()
        
        self.strategy = PairsStatArb()
        self._init_broker()
        self._init_reporter()
        
        logger.info(f"PairsArbEngine initialized: {self.strategy.name}")
    
    def _init_broker(self):
        from otq.live.brokers.alpaca_pro_adapter import AlpacaProAdapter
        
        self.broker = AlpacaProAdapter(
            api_key=os.getenv("ALPACA_API_KEY"),
            secret_key=os.getenv("ALPACA_SECRET_KEY"),
            paper=self.paper
        )
    
    def _init_reporter(self):
        from otq.analytics.live_reporter import LiveReporter
        
        self.reporter = LiveReporter(
            reports_dir="reports/pairs",
            strategy_name=self.strategy.name
        )
        self.reporter.load_state()
    
    def start(self):
        logger.info("=" * 60)
        logger.info("📊 STARTING PAIRS STATARB ENGINE")
        logger.info("=" * 60)
        
        self.running = True
        
        account = self.broker.get_account()
        logger.info(f"Account Equity: ${account.equity:,.2f}")
        self.reporter.start_new_day(account.equity)
        
        try:
            self._run_trading_loop()
        except KeyboardInterrupt:
            from otq.utils.shutdown import request_stop
            request_stop()
        finally:
            self.stop()
    
    def stop(self):
        self.running = False
        self._shutdown_event.set()
        self.reporter.end_of_day_reports(auto_push=not self.paper)
        self.reporter.save_state()
    
    def _run_trading_loop(self):
        poly_key = os.getenv("POLYGON_API_KEY")
        all_symbols = set()
        for a, b in self.strategy.config.pairs:
            all_symbols.add(a)
            all_symbols.add(b)
        
        while self.running and not self._shutdown_event.is_set():
            try:
                now = datetime.now()
                current_time = now.time()
                
                # Check signals at 10:00
                if current_time >= dtime(10, 0) and current_time < dtime(10, 1):
                    logger.info("Checking pairs signals...")
                    
                    # Fetch data for all symbols
                    price_data = {}
                    for symbol in all_symbols:
                        df = self._fetch_daily_data(symbol, poly_key, days=100)
                        if not df.empty:
                            price_data[symbol] = df
                    
                    # Check exits first
                    exits = self.strategy.check_exits(price_data, now)
                    for pair_id, reason in exits:
                        self._execute_pair_exit(pair_id, reason, price_data)
                    
                    # Generate new signals
                    signals = self.strategy.generate_signals(price_data, now)
                    
                    account = self.broker.get_account()
                    for signal in signals:
                        self._execute_pair_entry(signal, account.equity, price_data)
                    
                    self.reporter.record_equity(now, account.equity)
                    
                    # Wait until next check
                    self._wait_interruptible(3600)
                else:
                    self._wait_interruptible(60)
                    
            except Exception as e:
                logger.error(f"Error: {e}")
                self._wait_interruptible(60)
    
    def _fetch_daily_data(self, symbol: str, api_key: str, days: int = 100) -> pd.DataFrame:
        import requests
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days + 30)).strftime('%Y-%m-%d')
        
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}?adjusted=true&sort=asc&limit=5000&apiKey={api_key}"
        
        try:
            resp = requests.get(url).json()
            if resp.get("status") == "OK" and resp.get("results"):
                df = pd.DataFrame(resp["results"])
                df['datetime'] = pd.to_datetime(df['t'], unit='ms')
                df.set_index('datetime', inplace=True)
                return df
        except Exception as e:
            logger.error(f"Failed to fetch {symbol}: {e}")
        
        return pd.DataFrame()
    
    def _execute_pair_entry(self, signal, equity: float, price_data: Dict):
        pair = signal.pair
        
        close_col = 'c' if 'c' in price_data[pair.symbol_a].columns else 'close'
        price_a = price_data[pair.symbol_a][close_col].iloc[-1]
        price_b = price_data[pair.symbol_b][close_col].iloc[-1]
        
        shares_a, shares_b = self.strategy.calculate_position_sizes(
            signal, equity, price_a, price_b
        )
        
        logger.info(f"🎯 Pairs Entry: {pair.pair_id} Z={signal.z_score:.2f}")
        logger.info(f"   {pair.symbol_a}: {shares_a} shares @ ${price_a:.2f}")
        logger.info(f"   {pair.symbol_b}: {shares_b} shares @ ${price_b:.2f}")
        
        # Execute both legs
        side_a = "buy" if shares_a > 0 else "sell"
        side_b = "buy" if shares_b > 0 else "sell"
        
        result_a = self.broker.submit_market_order(pair.symbol_a, abs(shares_a), side_a)
        result_b = self.broker.submit_market_order(pair.symbol_b, abs(shares_b), side_b)
        
        if result_a.status.value == "filled" and result_b.status.value == "filled":
            self.strategy.open_position(
                signal, shares_a, shares_b,
                result_a.filled_avg_price, result_b.filled_avg_price
            )
            logger.info(f"✅ Pairs position opened: {pair.pair_id}")
    
    def _execute_pair_exit(self, pair_id: str, reason: str, price_data: Dict):
        position = self.strategy.get_positions().get(pair_id)
        if not position:
            return
        
        logger.info(f"🚪 Pairs Exit: {pair_id} - {reason}")
        
        # Close both legs
        if position.shares_a != 0:
            side_a = "sell" if position.shares_a > 0 else "buy"
            self.broker.submit_market_order(position.pair.symbol_a, abs(position.shares_a), side_a)
        
        if position.shares_b != 0:
            side_b = "sell" if position.shares_b > 0 else "buy"
            self.broker.submit_market_order(position.pair.symbol_b, abs(position.shares_b), side_b)
        
        self.strategy.close_position(pair_id)
        logger.info(f"✅ Pairs position closed: {pair_id}")
    
    def _wait_interruptible(self, seconds: float):
        self._shutdown_event.wait(timeout=seconds)


# =============================================================================
# CRYPTO MR ENGINE
# =============================================================================

class CryptoMREngine:
    """
    Crypto MR trading engine.
    
    Supports:
    - Bybit perpetuals (global, default)
    - Binance.US spot (for US traders)
    
    Set CRYPTO_EXCHANGE=binanceus in .env for US traders.
    """
    
    def __init__(
        self,
        testnet: bool = True,
        paper: bool = True,
        exchange: Optional[str] = None,
        config: Optional["CryptoMRConfig"] = None,
        reports_dir: str = "reports/crypto",
        name: Optional[str] = None,
        *,
        portfolio_manager=None,
        portfolio_state=None,
    ):
        self.testnet = testnet
        self.paper = bool(paper)
        self.running = False
        self._shutdown_event = threading.Event()
        self.reports_dir = reports_dir
        self.engine_name = name or "Crypto MR Engine"
        
        # Determine which exchange to use
        self.exchange_name = exchange or os.getenv("CRYPTO_EXCHANGE", "bybit").lower()
        
        # Strategy selection
        if config is not None:
            self.strategy = CryptoMRIntraday(config)
        elif self.exchange_name == "binanceus":
            from otq.strategies.crypto_mr_intraday import CryptoMRConfig
            self.strategy = CryptoMRIntraday(CryptoMRConfig(
                symbols=["BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD"]
            ))
        else:
            self.strategy = CryptoMRIntraday()
        
        self._init_data_adapter()
        self._init_reporter()

        # Optional portfolio/router layer (default off to avoid breaking single-venue runs)
        # If injected, coordinator owns lifecycle.
        self._owns_portfolio_manager = False
        self.portfolio_manager = portfolio_manager
        self.portfolio_state = portfolio_state
        self.enable_portfolio_manager = bool(self.portfolio_manager and self.portfolio_state) or (
            os.getenv("OTQ_ENABLE_PORTFOLIO_MANAGER", "0").lower() in {"1", "true", "yes", "on"}
        )

        if self.enable_portfolio_manager and (self.portfolio_manager is None or self.portfolio_state is None):
            from otq.portfolio import PortfolioManager, PortfolioManagerConfig, PortfolioState

            enabled_venues = {"binanceus" if self.exchange_name == "binanceus" else "bybit"}
            cfg = PortfolioManagerConfig(
                enabled_venues=enabled_venues,
                strategy_priority=["crypto_mr_intraday"],
                max_positions_total=int(os.getenv("OTQ_MAX_POSITIONS_TOTAL", "10")),
                max_exposure_per_asset=float(os.getenv("OTQ_MAX_EXPOSURE_PER_ASSET", "10000")),
                allow_multi_venue_exposure=os.getenv("OTQ_ALLOW_MULTI_VENUE_EXPOSURE", "0").lower() in {"1", "true", "yes", "on"},
                max_venues_per_symbol=int(os.getenv("OTQ_MAX_VENUES_PER_SYMBOL", "1")),
                decision_audit_path=os.getenv("OTQ_DECISION_AUDIT_PATH"),
            )
            self.portfolio_manager = PortfolioManager(cfg)
            self.portfolio_state = PortfolioState()
            self._owns_portfolio_manager = True
            logger.info(f"PortfolioManager enabled for {self.engine_name}")
        
        logger.info(f"{self.engine_name} initialized on {self.exchange_name.upper()}")

        # Optional: emit one concise decision log per evaluated symbol.
        # Off by default to avoid noisy INFO logs.
        self._decision_log_enabled = os.getenv("CRYPTO_DECISION_LOG", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    
    def _init_data_adapter(self):
        if self.exchange_name == "binanceus":
            # Binance.US for US traders (spot only)
            from otq.data.vendors.binance_us_adapter import BinanceUSAdapter
            
            self.data_adapter = BinanceUSAdapter(
                symbols=self.strategy.config.symbols,
                paper=self.paper,
                on_bar_1min=self._on_bar_1min,
                on_bar_5min=self._on_bar_5min
            )
            logger.info("Using Binance.US (spot) - smaller edges but US-legal")
        else:
            # Bybit blocked: fall back to hybrid pull-based data + paper exec
            try:
                from src.adapters.market_data.polygon_adapter import PolygonMarketDataAdapter
                from src.adapters.market_data.coingecko_adapter import CoinGeckoMarketDataAdapter
                from src.application.services.hybrid_market_data import HybridMarketDataService
                from otq.data.vendors.hybrid_pull_adapter import HybridPullAdapter
            except Exception as exc:
                raise RuntimeError(f"Hybrid market data unavailable: {exc}") from exc

            polygon_key = os.getenv("POLYGON_API_KEY")
            if not polygon_key:
                raise RuntimeError("POLYGON_API_KEY required for hybrid crypto feed.")
            coingecko_key = os.getenv("COINGECKO_API_KEY", "")

            polygon = PolygonMarketDataAdapter(api_key=polygon_key)
            coingecko = CoinGeckoMarketDataAdapter(api_key=coingecko_key)
            hybrid = HybridMarketDataService(polygon, coingecko, enabled=True, cache_ttl_seconds=5)

            self.data_adapter = HybridPullAdapter(
                hybrid_service=hybrid,
                symbols=self.strategy.config.symbols,
                starting_cash=10_000.0,
            )
            logger.info("Using hybrid pull-based market data (Polygon primary, CoinGecko fallback) with paper execution for crypto.")
    
    def _init_reporter(self):
        from otq.analytics.live_reporter import LiveReporter
        
        self.reporter = LiveReporter(
            reports_dir=self.reports_dir,
            strategy_name=self.strategy.name
        )
        self.reporter.load_state()
    
    def start(self):
        logger.info("=" * 60)
        logger.info(f"🪙 STARTING {self.engine_name} (24/7) - {self.exchange_name.upper()}")
        logger.info("=" * 60)
        
        self.running = True
        self.data_adapter.start(backfill_bars=300)
        
        time.sleep(5)
        
        # Get balance (USD for Binance.US, USDT for Bybit)
        if self.exchange_name == "binanceus":
            balance = self.data_adapter.get_balance('USD')
            logger.info(f"USD Balance: ${balance['total']:,.2f}")
        else:
            balance = self.data_adapter.get_balance()
            logger.info(f"USDT Balance: ${balance['total']:,.2f}")
        
        self.reporter.start_new_day(balance['total'])

        if self.enable_portfolio_manager and self.portfolio_manager:
            self.portfolio_manager.risk.on_day_start(balance['total'], datetime.now(timezone.utc).replace(tzinfo=None))
        
        try:
            self._run_trading_loop()
        except KeyboardInterrupt:
            from otq.utils.shutdown import request_stop
            request_stop()
        finally:
            self.stop()
    
    def stop(self):
        self.running = False
        self._shutdown_event.set()
        
        # Close all positions (different methods for each exchange)
        try:
            if self.exchange_name == "binanceus":
                # Binance.US: sell all crypto holdings
                positions = self.data_adapter.get_positions()
                by_symbol = positions.get("_by_symbol") if isinstance(positions, dict) else None
                if isinstance(by_symbol, dict) and by_symbol:
                    for symbol, amount in by_symbol.items():
                        if isinstance(amount, (int, float)) and float(amount) > 0:
                            self.data_adapter.close_position(symbol)
                elif isinstance(positions, dict):
                    for currency, amount in positions.items():
                        if str(currency).startswith("_"):
                            continue
                        if isinstance(amount, (int, float)) and float(amount) > 0:
                            symbol = f"{currency}/USD"
                            self.data_adapter.close_position(symbol)
            else:
                # Bybit: close perpetual positions
                for pos in self.data_adapter.get_all_positions():
                    self.data_adapter.close_position(pos['symbol'])
        except Exception as e:
            logger.error(f"Error closing positions: {e}")
        
        self.data_adapter.stop()

        if self.enable_portfolio_manager and self.portfolio_manager and self._owns_portfolio_manager:
            # Publish kill switch status + blockers into markdown report.
            try:
                self.reporter.set_kill_switch_status(
                    paused=self.portfolio_manager.risk.trading_paused,
                    reason=self.portfolio_manager.risk.paused_reason,
                    at_utc=self.portfolio_manager.risk.paused_at_utc,
                )
                self.reporter.set_blocked_reason_summary(self.portfolio_manager.blocked)
            except Exception as exc:  # pragma: no cover
                logger.warning(f"Failed to attach router summaries to reporter: {exc}")
            finally:
                self.portfolio_manager.close()

        self.reporter.end_of_day_reports(auto_push=not self.paper)
        self.reporter.save_state()
    
    def _run_trading_loop(self):
        last_signal_check = datetime.min
        
        while self.running and not self._shutdown_event.is_set():
            try:
                now = datetime.now(timezone.utc).replace(tzinfo=None)  # Crypto uses UTC
                
                # Check exits
                self._check_exits()
                
                # Check signals every minute
                if (now - last_signal_check).total_seconds() >= 60:
                    self._check_signals()
                    last_signal_check = now
                
                # Record equity every 5 minutes
                if now.minute % 5 == 0:
                    balance = self.data_adapter.get_balance()
                    self.reporter.record_equity(now, balance['total'])

                    if self.enable_portfolio_manager and self.portfolio_manager:
                        self.portfolio_manager.risk.on_equity_update(balance['total'], now)

                        if self.portfolio_manager.risk.trading_paused:
                            logger.warning(
                                f"KILL_SWITCH_TRIPPED reason={self.portfolio_manager.risk.paused_reason} at={self.portfolio_manager.risk.paused_at_utc}"
                            )
                
                self._wait_interruptible(1)
                
            except Exception as e:
                logger.error(f"Error: {e}")
                self._wait_interruptible(10)
    
    def _check_signals(self):
        # Get balance (USD for Binance.US, USDT for Bybit)
        if self.exchange_name == "binanceus":
            balance = self.data_adapter.get_balance('USD')
        else:
            balance = self.data_adapter.get_balance()

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        venue = "binanceus" if self.exchange_name == "binanceus" else "bybit"

        def _decision_log(msg: str) -> None:
            if self._decision_log_enabled:
                logger.info(msg)
            else:
                logger.debug(msg)
        
        for symbol in self.strategy.config.symbols:
            try:
                bars_5min = self.data_adapter.get_bars_5min(symbol, n=250)
                bars_1min = self.data_adapter.get_bars_1min(symbol, n=100)

                bars5 = 0 if bars_5min is None else int(len(bars_5min))
                bars1 = 0 if bars_1min is None else int(len(bars_1min))
                if getattr(bars_5min, "empty", True) or getattr(bars_1min, "empty", True):
                    _decision_log(
                        f"CRYPTO_DECISION venue={venue} symbol={symbol} action=SKIP reason=no_bars bars_5m={bars5} bars_1m={bars1}"
                    )
                    if self.enable_portfolio_manager and self.portfolio_manager:
                        self.portfolio_manager.audit_blocked(
                            instrument=symbol,
                            venue=venue,
                            info={"blocked_reason": "no_bars", "strategy_id": "crypto_mr_intraday"},
                            now_utc=now,
                        )
                    continue

                # Normalize to (signal, info)
                if hasattr(self.strategy, "generate_signal_with_info"):
                    signal, info = self.strategy.generate_signal_with_info(
                        symbol=symbol,
                        bars_5min=bars_5min,
                        bars_1min=bars_1min,
                        current_time=now,
                        current_equity=balance['total'],
                    )
                else:
                    signal = self.strategy.generate_signal(
                        symbol=symbol,
                        bars_5min=bars_5min,
                        bars_1min=bars_1min,
                        current_time=now,
                        current_equity=balance['total'],
                    )
                    info = {"blocked_reason": "unknown"} if signal is None else {}

                # Always emit a decision log (signal or blocked reason).
                blocked_reason = (info or {}).get("blocked_reason") or getattr(signal, "blocked_reason", None) or ""
                if signal is None:
                    rsi = (info or {}).get("rsi")
                    _decision_log(
                        "CRYPTO_DECISION venue={} symbol={} action=FLAT reason={} rsi={} bars_5m={} bars_1m={}".format(
                            venue,
                            symbol,
                            blocked_reason or "none",
                            ("{:.2f}".format(float(rsi)) if rsi is not None else "na"),
                            bars5,
                            bars1,
                        )
                    )
                else:
                    _decision_log(
                        "CRYPTO_DECISION venue={} symbol={} action=ENTER side={} entry={:.4f} rsi={:.2f}".format(
                            venue,
                            symbol,
                            getattr(signal.signal_type, "name", str(signal.signal_type)),
                            float(signal.entry_price),
                            float(getattr(signal, "rsi_value", float("nan"))),
                        )
                    )

                if self.enable_portfolio_manager and self.portfolio_manager and self.portfolio_state:
                    # Always emit one decision audit per evaluated instrument
                    if signal is None:
                        info = dict(info)
                        info.setdefault("strategy_id", "crypto_mr_intraday")
                        self.portfolio_manager.audit_blocked(
                            instrument=symbol,
                            venue=venue,
                            info=info,
                            now_utc=now,
                            default_reason="unknown",
                        )
                        continue

                    # Build a candidate action with notional sizing (quote currency)
                    current_price = self.data_adapter.get_latest_price(symbol) or signal.entry_price
                    size, notional = self.strategy.calculate_position_size(signal, balance['total'], current_price)
                    if notional <= 0:
                        _decision_log(
                            f"CRYPTO_DECISION venue={venue} symbol={symbol} action=SKIP reason=below_min_notional notional_usd=0"
                        )
                        self.portfolio_manager.audit_blocked(
                            instrument=symbol,
                            venue=venue,
                            info={"blocked_reason": "below_min_notional", "strategy_id": "crypto_mr_intraday"},
                            now_utc=now,
                        )
                        continue

                    base_asset, quote_asset = self._extract_base_quote(symbol)
                    from otq.portfolio.types import CandidateAction

                    side = "buy" if signal.signal_type == CryptoSignalType.LONG else "sell"
                    cand = CandidateAction(
                        strategy_id="crypto_mr_intraday",
                        venue=venue,
                        instrument=symbol,
                        base_asset=base_asset,
                        quote_asset=quote_asset,
                        side=side,
                        notional=float(notional),
                        score=getattr(signal, "confidence", None),
                        timestamp=now,
                        info=info,
                    )

                    selected = self.portfolio_manager.evaluate_instrument(symbol, [cand], self.portfolio_state, now)
                    if selected:
                        self._execute_signal(signal, balance['total'])
                    else:
                        # PortfolioManager emits DECISION_REJECTED with rejected_reason; keep one readable line too.
                        _decision_log(f"CRYPTO_DECISION venue={venue} symbol={symbol} action=REJECT reason=portfolio_policy")
                    continue

                # Legacy behavior (no portfolio manager)
                if signal:
                    self._execute_signal(signal, balance['total'])
                    
            except Exception as e:
                logger.error(f"Signal error for {symbol}: {e}")

    def _extract_base_quote(self, symbol: str) -> tuple[str, str]:
        """Extract base/quote from symbols like SOL/USD or SOLUSDT."""
        if "/" in symbol:
            base, quote = symbol.split("/", 1)
            return base, quote
        for suffix in ("USDT", "USD", "USDC"):
            if symbol.endswith(suffix):
                return symbol[: -len(suffix)], suffix
        return symbol, "USD"
    
    def _execute_signal(self, signal, equity: float):
        logger.info(f"🎯 CRYPTO SIGNAL: {signal.signal_type.name} {signal.symbol} @ ${signal.entry_price:.4f}")
        
        current_price = self.data_adapter.get_latest_price(signal.symbol) or signal.entry_price
        size, notional = self.strategy.calculate_position_size(signal, equity, current_price)
        
        if size <= 0:
            return
        
        side = "buy" if signal.signal_type == CryptoSignalType.LONG else "sell"
        adapter = self.data_adapter
        logger.info(
            "EXEC_CTX venue={} paper={} trading_enabled={} has_api_keys={} notional_usd={:.2f} min_internal_notional={}"
            .format(
                self.exchange_name,
                getattr(adapter, "paper", None),
                getattr(adapter, "trading_enabled", None),
                getattr(adapter, "has_api_keys", None),
                float(notional),
                getattr(adapter, "min_internal_notional", None),
            )
        )
        result = self.place_order_usd(signal.symbol, side, float(notional))
        
        if 'error' not in result:
            logger.info(
                f"✅ CRYPTO FILLED: {side.upper()} ${notional:.2f} notional ({size:.4f} {signal.symbol})"
            )
            self.strategy.open_position(signal, size, notional, current_price)

            reconciler = getattr(self, "reconciler", None)
            if reconciler is not None:
                try:
                    venue = "binanceus" if self.exchange_name == "binanceus" else "bybit"
                    reconciler.update_from_fill(
                        {
                            "venue": venue,
                            "instrument": signal.symbol,
                            "side": side,
                            "notional": float(notional),
                            "fill_price": float(current_price),
                        }
                    )
                except Exception:
                    pass

            if self.enable_portfolio_manager and self.portfolio_manager and self.portfolio_state:
                venue = "binanceus" if self.exchange_name == "binanceus" else "bybit"
                base_asset, quote_asset = self._extract_base_quote(signal.symbol)
                from otq.portfolio.types import PositionRecord

                self.portfolio_state.add_position(
                    PositionRecord(
                        venue=venue,
                        instrument=signal.symbol,
                        base_asset=base_asset,
                        quote_asset=quote_asset,
                        side=side,
                        notional=float(notional),
                        opened_at=datetime.now(timezone.utc).replace(tzinfo=None),
                        strategy_id="crypto_mr_intraday",
                    )
                )
                self.portfolio_manager.risk.on_execution_success()
        else:
            logger.warning(
                "ORDER_BLOCKED venue={} symbol={} side={} notional_usd={:.2f} result={}"
                .format(self.exchange_name, signal.symbol, side, float(notional), result)
            )
            if self.enable_portfolio_manager and self.portfolio_manager:
                self.portfolio_manager.risk.on_execution_error(datetime.now(timezone.utc).replace(tzinfo=None))

    def place_order_usd(self, symbol: str, side: str, notional_usd: float) -> Dict[str, Any]:
        """Route USD-notional orders through the correct adapter API.

        Binance.US must use notional-based sizing to avoid tiny base amounts.
        """
        if self.exchange_name == "binanceus":
            logger.info(
                "NOTIONAL_ORDER venue=binanceus symbol={} side={} notional_usd={:.2f}".format(
                    symbol,
                    side,
                    float(notional_usd),
                )
            )
            return self.data_adapter.place_market_order_notional(symbol, side, float(notional_usd))

        return self.data_adapter.place_market_order_notional(symbol, side, float(notional_usd))
    
    def _check_exits(self):
        positions = self.strategy.get_positions()
        if not positions:
            return
        
        current_prices = self.data_adapter.get_latest_prices()
        exits = self.strategy.check_exits(current_prices, datetime.utcnow())
        
        for symbol, reason in exits:
            self._execute_exit(symbol, reason)
    
    def _execute_exit(self, symbol: str, reason: str):
        position = self.strategy.get_positions().get(symbol)
        if not position:
            return
        
        logger.info(f"🚪 CRYPTO EXIT: {symbol} - {reason}")

        adapter = self.data_adapter
        logger.info(
            "EXIT_CTX venue={} paper={} trading_enabled={} has_api_keys={} min_internal_notional={}"
            .format(
                self.exchange_name,
                getattr(adapter, "paper", None),
                getattr(adapter, "trading_enabled", None),
                getattr(adapter, "has_api_keys", None),
                getattr(adapter, "min_internal_notional", None),
            )
        )

        result = self.data_adapter.close_position(symbol)

        if 'error' not in result:
            self.strategy.close_position(symbol)
            logger.info(f"✅ Position closed: {symbol}")

            reconciler = getattr(self, "reconciler", None)
            if reconciler is not None:
                try:
                    venue = "binanceus" if self.exchange_name == "binanceus" else "bybit"
                    reconciler.update_from_positions({"venue": venue, "instrument": symbol, "event": "closed"})
                except Exception:
                    pass
            if self.enable_portfolio_manager and self.portfolio_state:
                venue = "binanceus" if self.exchange_name == "binanceus" else "bybit"
                self.portfolio_state.remove_positions_for_instrument(venue, symbol)
            if self.enable_portfolio_manager and self.portfolio_manager:
                self.portfolio_manager.risk.on_execution_success()
        else:
            logger.warning(
                "EXIT_BLOCKED venue={} symbol={} reason={} result={}".format(
                    self.exchange_name,
                    symbol,
                    reason,
                    result,
                )
            )
            if self.enable_portfolio_manager and self.portfolio_manager:
                self.portfolio_manager.risk.on_execution_error(datetime.now(timezone.utc).replace(tzinfo=None))
    
    def _on_bar_1min(self, symbol: str, bar):
        pass
    
    def _on_bar_5min(self, symbol: str, bar):
        pass
    
    def _wait_interruptible(self, seconds: float):
        self._shutdown_event.wait(timeout=seconds)


# =============================================================================
# MULTI-STRATEGY RUNNER
# =============================================================================

def _start_intraday(paper: bool):
    engine = LiveTradingEngine(paper=paper, reports_dir="reports/intraday")
    engine.start()


def _start_momentum(paper: bool):
    engine = MomentumTradingEngine(paper=paper)
    engine.start()


def _start_pairs(paper: bool):
    engine = PairsArbEngine(paper=paper)
    engine.start()


def _start_crypto(paper: bool):
    engine = CryptoMREngine(testnet=paper, paper=paper)
    engine.start()


def _start_binance(paper: bool):
    from otq.engines.binance_mr_engine import BinanceMREngine
    engine = BinanceMREngine(paper=paper, testnet=paper)
    engine.start()


def _start_jupiter_mr(paper: bool):
    from otq.engines.jupiter_mr_engine import build_jupiter_mr_engine

    engine = build_jupiter_mr_engine(paper=paper)
    engine.start()


def _start_ot_movers(paper: bool):
    from otq.engines.solana_ot_movers_engine import build_solana_ot_movers_engine

    engine = build_solana_ot_movers_engine(paper=paper)
    engine.start()


def _start_solana_bridge(paper: bool):
    from otq.engines.solana_bridge_engine import build_solana_bridge_engine

    engine = build_solana_bridge_engine(paper=paper)
    engine.start()


def run_all_strategies(paper: bool = True):
    """Run selected strategies, each in its own console."""
    logger.info("=" * 60)
    logger.info("🚀 STARTING ALL STRATEGIES (separate consoles)")
    logger.info("=" * 60)

    def _spawn_console(name: str, code: str):
        env = os.environ.copy()
        env.setdefault("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        proc = subprocess.Popen(
            [sys.executable, "-c", code],
            env=env,
            creationflags=creationflags,
        )
        logger.info(f"Started {name} in new console (pid={proc.pid})")
        return proc

    paper_flag = "True" if paper else "False"
    env_ot_mainnet = os.getenv("OTQ_SOLANA_OT_MAINNET", "").lower() in {"1", "true", "yes", "on"}
    paper_flag_ot = "False" if env_ot_mainnet else paper_flag

    launches = [
        ("BinanceMR", f"from otq.main import _start_binance; _start_binance({paper_flag})"),
        ("JupiterMR", f"from otq.main import _start_jupiter_mr; _start_jupiter_mr(False)"),
        ("SolanaOTMovers", f"from otq.main import _start_ot_movers; _start_ot_movers(False)"),
    ]

    procs = []
    for name, code in launches:
        procs.append(_spawn_console(name, code))

    logger.info("All requested strategies launched; consoles will manage their own lifecycle.")


# =============================================================================
# CLI COMMANDS
# =============================================================================

def command_paper(args):
    """Run intraday MR paper trading."""
    print("🧪 PAPER TRADING - Intraday MR + Volume Explosion")
    engine = LiveTradingEngine(paper=True)
    engine.start()


def command_live(args):
    """Run intraday MR live trading."""
    print("🔴 LIVE TRADING - REAL MONEY")
    confirm = input("Type 'CONFIRM LIVE' to proceed: ")
    if confirm != "CONFIRM LIVE":
        print("Aborted.")
        return
    
    engine = LiveTradingEngine(paper=False)
    engine.start()


def command_momentum(args):
    """Run ETF momentum rotation."""
    print("🔄 ETF MOMENTUM ROTATION - TQQQ/SQQQ/UVXY/GLD")
    engine = MomentumTradingEngine(paper=True)
    engine.start()


def command_pairs(args):
    """Run pairs statistical arbitrage."""
    print("📊 PAIRS STATISTICAL ARBITRAGE")
    engine = PairsArbEngine(paper=True)
    engine.start()


def command_crypto(args):
    """Run crypto MR on Bybit or Binance.US."""
    # Check env var first, then CLI flag
    env_exchange = os.getenv("CRYPTO_EXCHANGE", "bybit").lower()
    use_binanceus = getattr(args, 'binanceus', False) or env_exchange == "binanceus"
    
    if use_binanceus:
        print("🪙 CRYPTO MR - Binance.US Spot (24/7)")
        print("   Note: Spot only, smaller edges (1.5-2.8% vs 3-5%)")
        exchange = "binanceus"
        testnet = False  # Binance.US doesn't have testnet
    else:
        print("🪙 CRYPTO MR - Bybit Perpetuals (24/7)")
        exchange = "bybit"
        testnet = not getattr(args, 'mainnet', False)
    
    paper = not getattr(args, 'mainnet', False)
    engine = CryptoMREngine(testnet=testnet, paper=paper, exchange=exchange)
    engine.start()


def command_jupiter(args):
    """Run Solana/Jupiter MR placeholder engine."""
    from otq.engines.jupiter_mr_engine import build_jupiter_mr_engine

    paper = not getattr(args, "mainnet", False)
    mode = "DEVNET" if paper else "MAINNET"
    
    # Pretty startup header
    UI.header(mode=mode)
    
    if not paper:
        print(f"{UI.YELLOW}{UI.BOLD}⚠ LIVE TRADING MODE{UI.RESET}")
        print(f"{UI.DIM}  Real funds at risk. Press Ctrl+C to abort.{UI.RESET}\n")
        time.sleep(2)
    
    engine = build_jupiter_mr_engine(paper=paper)
    engine.start()


def command_jupiter_ot(args):
    """Run Solana OT Movers placeholder engine."""
    from otq.engines.solana_ot_movers_engine import build_solana_ot_movers_engine

    paper = not getattr(args, "mainnet", False)
    print(f"🛰️  SOLANA OT MOVERS - {'PAPER' if paper else 'LIVE'}")
    engine = build_solana_ot_movers_engine(paper=paper)
    engine.start()


def command_jupiter_parasite(args):
    """Run Solana bridge/parasite placeholder engine."""
    from otq.engines.solana_bridge_engine import build_solana_bridge_engine

    paper = not getattr(args, "mainnet", False)
    print(f"🌉 SOLANA BRIDGE - {'PAPER' if paper else 'LIVE'}")
    engine = build_solana_bridge_engine(paper=paper)
    engine.start()


def command_binanceus(args):
    """Run Binance.US spot MR engine."""
    paper = not getattr(args, "mainnet", False)
    print(f"🪙 BINANCE.US MR - {'PAPER' if paper else 'LIVE'}")
    if not paper:
        confirm = input("Type 'CONFIRM LIVE' to proceed: ")
        if confirm != "CONFIRM LIVE":
            print("Aborted.")
            return

    # Avoid importing otq.engines.binance_mr_engine here to prevent circular import
    # (that module imports CryptoMREngine from this file).
    engine = CryptoMREngine(
        testnet=False,
        paper=paper,
        exchange="binanceus",
        reports_dir="reports/crypto/binanceus",
        name="Binance.US MR Engine",
    )
    engine.start()


def command_perps(args):
    """Run the perps loop (sim-first) via the Coordinator."""
    from otq.coordinator import Coordinator, CoordinatorConfig

    paper = not getattr(args, "mainnet", False)
    signal_source = getattr(args, "signal_source", None)
    tick_s = float(getattr(args, "tick", 1.0))

    if signal_source and signal_source != "none":
        os.environ["PERPS_SIGNAL_SOURCE"] = str(signal_source)

    cfg = CoordinatorConfig(
        enable_binanceus=False,
        enable_jupiter=False,
        enable_perps=True,
        perps_tick_interval_s=tick_s,
        paper=paper,
    )

    print(f"📈 PERPS LOOP - {'PAPER' if paper else 'LIVE'} (sim broker)")
    if signal_source and signal_source != "none":
        print(f"   Signal source: {signal_source}")

    coord = Coordinator(cfg)
    coord.run()


def command_perps_mr(args):
    """Shortcut: perps loop with MR signal adapter (PERPS_SIGNAL_SOURCE=mr)."""
    setattr(args, "signal_source", "mr")
    return command_perps(args)


def command_ot(args):
    """Alias for jupiter-ot (Solana OT movers)."""
    return command_jupiter_ot(args)


def command_all(args):
    """Run all strategies in parallel."""
    print("ALL STRATEGIES - Parallel Execution")
    run_all_strategies(paper=True)


def command_coordinator(args):
    """Run the multi-venue Coordinator in one process."""
    from otq.coordinator import Coordinator, CoordinatorConfig

    # If --mainnet is used we still keep CoordinatorConfig.paper for symmetry.
    paper = not getattr(args, "mainnet", False)

    cfg = CoordinatorConfig(
        enable_binanceus=not getattr(args, "no_binanceus", False),
        enable_jupiter=not getattr(args, "no_jupiter", False),
        enable_perps=bool(getattr(args, "perps", False)),
        paper=paper,
    )

    coord = Coordinator(cfg)
    coord.run()


def command_fetch(args):
    """Fetch market data."""
    import requests
    
    symbol = args.symbol
    poly_key = os.getenv("POLYGON_API_KEY")
    
    if not poly_key:
        print("❌ POLYGON_API_KEY not found")
        return
    
    end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    print(f"📊 Fetching {symbol} ({start_date} -> {end_date})...")
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}?adjusted=true&sort=asc&limit=5000&apiKey={poly_key}"
    
    try:
        resp = requests.get(url).json()
        if resp.get("status") != "OK":
            print(f"❌ Failed: {resp}")
            return
        
        df = pd.DataFrame(resp["results"])
        print(f"✅ Fetched {len(df)} days")
        print(f"📈 Latest: ${df['c'].iloc[-1]:.2f}")
    except Exception as e:
        print(f"❌ Error: {e}")


def command_analyze(args):
    """Analyze a symbol."""
    import requests
    
    symbol = args.symbol.upper()
    poly_key = os.getenv("POLYGON_API_KEY")
    
    if not poly_key:
        print("❌ POLYGON_API_KEY not found")
        return
    
    print(f"🔍 Analyzing {symbol}...")
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
    
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/5/minute/{start_date}/{end_date}?adjusted=true&sort=asc&limit=5000&apiKey={poly_key}"
    
    try:
        resp = requests.get(url).json()
        if resp.get("status") != "OK":
            print(f"❌ Failed: {resp}")
            return
        
        df = pd.DataFrame(resp["results"])
        df['datetime'] = pd.to_datetime(df['t'], unit='ms')
        df.set_index('datetime', inplace=True)
        
        strategy = IntradayMRVolumePro()
        signals, rsi, sma_200, _ = strategy.calculate_signals_vectorized(df, df)
        
        print(f"\n{'='*60}")
        print(f" 📊 ANALYSIS: {symbol}")
        print(f"{'='*60}")
        print(f" 💰 Price: ${df['c'].iloc[-1]:.2f}")
        print(f" 📊 RSI(14): {rsi[-1]:.1f}")
        print(f" 📈 200 SMA: ${sma_200[-1]:.2f}")
        print(f" 🔄 Trend: {'ABOVE' if df['c'].iloc[-1] > sma_200[-1] else 'BELOW'} SMA")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


def command_status(args):
    """Show account status."""
    from otq.live.brokers.alpaca_pro_adapter import create_alpaca_adapter
    
    try:
        broker = create_alpaca_adapter(paper=True)
        account = broker.get_account()
        
        print(f"\n{'='*60}")
        print(" 📊 ACCOUNT STATUS")
        print(f"{'='*60}")
        print(f" 💰 Equity: ${account.equity:,.2f}")
        print(f" 💵 Cash: ${account.cash:,.2f}")
        print(f" 🏦 Buying Power: ${account.buying_power:,.2f}")
        
        positions = broker.get_positions()
        if positions:
            print(f"\n 📋 POSITIONS")
            for symbol, pos in positions.items():
                print(f"   {symbol}: {pos.qty} @ ${pos.avg_entry_price:.2f}")
        
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"❌ Error: {e}")


# =============================================================================
# MAIN CLI
# =============================================================================

def main():
    from otq.utils.shutdown import install_signal_handlers

    install_signal_handlers()

    parser = argparse.ArgumentParser(
        description="OTQ Platform - Multi-Strategy Trading System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Strategies:
    otq paper                 Intraday MR + Volume (paper)
    otq live                  Intraday MR + Volume (LIVE)
    otq momentum              ETF Momentum Rotation
    otq pairs                 Pairs Statistical Arbitrage
    otq crypto                Crypto MR (Bybit perps or Binance.US spot)
    otq binanceus             Binance.US MR (spot)
    otq jupiter               Jupiter MR (Solana spot)
    otq jupiter-ot            Solana OT Movers (Jupiter stack)
    otq ot                    Alias for jupiter-ot
    otq perps                 Perps loop (sim-first)
    otq perps-mr              Perps loop with MR signal adapter
    otq all                   All strategies in parallel

Utilities:
    otq analyze --symbol QQQ  Analyze symbol
    otq status                Account status
    otq fetch --symbol SPY    Fetch data
        """
    )
    
    subparsers = parser.add_subparsers(dest="command")
    
    # Strategy commands
    subparsers.add_parser("paper", help="Intraday MR paper trading")
    subparsers.add_parser("live", help="Intraday MR live trading")
    subparsers.add_parser("momentum", help="ETF Momentum Rotation")
    subparsers.add_parser("pairs", help="Pairs StatArb")
    
    parser_jupiter = subparsers.add_parser("jupiter", help="Jupiter MR (Solana spot)")
    parser_jupiter.add_argument("--mainnet", action="store_true", help="Use mainnet (real money)")
    
    parser_jupiter_ot = subparsers.add_parser("jupiter-ot", help="Solana OT Movers (Jupiter stack)")
    parser_jupiter_ot.add_argument("--mainnet", action="store_true", help="Use mainnet (real money)")

    parser_ot = subparsers.add_parser("ot", help="Alias for jupiter-ot")
    parser_ot.add_argument("--mainnet", action="store_true", help="Use mainnet (real money)")
    
    parser_jupiter_parasite = subparsers.add_parser("jupiter-parasite", help="Solana bridge")
    parser_jupiter_parasite.add_argument("--mainnet", action="store_true", help="Use mainnet (real money)")
    
    parser_crypto = subparsers.add_parser("crypto", help="Crypto MR (Bybit or Binance.US)")
    parser_crypto.add_argument("--mainnet", action="store_true", help="Use mainnet (real money)")
    parser_crypto.add_argument("--binanceus", action="store_true", help="Use Binance.US (spot) instead of Bybit")

    parser_binanceus = subparsers.add_parser("binanceus", help="Binance.US MR (spot)")
    parser_binanceus.add_argument("--mainnet", action="store_true", help="Use mainnet (real money)")

    parser_perps = subparsers.add_parser("perps", help="Perps loop (sim-first)")
    parser_perps.add_argument("--mainnet", action="store_true", help="Use mainnet semantics where applicable")
    parser_perps.add_argument(
        "--signal-source",
        default=os.getenv("PERPS_SIGNAL_SOURCE", "none").strip().lower() or "none",
        choices=["none", "mr"],
        help="Perps signal source wiring (none|mr). 'mr' uses MR adapter + Helius price feed.",
    )
    parser_perps.add_argument("--tick", type=float, default=float(os.getenv("PERPS_TICK_INTERVAL_S", "1.0")), help="Tick interval seconds")

    parser_perps_mr = subparsers.add_parser("perps-mr", help="Perps loop with MR signal adapter")
    parser_perps_mr.add_argument("--mainnet", action="store_true", help="Use mainnet semantics where applicable")
    parser_perps_mr.add_argument("--tick", type=float, default=float(os.getenv("PERPS_TICK_INTERVAL_S", "1.0")), help="Tick interval seconds")

    parser_coord = subparsers.add_parser("coordinator", help="Run multi-venue coordinator (one process)")
    parser_coord.add_argument("--mainnet", action="store_true", help="Use mainnet (real money) where applicable")
    parser_coord.add_argument("--perps", action="store_true", help="Enable perps loop (sim-first; honors PERPS_ENABLED too)")
    parser_coord.add_argument("--no-binanceus", action="store_true", help="Disable Binance.US engine")
    parser_coord.add_argument("--no-jupiter", action="store_true", help="Disable Jupiter engine")
    
    subparsers.add_parser("all", help="Run all strategies")
    
    # Backtest
    parser_bt = subparsers.add_parser("backtest", help="Run backtest")
    parser_bt.add_argument("--symbol", default="SPY")
    parser_bt.add_argument("--strategy", default="golden_cross", choices=["golden_cross", "intraday_mr"])
    
    # Utilities
    parser_fetch = subparsers.add_parser("fetch", help="Fetch data")
    parser_fetch.add_argument("--symbol", default="SPY")
    
    parser_analyze = subparsers.add_parser("analyze", help="Analyze symbol")
    parser_analyze.add_argument("--symbol", default="QQQ")
    
    subparsers.add_parser("status", help="Account status")
    subparsers.add_parser("hello", help="Verify CLI")
    subparsers.add_parser("gpu", help="GPU status")
    
    args = parser.parse_args()
    
    commands = {
        "paper": command_paper,
        "live": command_live,
        "momentum": command_momentum,
        "pairs": command_pairs,
        "jupiter": command_jupiter,
        "jupiter-ot": command_jupiter_ot,
        "ot": command_ot,
        "jupiter-parasite": command_jupiter_parasite,
        "crypto": command_crypto,
        "binanceus": command_binanceus,
        "perps": command_perps,
        "perps-mr": command_perps_mr,
        "all": command_all,
        "coordinator": command_coordinator,
        "backtest": command_backtest,
        "fetch": command_fetch,
        "analyze": command_analyze,
        "status": command_status,
    }
    
    if args.command in commands:
        commands[args.command](args)
    elif args.command == "hello":
        print("👋 OTQ Online - CLI Ready")
        print("   - Intraday MR + Volume (paper/live)")
        print("   - ETF Momentum Rotation")
        print("   - Pairs StatArb")
        print("   - Jupiter MR (Solana spot)")
        print("   - Solana OT Movers (Jupiter stack)")
        print("   - Binance.US MR (spot)")
        print("   - Perps loop (sim-first; optional MR signals)")
    elif args.command == "gpu":
        import torch
        print(f"🖥️  GPU: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"   Device: {torch.cuda.get_device_name(0)}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
