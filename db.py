import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                target_price REAL,
                currency TEXT NOT NULL DEFAULT 'PLN',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                price REAL NOT NULL,
                source TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_history_item_checked
                ON price_history(item_id, checked_at DESC);
            """
        )


def upsert_item(
    db_path: Path,
    name: str,
    url: str,
    target_price: Optional[float],
    currency: str,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO items (name, url, target_price, currency, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                url = excluded.url,
                target_price = excluded.target_price,
                currency = excluded.currency
            """,
            (name, url, target_price, currency, now),
        )
        row = conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()
        return int(row["id"])


def add_price_record(db_path: Path, item_id: int, price: float, source: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO price_history (item_id, price, source, checked_at)
            VALUES (?, ?, ?, ?)
            """,
            (item_id, price, source, now),
        )


def get_item_history(db_path: Path, name: str, limit: int = 10) -> list[sqlite3.Row]:
    with get_connection(db_path) as conn:
        return conn.execute(
            """
            SELECT h.price, h.source, h.checked_at, i.currency
            FROM price_history h
            JOIN items i ON i.id = h.item_id
            WHERE i.name = ?
            ORDER BY h.id DESC
            LIMIT ?
            """,
            (name, limit),
        ).fetchall()


def get_all_stats(db_path: Path) -> list[sqlite3.Row]:
    with get_connection(db_path) as conn:
        return conn.execute(
            """
            SELECT
                i.name,
                i.currency,
                i.target_price,
                COUNT(h.id) AS checks_count,
                MIN(h.price) AS min_price,
                MAX(h.price) AS max_price,
                ROUND(AVG(h.price), 2) AS avg_price,
                (
                    SELECT h2.price
                    FROM price_history h2
                    WHERE h2.item_id = i.id
                    ORDER BY h2.id DESC
                    LIMIT 1
                ) AS last_price
            FROM items i
            LEFT JOIN price_history h ON h.item_id = i.id
            GROUP BY i.id
            ORDER BY i.name ASC
            """
        ).fetchall()	