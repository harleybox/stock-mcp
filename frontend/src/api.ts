export type Row = {
  ticker: string;
  longName: string | null;
  shortName: string | null;
  sector: string | null;
  combined_score: number | null;
  value_score: number | null;
  growth_score: number | null;
  quality_score: number | null;
  peg_score: number | null;
  trailingPE: number | null;
  forwardPE: number | null;
  returnOnEquity: number | null;
  revenueGrowth: number | null;
  earningsGrowth: number | null;
  currentPrice: number | null;
  marketCap: number | null;
  rsi14: number | null;
  ma50_pct: number | null;
  hi52_pct: number | null;
  mfi: number | null;
  volume_ratio: number | null;
  inflow: boolean | null;
  value_trap_flag: boolean | null;
  recommendationKey: string | null;
  upside: number | null;
};

export type Job = { done: number; total: number; error: string | null };

export type ScreenResponse = {
  universe: string;
  rows: Row[];
  saved_at: number | null;
  job: Job | null;
};

export type Bar = { time: string; open: number; high: number; low: number; close: number; volume: number };

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

export const getUniverses = () => json<{ id: string; label: string }[]>("/api/universes");
export const getScreen = (universe: string) =>
  json<ScreenResponse>(`/api/screen?universe=${encodeURIComponent(universe)}`);
export const refreshScreen = (universe: string) =>
  json<{ job: Job | null }>(`/api/screen/refresh?universe=${encodeURIComponent(universe)}`, { method: "POST" });
export const getBars = (ticker: string, freq: "daily" | "weekly") =>
  json<{ ticker: string; bars: Bar[] }>(
    `/api/bars?ticker=${encodeURIComponent(ticker)}&freq=${freq}&days=${freq === "weekly" ? 1825 : 730}`,
  );
