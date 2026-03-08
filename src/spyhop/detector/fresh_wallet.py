"""FreshWalletDetector — flags wallets with few prior Polymarket trades.

Graduated scoring: 0 trades = most suspicious, >5 = no signal.
All thresholds from config (no magic numbers).
"""

from __future__ import annotations

from typing import Any

from spyhop.detector.base import DetectionContext, DetectorResult


class FreshWalletDetector:
    """Detects trades from wallets with little Polymarket history."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.max_prior = config.get("max_prior_trades", 5)
        self.mult_zero = config.get("multiplier_zero", 3.0)
        self.mult_low = config.get("multiplier_low", 2.5)
        self.mult_mid = config.get("multiplier_mid", 2.0)

    @property
    def max_multiplier(self) -> float:
        return self.mult_zero

    def evaluate(self, context: DetectionContext) -> DetectorResult:
        if context.wallet_profile is None:
            return DetectorResult("fresh_wallet", 1.0, "no wallet data")

        count = context.wallet_profile.trade_count

        if count == 0:
            return DetectorResult("fresh_wallet", self.mult_zero, "0 prior trades")
        if count <= 2:
            return DetectorResult("fresh_wallet", self.mult_low, f"{count} prior trades")
        if count <= self.max_prior:
            return DetectorResult("fresh_wallet", self.mult_mid, f"{count} prior trades")

        return DetectorResult("fresh_wallet", 1.0, f"{count} prior trades")
