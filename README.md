<div align="center">

# stock-mcp

### 给你的 AI 装一个选股工具

让 Claude、Cursor 直接给整个指数打分排名、看 K 线,<br>
还能现场跑回测,验一验「网上那套交易方法」到底有没有用。

[![License: MIT](https://img.shields.io/badge/License-MIT-3ecf6b.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/Python-3.10+-4f9cf9.svg)
![MCP](https://img.shields.io/badge/MCP-server-8b5cf6.svg)
[![X @harleybox](https://img.shields.io/badge/X-@harleybox-000000.svg?logo=x)](https://x.com/harleybox)

[English](README.en.md) · 中文

<img src="docs/demo.png" alt="在 AI 里提问:选股与回测验证" width="100%">

<sub>示意图 —— 表里的数字是 2026-11-09 真实调用返回的结果</sub>

</div>

## 为什么做这个

- **不用注册,不用 API key,不用数据库。** 数据来自 Yahoo Finance,缓存在本地一个 SQLite 文件里。
- **AI 拿到的是算好的数,不是让它自己编。** 四个维度的池内排名、资金流入、价值陷阱标记,都是代码算出来再交给 AI 解读。
- **自带「打假」工具。** 每份回测都带安慰剂对照:同样的规则套在随机挑的日子上。真信号比不过随机日,就是没用。

## 三步装好

需要 Python 3.10+。

```bash
git clone https://github.com/harleybox/stock-mcp.git && cd stock-mcp
```

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
```

```bash
claude mcp add stock -- "$PWD/.venv/bin/python" "$PWD/backend/mcp_server.py"
```

<details>
<summary>Claude Desktop / Cursor 等其它客户端</summary>

在 MCP 配置里加一段,路径换成你的绝对路径:

```json
{
  "mcpServers": {
    "stock": {
      "command": "/绝对路径/stock-mcp/.venv/bin/python",
      "args": ["/绝对路径/stock-mcp/backend/mcp_server.py"]
    }
  }
}
```

</details>

## 然后直接问

> 纳指100 里综合分最高的 10 只科技股,排除价值陷阱

> NVDA 在池子里排第几?估值和成长各多少分?

> BTC 最近 60 天走势怎么样,在 60 日均线上面还是下面?

> 三倍量阳线买入法有用吗?跑一下回测

第一次筛某个股票池要现拉数据(纳指100 约 1~2 分钟),AI 会收到进度并自动重试,之后走本地缓存。

## 网上的交易方法,验了三个

| 方法 | 流传的说法 | 实测 |
|---|---|---|
| Larry Williams 外包线 | BTC 胜率 94% | 1190 个信号,5 个参数格全部和随机日没区别 |
| 三倍量阳线 + 回踩 | 放量阳线后缩量回踩就买 | 16 个参数格全部和随机日没区别;「三倍量」十年只出现 6 次 |
| EMA 五线多头排列 | 均线全多头排列就持有 | 年化 9.0%,买入持有是 14.9% |

三个都没测出比「随便哪天买」更多的东西。口径、完整数字和复现命令在 [research/](research/README.md),也可以让 AI 用 `run_study` 现场跑。

**更多回测结论和看盘笔记发在 X → [@harleybox](https://x.com/harleybox)**

## 也有网页版

还需要 Node 20+。

```bash
./run.sh
```

打开 <http://localhost:5173>。网页和 MCP 共用同一份本地缓存。

<img src="docs/screener.png" alt="选股表" width="100%">

点任意一行看 K 线(日线 / 周线,MA20 / 60 / 120,成交量);`/?chart=NVDA` 可以直接打开某只的图。

<img src="docs/chart.png" alt="K 线图" width="100%">

## 工具列表

| 工具 | 作用 |
|---|---|
| `list_universes` | 有哪些股票池、哪些已有本地缓存 |
| `screen_stocks` | 给股票池打分排名;可按任意列排序,按行业、资金流入、排除价值陷阱过滤 |
| `get_stock` | 单只股票的全部指标和池内排名 |
| `get_price_history` | 任意 Yahoo 代码的日线 / 周线(美股、ETF、币、A股),附区间涨跌和 MA20/60/120 |
| `list_studies` | 内置了哪些回测研究 |
| `run_study` | 现场跑一份回测,返回带安慰剂对照的结果 |

股票池:纳斯达克100、标普500、沪深300、上证50。

<details>
<summary><b>分数是怎么算的</b></summary>

四个维度都是**池内百分位排名**(0~100),不用写死的阈值:

| 维度 | 用到的指标 | 权重 |
|---|---|---|
| 价值 | PE、预期PE、PB、EV/EBITDA | 30% |
| 成长 | 营收增速、盈利增速 | 25% |
| 质量 | ROE、净利率、毛利率 | 25% |
| PEG | PE ÷ 盈利增速 | 20% |

另外附带:

- 技术面快照:RSI、距 50 日线、距 52 周高点、量比
- 资金流入标记:MFI > 50 且 OBV 向上
- 价值陷阱标记:高负债,或盈利下滑且营收不增长

核心逻辑在 [backend/screener/fundamentals.py](backend/screener/fundamentals.py),一个文件能读完。

</details>

<details>
<summary><b>目录结构</b></summary>

```
backend/    mcp_server.py(MCP)、app.py(网页接口)、screener/(打分逻辑)
frontend/   React + lightweight-charts
research/   回测脚本,可单独运行
```

</details>

## 须知

- 这是**选股辅助**,不构成投资建议。
- 基本面是当前快照,不是历史时点数据,所以这套打分**不能拿去回测**(会有前视偏差)。
- 成分股名单是手工维护的快照,可能和最新成分有出入。
- Yahoo 的数据可能延迟、缺失或限流;拉取失败过几分钟再试。

## License

[MIT](LICENSE) · 觉得有用就点个 ⭐,或者来 X 找我聊:[@harleybox](https://x.com/harleybox)
