"""Paper trader — orchestrates risk evaluation and position entry."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
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
        self._max_days = config["paper"].get("max_days_to_resolution", 30)
        self._blocked_categories: set[str] = set(
            config["paper"].get("blocked_categories", [])
        )
        # MM filter config
        mm_cfg = config.get("detector", {}).get("mm_filter", {})
        self._mm_enabled = mm_cfg.get("enabled", False)
        self._wallet_lookback_minutes = mm_cfg.get("wallet_lookback_minutes", 120)
        self._pair_max_gap_seconds = mm_cfg.get("pair_max_gap_seconds", 10)
        self._settle_delay = mm_cfg.get("settle_delay_seconds", 5)
        self._conn = conn

    @property
    def min_score(self) -> float:
        """Minimum score for paper trade consideration (used by cli for delay gate)."""
        return self._min_score

    @property
    def settle_delay(self) -> float:
        """Seconds to wait for settlement counterparts (0 if MM filter disabled)."""
        return self._settle_delay if self._mm_enabled else 0

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

            # Category blocklist — skip categories with no insider signal
            category = trade.get("primary_tag", "")
            if category and self._blocked_categories and category in self._blocked_categories:
                log.info(
                    "Paper trade rejected: blocked category %s, %s",
                    category, trade.get("condition_id", "")[:12],
                )
                return PaperTradeResult(
                    executed=False, reason=f"blocked category: {category}",
                )

            # MM filter: wallet lookback + matched-pair detection
            if self._mm_enabled:
                side = trade.get("side", "BUY")
                oi = trade.get("outcome_index", 0)
                effective_outcome = (1 - oi) if side == "SELL" else oi
                cid = trade.get("condition_id", "")
                ts = trade.get("timestamp", "")

                # Check 2: same-wallet opposite-side within lookback window
                if db.has_wallet_opposite_trade(
                    self._conn,
                    wallet=trade.get("wallet", ""),
                    condition_id=cid,
                    effective_outcome=effective_outcome,
                    trade_timestamp=ts,
                    lookback_minutes=self._wallet_lookback_minutes,
                ):
                    log.info(
                        "Paper trade rejected: wallet traded opposite side within %dm, %s",
                        self._wallet_lookback_minutes, cid[:12],
                    )
                    return PaperTradeResult(
                        executed=False,
                        reason=f"mm_filter: wallet opposite-side within {self._wallet_lookback_minutes}m",
                    )

                # Check 1: matched settlement pair within gap window
                if db.has_matched_pair(
                    self._conn,
                    condition_id=cid,
                    effective_outcome=effective_outcome,
                    trade_timestamp=ts,
                    max_gap_seconds=self._pair_max_gap_seconds,
                ):
                    log.info(
                        "Paper trade rejected: matched settlement pair within %ds, %s",
                        self._pair_max_gap_seconds, cid[:12],
                    )
                    return PaperTradeResult(
                        executed=False,
                        reason=f"mm_filter: matched pair within {self._pair_max_gap_seconds}s",
                    )

            # Resolution proximity check — skip markets too far out
            if self._max_days > 0:
                condition_id = trade.get("condition_id", "")
                market_row = db.get_market(self._conn, condition_id)
                if market_row and market_row.get("end_date"):
                    try:
                        end_dt = datetime.fromisoformat(market_row["end_date"])
                        if end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=timezone.utc)
                        days_out = (end_dt - datetime.now(timezone.utc)).days
                        if days_out > self._max_days:
                            log.info(
                                "Paper trade rejected: resolves in %d days (max %d), %s",
                                days_out, self._max_days, condition_id[:12],
                            )
                            return PaperTradeResult(
                                executed=False,
                                reason=f"resolves in {days_out}d (max {self._max_days}d)",
                            )
                    except (ValueError, TypeError):
                        pass  # Unparseable date — allow trade through

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
