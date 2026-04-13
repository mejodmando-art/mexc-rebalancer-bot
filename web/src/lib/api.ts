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
export const getStatus    = ()       => req<any>('/api/status');
export const getHistory   = (n = 50) => req<any[]>(`/api/history?limit=${n}`);
export const getSnapshots = (n = 90) => req<any[]>(`/api/snapshots?limit=${n}`);
export const getConfig    = ()       => req<any>('/api/config');

// ── Config update ───────────────────────────────────────────────────────────
export const updateConfig = (body: Record<string, unknown>) =>
  req<{ ok: boolean }>('/api/config', { method: 'POST', body: JSON.stringify(body) });

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
