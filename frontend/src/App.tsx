import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Chart from "./Chart";
import { getScreen, getUniverses, refreshScreen, type Job, type Row } from "./api";
import { REPO_URL, X_HANDLE } from "./config";

type Fmt = "score" | "num" | "pct" | "pctRaw" | "price" | "cap";
type Col = { key: keyof Row; label: string; fmt: Fmt; tip: string; tone?: boolean };

const COLS: Col[] = [
  { key: "combined_score", label: "综合", fmt: "score", tip: "综合分 = 价值30% + 成长25% + 质量25% + PEG20%,池内百分位排名(0~100)" },
  { key: "value_score", label: "价值", fmt: "score", tip: "便宜程度:PE、预期PE、PB、EV/EBITDA 越低越高分" },
  { key: "growth_score", label: "成长", fmt: "score", tip: "营收增速 + 盈利增速" },
  { key: "quality_score", label: "质量", fmt: "score", tip: "ROE、净利率、毛利率" },
  { key: "peg_score", label: "PEG", fmt: "score", tip: "PE ÷ 盈利增速%,相对成长是否便宜" },
  { key: "currentPrice", label: "价格", fmt: "price", tip: "快照时的价格" },
  { key: "marketCap", label: "市值", fmt: "cap", tip: "总市值" },
  { key: "trailingPE", label: "PE", fmt: "num", tip: "滚动市盈率" },
  { key: "forwardPE", label: "预期PE", fmt: "num", tip: "按未来12个月预期盈利算的市盈率" },
  { key: "returnOnEquity", label: "ROE", fmt: "pct", tip: "净资产收益率" },
  { key: "revenueGrowth", label: "营收增速", fmt: "pct", tip: "营收同比", tone: true },
  { key: "earningsGrowth", label: "盈利增速", fmt: "pct", tip: "盈利同比(GAAP 口径,噪音大)", tone: true },
  { key: "rsi14", label: "RSI", fmt: "num", tip: "14日 RSI" },
  { key: "ma50_pct", label: "距50日线", fmt: "pctRaw", tip: "现价高于(+)/低于(-) 50日均线的幅度", tone: true },
  { key: "hi52_pct", label: "距52周高", fmt: "pctRaw", tip: "距52周最高价的幅度,0 = 就在高点", tone: true },
  { key: "volume_ratio", label: "量比", fmt: "num", tip: "当日成交量 ÷ 20日均量" },
  { key: "upside", label: "目标空间", fmt: "pct", tip: "分析师平均目标价相对现价的空间", tone: true },
];

function fmt(v: number | null | undefined, f: Fmt): string {
  // `== null` on purpose: a missing JSON key is undefined, not null.
  if (v == null || !Number.isFinite(v)) return "—";
  switch (f) {
    case "score": return v.toFixed(0);
    case "num": return v.toFixed(1);
    case "pct": return `${(v * 100).toFixed(1)}%`;
    case "pctRaw": return `${v.toFixed(1)}%`;
    case "price": return v.toFixed(2);
    case "cap":
      return v >= 1e12 ? `${(v / 1e12).toFixed(2)}万亿` : v >= 1e8 ? `${(v / 1e8).toFixed(0)}亿` : `${(v / 1e4).toFixed(0)}万`;
  }
}

const tone = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) || v === 0 ? "" : v > 0 ? "text-up" : "text-down";

function ago(ts: number | null): string {
  if (!ts) return "";
  const m = Math.floor((Date.now() / 1000 - ts) / 60);
  if (m < 1) return "刚刚更新";
  if (m < 60) return `${m} 分钟前更新`;
  if (m < 1440) return `${Math.floor(m / 60)} 小时前更新`;
  return `${Math.floor(m / 1440)} 天前更新`;
}

export default function App() {
  const [universes, setUniverses] = useState<{ id: string; label: string }[]>([]);
  const [universe, setUniverse] = useState(() => localStorage.getItem("universe") || "nasdaq100");
  const [rows, setRows] = useState<Row[]>([]);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [sort, setSort] = useState<{ key: keyof Row; desc: boolean }>({ key: "combined_score", desc: true });
  const [q, setQ] = useState("");
  const [sector, setSector] = useState("");
  const [inflowOnly, setInflowOnly] = useState(false);
  const [hideTraps, setHideTraps] = useState(false);
  const [open, setOpen] = useState<Row | null>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => { getUniverses().then(setUniverses).catch(() => {}); }, []);

  const load = useCallback(async (u: string) => {
    window.clearTimeout(timer.current);
    try {
      const r = await getScreen(u);
      setRows(r.rows);
      setSavedAt(r.saved_at);
      setJob(r.job);
      setErr("");
      // Poll while a fetch is running; stop on success or on a job error.
      if (r.job && !r.job.error) timer.current = window.setTimeout(() => load(u), 2000);
    } catch (e) {
      setErr("连不上后端 —— 确认 ./run.sh 还在跑");
      timer.current = window.setTimeout(() => load(u), 4000);
      void e;
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("universe", universe);
    setRows([]);
    setSavedAt(null);
    setJob(null);
    setLoaded(false);
    setSector("");
    load(universe);
    return () => window.clearTimeout(timer.current);
  }, [universe, load]);

  // Deep link: /?chart=NVDA opens that ticker's chart once the table has loaded.
  const deepLink = useRef(new URLSearchParams(location.search).get("chart")?.toUpperCase());
  useEffect(() => {
    if (!deepLink.current || !rows.length) return;
    const hit = rows.find((r) => r.ticker.toUpperCase() === deepLink.current);
    deepLink.current = undefined;
    if (hit) setOpen(hit);
  }, [rows]);

  const refresh = async () => {
    try {
      const r = await refreshScreen(universe);
      setJob(r.job);
      load(universe);
    } catch {
      setErr("连不上后端 —— 确认 ./run.sh 还在跑");
    }
  };

  const sectors = useMemo(
    () => [...new Set(rows.map((r) => r.sector).filter((s): s is string => !!s))].sort(),
    [rows],
  );

  const view = useMemo(() => {
    const k = q.trim().toLowerCase();
    const out = rows.filter((r) =>
      (!k || r.ticker.toLowerCase().includes(k) || (r.longName ?? r.shortName ?? "").toLowerCase().includes(k)) &&
      (!sector || r.sector === sector) &&
      (!inflowOnly || r.inflow === true) &&
      (!hideTraps || r.value_trap_flag !== true));
    const { key, desc } = sort;
    return out.sort((a, b) => {
      const x = a[key], y = b[key];
      // Missing values always sink to the bottom, whichever way we sort.
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      const d = typeof x === "string" ? x.localeCompare(y as string) : (x as number) - (y as number);
      return desc ? -d : d;
    });
  }, [rows, q, sector, inflowOnly, hideTraps, sort]);

  const running = !!job && !job.error;
  const pct = job && job.total ? Math.round((job.done / job.total) * 100) : 0;
  const chip = (on: boolean) =>
    `px-2 py-1 rounded text-xs border ${on ? "border-primary text-fg bg-surface-2" : "border-border text-muted hover:text-fg"}`;
  const th = "px-2 py-2 font-normal text-muted whitespace-nowrap cursor-pointer select-none hover:text-fg";

  return (
    <div className="h-full flex flex-col">
      <header className="flex flex-wrap items-center gap-2 px-4 py-2 border-b border-border bg-surface">
        <span className="font-semibold mr-2">选股筛选器</span>
        <select
          className="bg-surface-2 border border-border rounded px-2 py-1 text-sm"
          value={universe}
          onChange={(e) => setUniverse(e.target.value)}
        >
          {(universes.length ? universes : [{ id: universe, label: universe }]).map((u) => (
            <option key={u.id} value={u.id}>{u.label}</option>
          ))}
        </select>
        <input
          className="bg-surface-2 border border-border rounded px-2 py-1 text-sm w-36"
          placeholder="代码 / 公司名"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          className="bg-surface-2 border border-border rounded px-2 py-1 text-sm max-w-40"
          value={sector}
          onChange={(e) => setSector(e.target.value)}
        >
          <option value="">全部行业</option>
          {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button
          className={chip(inflowOnly)}
          title="MFI > 50 且 OBV 20日斜率向上"
          onClick={() => setInflowOnly((v) => !v)}
        >
          资金流入
        </button>
        <button
          className={chip(hideTraps)}
          title="隐藏「便宜但可能是价值陷阱」:负债率 > 200%,或盈利下滑且营收不增长"
          onClick={() => setHideTraps((v) => !v)}
        >
          排除价值陷阱
        </button>
        <span className="flex-1" />
        <span className="text-xs text-muted">
          {running ? `正在拉取 ${job.done}/${job.total || "…"}` : `${view.length} 只 · ${ago(savedAt)}`}
        </span>
        <button
          className="px-2 py-1 rounded text-xs border border-border text-muted hover:text-fg disabled:opacity-40"
          disabled={running}
          onClick={refresh}
        >
          刷新数据
        </button>
        {X_HANDLE && (
          <a className="text-xs text-primary hover:underline" href={`https://x.com/${X_HANDLE}`} target="_blank" rel="noreferrer">
            𝕏 @{X_HANDLE}
          </a>
        )}
        {REPO_URL && (
          <a className="text-xs text-muted hover:text-fg" href={REPO_URL} target="_blank" rel="noreferrer">GitHub</a>
        )}
      </header>

      {running && (
        <div className="h-0.5 bg-surface-2">
          <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}
      {(err || job?.error) && (
        <div className="px-4 py-2 text-sm text-down border-b border-border">
          {err || `拉取失败:${job?.error}(多半是 Yahoo 限流,过几分钟点「刷新数据」再试)`}
        </div>
      )}

      <main className="flex-1 min-h-0 overflow-auto">
        {!rows.length ? (
          <div className="h-full flex items-center justify-center text-muted text-sm">
            {!loaded ? "加载中…" : running
              ? `首次拉取基本面并打分中(${job.done}/${job.total || "…"}),整个指数约需 1~5 分钟,之后走本地缓存`
              : "暂无数据"}
          </div>
        ) : (
          <table className="w-full text-sm tabular-nums border-collapse">
            <thead className="sticky top-0 bg-surface z-10">
              <tr className="border-b border-border">
                <th className={`${th} text-left pl-4`} onClick={() => setSort((s) => ({ key: "ticker", desc: s.key === "ticker" ? !s.desc : false }))}>
                  代码{sort.key === "ticker" ? (sort.desc ? " ↓" : " ↑") : ""}
                </th>
                <th className={`${th} text-left`} onClick={() => setSort((s) => ({ key: "sector", desc: s.key === "sector" ? !s.desc : false }))}>
                  行业{sort.key === "sector" ? (sort.desc ? " ↓" : " ↑") : ""}
                </th>
                {COLS.map((c) => (
                  <th
                    key={c.key}
                    className={`${th} text-right`}
                    title={c.tip}
                    onClick={() => setSort((s) => ({ key: c.key, desc: s.key === c.key ? !s.desc : true }))}
                  >
                    {c.label}{sort.key === c.key ? (sort.desc ? " ↓" : " ↑") : ""}
                  </th>
                ))}
                <th className="px-2 py-2 pr-4 font-normal text-muted text-left whitespace-nowrap">标记</th>
              </tr>
            </thead>
            <tbody>
              {view.map((r) => (
                <tr
                  key={r.ticker}
                  className="border-b border-border/50 hover:bg-surface-2 cursor-pointer"
                  onClick={() => setOpen(r)}
                >
                  <td className="px-2 py-1.5 pl-4 whitespace-nowrap">
                    <span className="font-medium">{r.ticker}</span>
                    <span className="text-muted text-xs ml-2 inline-block max-w-44 truncate align-bottom">
                      {r.shortName ?? r.longName ?? ""}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-muted text-xs whitespace-nowrap">{r.sector ?? "—"}</td>
                  {COLS.map((c) => {
                    const v = r[c.key] as number | null;
                    return (
                      <td
                        key={c.key}
                        className={`px-2 py-1.5 text-right whitespace-nowrap ${c.tone ? tone(v) : ""} ${c.key === "combined_score" ? "font-semibold" : ""}`}
                        // Scores: low = dim, high = bright.
                        style={c.fmt === "score" && v != null ? { opacity: 0.45 + (Math.min(100, Math.max(0, v)) / 100) * 0.55 } : undefined}
                      >
                        {fmt(v, c.fmt)}
                      </td>
                    );
                  })}
                  <td className="px-2 py-1.5 pr-4 whitespace-nowrap text-xs">
                    {r.inflow && <span className="text-up mr-2" title="MFI > 50 且 OBV 向上">流入</span>}
                    {r.value_trap_flag && <span className="text-down" title="便宜但可能是价值陷阱">陷阱?</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>

      <footer className="px-4 py-1.5 text-xs text-muted border-t border-border">
        选股辅助,不构成投资建议。基本面是当前快照、排名是池内相对排名;数据来自 Yahoo Finance,可能延迟或缺失。
      </footer>

      {open && (
        <Chart ticker={open.ticker} name={open.longName ?? open.shortName ?? ""} onClose={() => setOpen(null)} />
      )}
    </div>
  );
}
