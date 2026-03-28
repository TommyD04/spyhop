"""Config loader — TOML-based configuration with layered defaults.

Supports both legacy flat config ([detector], [scorer], [paper]) and
the new multi-thesis structure ([thesis.insider.*], [thesis.sporty_investor.*]).
_migrate_config() transparently handles both directions so existing
config.toml files continue to work.
"""

from __future__ import annotations

import logging
import sys
import tomllib
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

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
    "display": {
        "max_rows": 50,
    },
    # Legacy flat keys — serve as defaults for old-style configs.
    # For new thesis-style configs, _migrate_config() overwrites these
    # from thesis.insider so they stay in sync.
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
        "entry_price": {
            "sweet_spot_low": 0.35,
            "sweet_spot_high": 0.50,
            "multiplier_sweet": 1.0,       # no boost — only near-certainty dampening
            "multiplier_adjacent": 1.0,
            "near_certainty_threshold": 0.85,
            "near_certainty_multiplier": 0.5,
        },
        "mm_filter": {
            "enabled": False,
            "settle_delay_seconds": 7,
            "pair_max_gap_seconds": 14,
            "wallet_lookback_minutes": 120,
        },
    },
    "scorer": {
        "alert_threshold": 7,
        "critical_threshold": 9,
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
    "resolution": {
        "poll_interval_minutes": 15,
        "request_delay_seconds": 1.0,
    },
}

# Default thesis definitions — used by _migrate_config() when building
# thesis structure from old-style configs or filling in missing theses.
_THESIS_DEFAULTS: dict[str, Any] = {
    "insider": {
        "enabled": True,
        "categories": [],
        "exclude_categories": ["Crypto", "Sports"],
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
            "entry_price": {
                "sweet_spot_low": 0.35,
                "sweet_spot_high": 0.50,
                "multiplier_sweet": 1.0,       # no boost — only near-certainty dampening
                "multiplier_adjacent": 1.0,
                "near_certainty_threshold": 0.85,
                "near_certainty_multiplier": 0.5,
            },
            "mm_filter": {
                "enabled": False,
                "settle_delay_seconds": 7,
                "pair_max_gap_seconds": 14,
                "wallet_lookback_minutes": 120,
            },
        },
        "scorer": {
            "alert_threshold": 7,
            "critical_threshold": 9,
        },
        "paper": {
            "enabled": False,
            "starting_capital": 100_000,
            "base_position_usd": 5_000,
            "max_position_pct": 0.10,
            "max_exposure_pct": 0.50,
            "max_concurrent": 10,
            "min_score": 7.0,
            "max_days_to_resolution": 30,
        },
    },
    "sporty_investor": {
        "enabled": True,
        "categories": ["Sports"],
        "exclude_categories": [],
        "detector": {
            "timing_gate": {
                "min_hours_before": 0,
            },
            "entry_price": {
                "sweet_spot_low": 0.35,
                "sweet_spot_high": 0.50,
                "multiplier_sweet": 2.0,
                "multiplier_adjacent": 1.5,
                "near_certainty_threshold": 0.85,
                "near_certainty_multiplier": 0.5,
            },
            "niche_nonlinear": {
                "sweet_spot_low_vol": 10_000,
                "sweet_spot_high_vol": 25_000,
                "multiplier_sweet": 2.0,
                "multiplier_adjacent": 1.5,
            },
            "wallet_experience": {
                "sweet_spot_low": 6,
                "sweet_spot_high": 25,
                "multiplier_sweet": 1.8,
                "multiplier_mid": 1.3,
                "multiplier_high": 1.5,
            },
            "mm_filter": {
                "enabled": True,
                "settle_delay_seconds": 7,
                "pair_max_gap_seconds": 14,
                "wallet_lookback_minutes": 120,
            },
        },
        "scorer": {
            "alert_threshold": 5,
            "critical_threshold": 8,
        },
        "paper": {
            "enabled": True,
            "starting_capital": 5_000_000,
            "base_position_usd": 3_000,
            "max_position_pct": 0.05,
            "max_exposure_pct": 0.40,
            "max_concurrent": 100,
            "min_score": 5.0,
            "max_days_to_resolution": 30,
        },
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


def _migrate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Ensure config has both thesis structure and flat backward-compat keys.

    Handles two migration directions:
    1. Old flat config (has [detector]/[scorer]/[paper] but no [thesis])
       → wrap into thesis.insider, add sporty_investor defaults
    2. New thesis config (has [thesis.insider.*])
       → overwrite flat detector/scorer/paper from thesis.insider

    Either way, after migration both config["detector"] and
    config["thesis"]["insider"]["detector"] are populated and consistent.
    """
    has_thesis = "thesis" in config

    if not has_thesis:
        # OLD FORMAT: wrap flat keys into thesis.insider
        log.info("Migrating flat config → thesis.insider structure")
        blocked = config.get("paper", {}).get("blocked_categories", [])
        insider_from_flat = {
            "enabled": True,
            "categories": [],
            "exclude_categories": blocked,
            "detector": config.get("detector", DEFAULTS["detector"]),
            "scorer": config.get("scorer", DEFAULTS["scorer"]),
            "paper": config.get("paper", DEFAULTS["paper"]),
        }
        config["thesis"] = _deep_merge(
            _THESIS_DEFAULTS,
            {"insider": insider_from_flat},
        )

    # Always ensure thesis has all expected theses with defaults filled in
    config["thesis"] = _deep_merge(_THESIS_DEFAULTS, config.get("thesis", {}))

    # Always overwrite flat compat keys from thesis.insider (the canonical source)
    insider = config["thesis"].get("insider", {})
    if insider:
        config["detector"] = insider.get("detector", DEFAULTS["detector"])
        config["scorer"] = insider.get("scorer", DEFAULTS["scorer"])
        paper = dict(insider.get("paper", DEFAULTS["paper"]))
        paper.setdefault(
            "blocked_categories",
            insider.get("exclude_categories", []),
        )
        config["paper"] = paper

    return config


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
    After loading, _migrate_config() ensures both thesis and flat keys exist.
    """
    if path is not None:
        with open(path, "rb") as f:
            log.info("Loaded config from %s", path)
            config = _deep_merge(DEFAULTS, tomllib.load(f))
            return _migrate_config(config)

    for candidate in _search_paths():
        if candidate.exists():
            with open(candidate, "rb") as f:
                log.info("Loaded config from %s", candidate.resolve())
                config = _deep_merge(DEFAULTS, tomllib.load(f))
                return _migrate_config(config)

    log.warning("No config.toml found; using built-in defaults")
    return _migrate_config(DEFAULTS.copy())


def db_path() -> Path:
    """Return platform-appropriate database path, creating parent dirs."""
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local" / "spyhop"
    else:
        base = Path.home() / ".local" / "share" / "spyhop"
    base.mkdir(parents=True, exist_ok=True)
    return base / "spyhop.db"
