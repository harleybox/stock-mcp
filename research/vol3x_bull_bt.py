"""「三倍量阳线 + 基准线回踩」选股法回测 —— 验它到底有没有信息。

出处:一条流传很广的短视频三步法(原话是 A 股场景):
  ① 收盘后把「成交量 = 前一日 3 倍」且「收阳线」的股票加自选
  ② 在那根三倍量阳线的**收盘价**拉一条水平基准线
  ③ 等**缩量回调**后重新**站上**这条线时买入,之后顺势持有

**视频没讲、但完全决定盈亏的三件事**(所以一律做成可扫开关,不由我拍板):
  · 止损在哪 —— 这里取「回调段最低点」,最自然也最贴"基准线失守就是错了"
  · "顺势持有"到什么时候 —— 做成 exit 网格(跌破基准线/跌破MA20/固定N天/2R)
  · "缩量"是多少 —— shrink 参数扫,0 = 不要求缩量

**这次要回答的问题不是"能不能赚",是这三个**:
  ① 「三倍量」这三个字本身有没有信息 —— 所以扫量比梯度 1.0(只要阳线)→5.0。
     若 1.0 和 3.0 一样赚,赚的就是"回踩站回"这套机制,跟放量无关。
  ② 跟随机日比呢 —— 安慰剂:随便挑个日子当"信号根",后面回踩/站回/持有逻辑
     **一模一样**。这一条同时免疫幸存者偏差(真信号和安慰剂用同一批成分股)。
  ③ 加上真实成本还剩多少 —— A 股单边约 0.1%(佣金+过户+卖出印花),美股 0.02~0.05%。

**口径**:
  · 信号根 i 是**最外层循环变量**,入场只用 i 之后的数据
  · 入场 = 站回基准线那根的**次日开盘**,不是当天收盘
  · 跳空:开盘已越过止损就**按开盘价成交**,不假设止损价必成交
    (假设止损价必成交会系统性高估收益)
  · A 股一字涨停买不进 —— 入场日开盘较前收 ≥9.8% 视为**不可成交**,整笔作废
  · 同时报「每笔」和「累计/回撤/在场天数」(每笔变好不等于组合变好)

用法:
    .venv/bin/python research/vol3x_bull_bt.py --set etf
    .venv/bin/python research/vol3x_bull_bt.py --set cn --placebo 30
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

# 无幸存者偏差的对照组:行业 ETF,十年前就在,不存在"事后挑出来的赢家"
ETF = ["SPY", "QQQ", "IWM", "DIA", "XLE", "XLF", "XLV", "XLK", "XLI", "XLP", "XLU", "XLB", "XLY"]


def load_universe(name: str, limit: int) -> list[str]:
    from screener.universe import CSI_300, SP_500                      # noqa: PLC0415
    if name == "etf":
        return ETF
    if name == "cn":
        return list(CSI_300)[:limit]
    if name == "us":
        return list(SP_500)[:limit]
    raise SystemExit(f"unknown set {name}")


def load(syms: list[str], years: int) -> dict[str, pd.DataFrame]:
    """拉日线。yfinance 常给「当日一行但 OHLC 全 nan」的占位行(A 股尤其多),
    必须先扔掉 —— nan 参与比较全返回 False,会静默骗过所有判定。"""
    import yfinance as yf                                       # noqa: PLC0415
    out: dict[str, pd.DataFrame] = {}
    for k in range(0, len(syms), 60):                           # 分批,整批失败不至于全丢
        chunk = syms[k:k + 60]
        raw = yf.download(chunk, period=f"{years}y", auto_adjust=True,
                          progress=False, group_by="ticker", threads=True)
        for s in chunk:
            try:
                df = raw[s] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                continue
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            df = df[df["Volume"] > 0]                           # 停牌行会毒化量比
            if len(df) > 250:
                out[s] = df
    return out


def signal_roots(df: pd.DataFrame, vol_mult: float) -> list[int]:
    """三倍量阳线的下标。vol_mult=1.0 即「只要阳线、不要求放量」的降级对照。"""
    o, c = df["Open"].to_numpy(float), df["Close"].to_numpy(float)
    v = df["Volume"].to_numpy(float)
    out = []
    for i in range(1, len(df) - 2):                             # 留出等待+成交的余地
        if c[i] > o[i] and v[i] >= vol_mult * v[i - 1]:
            out.append(i)
    return out


def placebo_roots(df: pd.DataFrame, n: int, rng: np.random.Generator) -> list[int]:
    """安慰剂:**随便挑日子**当信号根,笔数和真信号一样,后面逻辑完全不变。

    为什么必须做:"回调后站回一条线"本身就是个突破策略,在长期上涨的池子里
    自带正期望 —— 不跟随机日对照,分不清赚的是「三倍量阳线」还是这套机制。
    (同样的坑:关键位 S1/R1 两次安慰剂证明线的位置根本没信息。)"""
    lo, hi = 1, len(df) - 3
    k = min(n, max(0, hi - lo))
    if k <= 0:
        return []
    idx = rng.choice(np.arange(lo, hi), size=k, replace=False)
    return sorted(int(i) for i in idx)


def wilder_atr(h, l, c, n=14):
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


def run(df: pd.DataFrame, roots: list[int], *, wait: int, shrink: float,
        exit_rule: str, cost_pct: float, max_hold: int, limit_guard: bool) -> list[dict]:
    """逐笔模拟第②③步:拉基准线 → 等缩量回调 → 站回买入 → 顺势持有。

    exit_rule:
      base  收盘跌回基准线下方就走(最贴"这条线是命根子"的读法)
      ma20  收盘跌破 20 日均线才走(最常见的"顺势持有"操作化)
      2r    先到 2R 止盈,否则止损
      holdN 固定持有 N 个交易日
    """
    o, h, l, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    v = df["Volume"].to_numpy(float)
    ma20 = pd.Series(c).rolling(20).mean().to_numpy()
    atr = wilder_atr(h, l, c)
    n = len(df)
    trades, busy_until = [], -1

    for i in roots:
        if i <= busy_until:
            continue
        base = c[i]                                             # ② 基准线 = 阳线收盘价
        # ③ 先回调(收盘跌破基准线),期间量能要缩,再站回
        pulled = False
        low_since = np.inf                                      # 回调段最低点 → 止损位
        entry_bar = None
        for j in range(i + 1, min(n - 1, i + 1 + wait)):
            if c[j] < base:
                if shrink > 0 and v[j] > shrink * v[i]:
                    continue                                    # 回调但没缩量 → 不算数
                pulled, low_since = True, min(low_since, l[j])
                continue
            if pulled and c[j] > base:                          # 站回基准线上方
                entry_bar = j + 1                               # → 次日开盘买
                break
        if entry_bar is None or entry_bar >= n:
            continue

        e = entry_bar
        entry = o[e]
        if limit_guard and c[e - 1] > 0 and o[e] / c[e - 1] - 1 >= 0.098:
            continue                                            # A 股一字涨停,买不进
        stop = min(low_since, l[e - 1])
        risk = entry - stop
        if not np.isfinite(risk) or risk < entry * 1e-3:
            continue

        target = entry + 2 * risk
        hold_n = int(exit_rule[4:]) if exit_rule.startswith("hold") else max_hold
        exit_px = exit_j = None
        why = ""
        for k2 in range(e, min(n, e + hold_n)):
            if o[k2] <= stop:                                   # 跳空穿止损 → 按开盘成交
                exit_px, exit_j, why = o[k2], k2, "gap_stop"
                break
            if l[k2] <= stop:
                exit_px, exit_j, why = stop, k2, "stop"
                break
            if exit_rule == "2r" and h[k2] >= target:
                exit_px, exit_j, why = target, k2, "2R"
                break
            if k2 > e and exit_rule == "base" and c[k2] < base:
                exit_px, exit_j, why = c[k2], k2, "lose_base"
                break
            if k2 > e and exit_rule == "ma20" and np.isfinite(ma20[k2]) and c[k2] < ma20[k2]:
                exit_px, exit_j, why = c[k2], k2, "lose_ma20"
                break
        if exit_px is None:
            exit_j = min(n, e + hold_n) - 1
            exit_px, why = c[exit_j], "timeout"

        gross = (exit_px - entry) / entry * 100.0
        net = gross - 2 * cost_pct
        trades.append({"ret": net, "R": (net / 100.0 * entry) / risk, "why": why,
                       "hold": exit_j - e + 1, "wait": e - i,
                       "risk%": risk / entry * 100.0})
        busy_until = exit_j
    return trades


def stat(tr: list[dict]) -> dict:
    if not tr:
        return {"n": 0}
    r = np.array([t["ret"] for t in tr])
    win = r > 0
    t = r.mean() / (r.std(ddof=1) / np.sqrt(len(r))) if len(r) > 1 and r.std() > 0 else 0.0
    eq = np.cumsum(r)                                           # 单利
    dd = float((np.maximum.accumulate(eq) - eq).max()) if len(eq) else 0.0
    return {"n": len(r), "win%": win.mean() * 100, "avg%": r.mean(),
            "avgR": np.mean([x["R"] for x in tr]), "t": t,
            "sum%": r.sum(), "maxDD%": dd, "hold": np.mean([x["hold"] for x in tr]),
            "wait": np.mean([x["wait"] for x in tr]),
            "risk%": np.mean([x["risk%"] for x in tr])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="etf", choices=["etf", "cn", "us"])
    ap.add_argument("--limit", type=int, default=120, help="成分股取前 N 只(先跑小市场)")
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--wait", type=int, default=20, help="拉线后等回踩的最长天数")
    ap.add_argument("--shrink", type=float, default=0.5, help="回调日量 ≤ 此倍数×信号根量;0=不要求")
    ap.add_argument("--max-hold", type=int, default=60)
    ap.add_argument("--placebo", type=int, default=0)
    ap.add_argument("--vol-mults", default="1.0,1.5,2.0,3.0,5.0")
    ap.add_argument("--exits", default="base,ma20,2r,hold20")
    ap.add_argument("--cost", type=float, default=-1, help="单边成本%;默认按市场取(A股0.1/美股0.03)")
    args = ap.parse_args()

    syms = load_universe(args.set, args.limit)
    cost = args.cost if args.cost >= 0 else (0.10 if args.set == "cn" else 0.03)
    guard = args.set == "cn"
    print(f"拉数据 {len(syms)} 个标的 / {args.years} 年 …")
    data = load(syms, args.years)
    print(f"到手 {len(data)} 个。单边成本 {cost}%,涨停闸 {'开' if guard else '关'},"
          f"等待窗口 {args.wait} 天,缩量阈值 {args.shrink or '关'}\n")

    mults = [float(x) for x in args.vol_mults.split(",")]
    exits = args.exits.split(",")

    if args.placebo:
        rng = np.random.default_rng(42)
        print(f"=== 安慰剂对照({args.placebo} 轮随机日,信号根数量与真信号一致)===\n")
        print("量比  出场    真信号n  真均收%   随机日均收%(±std)     差值    z      判定")
        print("-" * 88)
        for vm in mults:
            roots = {s: signal_roots(df, vm) for s, df in data.items()}
            for ex in exits:
                real = stat([t for s, df in data.items()
                             for t in run(df, roots[s], wait=args.wait, shrink=args.shrink,
                                          exit_rule=ex, cost_pct=cost,
                                          max_hold=args.max_hold, limit_guard=guard)])
                if not real["n"]:
                    continue
                pl = []
                for _ in range(args.placebo):
                    tr = []
                    for s, df in data.items():
                        tr += run(df, placebo_roots(df, len(roots[s]), rng),
                                  wait=args.wait, shrink=args.shrink, exit_rule=ex,
                                  cost_pct=cost, max_hold=args.max_hold, limit_guard=guard)
                    st = stat(tr)
                    if st["n"]:
                        pl.append(st["avg%"])
                if len(pl) < 2:
                    continue
                pm, ps = float(np.mean(pl)), float(np.std(pl, ddof=1))
                z = (real["avg%"] - pm) / ps if ps > 0 else 0.0
                verdict = "信号有效" if z >= 2 else ("和随机无区别" if z > -2 else "反而更差")
                print(f"{vm:4.1f}  {ex:6s} {real['n']:7d} {real['avg%']:9.3f} "
                      f"{pm:12.3f} ±{ps:.3f} {real['avg%'] - pm:9.3f} {z:6.2f}   {verdict}")
        print()
        return

    print("量比  出场    笔数   胜率%   均收%    均R      t    累计%   最大回撤%  持有  等待  止损宽%")
    print("-" * 100)
    for vm in mults:
        roots = {s: signal_roots(df, vm) for s, df in data.items()}
        nsig = sum(len(v) for v in roots.values())
        for ex in exits:
            tr = []
            for s, df in data.items():
                tr += run(df, roots[s], wait=args.wait, shrink=args.shrink, exit_rule=ex,
                          cost_pct=cost, max_hold=args.max_hold, limit_guard=guard)
            st = stat(tr)
            if not st["n"]:
                continue
            print(f"{vm:4.1f}  {ex:6s} {st['n']:6d} {st['win%']:7.2f} {st['avg%']:7.3f} "
                  f"{st['avgR']:7.3f} {st['t']:6.2f} {st['sum%']:8.1f} {st['maxDD%']:9.1f} "
                  f"{st['hold']:5.1f} {st['wait']:5.1f} {st['risk%']:7.2f}")
        print(f"      (量比 {vm} 的信号根共 {nsig} 个 → 成交率见上)\n")


if __name__ == "__main__":
    main()
