"""CLI entry point — spyhop watch / wallet / history."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from spyhop.config import load_config, db_path
from spyhop.storage.db import init_db
from spyhop.cli import watch, wallet_lookup, history_view, positions_view, paper_reset


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="spyhop",
        description="Polymarket whale & insider tracker",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "-c", "--config", type=str, default=None, help="Path to config.toml"
    )

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("watch", help="Stream whale trades in real time")
    wallet_parser = sub.add_parser("wallet", help="Look up a wallet profile")
    wallet_parser.add_argument("address", help="Proxy wallet address to look up")
    history_parser = sub.add_parser("history", help="Show past detection signals")
    history_parser.add_argument(
        "--min-score", type=float, default=0.0, help="Minimum score to show (default: 0)"
    )
    history_parser.add_argument(
        "--limit", type=int, default=50, help="Max signals to show (default: 50)"
    )
    history_parser.add_argument(
        "--thesis", type=str, default=None,
        help="Filter by thesis name (e.g. 'insider', 'sporty_investor')",
    )

    positions_parser = sub.add_parser("positions", help="Show open paper trading positions")
    positions_parser.add_argument(
        "--refresh", action="store_true",
        help="Fetch fresh market prices for mark-to-market"
    )

    reset_parser = sub.add_parser("paper-reset", help="Reset paper trading portfolio")
    reset_parser.add_argument(
        "--confirm", action="store_true",
        help="Skip confirmation prompt"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    config_path = args.config
    if config_path:
        from pathlib import Path
        config_path = Path(config_path)

    config = load_config(config_path)
    conn = init_db(db_path())

    if args.command == "watch":
        try:
            asyncio.run(watch(config, conn))
        except KeyboardInterrupt:
            pass
        finally:
            conn.close()

    elif args.command == "wallet":
        try:
            asyncio.run(wallet_lookup(config, conn, args.address))
        except KeyboardInterrupt:
            pass
        finally:
            conn.close()

    elif args.command == "history":
        try:
            asyncio.run(history_view(
                config, conn, limit=args.limit, min_score=args.min_score,
                thesis=args.thesis,
            ))
        except KeyboardInterrupt:
            pass
        finally:
            conn.close()

    elif args.command == "positions":
        try:
            asyncio.run(positions_view(config, conn, refresh=args.refresh))
        except KeyboardInterrupt:
            pass
        finally:
            conn.close()

    elif args.command == "paper-reset":
        try:
            paper_reset(conn, confirm=args.confirm)
        except KeyboardInterrupt:
            pass
        finally:
            conn.close()


if __name__ == "__main__":
    main()
