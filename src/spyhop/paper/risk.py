"""Risk engine — position sizing, exposure limits, and duplicate prevention."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from spyhop.storage import db


@dataclass
class RiskDecision:
    """Result of a risk evaluation."""
    allowed: bool
    position_size_usd: float  # 0 if not allowed
    reject_reason: str  # empty if allowed


class RiskEngine:
    """Evaluates whether a paper trade should be taken and at what size.

    When thesis is provided, all position/exposure queries are scoped to
    that thesis — enabling independent capital pools per thesis.
    """

    def __init__(self, config: dict, conn: sqlite3.Connection, thesis: str | None = None) -> None:
        paper_cfg = config["paper"]
        self._capital = paper_cfg["starting_capital"]
        self._base_size = paper_cfg["base_position_usd"]
        self._max_pos_pct = paper_cfg["max_position_pct"]
        self._max_exposure_pct = paper_cfg["max_exposure_pct"]
        self._max_concurrent = paper_cfg["max_concurrent"]
        self._alert_threshold = config["scorer"]["alert_threshold"]
        self._conn = conn
        self._thesis = thesis

    def evaluate(self, condition_id: str, outcome: str, score: float) -> RiskDecision:
        """Decide whether to take a paper position and at what size.

        Checks (in order):
        1. Duplicate: already have an open position on same condition+outcome
        2. Concurrent limit: too many open positions
        3. Score-weighted sizing with per-position cap
        4. Exposure limit: total deployed capital cap
        5. Available capital: enough undeployed capital
        """
        # 0. Anti-hedge: block if we hold ANY position on this market
        if db.has_position_on_market(self._conn, condition_id, thesis=self._thesis):
            return RiskDecision(False, 0.0, "anti-hedge: already positioned on this market")

        # 1. Duplicate check (subset of anti-hedge, kept as safety net)
        if db.has_position_on(self._conn, condition_id, outcome, thesis=self._thesis):
            return RiskDecision(False, 0.0, "duplicate: already positioned on this outcome")

        # 2. Max concurrent positions
        open_count = db.count_open_positions(self._conn, thesis=self._thesis)
        if open_count >= self._max_concurrent:
            return RiskDecision(False, 0.0,
                                f"max concurrent: {open_count}/{self._max_concurrent}")

        # 3. Score-weighted sizing: base × (score / alert_threshold)
        size = self._base_size * (score / self._alert_threshold)

        # 4. Clamp to max per-position size
        max_single = self._max_pos_pct * self._capital
        size = min(size, max_single)

        # 5. Exposure check
        deployed = db.sum_deployed_capital(self._conn, thesis=self._thesis)
        max_exposure = self._max_exposure_pct * self._capital
        if deployed + size > max_exposure:
            remaining = max_exposure - deployed
            if remaining <= 0:
                return RiskDecision(False, 0.0,
                                    f"max exposure: ${deployed:,.0f}/${max_exposure:,.0f}")
            size = remaining  # take what's left

        # 6. Available capital
        available = self._capital - deployed
        if size > available:
            size = available
        if size <= 0:
            return RiskDecision(False, 0.0, "no capital available")

        return RiskDecision(True, size, "")
