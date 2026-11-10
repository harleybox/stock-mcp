"""stock-mcp: an MCP server that gives AI assistants a stock screener.

Tools:
    list_universes     which stock pools can be screened
    screen_stocks      rank a pool by value / growth / quality / PEG
    get_stock          every stored metric for one ticker
    get_price_history  daily / weekly OHLCV with moving averages
    list_studies       backtest studies of popular trading recipes
    run_study          run one study and return its placebo-controlled result

Runs over stdio. Register it with an MCP client, e.g.:

    claude mcp add stock -- /path/to/.venv/bin/python /path/to/backend/mcp_server.py

No API keys: data comes from Yahoo Finance and is cached in a local SQLite file.
"""
from __future__ import annotations

import contextlib
import subprocess
import sys
import time
from pathlib import Path

import anyio
from mcp.server.mcpserver import MCPServer

from screener import service

ROOT = Path(__file__).resolve().parents[1]

mcp = MCPServer(
    "stock-mcp",
    instructions=(
        "Stock screening and backtest tools backed by Yahoo Finance data. "
        "Scores are percentile ranks WITHIN the chosen universe (0-100, higher is better) "
        "built from a CURRENT fundamentals snapshot: a selection aid, not a backtested "
        "strategy and not investment advice. The first screen of a universe has to download "
        "data and can take minutes; screen_stocks reports progress, so call it again."
    ),
)

# Compact column set for ranked lists; get_stock returns everything.
_LIST_COLS = [
    "ticker", "shortName", "sector", "combined_score", "value_score", "growth_score",
    "quality_score", "peg_score", "currentPrice", "marketCap", "trailingPE", "forwardPE",
    "returnOnEquity", "revenueGrowth", "earningsGrowth", "rsi14", "ma50_pct", "hi52_pct",
    "volume_ratio", "inflow", "value_trap_flag", "upside",
]

STUDIES = {
    "lw_outside_day": {
        "claim": "Larry Williams 'outside day' reversal: a viral video claims a 94% win rate on BTC.",
        "method": "12 US ETFs, 10 years, entry next open, exit at first profitable open, "
                  "stop-buffer grid, vs. 30 rounds of random-day placebo.",
        "cmd": ["lw_outside_day_bt.py", "--set", "etf", "--placebo", "30"],
    },
    "vol3x_bull": {
        "claim": "Buy after a 3x-volume bullish candle once price pulls back on low volume and "
                 "reclaims that candle's close.",
        "method": "13 US ETFs, 10 years, volume-multiple grid 1x-5x and four exit rules, "
                  "vs. 30 rounds of random-day placebo.",
        "cmd": ["vol3x_bull_bt.py", "--set", "etf", "--placebo", "30"],
    },
    "ema_stack_timing": {
        "claim": "Hold a stock only while close > EMA20 > EMA30 > EMA40 > EMA50 > EMA60 "
                 "(a 'fully stacked' uptrend).",
        "method": "First 100 S&P 500 names, 10 years, paired t-test of the timed portfolio "
                  "against buy-and-hold of the same names, plus a non-overlapping event study.",
        "cmd": ["ema_stack_timing_bt.py", "--set", "stock", "--limit", "100"],
    },
}


async def _in_thread(fn, *args):
    """Run blocking work off the event loop, with stray prints kept away from
    stdout (stdout carries the JSON-RPC stream)."""
    def call():
        with contextlib.redirect_stdout(sys.stderr):
            return fn(*args)
    return await anyio.to_thread.run_sync(call)


def _universe_error(universe: str) -> dict | None:
    if universe in service.UNIVERSES:
        return None
    return {"error": f"unknown universe {universe!r}", "available": list(service.UNIVERSES)}


def _progress(universe: str) -> dict:
    job = service.job(universe) or {}
    if job.get("error"):
        return {"status": "failed", "error": job["error"],
                "hint": "Usually Yahoo rate limiting. Retry with refresh=true in a few minutes."}
    return {"status": "fetching", "done": job.get("done", 0), "total": job.get("total", 0),
            "hint": "Downloading fundamentals (roughly 1 second per ticker). Call screen_stocks "
                    "again in about a minute; results are cached locally afterwards."}


@mcp.tool()
async def list_universes() -> list[dict]:
    """List the stock universes that can be screened, and whether each already
    has a locally cached snapshot (cached ones answer instantly)."""
    def work():
        out = []
        for uid, label in service.UNIVERSES.items():
            _, saved_at = service.rows(uid)
            out.append({"id": uid, "label": label, "cached": saved_at is not None,
                        "age_hours": round((time.time() - saved_at) / 3600, 1) if saved_at else None})
        return out
    return await _in_thread(work)


@mcp.tool()
async def screen_stocks(
    universe: str = "nasdaq100",
    top: int = 20,
    sort_by: str = "combined_score",
    ascending: bool = False,
    sector: str | None = None,
    inflow_only: bool = False,
    exclude_value_traps: bool = False,
    refresh: bool = False,
) -> dict:
    """Rank the stocks in a universe.

    Scores are percentile ranks within the universe, 0-100, higher is better:
    value_score (P/E, forward P/E, P/B, EV/EBITDA), growth_score (revenue and
    earnings growth), quality_score (ROE, margins), peg_score (P/E relative to
    growth), and combined_score = 30% value + 25% growth + 25% quality + 20% PEG.

    Args:
        universe: nasdaq100, sp500, csi300 or sse50 (see list_universes).
        top: how many rows to return (max 100).
        sort_by: any returned column, e.g. combined_score, value_score, rsi14, hi52_pct, upside.
        ascending: sort low-to-high instead of high-to-low.
        sector: keep one sector only (case-insensitive substring, e.g. "tech").
        inflow_only: keep only stocks with money flowing in (MFI > 50 and rising OBV).
        exclude_value_traps: drop cheap-but-troubled names (debt/equity > 200%, or
            earnings falling while revenue is flat).
        refresh: re-download from Yahoo instead of using the cached snapshot.

    Ratios such as returnOnEquity, revenueGrowth and upside are fractions (0.25 = 25%);
    ma50_pct and hi52_pct are already in percent. If the universe has no cached data
    yet this starts a download and returns status "fetching": call again shortly.
    """
    if err := _universe_error(universe):
        return err

    def work():
        if refresh:
            service.start_fetch(universe)
        rows, saved_at = service.rows(universe)
        if saved_at is None and service.job(universe) is None:
            service.start_fetch(universe)
        if refresh or saved_at is None:
            # Small pools finish quickly: wait a little so one call is often enough.
            deadline = time.time() + 25
            while time.time() < deadline:
                job = service.job(universe)
                if job is None or job.get("error"):
                    break
                time.sleep(1)
            rows, saved_at = service.rows(universe)
            if service.job(universe) is not None:
                return {"universe": universe, **_progress(universe)}

        if rows and sort_by not in rows[0]:
            return {"error": f"unknown sort_by {sort_by!r}", "available": sorted(rows[0])}
        out = [r for r in rows
               if (not sector or sector.lower() in (r.get("sector") or "").lower())
               and (not inflow_only or r.get("inflow") is True)
               and (not exclude_value_traps or r.get("value_trap_flag") is not True)]
        # Missing values always sort last, whichever direction.
        have = [r for r in out if r.get(sort_by) is not None]
        miss = [r for r in out if r.get(sort_by) is None]
        have.sort(key=lambda r: r[sort_by], reverse=not ascending)
        n = max(1, min(int(top), 100))
        return {
            "universe": universe,
            "status": "ok",
            "snapshot_age_hours": round((time.time() - saved_at) / 3600, 1),
            "universe_size": len(rows),
            "matched": len(out),
            "rows": [{c: r.get(c) for c in _LIST_COLS} for r in (have + miss)[:n]],
        }
    return await _in_thread(work)


@mcp.tool()
async def get_stock(ticker: str) -> dict:
    """Return every stored metric for one ticker (scores, valuation, growth,
    margins, technical snapshot, analyst target) from the cached snapshots.

    Scores are relative to the universe the stock was screened in. A ticker
    only appears here after its universe has been screened with screen_stocks.
    """
    def work():
        t = ticker.strip().upper()
        searched = []
        for uid in service.UNIVERSES:
            rows, saved_at = service.rows(uid)
            if saved_at is None:
                continue
            searched.append(uid)
            for i, r in enumerate(rows):
                if r["ticker"].upper() == t:
                    return {"universe": uid, "rank": i + 1, "universe_size": len(rows),
                            "snapshot_age_hours": round((time.time() - saved_at) / 3600, 1), **r}
        return {"error": f"{t} not found in any cached universe",
                "cached_universes": searched,
                "hint": "Run screen_stocks on the universe that contains it first."}
    return await _in_thread(work)


@mcp.tool()
async def get_price_history(ticker: str, days: int = 180, freq: str = "daily") -> dict:
    """Price history for any Yahoo Finance ticker (US stocks, ETFs, crypto like
    BTC-USD, China A-shares like 600519.SS), split/dividend adjusted.

    Args:
        ticker: Yahoo symbol.
        days: calendar days of history to return (30-3650).
        freq: "daily" or "weekly".

    Returns OHLCV bars (oldest first, at most the last 260) plus a summary with
    the latest close, period return, period high/low and 20/60/120-bar moving averages.
    """
    if freq not in ("daily", "weekly"):
        return {"error": "freq must be 'daily' or 'weekly'"}
    days_ = max(30, min(int(days), 3650))

    def work():
        # Fetch extra history so the long moving average is defined at the last bar.
        extra = 200 if freq == "daily" else 900
        all_bars = service.bars(ticker, days_ + extra, freq)
        if not all_bars:
            return {"ticker": ticker.strip().upper(), "error": "no price data (bad symbol or Yahoo unavailable)"}
        closes = [b["close"] for b in all_bars]
        cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - days_ * 86400))
        view = [b for b in all_bars if b["time"] >= cutoff] or all_bars[-1:]

        def ma(n):
            return round(sum(closes[-n:]) / n, 4) if len(closes) >= n else None

        return {
            "ticker": ticker.strip().upper(),
            "freq": freq,
            "summary": {
                "last_date": view[-1]["time"],
                "last_close": view[-1]["close"],
                "period_return": round(view[-1]["close"] / view[0]["close"] - 1, 4),
                "period_high": max(b["high"] for b in view),
                "period_low": min(b["low"] for b in view),
                "ma20": ma(20), "ma60": ma(60), "ma120": ma(120),
                "bars_in_period": len(view),
            },
            "bars": view[-260:],
        }
    return await _in_thread(work)


@mcp.tool()
async def list_studies() -> list[dict]:
    """List the built-in backtest studies. Each one tests a popular trading
    recipe against a placebo (the same rules applied to random days) to see
    whether the signal carries any information at all."""
    return [{"name": k, "claim": v["claim"], "method": v["method"]} for k, v in STUDIES.items()]


@mcp.tool()
async def run_study(name: str) -> dict:
    """Run one backtest study live on fresh Yahoo data and return its report.

    Takes about 30-90 seconds. The report is a plain-text table (in Chinese).
    How to read it: a signal only "works" if it beats the random-day placebo by
    a clear margin; |z| or |t| below 2 means indistinguishable from random.

    Args:
        name: one of the names from list_studies.
    """
    study = STUDIES.get(name)
    if not study:
        return {"error": f"unknown study {name!r}", "available": list(STUDIES)}

    def work():
        script, *args = study["cmd"]
        try:
            p = subprocess.run([sys.executable, str(ROOT / "research" / script), *args],
                               capture_output=True, text=True, timeout=600, cwd=ROOT)
        except subprocess.TimeoutExpired:
            return {"name": name, "error": "timed out after 10 minutes (Yahoo slow or rate limiting)"}
        if p.returncode != 0:
            return {"name": name, "error": "study failed", "stderr": p.stderr[-2000:]}
        return {"name": name, "claim": study["claim"], "method": study["method"], "report": p.stdout}
    return await _in_thread(work)


if __name__ == "__main__":
    mcp.run()
