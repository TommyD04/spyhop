# Spyhop

> A spyhop is when a whale pokes its head above the waterline to observe its surroundings.

Local-first Python CLI that monitors Polymarket for whale trading activity via public APIs.

## Requirements

- Python 3.11+

## Installation

```bash
cd spyhop
pip install -e .
```

This installs the `spyhop` command. You can also run directly with `python -m spyhop`.

## Configuration

Spyhop uses a `config.toml` file. Place it in the project root or at `~/.config/spyhop/config.toml` (Linux/macOS) / `%APPDATA%\spyhop\config.toml` (Windows).

Default settings are built in -- the config file is optional and only needed to override defaults.

```toml
[ingestor]
usd_threshold = 10_000          # Minimum trade size in USD to display
ws_url = "wss://ws-live-data.polymarket.com"
reconnect_delay_sec = 5

[market_cache]
gamma_url = "https://gamma-api.polymarket.com"
ttl_minutes = 60

[profiler]
data_api_url = "https://data-api.polymarket.com"
max_trades_to_fetch = 200
wallet_cache_ttl_minutes = 30

[display]
max_rows = 50
```

## Usage

### Watch live trades

Stream whale trades in real time with a Rich live table:

```bash
spyhop watch
```

The table shows timestamp, wallet name/address, wallet trade count (Wlt column), side, USDC amount, price, and market question. Fresh wallets (5 or fewer prior trades) are highlighted in yellow/red.

### Look up a wallet

Deep-fetch a wallet's profile and recent trade history:

```bash
spyhop wallet <address>
```

Example:

```bash
spyhop wallet 0xd04d93BE590Ded67B99F053d4B6D29D3F8483312
```

Displays a profile panel (trade count, unique markets, wallet age, freshness) and a table of the 20 most recent trades.

### Options

```
-v, --verbose    Enable debug logging
-c, --config     Path to a custom config.toml
```

Examples:

```bash
spyhop -v watch                          # verbose logging
spyhop -c /path/to/config.toml watch     # custom config
```

## Data Storage

Spyhop stores data in a local SQLite database:

- **Linux/macOS**: `~/.local/share/spyhop/spyhop.db`
- **Windows**: `%LOCALAPPDATA%\spyhop\spyhop.db`

Tables: `trades` (persisted whale trades), `markets` (Gamma API cache), `wallets` (Data API profile cache).

## Architecture

```
CLI (Rich)  <--  watch / wallet commands
                   |
               PROFILER (wallet history + market metadata)
                   |
               INGESTOR (RTDS WebSocket live stream)
                   |
               STORAGE (SQLite)
```

Pipeline: `ingestor -> profiler -> display`

## Dependencies

- [httpx](https://www.python-httpx.org/) -- async HTTP client
- [websockets](https://websockets.readthedocs.io/) -- RTDS WebSocket connection
- [rich](https://rich.readthedocs.io/) -- terminal tables and live display
