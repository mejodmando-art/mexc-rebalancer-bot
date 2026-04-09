import axios from "axios";

const BASE = import.meta.env.VITE_API_URL || "";
const SECRET = import.meta.env.VITE_WEB_SECRET || "mexc-dashboard-secret";

const client = axios.create({
  baseURL: BASE,
  headers: { Authorization: `Bearer ${SECRET}` },
});

// ── Types ──────────────────────────────────────────────────────────────────────

export interface Asset {
  symbol: string;
  amount: number;
  value_usdt: number;
  price: number;
  current_pct: number;
  target_pct: number | null;
  drift_pct: number | null;
  needs_action: boolean;
}

export interface PortfolioData {
  total_usdt: number;
  capital_usdt: number;
  effective_total: number;
  portfolio_name: string;
  threshold: number;
  assets: Asset[];
}

export interface DriftItem {
  symbol: string;
  current_pct: number;
  target_pct: number;
  drift_pct: number;
  drift_abs: number;
  needs_action: boolean;
}

export interface TradeItem {
  symbol: string;
  action: "buy" | "sell";
  usdt_amount: number;
  drift_pct: number;
}

export interface AnalysisData {
  portfolio_name: string;
  total_usdt: number;
  effective_total: number;
  threshold: number;
  allocations_sum: number;
  drift_report: DriftItem[];
  trades: TradeItem[];
  needs_rebalance: boolean;
}

export interface HistoryItem {
  id: number;
  timestamp: string;
  summary: string;
  total_traded_usdt: number;
  success: number;
  portfolio_name?: string;
}

export interface AllocationItem {
  symbol: string;
  target_percentage: number;
}

export interface SettingsData {
  has_api_keys: boolean;
  api_key_preview: string | null;
  threshold: number;
  portfolio_name: string;
  capital_usdt: number;
  allocations: AllocationItem[];
}

// ── API calls ──────────────────────────────────────────────────────────────────

export const api = {
  health: () => client.get("/api/health"),

  getPortfolio: () => client.get<PortfolioData>("/api/portfolio"),

  analyzeRebalance: () => client.get<AnalysisData>("/api/rebalance/analyze"),
  executeRebalance: () => client.post("/api/rebalance/execute"),

  getHistory: (limit = 20) => client.get<{ history: HistoryItem[] }>(`/api/history?limit=${limit}`),

  getSettings: () => client.get<SettingsData>("/api/settings"),
  saveApiKeys: (api_key: string, secret_key: string) =>
    client.post("/api/settings/api-keys", { api_key, secret_key }),
  saveThreshold: (threshold: number) =>
    client.post("/api/settings/threshold", { threshold }),
  saveCapital: (capital_usdt: number) =>
    client.post("/api/settings/capital", { capital_usdt }),
  saveAllocations: (allocations: AllocationItem[]) =>
    client.post("/api/settings/allocations", { allocations }),
  validateKeys: () => client.get<{ valid: boolean; message: string }>("/api/validate-keys"),
};
