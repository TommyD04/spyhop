"""CLI entry point — spyhop watch."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from spyhop.config import load_config, db_path
from spyhop.storage.db import init_db
from spyhop.cli import watch, wallet_lookup


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


if __name__ == "__main__":
    main()
