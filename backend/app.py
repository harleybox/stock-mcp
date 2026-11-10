"""Stock screener web API (the browser UI talks to this).

    GET  /api/universes        available stock pools
    GET  /api/screen           scored table for a pool (kicks off a fetch if none saved)
    POST /api/screen/refresh   re-pull from yfinance in the background
    GET  /api/bars             daily / weekly OHLCV for the chart

Everything runs locally: data comes from yfinance, snapshots live in SQLite.
The same logic is exposed to AI assistants by mcp_server.py.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from screener import service

app = FastAPI(title="stock-mcp")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _check(universe: str) -> None:
    if universe not in service.UNIVERSES:
        raise HTTPException(400, f"unknown universe {universe!r}")


@app.get("/api/universes")
def universes() -> list[dict]:
    return [{"id": k, "label": v} for k, v in service.UNIVERSES.items()]


@app.get("/api/screen")
def screen_endpoint(universe: str = Query("nasdaq100")) -> dict:
    _check(universe)
    rows, saved_at = service.rows(universe)
    if saved_at is None and service.job(universe) is None:
        service.start_fetch(universe)
    return {"universe": universe, "rows": rows, "saved_at": saved_at, "job": service.job(universe)}


@app.post("/api/screen/refresh")
def screen_refresh(universe: str = Query("nasdaq100")) -> dict:
    _check(universe)
    service.start_fetch(universe)
    return {"job": service.job(universe)}


@app.get("/api/bars")
def bars(ticker: str = Query(...), days: int = Query(730, ge=30, le=3650),
         freq: str = Query("daily", pattern="^(daily|weekly)$")) -> dict:
    return {"ticker": ticker.strip().upper(), "bars": service.bars(ticker, days, freq)}
