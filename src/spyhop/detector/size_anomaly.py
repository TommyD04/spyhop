"""SizeAnomalyDetector — flags trades that are large relative to market volume.

Uses Gamma API volume_24hr as a proxy for order book depth. The CLOB
order-book-impact sub-signal will be added when CLOB data is available (V6).
"""

from __future__ import annotations

from typing import Any

from spyhop.detector.base import DetectionContext, DetectorResult


class SizeAnomalyDetector:
    """Detects outsized trades relative to a market's daily volume."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.min_trade = config.get("min_trade_usd", 10_000)
        self.mult_low = config.get("multiplier_low", 1.5)
        self.mult_mid = config.get("multiplier_mid", 2.0)
        self.mult_high = config.get("multiplier_high", 3.0)

    @property
    def max_multiplier(self) -> float:
        return self.mult_high

    def evaluate(self, context: DetectionContext) -> DetectorResult:
        usdc = context.trade.get("usdc_size", 0)
        if usdc < self.min_trade:
            return DetectorResult("size_anomaly", 1.0, f"${usdc:,.0f} below threshold")

        if context.market is None or context.market.volume_24hr <= 0:
            return DetectorResult("size_anomaly", 1.0, "no market volume data")

        vol = context.market.volume_24hr
        ratio = usdc / vol

        if ratio >= 0.10:
            mult = self.mult_high
        elif ratio >= 0.05:
            mult = self.mult_mid
        elif ratio >= 0.02:
            mult = self.mult_low
        else:
            mult = 1.0

        detail = f"trade is {ratio:.1%} of 24h vol (${vol:,.0f})"
        return DetectorResult("size_anomaly", mult, detail)
