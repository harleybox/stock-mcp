"""Local snapshot store: one SQLite file, one row per universe.

Fetching fundamentals for a whole index takes a minute or two, so the scored
table is persisted and reused until the user asks for a refresh.
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from io import StringIO
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "screener.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute("CREATE TABLE IF NOT EXISTS snapshot ("
              "universe TEXT PRIMARY KEY, saved_at REAL NOT NULL, payload TEXT NOT NULL)")
    return c


def save(universe: str, df: pd.DataFrame) -> None:
    with closing(_conn()) as c, c:
        c.execute("INSERT OR REPLACE INTO snapshot VALUES (?, ?, ?)",
                  (universe, time.time(), df.to_json(orient="split")))


def load(universe: str) -> tuple[pd.DataFrame, float] | None:
    """Return (scored table, saved_at epoch seconds), or None if never fetched."""
    with closing(_conn()) as c:
        row = c.execute("SELECT payload, saved_at FROM snapshot WHERE universe = ?",
                        (universe,)).fetchone()
    if not row:
        return None
    return pd.read_json(StringIO(row[0]), orient="split"), row[1]
