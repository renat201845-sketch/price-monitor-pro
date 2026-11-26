# price-monitor-pro

Modular Python CLI utility for tracking product prices, storing historical measurements in SQLite, calculating price statistics, and sending deal alerts.

## Architecture

- `main.py` — CLI entry point (`check`, `stats`, `history`, `--verbose` logging).
- `db.py` — SQLite schema (`items`, `price_history`), upsert/insert operations, and aggregate SQL queries (`MIN`, `MAX`, `AVG`, latest price).
- `fetcher.py` — HTML parsing with selector/meta/currency extraction, price normalization, and fallback support using only the Python standard library.
- `notifier.py` — Console deal alerts and optional Telegram Bot API notifications.
- `config.json` — Monitored items, target prices, request timeout, and notification settings.

## Usage

```bash
python main.py check
python main.py stats
python main.py history "Example Mechanical Keyboard"