"""TimingGateDetector — GATE that zeroes composite for during/after-game trades.

For sports markets, pre-game trades carry informational value (someone believes
they know who will win before the game starts). In-play and post-game trades
are a different thesis entirely (live hedging, score-chasing) and should not
score on the sporty_investor thesis.

Returns mult=1.0 (pass) if trade is before game start, mult=0.0 (gate) if
during/after. Since the scorer uses multiplicative composition, 0.0 zeroes
the entire composite score.

max_multiplier = 1.0 because this is a gate, not an amplifier — it never
contributes to the normalizer calculation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from spyhop.detector.base import DetectionContext, DetectorResult


class TimingGateDetector:
    """Gates out trades placed during or after a sporting event."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._min_hours = config.get("min_hours_before", 0)

    @property
    def max_multiplier(self) -> float:
        return 1.0  # Gate, not amplifier

    def evaluate(self, context: DetectionContext) -> DetectorResult:
        if context.market is None or not context.market.end_date:
            # No end_date available — pass through permissively
            return DetectorResult("timing_gate", 1.0, "no end_date (pass-through)")

        trade_ts = context.trade.get("timestamp", "")
        if not trade_ts:
            return DetectorResult("timing_gate", 1.0, "no timestamp (pass-through)")

        try:
            trade_dt = datetime.fromisoformat(trade_ts)
            if trade_dt.tzinfo is None:
                trade_dt = trade_dt.replace(tzinfo=timezone.utc)

            end_dt = datetime.fromisoformat(context.market.end_date)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)

            hours_before = (end_dt - trade_dt).total_seconds() / 3600

            if hours_before > self._min_hours:
                return DetectorResult(
                    "timing_gate", 1.0, f"{hours_before:.1f}h before"
                )
            else:
                return DetectorResult(
                    "timing_gate", 0.0, f"{-hours_before:.1f}h after start"
                )
        except (ValueError, TypeError):
            return DetectorResult("timing_gate", 1.0, "unparseable date (pass-through)")
