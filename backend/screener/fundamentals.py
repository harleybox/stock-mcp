"""Fundamental data + value/growth/quality scoring (stock screener).

⚠️ This is a SELECTION AID, not a backtestable strategy. yfinance fundamentals
are a CURRENT snapshot (not point-in-time history), so backtesting these scores
would have look-ahead bias. Use it to surface candidates to research by hand —
not to claim a historical edge.

Scoring philosophy (matches "undervalued + good prospects"):
* VALUE   — is it cheap? (P/E, forward P/E, P/B, EV/EBITDA)
* GROWTH  — is it growing? (revenue & earnings growth)
* QUALITY — does it actually make money well? (ROE, net & gross margin)
* Plus a self-computed PEG (P/E ÷ earnings-growth%) — cheap RELATIVE to growth,
  the single best "undervalued + growing" gauge — and a value-trap guard.

Each stock is ranked by percentile within the screened set on each pillar, then
combined. Cross-sectional ranking avoids hard-coded thresholds that age badly.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_FIELDS = [
    "longName", "shortName",
    "trailingPE", "forwardPE", "priceToBook", "enterpriseToEbitda",
    "returnOnEquity", "profitMargins", "grossMargins",
    "revenueGrowth", "earningsGrowth", "debtToEquity",
    "marketCap", "sector", "currentPrice", "dividendYield",
    "recommendationKey", "recommendationMean", "targetMeanPrice",
]


def _fetch_info(sym: str, attempts: int = 5) -> dict:
    """Fetch yfinance .info, retrying on a partial payload or rate limit.

    yfinance's .info intermittently returns a sparse subset (e.g. P/E present but
    revenueGrowth/currentPrice/analyst fields missing). A present currentPrice or
    marketCap signals a full payload; retry a fresh Ticker otherwise. On a
    "Too Many Requests" rate-limit error we back off exponentially before
    retrying so a large universe (e.g. S&P 500) eventually fetches in full.
    """
    import time

    import yfinance as yf

    info: dict = {}
    delay = 0.0
    for i in range(attempts):
        if delay:
            time.sleep(delay)
        try:
            info = yf.Ticker(sym).info or {}
        except Exception as e:
            info = {}
            msg = str(e)
            if "Too Many Requests" in msg or "Rate limit" in msg:
                delay = max(delay * 2, 3.0)  # back off hard on rate limit
                continue
            if "Not Found" in msg or "Quote not found" in msg:
                return {}  # delisted / invalid symbol — retrying is wasted
        if info.get("currentPrice") is not None or info.get("marketCap") is not None:
            return info
        if len(info) <= 3 and i >= 1:
            return {}  # near-empty payload twice → delisted/invalid, stop reconnecting
        delay = max(delay * 1.5, 1.0)  # partial payload → gentle retry
    return info  # return whatever we last got (may be partial)


def fetch_fundamentals(tickers: list[str], throttle: float = 0.12, progress=None) -> pd.DataFrame:
    """Pull a current fundamental snapshot for each ticker (best-effort).

    ``throttle`` is a small inter-request sleep to stay under yfinance's rate
    limit when scanning a large universe.
    """
    import time

    rows = []
    for i, sym in enumerate(tickers):
        if progress:
            progress(i, len(tickers))
        info = _fetch_info(sym)
        if info:
            row = {"ticker": sym}
            for f in _FIELDS:
                row[f] = info.get(f)
            rows.append(row)
        if throttle:
            time.sleep(throttle)
    if not rows:
        raise RuntimeError("yfinance returned no fundamentals (rate-limited or offline?)")
    df = pd.DataFrame(rows).set_index("ticker")
    # Self-computed PEG: P/E ÷ (earnings growth in %). Lower = cheaper vs growth.
    eg = pd.to_numeric(df["earningsGrowth"], errors="coerce") * 100
    pe = pd.to_numeric(df["trailingPE"], errors="coerce")
    df["pegComputed"] = np.where(eg > 0, pe / eg, np.nan)
    return df


def _pct_rank(s: pd.Series, higher_is_better: bool) -> pd.Series:
    """Percentile rank in [0,1]; NaNs get the neutral 0.5 so they don't dominate."""
    x = pd.to_numeric(s, errors="coerce")
    r = x.rank(pct=True)
    if not higher_is_better:
        r = 1.0 - r
    return r.fillna(0.5)


def score(df: pd.DataFrame) -> pd.DataFrame:
    """Add value/growth/quality pillar scores and a combined score (0-100)."""
    out = df.copy()

    # VALUE — cheaper is better (lower multiples).
    value = (
        _pct_rank(out["trailingPE"], False) * 0.30
        + _pct_rank(out["forwardPE"], False) * 0.25
        + _pct_rank(out["priceToBook"], False) * 0.20
        + _pct_rank(out["enterpriseToEbitda"], False) * 0.25
    )
    # GROWTH — faster is better.
    growth = (
        _pct_rank(out["revenueGrowth"], True) * 0.5
        + _pct_rank(out["earningsGrowth"], True) * 0.5
    )
    # QUALITY — more profitable / efficient is better.
    quality = (
        _pct_rank(out["returnOnEquity"], True) * 0.4
        + _pct_rank(out["profitMargins"], True) * 0.35
        + _pct_rank(out["grossMargins"], True) * 0.25
    )
    # PEG — cheap relative to growth (lower is better). Ties value+growth together.
    peg = _pct_rank(out["pegComputed"], False)

    out["value_score"] = (value * 100).round(1)
    out["growth_score"] = (growth * 100).round(1)
    out["quality_score"] = (quality * 100).round(1)
    out["peg_score"] = (peg * 100).round(1)

    # Combined: balance all four. PEG weighted because it captures the core
    # "undervalued + growing" idea directly.
    combined = value * 0.30 + growth * 0.25 + quality * 0.25 + peg * 0.20
    out["combined_score"] = (combined * 100).round(1)

    # Value-trap guard: flag cheap names that look structurally troubled.
    # earningsGrowth is noisy GAAP (amortization/one-offs), so only let an earnings
    # decline count as a trap when revenue ALSO isn't growing — otherwise names
    # like MRVL (rev +28%, EPS beating) mis-flag on GAAP noise.
    d2e = pd.to_numeric(out["debtToEquity"], errors="coerce")
    eg = pd.to_numeric(out["earningsGrowth"], errors="coerce")
    rg = pd.to_numeric(out["revenueGrowth"], errors="coerce")
    out["value_trap_flag"] = ((d2e > 200) | ((eg < -0.10) & (rg < 0.05))).fillna(False)

    return out.sort_values("combined_score", ascending=False)


def fetch_panels(tickers: list[str], days: int = 400) -> dict:
    """Daily OHLCV as wide panels {field: DataFrame(index=date, columns=ticker)}.

    ~400 calendar days covers the 252-day (52-week) high/low window. yfinance's
    ``end`` is EXCLUSIVE, so ask for tomorrow to include today's closed bar.
    """
    from datetime import date, timedelta

    import yfinance as yf

    start = (date.today() - timedelta(days=days)).isoformat()
    end = (date.today() + timedelta(days=1)).isoformat()
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True,
                      progress=False, group_by="column", threads=True)
    if raw is None or raw.empty:
        raise RuntimeError("yfinance returned no price data")
    if not isinstance(raw.columns, pd.MultiIndex):       # single ticker
        raw.columns = pd.MultiIndex.from_product([raw.columns, tickers[:1]])
    # yfinance sometimes emits a placeholder row for today with all-NaN OHLC;
    # drop rows where every close is NaN so "last row" means a real session.
    raw = raw[raw["Close"].notna().any(axis=1)]
    return {f.lower(): raw[f] for f in ["Open", "High", "Low", "Close", "Volume"]}


def screen(tickers: list[str], progress=None) -> pd.DataFrame:
    """Fundamentals + scores, joined with a money-flow and technical snapshot.

    The price-based columns are best-effort: if the price download fails the
    fundamental ranking is still returned.
    """
    from .moneyflow import snapshot as flow_snapshot
    from .technicals import snapshot as tech_snapshot

    df = fetch_fundamentals(tickers, progress=progress)
    try:
        panels = fetch_panels(list(df.index))
        df = df.join(flow_snapshot(panels), how="left")
        df = df.join(tech_snapshot(panels), how="left")
    except Exception as e:  # noqa: BLE001
        import sys

        # stderr, never stdout: the MCP server speaks JSON-RPC over stdout.
        print(f"[screen] price snapshot skipped: {e}", file=sys.stderr)
    return score(df)
