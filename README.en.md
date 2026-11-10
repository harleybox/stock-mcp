# stock-mcp

English · [中文](README.md) · [![X @harleybox](https://img.shields.io/badge/X-@harleybox-000000.svg?logo=x)](https://x.com/harleybox) [![MIT](https://img.shields.io/badge/License-MIT-3ecf6b.svg)](LICENSE)

**An MCP server that lets Claude and Cursor screen stocks, read price charts and run backtests for you.**

Once it is installed, one sentence gets the AI to rank all hundred Nasdaq-100 stocks by value, growth and quality, pull the price history of any stock or coin, or run a backtest on the spot to see whether a popular buying method does anything.

No sign-up, no API key, free data, and everything runs on your own machine.

<img src="docs/demo.png" alt="Asking an AI to screen stocks and verify a trading method" width="100%">

<sub>Illustration, in Chinese. The numbers are real output from 2026-11-09. Left: "top 5 Nasdaq-100 tech stocks, no value traps". Right: "does the 3x-volume candle method work?"</sub>

## What it can do

### 1. Screen a whole index in one sentence

> Find me the 10 Nasdaq-100 tech stocks that are cheap and still growing. Skip the heavily indebted ones.

The AI receives four scores for every stock in the index (value, growth, quality, PEG) plus a combined score, then sorts and filters them the way you asked. Nasdaq-100, S&P 500, CSI 300 and SSE 50 are covered.

You can sort by any metric, filter by sector, keep only stocks with money flowing in, or drop value traps that look cheap for a bad reason.

### 2. Get the full picture on one stock

> Is NVDA expensive right now? Where does it rank in the Nasdaq-100?

You get every number for that stock: P/E, forward P/E, ROE, revenue and earnings growth, RSI, distance from the 50-day average and the 52-week high, upside to the analyst target, plus its overall rank in the index and its four scores.

### 3. Look up the price history of any symbol

> How has BTC done over the last two months? Is it above or below its 60-day average?

US stocks, ETFs, A-shares and crypto all work, as long as Yahoo has the symbol. Daily or weekly bars, with the period return, high, low and MA20 / 60 / 120.

### 4. Test a trading method on the spot

> Does the 3x-volume candle method hold up? Run the backtest and show me.

The AI runs ten years of data and reports back. Every backtest has a control group: the same entry and exit rules applied to randomly chosen days, 30 times over. If buying on the signal is no better than buying at random, the method is worthless.

Three are built in so far:

| Method | The claim | The result |
|---|---|---|
| Larry Williams outside day | 94% win rate on BTC | 1,190 signals, 5 parameter sets, none better than random days |
| 3x-volume candle, buy the pullback | A high-volume candle followed by a quiet pullback is a buy | All 16 parameter sets matched random |
| EMA five-line stack | Hold while five EMAs are lined up | 9.0% a year, against 14.9% for simply holding |

Full numbers and scripts are in [research/](research/README.md) (Chinese). More tested methods on X: **[@harleybox](https://x.com/harleybox)**

### 5. A web page for when you do not want the AI

The same data as a sortable, filterable table. Click any row for its chart. The interface is in Chinese.

<img src="docs/screener.png" alt="Screener table" width="100%">

<img src="docs/chart.png" alt="Price chart" width="100%">

## Install

You need Python 3.10 or newer.

```bash
git clone https://github.com/harleybox/stock-mcp.git && cd stock-mcp
```

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
```

Connect it to Claude Code:

```bash
claude mcp add stock -- "$PWD/.venv/bin/python" "$PWD/backend/mcp_server.py"
```

<details>
<summary>Connect it to Claude Desktop, Cursor or another client</summary>

Add this to the MCP config, with the absolute paths on your machine:

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

</details>

Then start asking. The first query on an index downloads data, about a minute or two for the Nasdaq-100. After that, answers come back right away.

For the web page, install Node 20 or newer as well, run the command below and open <http://localhost:5173>:

```bash
./run.sh
```

## Details

<details>
<summary><b>How the scores are calculated</b></summary>

Each of the four is a rank inside the index, from 0 to 100. There are no fixed cut-offs.

| Score | Based on | Weight |
|---|---|---|
| Value | P/E, forward P/E, P/B, EV/EBITDA | 30% |
| Growth | Revenue growth, earnings growth | 25% |
| Quality | ROE, net margin, gross margin | 25% |
| PEG | P/E ÷ earnings growth | 20% |

Also included:

- Money inflow: MFI above 50 with OBV rising
- Value trap: high debt, or earnings falling while revenue is flat

All of it lives in [backend/screener/fundamentals.py](backend/screener/fundamentals.py), a single file.

</details>

<details>
<summary><b>The six MCP tools</b></summary>

| Tool | What it does |
|---|---|
| `list_universes` | Which indexes exist and which already have local data |
| `screen_stocks` | Scores and ranks an index, with sorting and filters |
| `get_stock` | Every metric for one stock and its rank in the index |
| `get_price_history` | Daily or weekly bars with period return and moving averages |
| `list_studies` | The built-in backtests |
| `run_study` | Runs one backtest on the spot |

</details>

<details>
<summary><b>Before you rely on it</b></summary>

- It does not pick stocks, predict prices or place orders. A score shows where a stock sits inside its index. For research only, not investment advice.
- Data comes from Yahoo Finance and can be late, missing or rate-limited. If a download fails, try again in a few minutes.
- Fundamentals are today's numbers, so the scores themselves cannot be backtested.
- Index member lists are maintained by hand and may lag the real index.

</details>

---

MIT licensed. A ⭐ helps if you find it useful. More backtests and market notes on X: [@harleybox](https://x.com/harleybox)
