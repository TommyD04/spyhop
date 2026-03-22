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
    """Top-level orchestrator: score threshold → risk check → execute.

    Each PaperTrader instance is scoped to a single thesis. The thesis name
    is stored on every position and signal, enabling independent capital
    pools and per-thesis P&L tracking.
    """

    def __init__(
        self,
        config: dict[str, Any],
        conn: sqlite3.Connection,
        thesis: str = "insider",
    ) -> None:
        # Resolve thesis-specific config if available, else fall back to flat
        thesis_cfg = config.get("thesis", {}).get(thesis, {})
        if thesis_cfg:
            paper_cfg = thesis_cfg.get("paper", config.get("paper", {}))
            scorer_cfg = thesis_cfg.get("scorer", config.get("scorer", {}))
            mm_cfg = thesis_cfg.get("detector", {}).get("mm_filter", {})
            exclude_cats = set(thesis_cfg.get("exclude_categories", []))
        else:
            paper_cfg = config["paper"]
            scorer_cfg = config["scorer"]
            mm_cfg = config.get("detector", {}).get("mm_filter", {})
            exclude_cats = set(config["paper"].get("blocked_categories", []))

        # Build risk engine with thesis-scoped config
        risk_config = {"paper": paper_cfg, "scorer": scorer_cfg}
        self._risk = RiskEngine(risk_config, conn, thesis=thesis)
        self._executor = PaperExecutor(conn)
        self._min_score = paper_cfg.get("min_score", scorer_cfg.get("alert_threshold", 7))
        self._capital = paper_cfg["starting_capital"]
        self._max_days = paper_cfg.get("max_days_to_resolution", 30)
        self._blocked_categories = exclude_cats
        self._thesis = thesis

        # MM filter config
        self._mm_enabled = mm_cfg.get("enabled", False)
        self._wallet_lookback_minutes = mm_cfg.get("wallet_lookback_minutes", 120)
        self._pair_max_gap_seconds = mm_cfg.get("pair_max_gap_seconds", 10)
        self._settle_delay = mm_cfg.get("settle_delay_seconds", 5)
        self._conn = conn

    @property
    def thesis(self) -> str:
        """Thesis name for this trader instance."""
        return self._thesis

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

            # Category blocklist — skip categories with no signal for this thesis
            category = trade.get("primary_tag", "")
            if category and self._blocked_categories and category in self._blocked_categories:
                log.info(
                    "Paper trade rejected [%s]: blocked category %s, %s",
                    self._thesis, category, trade.get("condition_id", "")[:12],
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
                        "Paper trade rejected [%s]: wallet traded opposite side within %dm, %s",
                        self._thesis, self._wallet_lookback_minutes, cid[:12],
                    )
                    return PaperTradeResult(
                        executed=False,
                        reason=(
                            f"mm_filter: wallet opposite-side"
                            f" within {self._wallet_lookback_minutes}m"
                        ),
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
                        "Paper trade rejected [%s]: matched settlement pair within %ds, %s",
                        self._thesis, self._pair_max_gap_seconds, cid[:12],
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
                                "Paper trade rejected [%s]: resolves in %d days (max %d), %s",
                                self._thesis, days_out, self._max_days, condition_id[:12],
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
                log.info("Paper trade rejected [%s]: %s (score=%.1f, %s)",
                         self._thesis, decision.reject_reason, score_result.composite,
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

            position_id = self._executor.execute(entry, thesis=self._thesis)
            log.info(
                "Paper entry [%s]: pos=%d, %s, $%.0f @ %.2f¢, score=%.1f",
                self._thesis, position_id, condition_id[:12],
                decision.position_size_usd, entry_price * 100, score_result.composite,
            )
            return PaperTradeResult(
                executed=True,
                position_id=position_id,
                size_usd=decision.position_size_usd,
            )
        except Exception:
            log.exception("Paper trade error [%s] for trade_id=%s — skipping",
                          self._thesis, trade_id)
            return PaperTradeResult(executed=False, reason="internal error")

    def get_summary_stats(self) -> dict[str, Any]:
        """Lightweight DB query for dashboard title stats (thesis-scoped)."""
        open_count = db.count_open_positions(self._conn, thesis=self._thesis)
        deployed = db.sum_deployed_capital(self._conn, thesis=self._thesis)
        return {"open_count": open_count, "deployed": deployed}
