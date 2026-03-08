"""Detection types — Protocol, context, and result dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from spyhop.profiler.market import Market
from spyhop.profiler.wallet import WalletProfile


@dataclass
class DetectionContext:
    """Bundled enrichment data passed to all detectors."""
    trade: dict[str, Any]
    wallet_profile: WalletProfile | None
    market: Market | None


@dataclass
class DetectorResult:
    """Output from a single detector."""
    name: str          # e.g. "fresh_wallet"
    multiplier: float  # 1.0 = no signal, higher = more suspicious
    detail: str        # human-readable explanation


@dataclass
class ScoreResult:
    """Composite scoring output."""
    composite: float                          # 0.0 to 10.0
    signals: list[DetectorResult] = field(default_factory=list)
    alert: bool = False                       # composite >= alert_threshold
    critical: bool = False                    # composite >= critical_threshold


class Detector(Protocol):
    """Interface for pluggable detectors."""
    def evaluate(self, context: DetectionContext) -> DetectorResult: ...
