"""Money-flow indicators (volume-based "is money flowing in?").

These approximate fund flow from price + volume — the only kind of flow that's
free to compute. They are AUXILIARY signals: useful to confirm whether a move
has volume behind it, but weak predictors on their own. Combine with
fundamentals / trend, don't trade them in isolation.

All functions take wide panels (index=date, columns=ticker) and return a
same-shaped panel, computed with only past data (no look-ahead).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def obv(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """On-Balance Volume: cumulative volume signed by daily price direction.

    Rising OBV = volume concentrated on up days = net accumulation.
    """
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume).cumsum()


def obv_slope(close: pd.DataFrame, volume: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Normalized OBV trend: % change of OBV over `window`, so it's comparable
    across stocks. Higher = stronger recent accumulation.
    """
    o = obv(close, volume)
    return o.diff(window) / o.abs().rolling(window).mean().replace(0.0, np.nan)


def mfi(high, low, close, volume, window: int = 14) -> pd.DataFrame:
    """Money Flow Index: a volume-weighted RSI in [0, 100].

    >80 overbought (heavy buying), <20 oversold. Measures the strength of
    money flowing in vs out, weighted by where price closed.
    """
    tp = (high + low + close) / 3.0           # typical price
    raw_flow = tp * volume
    pos = raw_flow.where(tp.diff() > 0, 0.0)
    neg = raw_flow.where(tp.diff() < 0, 0.0)
    pos_sum = pos.rolling(window).sum()
    neg_sum = neg.rolling(window).sum().replace(0.0, np.nan)
    ratio = pos_sum / neg_sum
    return 100.0 - 100.0 / (1.0 + ratio)


def ad_line(high, low, close, volume) -> pd.DataFrame:
    """Accumulation/Distribution line: volume weighted by close's position in
    the day's range. Rising = accumulation.
    """
    rng = (high - low).replace(0.0, np.nan)
    mfm = ((close - low) - (high - close)) / rng   # money flow multiplier in [-1,1]
    return (mfm.fillna(0.0) * volume).cumsum()


def volume_ratio(volume: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Today's volume relative to its `window`-day average. >1 = above-average
    participation (possible conviction behind a move).
    """
    return volume / volume.rolling(window).mean()


def snapshot(panels: dict, window: int = 14) -> pd.DataFrame:
    """Latest-day money-flow snapshot per ticker, for the screener.

    `panels` is {field: wide_panel} with open/high/low/close/volume.
    Returns a per-ticker DataFrame with MFI, OBV slope, volume ratio.
    """
    high, low = panels["high"], panels["low"]
    close, volume = panels["close"], panels["volume"]

    # Use each ticker's LAST VALID value, not the last row — the latest calendar
    # day is often a weekend/partial bar that's NaN for many tickers.
    def _last_valid(df: pd.DataFrame) -> pd.Series:
        return df.ffill().iloc[-1]

    m = _last_valid(mfi(high, low, close, volume, window))
    os_ = _last_valid(obv_slope(close, volume, 20))
    vr = _last_valid(volume_ratio(volume, 20))

    out = pd.DataFrame({
        "mfi": m.round(1),
        "obv_slope": os_.round(4),
        "volume_ratio": vr.round(2),
    })
    # Simple inflow signal: MFI above 50 AND OBV trending up.
    out["inflow"] = ((out["mfi"] > 50) & (out["obv_slope"] > 0))
    return out
