import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries, HistogramSeries, LineSeries, createChart,
  type IChartApi, type ISeriesApi, type Time,
} from "lightweight-charts";
import { getBars, type Bar } from "./api";

const MAS = [
  { n: 20, color: "#f5c542" },
  { n: 60, color: "#4f8cff" },
  { n: 120, color: "#c084fc" },
];

function sma(bars: Bar[], n: number) {
  const out: { time: Time; value: number }[] = [];
  let sum = 0;
  for (let i = 0; i < bars.length; i++) {
    sum += bars[i].close;
    if (i >= n) sum -= bars[i - n].close;
    if (i >= n - 1) out.push({ time: bars[i].time as Time, value: sum / n });
  }
  return out;
}

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export default function Chart({ ticker, name, onClose }: { ticker: string; name: string; onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const maSeries = useRef<Record<number, ISeriesApi<"Line">>>({});
  const [freq, setFreq] = useState<"daily" | "weekly">("daily");
  const [maOn, setMaOn] = useState<Record<number, boolean>>({ 20: true, 60: true, 120: false });
  const [bars, setBars] = useState<Bar[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    let live = true;
    setBars(null);
    setErr("");
    getBars(ticker, freq)
      .then((r) => { if (live) setBars(r.bars); })
      .catch((e: Error) => { if (live) setErr(e.message); });
    return () => { live = false; };
  }, [ticker, freq]);

  useEffect(() => {
    if (!box.current || !bars?.length) return;
    const up = css("--color-up"), down = css("--color-down");
    const c = createChart(box.current, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: css("--color-muted") },
      grid: { vertLines: { color: css("--color-surface-2") }, horzLines: { color: css("--color-surface-2") } },
      rightPriceScale: { borderColor: css("--color-border") },
      timeScale: { borderColor: css("--color-border") },
    });
    chart.current = c;
    const candles = c.addSeries(CandlestickSeries, {
      upColor: up, downColor: down, wickUpColor: up, wickDownColor: down, borderVisible: false,
    });
    candles.setData(bars.map((b) => ({ ...b, time: b.time as Time })));
    maSeries.current = {};
    for (const m of MAS) {
      const s = c.addSeries(LineSeries, {
        color: m.color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      s.setData(sma(bars, m.n));
      maSeries.current[m.n] = s;
    }
    const vol = c.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceLineVisible: false }, 1);
    vol.setData(bars.map((b) => ({
      time: b.time as Time, value: b.volume, color: (b.close >= b.open ? up : down) + "99",
    })));
    // With autoSize the pane ratio must be set via stretch factors, not pixel heights.
    const panes = c.panes();
    panes[0]?.setStretchFactor(4);
    panes[1]?.setStretchFactor(1);
    c.timeScale().setVisibleLogicalRange({ from: Math.max(0, bars.length - 160), to: bars.length + 4 });
    return () => { c.remove(); chart.current = null; };
  }, [bars]);

  useEffect(() => {
    for (const m of MAS) maSeries.current[m.n]?.applyOptions({ visible: !!maOn[m.n] });
  }, [maOn, bars]);

  const tab = (on: boolean) =>
    `px-2 py-0.5 rounded text-xs border ${on ? "border-primary text-fg" : "border-border text-muted hover:text-fg"}`;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-surface border border-border rounded-lg w-full max-w-5xl h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border">
          <span className="font-semibold">{ticker}</span>
          <span className="text-muted text-sm truncate">{name}</span>
          <span className="flex-1" />
          {MAS.map((m) => (
            <button
              key={m.n}
              className={tab(!!maOn[m.n])}
              style={maOn[m.n] ? { color: m.color, borderColor: m.color } : undefined}
              onClick={() => setMaOn((s) => ({ ...s, [m.n]: !s[m.n] }))}
            >
              MA{m.n}
            </button>
          ))}
          <span className="w-2" />
          <button className={tab(freq === "daily")} onClick={() => setFreq("daily")}>日线</button>
          <button className={tab(freq === "weekly")} onClick={() => setFreq("weekly")}>周线</button>
          <button className="ml-2 text-muted hover:text-fg text-lg leading-none" onClick={onClose} aria-label="关闭">×</button>
        </div>
        <div className="relative flex-1 min-h-0">
          <div ref={box} className="absolute inset-0" />
          {(!bars || !bars.length || err) && (
            <div className="absolute inset-0 flex items-center justify-center text-muted text-sm">
              {err ? `加载失败:${err}` : bars ? "没有数据" : "加载中…"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
