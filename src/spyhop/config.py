"""Config loader — TOML-based configuration with layered defaults."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "ingestor": {
        "usd_threshold": 10_000,
        "ws_url": "wss://ws-live-data.polymarket.com",
        "reconnect_delay_sec": 5,
    },
    "market_cache": {
        "gamma_url": "https://gamma-api.polymarket.com",
        "ttl_minutes": 60,
    },
    "event_cache": {
        "gamma_url": "https://gamma-api.polymarket.com",
        "ttl_minutes": 120,
    },
    "profiler": {
        "data_api_url": "https://data-api.polymarket.com",
        "max_trades_to_fetch": 200,
        "wallet_cache_ttl_minutes": 30,
    },
    "detector": {
        "fresh_wallet": {
            "max_prior_trades": 5,
            "multiplier_zero": 3.0,
            "multiplier_low": 2.5,
            "multiplier_mid": 2.0,
        },
        "size_anomaly": {
            "min_trade_usd": 10_000,
            "orderbook_impact_pct": 0.02,
            "volume_spike_multiplier": 5.0,
            "multiplier_low": 1.5,
            "multiplier_mid": 2.0,
            "multiplier_high": 3.0,
        },
        "niche_market": {
            "max_daily_volume_usd": 50_000,
            "multiplier_low": 1.5,
            "multiplier_mid": 2.0,
            "multiplier_high": 2.5,
        },
    },
    "scorer": {
        "alert_threshold": 7,
        "critical_threshold": 9,
    },
    "display": {
        "max_rows": 50,
    },
    "paper": {
        "enabled": False,
        "starting_capital": 100_000,
        "base_position_usd": 5_000,
        "max_position_pct": 0.10,
        "max_exposure_pct": 0.50,
        "max_concurrent": 10,
        "min_score": 7.0,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base, recursing into nested dicts."""
    merged = base.copy()
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def _project_root() -> Path:
    """Resolve the project root (where config.toml lives next to pyproject.toml)."""
    return Path(__file__).resolve().parent.parent.parent


def _search_paths() -> list[Path]:
    """Return config file search paths in priority order."""
    paths = [Path("config.toml")]
    # Project root — works regardless of CWD when installed via pip install -e
    root_config = _project_root() / "config.toml"
    if root_config.resolve() != Path("config.toml").resolve():
        paths.append(root_config)
    if sys.platform == "win32":
        appdata = Path.home() / "AppData" / "Roaming" / "spyhop"
        paths.append(appdata / "config.toml")
    else:
        paths.append(Path.home() / ".config" / "spyhop" / "config.toml")
    return paths


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config from file, falling back to built-in defaults.

    Search order: explicit path → ./config.toml → project root → user config dir → defaults only.
    """
    if path is not None:
        with open(path, "rb") as f:
            return _deep_merge(DEFAULTS, tomllib.load(f))

    for candidate in _search_paths():
        if candidate.exists():
            with open(candidate, "rb") as f:
                return _deep_merge(DEFAULTS, tomllib.load(f))

    return DEFAULTS.copy()


def db_path() -> Path:
    """Return platform-appropriate database path, creating parent dirs."""
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local" / "spyhop"
    else:
        base = Path.home() / ".local" / "share" / "spyhop"
    base.mkdir(parents=True, exist_ok=True)
    return base / "spyhop.db"
