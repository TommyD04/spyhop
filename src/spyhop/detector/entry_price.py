"""EntryPriceDetector — contrarian sweet-spot scoring for entry prices.

The sporty_investor thesis identifies value in contrarian bets: prices in the
$0.35-$0.50 range (betting on an underdog with decent implied probability).
Near-certainty entries ($0.85+) are dampened — minimal upside with full
downside exposure.

Uses the effective entry price (SELL trades are normalized to their BUY
equivalent: 1.0 - price).
"""

from __future__ import annotations

from typing import Any

from spyhop.detector.base import DetectionContext, DetectorResult


class EntryPriceDetector:
    """Scores trades by how contrarian/informative the entry price is."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._sweet_low = config.get("sweet_spot_low", 0.35)
        self._sweet_high = config.get("sweet_spot_high", 0.50)
        self._mult_sweet = config.get("multiplier_sweet", 2.0)
        self._mult_adjacent = config.get("multiplier_adjacent", 1.5)
        self._near_certainty = config.get("near_certainty_threshold", 0.85)
        self._near_certainty_mult = config.get("near_certainty_multiplier", 0.5)

    @property
    def max_multiplier(self) -> float:
        return self._mult_sweet

    def evaluate(self, context: DetectionContext) -> DetectorResult:
        price = context.trade.get("price", 0)
        side = context.trade.get("side", "BUY")

        # Normalize SELL → effective BUY price
        if side == "SELL":
            effective = 1.0 - price
        else:
            effective = price

        if effective <= 0 or effective >= 1.0:
            return DetectorResult("entry_price", 1.0, f"invalid price ${effective:.2f}")

        # Near-certainty dampen (highest priority)
        if effective >= self._near_certainty:
            return DetectorResult(
                "entry_price", self._near_certainty_mult,
                f"near-certainty ${effective:.2f}",
            )

        # Sweet spot
        if self._sweet_low <= effective <= self._sweet_high:
            return DetectorResult(
                "entry_price", self._mult_sweet,
                f"sweet spot ${effective:.2f}",
            )

        # Adjacent ranges: just below sweet or just above sweet to $0.65
        adjacent_low = self._sweet_low - 0.10  # $0.25 default
        adjacent_high = self._sweet_high + 0.15  # $0.65 default
        below_sweet = adjacent_low <= effective < self._sweet_low
        above_sweet = self._sweet_high < effective <= adjacent_high
        if below_sweet or above_sweet:
            return DetectorResult(
                "entry_price", self._mult_adjacent,
                f"adjacent ${effective:.2f}",
            )

        return DetectorResult("entry_price", 1.0, f"outside ${effective:.2f}")
