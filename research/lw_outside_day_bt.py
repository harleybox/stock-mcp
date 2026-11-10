"""Larry Williams 外包线(Outside Day)策略回测 —— 验它到底可不可靠。

出处:一段短视频 + TradingView「LW Outside Day Strategy [SpeculationLab]」
的参数截图。视频宣称 BTC 过去一年胜率 94.12%、
近 100 笔 81%,且"在表现最好的五个标的里只排第三"。

**规则**(视频口述 + 截图,两者不一致的地方以截图为准,因为那是真正跑出 94% 的配置):
  · 外包线:当根 high > 前根 high 且 当根 low < 前根 low
  · 实体过滤:|close−open| ≥ 实体最小倍数 × |前根 close−open|
    ⚠️ **视频里没提这条**,是截图里的「实体最小倍速 2」。它会大幅削减交易数,
       也是胜率的一部分来源 —— 只按口述实现测的就是另一个策略,所以做成开关。
  · 做多:外包线**收盘跌破**前根 low(散户眼里的看跌信号)→ 次日开盘买入
  · 做空:外包线**收盘升破**前根 high → 次日开盘卖空
  · 止损:多单 = 前根 low − 缓冲;空单 = 前根 high + 缓冲(截图:止损模式 Prev Low)
  · 止盈:**FPO**(first profitable open)—— 每天开盘看,一有浮盈就按开盘价平;
    没盈利也没触止损就继续持有

**这次要回答的问题不是"胜率多少",是这三个**:
  ① 加上真实成本还剩多少。截图里手续费和滑点**都是 0**,而 FPO 天然是
     "一有浮盈就跑",平均盈利极小 —— 成本很可能直接吃掉全部边际。
  ② 换个缓冲还成不成立。单一参数格的漂亮数字没有意义,所以缓冲扫网格,每格报 t 值。
  ③ 换个标的还成不成立。"五个标的里排第三"是**从一堆里挑出来的**,
     本身就是多重比较。所以跑全样本、不挑品种。

**口径**:
  · 入场价 = 次日**开盘价**,不是信号日收盘 —— 信号根是最外层循环变量,
    不存在未来数据
  · 跳空:开盘已经越过止损就**按开盘价成交**,不假设止损价必成交
    (假设止损价必成交会系统性高估收益,而且偏袒窄止损)
  · 成本按**往返**折进收益,单边可调
  · 同时报「每笔 R」和「按笔平均收益%」—— FPO 的 R 会非常小,只看 R 会误判

用法:
    .venv/bin/python research/lw_outside_day_bt.py                 # 币,默认网格
    .venv/bin/python research/lw_outside_day_bt.py --set stock     # 换股票池
    .venv/bin/python research/lw_outside_day_bt.py --no-body       # 关掉实体过滤
"""
from __future__ import annotations

import argparse
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# 视频说"表现最好的五个标的",没说是哪五个 —— 这里取主流币,不挑。
CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD", "LTC-USD"]
# 股票端刻意混宽基和个股,避免只测幸存的大牛股
STOCK = ["SPY", "QQQ", "IWM", "DIA", "XLE", "XLF", "XLV", "XLK",
         "AAPL", "MSFT", "NVDA", "JPM", "XOM", "KO", "PFE", "INTC"]
# ⚠️ 上面那个池混了 AAPL/MSFT/NVDA 这些**事后才知道**的十年大牛股 —— 幸存者偏差。
#    所以结论必须以 ETF 组为准。
ETF = ["SPY", "QQQ", "IWM", "DIA", "XLE", "XLF", "XLV", "XLK", "XLI", "XLP", "XLU", "XLB"]


def placebo_signals(df: pd.DataFrame, n_long: int, n_short: int,
                    rng: np.random.Generator) -> list[tuple[int, int]]:
    """安慰剂:**随机挑日子**,笔数和多空比例和真信号一样,其余逻辑完全不变。

    为什么必须做:FPO 是"一有浮盈就跑",而隔夜收益本身有正漂移 —— 光这一条在
    上涨市场里就能造出正期望,跟"外包线"这个形态一点关系都没有。不跟随机日对照,
    就分不清赚的是**信号**还是**出场方式 + 做多偏置**。
    (同样的坑踩过:关键位 S1/R1 那次,两次安慰剂证明线的位置根本没信息。)"""
    lo, hi = 1, len(df) - 2
    k = min(n_long + n_short, hi - lo)
    if k <= 0:
        return []
    idx = rng.choice(np.arange(lo, hi), size=k, replace=False)
    idx.sort()
    return [(int(i), (+1 if n < n_long else -1)) for n, i in enumerate(idx)]


def load(syms: list[str], years: int) -> dict[str, pd.DataFrame]:
    """拉日线。yfinance 常给「当日一行但 OHLC 全 nan」的占位行,必须先扔掉 ——
    nan 参与比较全返回 False,会**静默**骗过所有形态判定。"""
    import yfinance as yf
    raw = yf.download(syms, period=f"{years}y", auto_adjust=True,
                      progress=False, group_by="ticker", threads=True)
    out = {}
    for s in syms:
        # ⚠️ 新版 yfinance 即使只要一个标的、即使 group_by="ticker",列也可能是
        #    MultiIndex。按 len(syms)>1 判断会在**单标的**上直接 KeyError。
        try:
            df = raw[s] if isinstance(raw.columns, pd.MultiIndex) else raw
        except KeyError:
            continue
        df = df[["Open", "High", "Low", "Close"]].dropna()
        if len(df) > 100:                      # 太短的不要,统计没意义
            out[s] = df
    return out


def wilder_atr(h, l, c, n=14):
    """Wilder 平滑的 ATR —— Pine 的 ta.atr(len) 用的是 RMA,不是简单均值。
    换成 SMA 会让缓冲整体偏小,止损更紧,胜率被低估。"""
    tr = np.full(len(h), np.nan)
    tr[1:] = np.maximum(h[1:] - l[1:],
                        np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    atr = np.full(len(h), np.nan)
    if len(h) <= n:
        return atr
    atr[n] = np.nanmean(tr[1:n + 1])
    for i in range(n + 1, len(h)):
        atr[i] = (atr[i - 1] * (n - 1) + tr[i]) / n
    return atr


def signals(df: pd.DataFrame, body_mult: float) -> list[tuple[int, int]]:
    """返回 [(信号根下标, 方向)],方向 +1 做多 / −1 做空。

    ⚠️ 信号根 i 是**最外层循环变量**,用到的全是 i 和 i−1 的收盘价 —— i+1 只在
       成交时用开盘价,没有任何未来信息漏进判定。"""
    o, h, l, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    body = np.abs(c - o)
    out = []
    for i in range(1, len(df) - 1):            # 最后一根没有次日开盘,不能成交
        if not (h[i] > h[i - 1] and l[i] < l[i - 1]):
            continue                           # 不是外包线
        if body_mult > 0 and body[i] < body_mult * body[i - 1]:
            continue                           # 实体不够大(截图里那条隐藏条件)
        if c[i] < l[i - 1]:
            out.append((i, +1))                # 收盘跌破前低 → 做多
        elif c[i] > h[i - 1]:
            out.append((i, -1))                # 收盘升破前高 → 做空
    return out


def run(df: pd.DataFrame, sig: list[tuple[int, int]], buf_mult: float,
        cost_pct: float, max_hold: int, atr_len: int = 14) -> list[dict]:
    """逐笔模拟,**照 Pine 源码**,不照字幕。三处按源码纠正过:

      ① 缓冲 = `atr_value * buffer_multi`,是 **ATR(14) 的倍数**,不是价格百分比
      ② 止损基准是 `low` —— **当根外包线自己的低点**,不是字幕说的"前一根最低价"。
         外包线的 low 按定义就低于前根 low,所以源码的止损比字幕版**更宽**。
      ③ FPO 是 `close > entry_price` **收盘判定**,再由 strategy.close 在
         **次日开盘**成交 —— 不是"开盘看一眼有浮盈就按开盘价平"。中间隔了一夜,
         这一夜的跳空是白拿的风险,回测必须照实模拟。

    cost_pct = **单边**成本(%)。源码里是 0.01% + 1 tick 滑点,这里做成可扫的。"""
    o, h, l, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    atr = wilder_atr(h, l, c, atr_len)
    n = len(df)
    trades = []
    busy_until = -1                            # 源码 pyramiding=0 且 position_size==0 才进
    for i, d in sig:
        e = i + 1                              # strategy.entry 市价单 → 次日开盘成交
        if e <= busy_until or e >= n or not np.isfinite(atr[i]):
            continue
        entry = o[e]
        buf = atr[i] * buf_mult                # ← ATR 倍数,不是百分比
        stop = (l[i] - buf) if d > 0 else (h[i] + buf)   # ← 当根 low/high
        risk = abs(entry - stop)
        if not np.isfinite(risk) or risk < entry * 1e-4:
            continue

        exit_px, exit_j, why = None, None, ""
        pending = False                        # 上一根收盘触发了 FPO,今天开盘平
        for j in range(e, min(n, e + max_hold)):
            # ① 昨天收盘判定要平 → 今天开盘市价成交(源码 strategy.close 的行为)
            if pending:
                exit_px, exit_j, why = o[j], j, "fpo"
                break
            # ② 止损是**挂单**,全天有效。开盘就跳空越过 → 按开盘价成交,
            #    不假设止损价必成交
            if (d > 0 and o[j] <= stop) or (d < 0 and o[j] >= stop):
                exit_px, exit_j, why = o[j], j, "gap_stop"
                break
            if (d > 0 and l[j] <= stop) or (d < 0 and h[j] >= stop):
                exit_px, exit_j, why = stop, j, "stop"
                break
            # ③ 收盘判 FPO:有浮盈就挂单,**明天开盘**才走
            if (d > 0 and c[j] > entry) or (d < 0 and c[j] < entry):
                pending = True
        if exit_px is None:
            exit_j = min(n, e + max_hold) - 1
            exit_px, why = c[exit_j], "timeout"

        gross = (exit_px - entry) / entry * d * 100.0
        net = gross - 2 * cost_pct
        trades.append({"ret": net, "gross": gross, "R": (net / 100.0 * entry) / risk,
                       "why": why, "hold": exit_j - e, "dir": d})
        busy_until = exit_j
    return trades


def stat(tr: list[dict]) -> dict:
    if not tr:
        return {"n": 0}
    r = np.array([t["ret"] for t in tr])
    R = np.array([t["R"] for t in tr])
    win = r > 0
    # t 值:期望是不是显著不为零。|t|<2 一律当"和零等价"
    t = r.mean() / (r.std(ddof=1) / np.sqrt(len(r))) if len(r) > 1 and r.std() > 0 else 0.0
    eq = np.cumsum(r)                          # 单利、固定风险额
    dd = float((np.maximum.accumulate(eq) - eq).max()) if len(eq) else 0.0
    return {"n": len(r), "win%": win.mean() * 100, "avg%": r.mean(), "avgR": R.mean(),
            "t": t, "win_avg%": r[win].mean() if win.any() else 0.0,
            "loss_avg%": r[~win].mean() if (~win).any() else 0.0,
            "sum%": r.sum(), "maxDD%": dd, "hold": np.mean([x["hold"] for x in tr])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="crypto",
                    choices=["crypto", "stock", "etf", "both"])
    ap.add_argument("--placebo", type=int, default=0,
                    help="跑 N 轮随机日安慰剂,和真信号对照")
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--body", type=float, default=2.0, help="实体最小倍数(截图是 2)")
    ap.add_argument("--no-body", action="store_true", help="关掉实体过滤(纯口述版)")
    ap.add_argument("--max-hold", type=int, default=60)
    ap.add_argument("--syms", default="", help="指定标的(逗号分隔),用来复现视频那个单标的数字")
    ap.add_argument("--bufs", default="", help="自定义缓冲网格(逗号分隔的%)")
    args = ap.parse_args()

    syms = (args.syms.split(",") if args.syms
            else {"crypto": CRYPTO, "stock": STOCK, "etf": ETF,
                  "both": CRYPTO + STOCK}[args.set])
    body = 0.0 if args.no_body else args.body
    print(f"拉数据 {len(syms)} 个标的 / {args.years} 年 …")
    data = load(syms, args.years)
    print(f"到手 {len(data)} 个:{', '.join(data)}\n")

    sigs = {s: signals(df, body) for s, df in data.items()}
    print(f"实体过滤 = {body or '关'}   信号总数 = {sum(len(v) for v in sigs.values())}")
    print(f"其中做多 {sum(1 for v in sigs.values() for _, d in v if d > 0)} / "
          f"做空 {sum(1 for v in sigs.values() for _, d in v if d < 0)}\n")

    # ── 安慰剂对照:随机日 vs 真信号 ──
    if args.placebo:
        rng = np.random.default_rng(42)
        print(f"=== 安慰剂对照({args.placebo} 轮随机日,笔数/多空比与真信号一致)===\n")
        print("ATR倍 成本%   真信号均收%   随机日均收%(均±标准差)   差值    差值/随机std   判定")
        print("-" * 96)
        for bp, cp in [(1.0, 0.01), (1.0, 0.05), (2.0, 0.01), (2.0, 0.05), (0.5, 0.01)]:
            real = stat([t for sy, df in data.items()
                         for t in run(df, sigs[sy], bp, cp, args.max_hold)])
            pl = []
            for _ in range(args.placebo):
                tr = []
                for sy, df in data.items():
                    nl = sum(1 for _, d in sigs[sy] if d > 0)
                    ns = len(sigs[sy]) - nl
                    tr += run(df, placebo_signals(df, nl, ns, rng), bp, cp, args.max_hold)
                st = stat(tr)
                if st["n"]:
                    pl.append(st["avg%"])
            if not pl:
                continue
            pm, ps = float(np.mean(pl)), float(np.std(pl, ddof=1))
            z = (real["avg%"] - pm) / ps if ps > 0 else 0.0
            # |z|<2 = 真信号和随便挑个日子没区别 → 这个形态本身没有信息
            verdict = "信号有效" if z >= 2 else ("和随机无区别" if abs(z) < 2 else "反而更差")
            print(f"{bp:5.2f} {cp:6.2f} {real['avg%']:12.4f} {pm:12.4f} ±{ps:.4f} "
                  f"{real['avg%'] - pm:10.4f} {z:12.2f}   {verdict}")
        print()
        return

    # ── 缓冲 × 成本 网格。单看一格没有意义,要看整片稳不稳 ──
    # 缓冲现在是 **ATR 倍数**(源码 buffer_multi,默认 2,截图是 1)
    BUFS = ([float(x) for x in args.bufs.split(",")] if args.bufs
            else [0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0])
    COSTS = [0.0, 0.05, 0.10, 0.20]
    print("ATR倍 成本%  笔数   胜率%   均收%   均R     t     赢均%   亏均%   累计%   最大回撤%  持有")
    print("-" * 104)
    for bp in BUFS:
        for cp in COSTS:
            tr = []
            for s, df in data.items():
                tr += run(df, sigs[s], bp, cp, args.max_hold)
            st = stat(tr)
            if not st["n"]:
                continue
            print(f"{bp:5.2f} {cp:6.2f} {st['n']:6d} {st['win%']:7.2f} {st['avg%']:7.3f} "
                  f"{st['avgR']:7.3f} {st['t']:6.2f} {st['win_avg%']:7.3f} "
                  f"{st['loss_avg%']:8.3f} {st['sum%']:8.1f} {st['maxDD%']:9.1f} {st['hold']:6.1f}")
        print()


if __name__ == "__main__":
    main()
