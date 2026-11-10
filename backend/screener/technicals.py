"""Latest-day technical snapshot per ticker, for the screener.

These are price-only fields (no fundamentals) that let the screener filter on
"where is the stock technically right now": above/below its 50-day average, how
far from its 52-week high/low, RSI, etc. Mirrors moneyflow.snapshot's shape so
fundamentals.screen can join both from the SAME price panels (one fetch).

All inputs are wide panels (index=date, columns=ticker). Everything uses only
past data — the latest valid value per ticker — so no look-ahead.
"""
from __future__ import annotations

import pandas as pd



def rsi(close: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Wilder's RSI in [0, 100] (Wilder smoothing == EMA with alpha = 1/window)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    return 100.0 - 100.0 / (1.0 + rs)

# 52 weeks ≈ 252 trading days; 50-day MA is the common "is it trending up" line.
_HI_LO_WINDOW = 252
_MA_WINDOW = 50
_RSI_WINDOW = 14


def snapshot(panels: dict) -> pd.DataFrame:
    """Per-ticker technical snapshot for the screener.

    `panels` is {field: wide_panel} with high/low/close. Returns a DataFrame
    indexed by ticker with:
      * ma50_pct  — % of price above (+) / below (-) its 50-day average
      * hi52_pct  — % from the 52-week high (0 = at the high, -20 = 20% below)
      * lo52_pct  — % above the 52-week low (0 = at the low, +50 = 50% above)
      * rsi14     — raw Wilder RSI in [0,100]
    """
    high, low, close = panels["high"], panels["low"], panels["close"]

    # Each ticker's LAST VALID value, not the last calendar row (often a NaN
    # weekend/partial bar) — same approach as moneyflow.snapshot.
    def _last_valid(df: pd.DataFrame) -> pd.Series:
        return df.ffill().iloc[-1]

    last_close = _last_valid(close)
    ma50 = _last_valid(close.rolling(_MA_WINDOW).mean())
    hi52 = _last_valid(high.rolling(_HI_LO_WINDOW, min_periods=60).max())
    lo52 = _last_valid(low.rolling(_HI_LO_WINDOW, min_periods=60).min())
    r14 = _last_valid(rsi(close, _RSI_WINDOW))

    out = pd.DataFrame({
        # Absolute levels (slow-moving) so the frontend can recompute the % live
        # against the real-time price, instead of being stuck at the last close.
        "ma50": ma50.round(2),
        "hi52": hi52.round(2),
        "lo52": lo52.round(2),
        # Snapshot %s (fallback when no live price is available).
        "ma50_pct": ((last_close / ma50 - 1.0) * 100).round(1),
        "hi52_pct": ((last_close / hi52 - 1.0) * 100).round(1),
        "lo52_pct": ((last_close / lo52 - 1.0) * 100).round(1),
        "rsi14": r14.round(1),
    })
    return out
