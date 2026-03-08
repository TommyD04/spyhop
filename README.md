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

The table shows timestamp, wallet name/address, wallet trade count (Wlt column), suspicion score, side, USDC amount, price, and market question. Fresh wallets (5 or fewer prior trades) are highlighted in yellow/red. Scores >= 7 trigger alert highlighting; >= 9 are critical.

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

### View detection signals

Show past scored trades, sorted by suspicion score:

```bash
spyhop history
spyhop history --min-score 5      # only medium+ signals
spyhop history --limit 20         # last 20 signals
```

Columns: timestamp, wallet, composite score, F/S/N multipliers (Fresh/Size/Niche), USDC amount, market.

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

Tables: `trades` (persisted whale trades), `markets` (Gamma API cache), `wallets` (Data API profile cache), `signals` (detection scores).

## Architecture

```
CLI (Rich)  <--  watch / wallet / history commands
                   |
               DETECTOR (3 detectors + composite scorer)
                   |
               PROFILER (wallet history + market metadata)
                   |
               INGESTOR (RTDS WebSocket live stream)
                   |
               STORAGE (SQLite)
```

Pipeline: `ingestor -> profiler -> detector -> display`

### Detection Model

Three independent detectors produce multipliers (1.0 = no signal). The scorer multiplies them and maps via log10 to a 0-10 scale:

- **FreshWallet**: flags wallets with 0-5 prior trades (up to 3.0x)
- **SizeAnomaly**: flags trades that are large relative to market daily volume (up to 3.0x)
- **NicheMarket**: flags trades on low-volume markets under $50K/day (up to 2.5x)

Single signal scores ~2-4. Two signals score ~5-7. Three signals score 7-10. Alert threshold: 7. Critical threshold: 9.

## Dependencies

- [httpx](https://www.python-httpx.org/) -- async HTTP client
- [websockets](https://websockets.readthedocs.io/) -- RTDS WebSocket connection
- [rich](https://rich.readthedocs.io/) -- terminal tables and live display
