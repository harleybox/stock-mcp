# stock-mcp

English | [中文](README.md)

**Give your AI a stock screener.** An MCP server that lets Claude, Cursor and other AI assistants rank every constituent of an index, pull price history, and run live backtests that check whether popular trading recipes carry any information. A local web UI is included.

No sign-up, no API key, no database server — data comes from Yahoo Finance and is cached in a local SQLite file.

> More backtest write-ups and market notes on X: **[@harleybox](https://x.com/harleybox)**

## Connect it to your AI

Requires Python 3.10+. Install first:

```bash
git clone https://github.com/harleybox/stock-mcp.git && cd stock-mcp
```

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
```

**Claude Code** (run inside the repo):

```bash
claude mcp add stock -- "$PWD/.venv/bin/python" "$PWD/backend/mcp_server.py"
```

**Claude Desktop, Cursor and others**: add this to the MCP config (use your absolute paths):

```json
{
  "mcpServers": {
    "stock": {
      "command": "/absolute/path/stock-mcp/.venv/bin/python",
      "args": ["/absolute/path/stock-mcp/backend/mcp_server.py"]
    }
  }
}
```

Then just ask:

- "Top 10 tech stocks in the Nasdaq-100 by combined score, excluding value traps"
- "Where does NVDA rank, and how does it score on value versus growth?"
- "How has BTC done over the last 60 days? Is it above its 60-day average?"
- "Does buying after a 3x-volume bullish candle work? Run the backtest."

The first screen of a universe downloads data (about 1–2 minutes for the Nasdaq-100); the AI gets progress and retries, and later calls hit the local cache.

### Tools

| Tool | What it does |
|---|---|
| `list_universes` | Available universes and which are already cached |
| `screen_stocks` | Rank a universe; sort by any column, filter by sector, money inflow, value traps |
| `get_stock` | Every metric for one ticker plus its rank in the universe |
| `get_price_history` | Daily/weekly bars for any Yahoo symbol (stocks, ETFs, crypto, A-shares) with period return and MA20/60/120 |
| `list_studies` | The built-in backtest studies |
| `run_study` | Run one study live and return its placebo-controlled report |

## Web UI

Also requires Node 20+. The UI is in Chinese.

```bash
./run.sh
```

Open <http://localhost:5173>. The web UI and the MCP server share the same local cache. Click refresh (刷新数据) to re-download.

## Scoring and web features

**Screener table**
- Universes: Nasdaq-100, S&P 500, CSI 300, SSE 50
- Four pillar scores, each a **percentile rank within the universe** (0–100) rather than hard-coded thresholds:
  - Value: P/E, forward P/E, P/B, EV/EBITDA
  - Growth: revenue growth, earnings growth
  - Quality: ROE, net margin, gross margin
  - PEG: P/E ÷ earnings growth
  - Combined = 30% value + 25% growth + 25% quality + 20% PEG
- Technical snapshot: RSI, distance from the 50-day average and the 52-week high, relative volume
- Money-inflow flag (MFI > 50 and rising OBV) and value-trap flag (high debt, or falling earnings with flat revenue)
- Sort by any column; filter by sector, ticker or name

**Chart**
- Daily / weekly candles, MA20 / MA60 / MA120, volume

**Backtest research** → [research/](research/README.md) (Chinese)
- Every script includes a placebo control (the same rules applied to random days), so the question answered is "does this signal carry information", not "did it make money in the past"

## Layout

```
backend/    mcp_server.py (MCP), app.py (web API), screener/ (scoring; fundamentals.py is the core)
frontend/   React + lightweight-charts
research/   standalone backtest scripts
```

## Caveats

- A selection aid, not investment advice.
- Fundamentals are a current snapshot, not point-in-time history, so these scores **cannot be backtested** without look-ahead bias.
- Constituent lists are hand-maintained snapshots and may lag the real index.
- Yahoo data can be delayed, missing or rate-limited; retry after a few minutes if a fetch fails.

## License

[MIT](LICENSE)
