"""WalletExperienceDetector — inverse of FreshWalletDetector.

The sporty_investor thesis values *experienced* wallets over fresh ones.
Fresh wallets placing large sports bets are more likely recreational gamblers
or reward farmers; experienced wallets (6-25 trades) with concentrated sports
positions suggest informed bettors who know the Polymarket ecosystem.

Very high trade counts (25+) still score, but slightly lower — these may
be systematic/algorithmic traders rather than conviction-driven bettors.
"""

from __future__ import annotations

from typing import Any

from spyhop.detector.base import DetectionContext, DetectorResult


class WalletExperienceDetector:
    """Scores trades by wallet's Polymarket trade history depth."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._sweet_low = config.get("sweet_spot_low", 6)
        self._sweet_high = config.get("sweet_spot_high", 25)
        self._mult_sweet = config.get("multiplier_sweet", 1.8)
        self._mult_mid = config.get("multiplier_mid", 1.3)
        self._mult_high = config.get("multiplier_high", 1.5)

    @property
    def max_multiplier(self) -> float:
        return self._mult_sweet

    def evaluate(self, context: DetectionContext) -> DetectorResult:
        if context.wallet_profile is None:
            return DetectorResult("wallet_experience", 1.0, "no wallet data")

        count = context.wallet_profile.trade_count

        # Sweet spot: experienced but not algorithmic
        if self._sweet_low <= count <= self._sweet_high:
            return DetectorResult(
                "wallet_experience", self._mult_sweet,
                f"sweet spot {count} trades",
            )

        # Veteran: very experienced, may be systematic
        if count > self._sweet_high:
            return DetectorResult(
                "wallet_experience", self._mult_high,
                f"veteran {count} trades",
            )

        # Moderate: some experience
        if 3 <= count < self._sweet_low:
            return DetectorResult(
                "wallet_experience", self._mult_mid,
                f"moderate {count} trades",
            )

        # Novice: 0-2 trades, no signal
        return DetectorResult(
            "wallet_experience", 1.0, f"novice {count} trades"
        )
