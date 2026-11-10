"""EMA 五线多头排列当择时信号 —— 跑不跑得赢买入持有。

常见说法:五条 EMA(20/30/40/50/60)全部多头排列、价格在最上面 = 强势,可以持有。
判据 stack5 = close > EMA20 > EMA30 > EMA40 > EMA50 > EMA60。

## 为什么主口径是「组合择时 vs 买持的配对检验」而不是「每笔」

去掉跳空这个前提后,每天有几百只票同时满足条件,而且**连续日子的持有期高度重叠** ——
按笔算 t 值会被重叠样本严重高估(几十万个"独立"观测其实只有几千个独立时段)。
所以改用组合口径:

  · 每天等权持有所有 stack5 成立的标的 → 一条组合日收益序列
  · 对照同一批标的的**全池等权买持** → 另一条日收益序列
  · 对**每日差值**做配对 t 检验 —— 这样市场共同因子(beta)被差掉,
    问的是"挑排列的票"比"全都持有"好在哪,而不是"这十年涨没涨"
  · 择时组和买持组用**同一批标的**,成分股回溯的幸存者偏差在差值里抵消

## 还必须报的两件事

  ① **在场日 vs 空仓日**:排列成立那些天,全池自己涨得好不好?
     若在场日的**买持**收益本来就高,那"排列"只是把好日子标了出来,不是选股能力。
  ② **在场比例 + 换手成本**:过滤器天然砍在场时间,组合年化会被腰斩。

## 口径

  · 无未来数据:第 i 日**收盘**确认排列 → 吃第 i+1 日的收益。信号根 i 是最外层变量。
  · EMA 热身 200 根(EMA 递推的头部会随窗口变,热身不够等于事后重画)。
  · 事件型(首次成立)单独报一份**非重叠**的每笔口径,那个才适合看每笔收益。
  · 降级对照:只要 c>EMA20(一条)、c>EMA20>EMA60(跳过中间三条)——
    若三者等价,"五条全排列"这个细节就是装饰。

用法:
    .venv/bin/python research/ema_stack_timing_bt.py --set stock
    .venv/bin/python research/ema_stack_timing_bt.py --set crypto
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

EMAS = [20, 30, 40, 50, 60]
WARM = 200
CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD", "LTC-USD"]


def ema_arr(v: np.ndarray, n: int) -> np.ndarray:
    k = 2.0 / (n + 1)
    out = np.empty_like(v)
    e = v[0]
    for i in range(len(v)):
        e = v[i] if i == 0 else v[i] * k + e * (1 - k)
        out[i] = e
    return out


def load(syms: list[str], years: int) -> dict[str, pd.DataFrame]:
    import yfinance as yf                                       # noqa: PLC0415
    out: dict[str, pd.DataFrame] = {}
    for k in range(0, len(syms), 80):
        raw = yf.download(syms[k:k + 80], period=f"{years}y", auto_adjust=True,
                          progress=False, group_by="ticker", threads=True)
        for s in syms[k:k + 80]:
            try:
                df = raw[s] if isinstance(raw.columns, pd.MultiIndex) else raw
            except KeyError:
                continue
            df = df[["Close"]].dropna()                          # 日线择时只要收盘
            if len(df) > WARM + 100:
                out[s] = df
    return out


def panels(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """摊成 日期×标的 的矩阵:次日收益 + 三种排列的布尔面板。"""
    ret, s5, s1, s2, s5n, d5, d5n = {}, {}, {}, {}, {}, {}, {}
    for s, df in data.items():
        c = df["Close"].to_numpy(float)
        idx = df.index
        e = {n: ema_arr(c, n) for n in EMAS}
        st5 = c > e[20]
        for a, b in zip(EMAS, EMAS[1:]):
            st5 = st5 & (e[a] > e[b])
        st1 = c > e[20]
        st2 = (c > e[20]) & (e[20] > e[60])
        # 空头排列 = 多头的镜像:价格在最下面,均线倒序排开
        dn5 = c < e[20]
        for a, b in zip(EMAS, EMAS[1:]):
            dn5 = dn5 & (e[a] < e[b])
        nw = np.zeros(len(c), bool)
        nw[1:] = st5[1:] & ~st5[:-1]                            # 事件型:首次成立
        dw = np.zeros(len(c), bool)
        dw[1:] = dn5[1:] & ~dn5[:-1]
        # 第 i 日信号 → 吃 i+1 日收益。末根没有次日,丢掉。
        nxt = np.full(len(c), np.nan)
        nxt[:-1] = c[1:] / c[:-1] - 1.0
        keep = slice(WARM, len(c) - 1)
        ret[s] = pd.Series(nxt[keep], index=idx[keep])
        s5[s] = pd.Series(st5[keep], index=idx[keep])
        s1[s] = pd.Series(st1[keep], index=idx[keep])
        s2[s] = pd.Series(st2[keep], index=idx[keep])
        s5n[s] = pd.Series(nw[keep], index=idx[keep])
        d5[s] = pd.Series(dn5[keep], index=idx[keep])
        d5n[s] = pd.Series(dw[keep], index=idx[keep])
    return {"ret": pd.DataFrame(ret), "s5": pd.DataFrame(s5).fillna(False),
            "s1": pd.DataFrame(s1).fillna(False), "s2": pd.DataFrame(s2).fillna(False),
            "s5n": pd.DataFrame(s5n).fillna(False),
            "d5": pd.DataFrame(d5).fillna(False),
            "d5n": pd.DataFrame(d5n).fillna(False)}


def ann(daily: np.ndarray, ppy: float) -> float:
    """年化(复利)。空仓日按 0 计入 —— 那是真实的资金曲线。"""
    if len(daily) == 0:
        return 0.0
    return float((np.prod(1 + daily) ** (ppy / len(daily)) - 1) * 100)


def mdd(daily: np.ndarray) -> float:
    eq = np.cumprod(1 + daily)
    return float((1 - eq / np.maximum.accumulate(eq)).max() * 100)


def timing(P: dict[str, pd.DataFrame], key: str, cost: float, ppy: float) -> dict:
    """每天等权持有 key 面板为 True 的标的;没有就空仓。对照全池等权买持。"""
    ret, sig = P["ret"], P[key]
    m = sig & ret.notna()
    n_on = m.sum(axis=1)
    # 择时组合日收益(空仓日 = 0)
    port = (ret.where(m).mean(axis=1)).fillna(0.0).to_numpy()
    # 买持:同一批标的全都持有
    bh = ret.mean(axis=1).fillna(0.0).to_numpy()
    # 换手成本:持仓集合变化的比例 × 单边成本 × 2(卖旧买新)
    prev = m.shift(1).fillna(False)
    both = (m & prev).sum(axis=1).to_numpy()
    now = n_on.to_numpy()
    turn = np.where(now > 0, 1 - both / np.maximum(now, 1), 0.0)
    port_net = port - turn * cost / 100.0 * 2
    d = port_net - bh                                           # 配对差值
    t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d))) if d.std() > 0 else 0.0
    on = now > 0
    # 在场日 vs 空仓日的**买持**收益 —— 排列成立的日子本来就是好日子吗
    bh_on = bh[on].mean() * 100 if on.any() else 0.0
    bh_off = bh[~on].mean() * 100 if (~on).any() else 0.0
    return {"ann": ann(port_net, ppy), "bh": ann(bh, ppy), "t": t,
            "mdd": mdd(port_net), "bh_mdd": mdd(bh),
            "on%": on.mean() * 100, "held": now[now > 0].mean() if on.any() else 0,
            "turn%": turn.mean() * 100, "bh_on": bh_on, "bh_off": bh_off,
            "days": len(d)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="stock", choices=["stock", "crypto"])
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--costs", default="0,0.02,0.05")
    args = ap.parse_args()

    if args.set == "crypto":
        syms, ppy = CRYPTO, 365.0
    else:
        from screener.universe import SP_500                          # noqa: PLC0415
        syms, ppy = list(SP_500)[:args.limit], 252.0
    print(f"拉数据 {len(syms)} 个 / {args.years} 年 …")
    data = load(syms, args.years)
    print(f"到手 {len(data)} 个\n")
    P = panels(data)

    print("=== 组合择时 vs 买入持有(配对 t 检验;同一批标的,幸存者偏差在差值里抵消)===")
    print(f"{'判据':24s} {'成本%':>6s} {'择时年化%':>10s} {'买持年化%':>10s} {'t':>7s} "
          f"{'择时回撤%':>10s} {'买持回撤%':>10s} {'在场日%':>8s} {'持仓数':>7s} {'换手%':>7s}")
    print("-" * 118)
    for key, label in [("s5", "五线排列 20/30/40/50/60"), ("s1", "降级:只要 c>EMA20"),
                       ("s2", "降级:c>EMA20>EMA60")]:
        for cost in [float(x) for x in args.costs.split(",")]:
            r = timing(P, key, cost, ppy)
            print(f"{label:24s} {cost:6.2f} {r['ann']:10.2f} {r['bh']:10.2f} {r['t']:7.2f} "
                  f"{r['mdd']:10.1f} {r['bh_mdd']:10.1f} {r['on%']:8.1f} {r['held']:7.1f} "
                  f"{r['turn%']:7.1f}")
        print()

    print("=== 在场日 vs 空仓日:排列成立那些天,**全池买持**自己涨得好不好 ===")
    print("(若在场日买持收益并不更高,说明「排列」没标出好日子;若更低 = 反向有本事)")
    print(f"{'判据':24s} {'在场日买持均收%':>16s} {'空仓日买持均收%':>16s} {'在场日%':>9s}")
    print("-" * 70)
    for key, label in [("s5", "五线排列"), ("s1", "只要 c>EMA20"), ("s2", "c>EMA20>EMA60")]:
        r = timing(P, key, 0.0, ppy)
        print(f"{label:24s} {r['bh_on']:16.4f} {r['bh_off']:16.4f} {r['on%']:9.1f}")
    print()

    # ── 事件型:首次成立那天买入,持有 N 日。非重叠(同一标的持有期内不重复进) ──
    print("=== 事件型:五线排列**首次成立**次日买入,持有 N 日(非重叠)===")
    print(f"{'持有N日':>8s} {'笔数':>8s} {'均收%':>9s} {'t':>7s} {'胜率%':>8s} "
          f"{'同期同票买持均收%':>18s} {'差值':>9s} {'配对t':>8s}")
    print("-" * 96)
    ret, s5n = P["ret"], P["s5n"]
    cl = {s: d["Close"] for s, d in data.items()}
    for hold in (1, 3, 5, 10, 20, 60):
        rs, bs = [], []
        for s in s5n.columns:
            c = cl[s].reindex(ret.index).to_numpy(float)
            ev = np.flatnonzero(s5n[s].to_numpy())
            busy = -1
            for i in ev:
                if i <= busy or i + hold >= len(c) or not np.isfinite(c[i]):
                    continue
                if not np.isfinite(c[i + hold]):
                    continue
                rs.append((c[i + hold] / c[i] - 1) * 100)
                busy = i + hold
        # 同期基准:同一批日子里,全池等权持有同样天数的收益
        idx_all = ret.index
        bh_d = ret.mean(axis=1).fillna(0.0).to_numpy()
        for s in s5n.columns:
            ev = np.flatnonzero(s5n[s].to_numpy())
            busy = -1
            for i in ev:
                if i <= busy or i + hold >= len(bh_d):
                    continue
                bs.append((np.prod(1 + bh_d[i:i + hold]) - 1) * 100)
                busy = i + hold
        if not rs:
            continue
        a, b = np.array(rs), np.array(bs[:len(rs)])
        t = a.mean() / (a.std(ddof=1) / np.sqrt(len(a))) if a.std() > 0 else 0.0
        d = a - b
        pt = d.mean() / (d.std(ddof=1) / np.sqrt(len(d))) if d.std() > 0 else 0.0
        print(f"{hold:8d} {len(a):8d} {a.mean():9.3f} {t:7.2f} {(a > 0).mean() * 100:8.2f} "
              f"{b.mean():18.3f} {d.mean():9.3f} {pt:8.2f}")
    print(f"\n(标的数 {len(data)},交易日 {len(ret)},年化按 {ppy:.0f} 期/年)")


if __name__ == "__main__":
    main()
