"""Shared service layer used by both the web API (app.py) and the MCP server.

Owns the background fetch jobs and turns stored snapshots / price history into
plain JSON-safe dicts.
"""
from __future__ import annotations

import math
import threading
from datetime import date, timedelta

import pandas as pd

from . import store
from .fundamentals import screen
from .universe import get_universe

UNIVERSES = {
    "nasdaq100": "纳斯达克100",
    "sp500": "标普500",
    "csi300": "沪深300",
    "sse50": "上证50",
}

# universe -> {"done": int, "total": int, "error": str | None}; present only while fetching
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_BOOL_COLS = {"value_trap_flag", "inflow"}


def _run(universe: str) -> None:
    job = _JOBS[universe]
    try:
        tickers = get_universe(universe)
        job["total"] = len(tickers)

        def progress(done: int, total: int) -> None:
            job["done"], job["total"] = done, total

        store.save(universe, screen(tickers, progress=progress))
        with _LOCK:
            _JOBS.pop(universe, None)
    except Exception as e:  # noqa: BLE001
        job["error"] = str(e) or type(e).__name__


def start_fetch(universe: str) -> None:
    """Start a background re-fetch unless one is already running."""
    with _LOCK:
        job = _JOBS.get(universe)
        if job and not job.get("error"):
            return
        _JOBS[universe] = {"done": 0, "total": 0, "error": None}
    threading.Thread(target=_run, args=(universe,), daemon=True).start()


def job(universe: str) -> dict | None:
    return _JOBS.get(universe)


def _clean(v):
    """JSON-safe scalar: NaN/inf -> None, numpy types -> python."""
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, (int, float)) or hasattr(v, "item"):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    return v


def rows(universe: str) -> tuple[list[dict], float | None]:
    """Scored rows for a universe (best first) and when they were saved.

    Returns ([], None) when nothing has been fetched yet.
    """
    snap = store.load(universe)
    if snap is None:
        return [], None
    df, saved_at = snap
    out = []
    for tk, r in df.iterrows():
        item = {"ticker": tk}
        for c in df.columns:
            v = r[c]
            item[c] = (bool(v) if pd.notna(v) else None) if c in _BOOL_COLS else _clean(v)
        cur, tgt = item.get("currentPrice"), item.get("targetMeanPrice")
        item["upside"] = round(tgt / cur - 1.0, 4) if (cur and tgt and cur > 0) else None
        out.append(item)
    return out, saved_at


def bars(ticker: str, days: int = 730, freq: str = "daily") -> list[dict]:
    """Daily or weekly OHLCV bars, oldest first (split/dividend adjusted)."""
    import yfinance as yf

    t = ticker.strip().upper()
    start = (date.today() - timedelta(days=days)).isoformat()
    end = (date.today() + timedelta(days=1)).isoformat()   # yfinance end is exclusive
    df = yf.download(t, start=start, end=end, auto_adjust=True, progress=False, threads=False)
    if df is None or df.empty:
        return []
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    # Yahoo sometimes returns today's row with all-NaN OHLC (volume only): drop it.
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if freq == "weekly":
        df = df.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min",
                                       "Close": "last", "Volume": "sum"}).dropna(subset=["Close"])
    return [{"time": d.strftime("%Y-%m-%d"),
             "open": round(float(r.Open), 4), "high": round(float(r.High), 4),
             "low": round(float(r.Low), 4), "close": round(float(r.Close), 4),
             "volume": int(r.Volume) if pd.notna(r.Volume) else 0}
            for d, r in df.iterrows()]
