"""NicheMarketDetector — flags trades on low-volume markets.

Insiders gravitate to niche markets where their information edge is
largest and price adjustment is slowest (SYNTHESIS §1.1, RQ3 §2.3).
"""

from __future__ import annotations

from typing import Any

from spyhop.detector.base import DetectionContext, DetectorResult


class NicheMarketDetector:
    """Detects trades on markets with low daily volume."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.max_daily_vol = config.get("max_daily_volume_usd", 50_000)
        self.mult_low = config.get("multiplier_low", 1.5)
        self.mult_mid = config.get("multiplier_mid", 2.0)
        self.mult_high = config.get("multiplier_high", 2.5)

    @property
    def max_multiplier(self) -> float:
        return self.mult_high

    def evaluate(self, context: DetectionContext) -> DetectorResult:
        if context.market is None or context.market.volume_24hr <= 0:
            return DetectorResult("niche_market", 1.0, "no market volume data")

        vol = context.market.volume_24hr

        if vol >= self.max_daily_vol:
            return DetectorResult("niche_market", 1.0, f"market 24h vol ${vol:,.0f}")

        if vol < 10_000:
            mult = self.mult_high
        elif vol < 25_000:
            mult = self.mult_mid
        else:
            mult = self.mult_low

        return DetectorResult("niche_market", mult, f"market 24h vol ${vol:,.0f}")
