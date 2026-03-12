"""Paper trader — orchestrates risk evaluation and position entry."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from spyhop.detector.base import ScoreResult
from spyhop.paper.executor import PaperEntry, PaperExecutor, PaperTradeResult
from spyhop.paper.risk import RiskEngine
from spyhop.storage import db

log = logging.getLogger(__name__)


class PaperTrader:
    """Top-level orchestrator: score threshold → risk check → execute."""

    def __init__(self, config: dict[str, Any], conn: sqlite3.Connection) -> None:
        self._risk = RiskEngine(config, conn)
        self._executor = PaperExecutor(conn)
        self._min_score = config["paper"].get(
            "min_score", config["scorer"]["alert_threshold"]
        )
        self._capital = config["paper"]["starting_capital"]
        self._conn = conn

    def maybe_trade(
        self,
        trade: dict[str, Any],
        score_result: ScoreResult,
        trade_id: int,
        signal_id: int | None,
    ) -> PaperTradeResult:
        """Evaluate a scored trade for paper entry.

        Always returns a PaperTradeResult — never raises. Errors are logged
        and returned as executed=False so one bad trade cannot kill the stream.
        """
        try:
            if score_result.composite < self._min_score:
                return PaperTradeResult(executed=False, reason="below min_score")
            if signal_id is None:
                return PaperTradeResult(executed=False, reason="no signal")

            # Normalize SELL → BUY opposite outcome
            side = trade.get("side", "BUY")
            outcome = trade.get("outcome", "")
            outcome_index = trade.get("outcome_index", 0)
            entry_price = trade.get("price", 0.0)

            if side == "SELL":
                outcome_index = 1 - outcome_index  # flip to opposite
                entry_price = 1.0 - entry_price
                outcome = f"!{outcome}" if outcome else "Opposite"

            condition_id = trade.get("condition_id", "")
            decision = self._risk.evaluate(condition_id, outcome, score_result.composite)

            if not decision.allowed:
                log.info("Paper trade rejected: %s (score=%.1f, %s)",
                         decision.reject_reason, score_result.composite,
                         condition_id[:12])
                return PaperTradeResult(executed=False, reason=decision.reject_reason)

            token_qty = decision.position_size_usd / entry_price if entry_price > 0 else 0

            entry = PaperEntry(
                trade_id=trade_id,
                signal_id=signal_id,
                condition_id=condition_id,
                market_question=trade.get("market_question", ""),
                outcome=outcome,
                outcome_index=outcome_index,
                side="BUY",
                entry_price=entry_price,
                size_usd=decision.position_size_usd,
                token_qty=token_qty,
                score_at_entry=score_result.composite,
                wallet=trade.get("wallet", ""),
                entry_timestamp=trade.get("timestamp", ""),
            )

            position_id = self._executor.execute(entry)
            log.info(
                "Paper entry: pos=%d, %s, $%.0f @ %.2f¢, score=%.1f",
                position_id, condition_id[:12], decision.position_size_usd,
                entry_price * 100, score_result.composite,
            )
            return PaperTradeResult(
                executed=True,
                position_id=position_id,
                size_usd=decision.position_size_usd,
            )
        except Exception:
            log.exception("Paper trade error for trade_id=%s — skipping", trade_id)
            return PaperTradeResult(executed=False, reason="internal error")

    def get_summary_stats(self) -> dict[str, Any]:
        """Lightweight DB query for dashboard title stats."""
        open_count = db.count_open_positions(self._conn)
        deployed = db.sum_deployed_capital(self._conn)
        return {"open_count": open_count, "deployed": deployed}
