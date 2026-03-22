"""NicheNonlinearDetector — non-linear volume sweet-spot for sports markets.

Unlike the insider thesis's NicheMarketDetector (linear: smaller = better),
the sporty_investor thesis has a *sweet spot* in the $10K-$25K daily volume
range. Below $10K the market may be too illiquid or obscure; above $50K
it's likely a major line with efficient pricing.

The non-linear shape matches the empirical finding that mid-thin markets
(enough liquidity to actually trade, thin enough that whale activity moves
the price) are where informed sports bettors concentrate.
"""

from __future__ import annotations

from typing import Any

from spyhop.detector.base import DetectionContext, DetectorResult


class NicheNonlinearDetector:
    """Scores trades by market 24h volume with non-linear sweet spot."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._sweet_low = config.get("sweet_spot_low_vol", 10_000)
        self._sweet_high = config.get("sweet_spot_high_vol", 25_000)
        self._mult_sweet = config.get("multiplier_sweet", 2.0)
        self._mult_adjacent = config.get("multiplier_adjacent", 1.5)

    @property
    def max_multiplier(self) -> float:
        return self._mult_sweet

    def evaluate(self, context: DetectionContext) -> DetectorResult:
        if context.market is None or context.market.volume_24hr <= 0:
            return DetectorResult("niche_nonlinear", 1.0, "no volume data")

        vol = context.market.volume_24hr

        # Sweet spot: moderate volume markets
        if self._sweet_low <= vol <= self._sweet_high:
            return DetectorResult(
                "niche_nonlinear", self._mult_sweet,
                f"sweet spot ${vol:,.0f}",
            )

        # Adjacent: above sweet spot but still relatively thin
        if self._sweet_high < vol <= self._sweet_high * 2:  # $25K-$50K default
            return DetectorResult(
                "niche_nonlinear", self._mult_adjacent,
                f"adjacent ${vol:,.0f}",
            )

        return DetectorResult("niche_nonlinear", 1.0, f"outside ${vol:,.0f}")
