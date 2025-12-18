import logging
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

import toml


logger = logging.getLogger(__name__)


@dataclass
class SchedulerConfig:
    mode: str = "BAR"
    bar_interval_seconds: int = 60
    interval_seconds: int = 10


@dataclass
class FeatureFlags:
    enable_new_regime_logic: bool = False
    enable_binance: bool = False
    enable_jupiter: bool = False
    enable_experimental_account: bool = False
    max_venues_per_symbol: int = 1
    allow_multi_venue: bool = False


@dataclass
class RiskLimits:
    max_quote_notional_usd: Decimal
    min_trade_notional_usd: Decimal
    max_leverage: Decimal
    max_daily_loss: Decimal
    max_notional_per_order: Decimal
    fat_finger_multiplier: float = 10.0
    max_slippage_bps: Optional[Decimal] = None


@dataclass
class PortfolioManagerSettings:
    """Optional portfolio/router settings.

    This is used by the OTQ multi-venue layer (Router / PortfolioManager). Defaults
    keep behavior unchanged unless explicitly enabled.
    """

    enabled: bool = False
    decision_audit_path: Optional[str] = None

    max_positions_total: int = 10
    max_exposure_per_asset: float = 10_000.0
    max_venues_per_symbol: int = 1
    allow_multi_venue_exposure: bool = False

    reconcile_interval_seconds: int = 60
    reconcile_max_mismatch_cycles: int = 3
    reconcile_backoff_seconds: int = 120


@dataclass
class OverrideRecord:
    key: str
    source: str
    old: Any
    new: Any


@dataclass
class AppConfig:
    scheduler: SchedulerConfig
    feature_flags: FeatureFlags
    instruments: List[str]
    instruments_raw: List[str]
    initial_capital: Decimal
    risk: RiskLimits
    portfolio_manager: PortfolioManagerSettings = field(default_factory=PortfolioManagerSettings)
    overrides: List[OverrideRecord] = field(default_factory=list)
    loaded_files: List[str] = field(default_factory=list)
    symbol_notes: List[str] = field(default_factory=list)
    duplicate_symbols_report: str = ""

    @classmethod
    def load(
        cls,
        settings_path: str,
        venue_paths: Optional[Union[str, List[str]]] = None,
        env_prefix: str = "APP__",
        symbol_mapping: Optional[Dict[str, str]] = None,
    ) -> "AppConfig":
        layers: List[Tuple[Dict[str, Any], str]] = []
        loaded_files: List[str] = []
        venue_symbols_raw: Dict[str, List[str]] = {}

        def _load_if_exists(path: Optional[str], label: str) -> None:
            if not path:
                return
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = toml.load(f)
                layers.append((data, label))
                loaded_files.append(label)
                if "instruments" in data:
                    venue_symbols_raw[label] = data.get("instruments", []) or []

        _load_if_exists(settings_path, os.path.basename(settings_path) or "settings.toml")

        if isinstance(venue_paths, str):
            venue_paths = [p.strip() for p in venue_paths.split(",") if p.strip()]
        if venue_paths:
            for vp in venue_paths:
                _load_if_exists(vp, os.path.basename(vp) if vp else "")

        env_overrides = _load_env_overrides(env_prefix)
        if env_overrides:
            layers.append((env_overrides, "env/cli"))
            if "instruments" in env_overrides:
                venue_symbols_raw["env/cli"] = env_overrides.get("instruments", []) or []

        merged: Dict[str, Any] = {}
        overrides: List[OverrideRecord] = []
        for payload, source in layers:
            _merge_dicts(merged, payload, source, overrides)

        scheduler = _build_scheduler(merged)
        feature_flags = _build_feature_flags(merged)
        risk_limits = _build_risk_limits(merged)
        portfolio_manager = _build_portfolio_manager(merged)

        instruments_raw = merged.get("instruments", []) or []
        normalized_instruments, symbol_notes = _normalize_instruments(instruments_raw, symbol_mapping or {})

        venue_symbols_normalized: Dict[str, List[str]] = {}
        for label, raw_syms in venue_symbols_raw.items():
            normalized_syms, venue_notes = _normalize_instruments(raw_syms, symbol_mapping or {})
            venue_symbols_normalized[label] = normalized_syms
            symbol_notes.extend([f"{label}: {note}" for note in venue_notes])

        _validate_venues(feature_flags)
        _validate_instruments(normalized_instruments, feature_flags)
        _validate_symbol_dupes(feature_flags, venue_symbols_normalized, venue_symbols_raw)

        dupes = _find_symbol_dupes(feature_flags, venue_symbols_normalized)
        dupes_report = "none" if not dupes else "; ".join(
            f"{sym} -> {', '.join(srcs)}" for sym, srcs in sorted(dupes.items())
        )

        cfg = cls(
            scheduler=scheduler,
            feature_flags=feature_flags,
            portfolio_manager=portfolio_manager,
            instruments=normalized_instruments,
            instruments_raw=instruments_raw,
            initial_capital=_to_decimal(merged.get("initial_capital", 100000), "initial_capital"),
            risk=risk_limits,
            overrides=overrides,
            loaded_files=loaded_files,
            symbol_notes=symbol_notes,
            duplicate_symbols_report=dupes_report,
        )

        cfg.log_summary()
        return cfg

    def log_summary(self) -> None:
        logger.info("Loaded config files: %s", ", ".join(self.loaded_files) or "<none>")
        for o in self.overrides:
            logger.info("Override: %s from %s (old=%s -> new=%s)", o.key, o.source, o.old, o.new)
        enabled = _enabled_venues(self.feature_flags)
        logger.info("Venues enabled: %s (allow_multi_venue=%s)", enabled or "<none>", self.feature_flags.allow_multi_venue)
        logger.info(
            "Scheduler: mode=%s, bar_interval_seconds=%s, interval_seconds=%s",
            self.scheduler.mode,
            self.scheduler.bar_interval_seconds,
            self.scheduler.interval_seconds,
        )
        logger.info("Instruments raw=%s normalized=%s", self.instruments_raw, self.instruments)
        if self.symbol_notes:
            for note in self.symbol_notes:
                logger.info("Symbol note: %s", note)
        logger.info("Duplicate symbols across venues: %s", self.duplicate_symbols_report or "none")
        logger.info(
            "Resolved risk: max_position_size=%s => max_quote_notional_usd=%s, min_trade_notional=%s",
            self.risk.max_quote_notional_usd,
            self.risk.max_quote_notional_usd,
            self.risk.min_trade_notional_usd,
        )
        if self.portfolio_manager.enabled:
            logger.info(
                "PortfolioManager enabled: max_positions_total=%s max_exposure_per_asset=%s max_venues_per_symbol=%s allow_multi_venue_exposure=%s audit=%s",
                self.portfolio_manager.max_positions_total,
                self.portfolio_manager.max_exposure_per_asset,
                self.portfolio_manager.max_venues_per_symbol,
                self.portfolio_manager.allow_multi_venue_exposure,
                self.portfolio_manager.decision_audit_path,
            )


def _merge_dicts(dst: Dict[str, Any], src: Dict[str, Any], source: str, overrides: List[OverrideRecord], prefix: str = "") -> None:
    for key, value in src.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _merge_dicts(dst[key], value, source, overrides, full_key)
        elif isinstance(value, dict):
            dst[key] = value.copy()
        else:
            if key in dst and dst[key] != value:
                overrides.append(OverrideRecord(full_key, source, dst[key], value))
            dst[key] = value


def _load_env_overrides(prefix: str) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    for env_key, env_val in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        path_parts = env_key[len(prefix):].lower().split("__")
        _assign_env_override(overrides, path_parts, env_val)
    return overrides


def _assign_env_override(dst: Dict[str, Any], path_parts: List[str], raw_val: str) -> None:
    cur = dst
    for part in path_parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    leaf = path_parts[-1]
    # Special-case list-like settings for CLI/env ergonomics
    if leaf == "instruments":
        cur[leaf] = [s.strip() for s in raw_val.split(",") if s.strip()]
        return
    cur[leaf] = _coerce_env_value(raw_val)


def _coerce_env_value(val: str) -> Any:
    lowered = val.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def _build_scheduler(cfg: Dict[str, Any]) -> SchedulerConfig:
    section = cfg.get("scheduler", {}) or {}
    return SchedulerConfig(
        mode=section.get("mode", "BAR"),
        bar_interval_seconds=int(section.get("bar_interval_seconds", 60)),
        interval_seconds=int(section.get("interval_seconds", 10)),
    )


def _build_feature_flags(cfg: Dict[str, Any]) -> FeatureFlags:
    section = cfg.get("feature_flags", {}) or {}
    return FeatureFlags(
        enable_new_regime_logic=bool(section.get("enable_new_regime_logic", False)),
        enable_binance=bool(section.get("enable_binance", False)),
        enable_jupiter=bool(section.get("enable_jupiter", False)),
        enable_experimental_account=bool(section.get("enable_experimental_account", False)),
        max_venues_per_symbol=int(section.get("max_venues_per_symbol", 1)),
        allow_multi_venue=bool(section.get("allow_multi_venue", False)),
    )


def _build_portfolio_manager(cfg: Dict[str, Any]) -> PortfolioManagerSettings:
    section = cfg.get("portfolio_manager", {}) or {}
    return PortfolioManagerSettings(
        enabled=bool(section.get("enabled", False)),
        decision_audit_path=section.get("decision_audit_path"),
        max_positions_total=int(section.get("max_positions_total", 10)),
        max_exposure_per_asset=float(section.get("max_exposure_per_asset", 10_000.0)),
        max_venues_per_symbol=int(section.get("max_venues_per_symbol", 1)),
        allow_multi_venue_exposure=bool(section.get("allow_multi_venue_exposure", False)),
        reconcile_interval_seconds=int(section.get("reconcile_interval_seconds", 60)),
        reconcile_max_mismatch_cycles=int(section.get("reconcile_max_mismatch_cycles", 3)),
        reconcile_backoff_seconds=int(section.get("reconcile_backoff_seconds", 120)),
    )


def _build_risk_limits(cfg: Dict[str, Any]) -> RiskLimits:
    section = cfg.get("risk", {}) or {}
    base_keys = {"max_position_size_base", "max_size_base", "max_base_notional"}
    bad_keys = base_keys.intersection(section.keys())
    if bad_keys:
        raise ValueError(f"Ambiguous sizing keys found: {sorted(bad_keys)}; use quote-notional keys only")

    if "max_position_size" not in section:
        raise ValueError("max_position_size is required and is interpreted as max_quote_notional_usd")
    if "min_trade_notional" not in section:
        raise ValueError("min_trade_notional is required (USD)")

    max_quote = _to_decimal(section["max_position_size"], "risk.max_position_size")
    min_trade = _to_decimal(section["min_trade_notional"], "risk.min_trade_notional")
    if max_quote < min_trade:
        raise ValueError(
            f"risk.max_position_size ({max_quote}) must be >= risk.min_trade_notional ({min_trade})"
        )

    max_slippage = section.get("max_slippage_bps")
    max_slippage_dec: Optional[Decimal] = _to_decimal(max_slippage, "risk.max_slippage_bps") if max_slippage is not None else None

    return RiskLimits(
        max_quote_notional_usd=max_quote,
        min_trade_notional_usd=min_trade,
        max_leverage=_to_decimal(section.get("max_leverage", 1.0), "risk.max_leverage"),
        max_daily_loss=_to_decimal(section.get("max_daily_loss", 0), "risk.max_daily_loss"),
        max_notional_per_order=_to_decimal(section.get("max_notional_per_order", max_quote), "risk.max_notional_per_order"),
        fat_finger_multiplier=float(section.get("fat_finger_multiplier", 10.0)),
        max_slippage_bps=max_slippage_dec,
    )


def _normalize_instruments(raw: List[str], mapping: Dict[str, str]) -> Tuple[List[str], List[str]]:
    normalized: List[str] = []
    notes: List[str] = []
    for sym in raw:
        cleaned = sym.strip().upper()
        if cleaned in mapping:
            normalized.append(mapping[cleaned])
            notes.append(f"Mapped {cleaned} -> {mapping[cleaned]}")
            continue
        if "/" in cleaned:
            base, quote = cleaned.split("/", 1)
            base = base.strip().upper()
            quote = quote.strip().upper()
            if quote == "USDT":
                notes.append(f"Normalized {cleaned} quote USDT -> USD")
                quote = "USD"
            normalized.append(f"{base}/{quote}")
            continue
        if cleaned.isalpha():
            notes.append(f"Symbol {cleaned} has no quote leg; treated as base-only")
            normalized.append(cleaned)
            continue
        raise ValueError(
            f"Unsupported symbol format '{sym}'. Use BASE/QUOTE or provide an explicit mapping"
        )
    return normalized, notes


def _enabled_venues(flags: FeatureFlags) -> List[str]:
    venues = []
    if flags.enable_binance:
        venues.append("binance")
    if flags.enable_jupiter:
        venues.append("jupiter")
    return venues


def _validate_venues(flags: FeatureFlags) -> None:
    venues = _enabled_venues(flags)
    if flags.max_venues_per_symbol < 1:
        raise ValueError("feature_flags.max_venues_per_symbol must be >= 1")
    if not venues:
        raise ValueError("No venues enabled; enable at least one venue to trade")
    if len(venues) > 1 and not flags.allow_multi_venue:
        raise ValueError(f"Multiple venues enabled {venues} without allow_multi_venue=true")
    if flags.allow_multi_venue and flags.max_venues_per_symbol == 1:
        logger.warning(
            "allow_multi_venue=true but max_venues_per_symbol=1; symbols will still be limited to one venue"
        )


def _validate_instruments(instruments: List[str], flags: FeatureFlags) -> None:
    venues = _enabled_venues(flags)
    if venues and not instruments:
        raise ValueError("Instruments list is required when venues are enabled")


def _validate_symbol_dupes(
    flags: FeatureFlags,
    venue_symbols_normalized: Dict[str, List[str]],
    venue_symbols_raw: Dict[str, List[str]],
) -> None:
    if flags.max_venues_per_symbol != 1:
        return

    duplicates = _find_symbol_dupes(flags, venue_symbols_normalized)
    if not duplicates:
        return

    details = []
    for sym, srcs in duplicates.items():
        raw_views = []
        for src in srcs:
            raw_syms = venue_symbols_raw.get(src, [])
            raw_views.append(f"{src}: raw={raw_syms}")
        details.append(f"{sym} in {', '.join(raw_views)}")

    raise ValueError(
        "Symbol appears in multiple enabled venues while max_venues_per_symbol=1: " + "; ".join(details)
    )


def _find_symbol_dupes(
    flags: FeatureFlags, venue_symbols_normalized: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    enabled_venues = {v for v in _enabled_venues(flags)}
    symbol_to_sources: Dict[str, List[str]] = {}
    for label, symbols in venue_symbols_normalized.items():
        venue_name = _resolve_venue_name(label)
        if venue_name not in enabled_venues:
            continue
        for sym in symbols:
            symbol_to_sources.setdefault(sym, []).append(label)
    return {sym: srcs for sym, srcs in symbol_to_sources.items() if len(srcs) > 1}


def _resolve_venue_name(label: str) -> str:
    lower = label.lower()
    if "binance" in lower:
        return "binance"
    if "jupiter" in lower:
        return "jupiter"
    return label


def _to_decimal(value: Any, label: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"Invalid decimal value for {label}: {value}") from exc

