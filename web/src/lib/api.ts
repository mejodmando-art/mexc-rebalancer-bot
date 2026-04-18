// API base URL:
// - In dev: use NEXT_PUBLIC_API_URL env var (defaults to localhost:8000)
// - In production build (static export): use empty string = same-origin
export const API_BASE =
  process.env.NODE_ENV === 'production'
    ? (process.env.NEXT_PUBLIC_API_URL ?? '')
    : (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000');

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  return res.json();
}

// ── Status & portfolio ──────────────────────────────────────────────────────
export const getStatus       = ()       => req<any>('/api/status');
export const getHistory      = (n = 50) => req<any[]>(`/api/history?limit=${n}`);
export const getSnapshots    = (n = 90) => req<any[]>(`/api/snapshots?limit=${n}`);
export const getConfig       = ()       => req<any>('/api/config');
export const getAccountTotal = ()       => req<{ ok: boolean; total_usdt: number; free_usdt: number; locked_usdt: number; assets: any[] }>('/api/account/total');

// ── Config update ───────────────────────────────────────────────────────────
export const updateConfig = (body: Record<string, unknown>) =>
  req<{ ok: boolean }>('/api/config', { method: 'POST', body: JSON.stringify(body) });

export const resetInitialValue = () =>
  req<{ ok: boolean; initial_value_usdt: number }>('/api/config/reset-initial-value', { method: 'POST' });

// ── Rebalance ───────────────────────────────────────────────────────────────
export const triggerRebalance = () =>
  req<{ ok: boolean; job_id: string; cancel_window_seconds: number }>('/api/rebalance', { method: 'POST' });

export const cancelRebalance = (jobId: string) =>
  req<{ ok: boolean; message: string }>(`/api/rebalance/cancel?job_id=${jobId}`, { method: 'POST' });

export const getRebalanceJobStatus = (jobId: string) =>
  req<{ job_id: string; cancelled: boolean; done: boolean; result: any[] | null }>(
    `/api/rebalance/status/${jobId}`
  );

// ── Bot control ─────────────────────────────────────────────────────────────
export const getBotStatus = () => req<any>('/api/bot/status');
export const startBot     = () => req<any>('/api/bot/start', { method: 'POST' });
export const stopBot      = () => req<any>('/api/bot/stop',  { method: 'POST' });

// ── Notifications ───────────────────────────────────────────────────────────
export const getNotifConfig    = ()                              => req<any>('/api/notifications/config');
export const updateNotifConfig = (body: Record<string, unknown>) =>
  req<{ ok: boolean }>('/api/notifications/config', { method: 'POST', body: JSON.stringify(body) });
export const testDiscord = () =>
  req<{ ok: boolean }>('/api/notifications/test', { method: 'POST' });

// ── Export ──────────────────────────────────────────────────────────────────
export const exportCsvUrl   = () => `${API_BASE}/api/export/csv`;
export const exportExcelUrl = () => `${API_BASE}/api/export/excel`;

// ── Multi-portfolio ──────────────────────────────────────────────────────────
export const listPortfolios    = ()                              => req<any[]>('/api/portfolios');
export const savePortfolio     = (config: Record<string, unknown>) =>
  req<{ ok: boolean; id: number }>('/api/portfolios', { method: 'POST', body: JSON.stringify({ config }) });
export const getPortfolio      = (id: number)                   => req<any>(`/api/portfolios/${id}`);
export const activatePortfolio = (id: number)                   =>
  req<{ ok: boolean; message: string }>(`/api/portfolios/${id}/activate`, { method: 'POST' });
export const deletePortfolio   = (id: number)                   =>
  req<{ ok: boolean }>(`/api/portfolios/${id}`, { method: 'DELETE' });
export const updatePortfolio   = (id: number, config: Record<string, unknown>) =>
  req<{ ok: boolean }>(`/api/portfolios/${id}`, { method: 'PUT', body: JSON.stringify({ config }) });

export const rebalancePortfolio = (id: number, rebalance_type: 'market_value' | 'equal') =>
  req<{ ok: boolean; job_id: string; cancel_window_seconds: number }>(
    `/api/portfolios/${id}/rebalance`,
    { method: 'POST', body: JSON.stringify({ rebalance_type }) }
  );

export const stopAndSellPortfolio = (id: number) =>
  req<{ ok: boolean; results: { symbol: string; action: string; qty?: number; error?: string }[] }>(
    `/api/portfolios/${id}/stop-and-sell`,
    { method: 'POST' }
  );

export const startPortfolio      = (id: number) => req<{ ok: boolean; message: string }>(`/api/portfolios/${id}/start`, { method: 'POST' });
export const stopPortfolio       = (id: number) => req<{ ok: boolean; message: string }>(`/api/portfolios/${id}/stop`,  { method: 'POST' });
export const getPortfolioStatus  = (id: number) => req<{ portfolio_id: number; running: boolean; started_at: string | null; error: string | null }>(`/api/portfolios/${id}/status`);
// ── Grid Bot ─────────────────────────────────────────────────────────────────
export const listGridBots    = ()                    => req<any[]>('/api/grid-bots');
export const getGridBot      = (id: number)          => req<any>(`/api/grid-bots/${id}`);
export const getGridOrders   = (id: number)          => req<any[]>(`/api/grid-bots/${id}/orders`);
export const createGridBot   = (body: {
  symbol: string;
  investment: number;
  grid_count?: number;
  lower_pct?: number;
  upper_pct?: number;
  price_low?: number;
  price_high?: number;
  expand_direction?: 'both' | 'lower' | 'upper';
  mode?: 'normal' | 'infinity';
  use_base_balance?: boolean;
}) =>
  req<{ ok: boolean; id: number }>('/api/grid-bots', { method: 'POST', body: JSON.stringify(body) });
export const stopGridBot     = (id: number)          => req<{ ok: boolean }>(`/api/grid-bots/${id}/stop`,   { method: 'POST' });
export const resumeGridBot   = (id: number)          => req<{ ok: boolean }>(`/api/grid-bots/${id}/resume`, { method: 'POST' });
export const deleteGridBot   = (id: number)          => req<{ ok: boolean }>(`/api/grid-bots/${id}`,        { method: 'DELETE' });
export const previewGridBot  = (
  symbol: string,
  investment: number,
  gridCount?: number,
  lowerPct?: number,
  upperPct?: number,
) => {
  const params = new URLSearchParams({ symbol, investment: String(investment) });
  if (gridCount && gridCount >= 2) params.set('grid_count', String(gridCount));
  if (lowerPct !== undefined) params.set('lower_pct', String(lowerPct));
  if (upperPct !== undefined) params.set('upper_pct', String(upperPct));
  return req<{ symbol: string; current_price: number; price_low: number; price_high: number; grid_count: number; usdt_per_grid: number; step: number; profit_per_grid_pct: number; est_profit_per_grid: number; free_usdt: number | null }>(
    `/api/grid-bots/preview?${params}`
  );
};

export const getSymbols = () => req<string[]>('/api/symbols');

export const getPortfolioAssets  = (id: number) => req<{
  portfolio_id: number; portfolio_name: string; total_usdt: number;
  mode: string; running: boolean; assets: any[];
}>(`/api/portfolios/${id}/assets`);

// ── Supertrend Scanner ───────────────────────────────────────────────────────
export const listSupertrendScanners  = ()           => req<any[]>('/api/supertrend-scanners');
export const getSupertrendScanner    = (id: number) => req<any>(`/api/supertrend-scanners/${id}`);
export const createSupertrendScanner = (body: {
  entry_usdt?: number;
  tp1_pct?: number;
  tp2_pct?: number;
  tp3_pct?: number;
}) => req<{ ok: boolean; id: number }>('/api/supertrend-scanners', { method: 'POST', body: JSON.stringify(body) });
export const stopSupertrendScanner   = (id: number) => req<{ ok: boolean }>(`/api/supertrend-scanners/${id}/stop`,   { method: 'POST' });
export const resumeSupertrendScanner = (id: number) => req<{ ok: boolean }>(`/api/supertrend-scanners/${id}/resume`, { method: 'POST' });
export const deleteSupertrendScanner = (id: number) => req<{ ok: boolean }>(`/api/supertrend-scanners/${id}`,        { method: 'DELETE' });
