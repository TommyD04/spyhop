"""Paper executor — records simulated trade entries and reads portfolio state."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from spyhop.storage import db


@dataclass
class PaperEntry:
    """All data needed to record a paper position."""
    trade_id: int
    signal_id: int
    condition_id: str
    market_question: str
    outcome: str
    outcome_index: int
    side: str  # always "BUY" after normalization
    entry_price: float
    size_usd: float
    token_qty: float  # size_usd / entry_price
    score_at_entry: float
    wallet: str
    entry_timestamp: str


@dataclass
class PaperTradeResult:
    """Outcome of a paper trade attempt."""
    executed: bool
    position_id: int | None = None
    size_usd: float = 0.0
    reason: str = ""


@dataclass
class PortfolioSummary:
    """Aggregated portfolio statistics."""
    starting_capital: float
    total_deployed: float
    available_capital: float
    open_count: int
    unrealized_pnl: float


class PaperExecutor:
    """Records paper positions in the database."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, entry: PaperEntry) -> int:
        """Insert a paper position, returns position ID."""
        position = {
            "trade_id": entry.trade_id,
            "signal_id": entry.signal_id,
            "condition_id": entry.condition_id,
            "market_question": entry.market_question,
            "outcome": entry.outcome,
            "outcome_index": entry.outcome_index,
            "side": entry.side,
            "entry_price": entry.entry_price,
            "size_usd": entry.size_usd,
            "token_qty": entry.token_qty,
            "score_at_entry": entry.score_at_entry,
            "wallet": entry.wallet,
            "entry_timestamp": entry.entry_timestamp,
        }
        return db.insert_paper_position(self._conn, position)

    def get_portfolio_summary(
        self,
        starting_capital: float,
        market_prices: dict[str, list[float]] | None = None,
    ) -> PortfolioSummary:
        """Aggregate open positions with optional mark-to-market.

        Args:
            starting_capital: Initial simulated capital.
            market_prices: Optional dict of condition_id → [yes_price, no_price]
                for mark-to-market. If None, unrealized P&L is 0.
        """
        positions = db.get_open_positions(self._conn)
        total_deployed = sum(p["size_usd"] for p in positions)
        unrealized = 0.0

        if market_prices:
            for pos in positions:
                prices = market_prices.get(pos["condition_id"])
                if prices and len(prices) > pos["outcome_index"]:
                    current = prices[pos["outcome_index"]]
                    unrealized += (current - pos["entry_price"]) * pos["token_qty"]

        return PortfolioSummary(
            starting_capital=starting_capital,
            total_deployed=total_deployed,
            available_capital=starting_capital - total_deployed,
            open_count=len(positions),
            unrealized_pnl=unrealized,
        )
