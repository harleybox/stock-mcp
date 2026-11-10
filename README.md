# stock-mcp

[English](README.en.md) | 中文

**给你的 AI 装一个选股工具。** 一个 MCP server,让 Claude、Cursor 等 AI 助手能直接给整个指数的成分股打分排名、查 K 线、现场跑回测验证「网上那套交易方法到底有没有用」。自带一个本地网页版。

不用注册、不用 API key、不用数据库 —— 数据来自 Yahoo Finance,缓存在本地 SQLite。

> 更多回测结论和看盘笔记发在 X:**[@harleybox](https://x.com/harleybox)**

## 接到 AI 里

需要 Python 3.10+。先装依赖:

```bash
git clone https://github.com/harleybox/stock-mcp.git && cd stock-mcp
```

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
```

**Claude Code**(在仓库目录里执行):

```bash
claude mcp add stock -- "$PWD/.venv/bin/python" "$PWD/backend/mcp_server.py"
```

**Claude Desktop / Cursor 等**:在 MCP 配置里加一段(路径换成你的绝对路径):

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

然后直接问:

- 「纳指100 里综合分最高的 10 只科技股,排除价值陷阱」
- 「NVDA 在池子里排第几?估值和成长各多少分?」
- 「BTC 最近 60 天走势怎么样,在 60 日均线上面还是下面?」
- 「三倍量阳线买入法有用吗?跑一下回测」

第一次筛某个股票池要现拉数据(纳指100 约 1~2 分钟),AI 会收到进度并自动重试,之后走本地缓存。

### 工具列表

| 工具 | 作用 |
|---|---|
| `list_universes` | 有哪些股票池、哪些已有本地缓存 |
| `screen_stocks` | 给股票池打分排名;可按任意列排序,按行业、资金流入、排除价值陷阱过滤 |
| `get_stock` | 单只股票的全部指标和池内排名 |
| `get_price_history` | 任意 Yahoo 代码的日线/周线(美股、ETF、币、A股),附区间涨跌和 MA20/60/120 |
| `list_studies` | 内置了哪些回测研究 |
| `run_study` | 现场跑一份回测,返回带安慰剂对照的结果 |

## 网页版

还需要 Node 20+。

```bash
./run.sh
```

打开 <http://localhost:5173>。网页和 MCP 共用同一份本地缓存。想更新数据点右上角「刷新数据」。

## 打分方法与网页功能

**选股表**
- 股票池:纳斯达克100、标普500、沪深300、上证50
- 四个维度打分,都是**池内百分位排名**(0~100),不用写死的阈值:
  - 价值:PE、预期PE、PB、EV/EBITDA
  - 成长:营收增速、盈利增速
  - 质量:ROE、净利率、毛利率
  - PEG:PE ÷ 盈利增速,相对成长是否便宜
  - 综合 = 价值30% + 成长25% + 质量25% + PEG20%
- 技术面快照:RSI、距50日线、距52周高点、量比
- 资金流入标记(MFI > 50 且 OBV 向上)、价值陷阱标记(高负债,或盈利下滑且营收不增长)
- 按任意列排序,按行业 / 代码 / 公司名筛选

**K 线图**
- 日线 / 周线,MA20 / MA60 / MA120,成交量

**回测研究** → [research/](research/README.md)
- 每份都带安慰剂对照(同样的规则套在随机日子上),回答的是「这个信号有没有信息」,而不是「过去赚没赚钱」

## 目录

```
backend/    mcp_server.py(MCP)、app.py(网页接口)、screener/(打分逻辑,fundamentals.py 是核心)
frontend/   React + lightweight-charts
research/   回测脚本,可单独运行
```

## 须知

- 这是**选股辅助**,不构成投资建议。
- 基本面是当前快照,不是历史时点数据,所以这套打分**不能拿去回测**(会有前视偏差)。
- 成分股名单是手工维护的快照,可能和最新成分有出入。
- Yahoo 的数据可能延迟、缺失或限流;拉取失败过几分钟再试。

## License

[MIT](LICENSE)
