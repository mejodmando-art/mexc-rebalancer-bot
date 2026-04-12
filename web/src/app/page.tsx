'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  PieChart, Pie, Cell, Tooltip as PieTooltip, ResponsiveContainer, Legend,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as LineTooltip,
} from 'recharts';
import { RefreshCw, TrendingUp, TrendingDown, Settings, Download, Play, Square } from 'lucide-react';
import clsx from 'clsx';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface Asset {
  symbol: string;
  balance: number;
  price: number;
  value_usdt: number;
  actual_pct: number;
  target_pct: number;
  deviation: number;
}

interface PnL {
  initial_usdt: number;
  current_usdt: number;
  pnl_usdt: number;
  pnl_pct: number;
}

interface Status {
  bot_name: string;
  total_usdt: number;
  mode: string;
  paper_trading: boolean;
  last_rebalance: string | null;
  assets: Asset[];
  pnl: PnL;
}

interface Snapshot { ts: string; total_usdt: number; }

interface RebalanceDetail {
  symbol: string; target_pct: number; actual_pct: number;
  deviation: number; diff_usdt: number; action: string;
}

interface HistoryRow {
  id: number; ts: string; mode: string;
  total_usdt: number; paper: number; details: RebalanceDetail[];
}

// ---------------------------------------------------------------------------
// Palette
// ---------------------------------------------------------------------------
const COLORS = ['#f0b90b','#3b82f6','#10b981','#8b5cf6','#ef4444',
                 '#f97316','#06b6d4','#ec4899','#84cc16','#a78bfa'];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span className={clsx('px-2 py-0.5 rounded text-xs font-semibold', color)}>
      {label}
    </span>
  );
}

function Card({ title, children, className }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={clsx('bg-gray-900 border border-gray-800 rounded-2xl p-5', className)}>
      {title && <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">{title}</h2>}
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function Dashboard() {
  const [status, setStatus]     = useState<Status | null>(null);
  const [snaps, setSnaps]       = useState<Snapshot[]>([]);
  const [history, setHistory]   = useState<HistoryRow[]>([]);
  const [loading, setLoading]   = useState(true);
  const [rebalancing, setRebalancing] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [error, setError]       = useState<string | null>(null);

  const API = process.env.NEXT_PUBLIC_API_URL || 'https://worker-production-5766.up.railway.app';

  const fetchAll = useCallback(async () => {
    try {
      const [s, sn, h] = await Promise.all([
        fetch(`${API}/api/status`).then(r => r.json()),
        fetch(`${API}/api/snapshots?limit=60`).then(r => r.json()),
        fetch(`${API}/api/history?limit=10`).then(r => r.json()),
      ]);
      setStatus(s);
      setSnaps(sn);
      setHistory(h);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Connection error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 30_000);
    return () => clearInterval(id);
  }, [fetchAll]);

  const handleRebalance = async () => {
    setRebalancing(true);
    try {
      await fetch(`${API}/api/rebalance`, { method: 'POST' });
      await fetchAll();
    } finally {
      setRebalancing(false);
    }
  };

  const handleExport = () => { window.open(`${API}/api/export/csv`, '_blank'); };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <RefreshCw className="animate-spin text-brand w-10 h-10" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <p className="text-red-400 text-lg">{error}</p>
        <button onClick={fetchAll} className="btn-primary">إعادة المحاولة</button>
      </div>
    );
  }

  const pnlPositive = (status?.pnl.pnl_usdt ?? 0) >= 0;

  return (
    <div className="min-h-screen p-4 md:p-8 max-w-7xl mx-auto space-y-6">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">{status?.bot_name}</h1>
          <div className="flex gap-2 mt-1 flex-wrap">
            <Badge label={status?.mode ?? ''} color="bg-brand/20 text-brand" />
            {status?.paper_trading && <Badge label="🧪 Paper Mode" color="bg-purple-500/20 text-purple-300" />}
            {status?.last_rebalance && (
              <span className="text-xs text-gray-500">آخر rebalance: {status.last_rebalance}</span>
            )}
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={fetchAll} className="icon-btn" title="تحديث">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button onClick={handleExport} className="icon-btn" title="تصدير CSV">
            <Download className="w-4 h-4" />
          </button>
          <button onClick={() => setShowSettings(s => !s)} className="icon-btn" title="الإعدادات">
            <Settings className="w-4 h-4" />
          </button>
          <button
            onClick={handleRebalance}
            disabled={rebalancing}
            className="btn-primary flex items-center gap-2"
          >
            {rebalancing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            Rebalance Now
          </button>
        </div>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <p className="text-xs text-gray-400">إجمالي المحفظة</p>
          <p className="text-2xl font-bold text-white mt-1">
            {status?.total_usdt.toFixed(2)} <span className="text-sm text-gray-400">USDT</span>
          </p>
        </Card>
        <Card>
          <p className="text-xs text-gray-400">الربح / الخسارة</p>
          <p className={clsx('text-2xl font-bold mt-1', pnlPositive ? 'text-green-400' : 'text-red-400')}>
            {pnlPositive ? '+' : ''}{status?.pnl.pnl_usdt.toFixed(2)} USDT
          </p>
          <p className={clsx('text-xs', pnlPositive ? 'text-green-500' : 'text-red-500')}>
            {pnlPositive ? '+' : ''}{status?.pnl.pnl_pct.toFixed(2)}%
          </p>
        </Card>
        <Card>
          <p className="text-xs text-gray-400">عدد الأصول</p>
          <p className="text-2xl font-bold text-white mt-1">{status?.assets.length}</p>
        </Card>
        <Card>
          <p className="text-xs text-gray-400">الاستثمار الأولي</p>
          <p className="text-2xl font-bold text-white mt-1">
            {status?.pnl.initial_usdt.toFixed(2)} <span className="text-sm text-gray-400">USDT</span>
          </p>
        </Card>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Pie chart */}
        <Card title="توزيع الأصول الحالي">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={status?.assets}
                dataKey="value_usdt"
                nameKey="symbol"
                cx="50%" cy="50%"
                outerRadius={90}
                label={({ symbol, actual_pct }) => `${symbol} ${actual_pct.toFixed(1)}%`}
                labelLine={false}
              >
                {status?.assets.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <PieTooltip
                formatter={(v: number) => [`${v.toFixed(2)} USDT`]}
                contentStyle={{ background: '#111827', border: '1px solid #374151' }}
              />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </Card>

        {/* Line chart */}
        <Card title="أداء المحفظة">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={snaps}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis
                dataKey="ts"
                tick={{ fill: '#6b7280', fontSize: 10 }}
                tickFormatter={v => v.slice(5, 16)}
              />
              <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
              <LineTooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151' }}
                formatter={(v: number) => [`${v.toFixed(2)} USDT`]}
              />
              <Line
                type="monotone"
                dataKey="total_usdt"
                stroke="#f0b90b"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Assets table */}
      <Card title="تفاصيل الأصول">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-gray-800">
                <th className="text-right py-2 pr-2">الأصل</th>
                <th className="text-right py-2">السعر</th>
                <th className="text-right py-2">القيمة (USDT)</th>
                <th className="text-right py-2">الحالي %</th>
                <th className="text-right py-2">الهدف %</th>
                <th className="text-right py-2">الانحراف</th>
              </tr>
            </thead>
            <tbody>
              {status?.assets.map((a, i) => {
                const dev = a.deviation;
                const devColor = Math.abs(dev) > 3 ? 'text-red-400' : Math.abs(dev) > 1 ? 'text-yellow-400' : 'text-green-400';
                return (
                  <tr key={a.symbol} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="py-3 pr-2 font-semibold flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-full inline-block"
                        style={{ background: COLORS[i % COLORS.length] }}
                      />
                      {a.symbol}
                    </td>
                    <td className="py-3 text-gray-300">${a.price.toFixed(4)}</td>
                    <td className="py-3 text-gray-300">{a.value_usdt.toFixed(2)}</td>
                    <td className="py-3">{a.actual_pct.toFixed(2)}%</td>
                    <td className="py-3 text-gray-400">{a.target_pct.toFixed(2)}%</td>
                    <td className={clsx('py-3 font-semibold', devColor)}>
                      {dev > 0 ? '+' : ''}{dev.toFixed(2)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* History */}
      <Card title="آخر عمليات إعادة التوازن">
        {history.length === 0 ? (
          <p className="text-gray-500 text-sm">لا توجد عمليات بعد.</p>
        ) : (
          <div className="space-y-3">
            {history.map(row => (
              <div key={row.id} className="bg-gray-800/50 rounded-xl p-4">
                <div className="flex flex-wrap items-center gap-3 mb-2">
                  <span className="text-xs text-gray-400">{row.ts}</span>
                  <Badge label={row.mode} color="bg-brand/20 text-brand" />
                  {row.paper ? <Badge label="Paper" color="bg-purple-500/20 text-purple-300" /> : null}
                  <span className="text-xs text-gray-300">{row.total_usdt.toFixed(2)} USDT</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {row.details.filter(d => d.action === 'BUY' || d.action === 'SELL').map((d, i) => (
                    <span
                      key={i}
                      className={clsx(
                        'text-xs px-2 py-1 rounded-lg font-mono',
                        d.action === 'BUY' ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'
                      )}
                    >
                      {d.action} {d.symbol} {d.diff_usdt > 0 ? '+' : ''}{d.diff_usdt.toFixed(2)} USDT
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Settings panel */}
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} onSaved={fetchAll} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Settings panel
// ---------------------------------------------------------------------------
function SettingsPanel({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [cfg, setCfg]     = useState<Record<string, unknown> | null>(null);
  const [saving, setSaving] = useState(false);

  const API = process.env.NEXT_PUBLIC_API_URL || 'https://worker-production-5766.up.railway.app';

  useEffect(() => {
    fetch(`${API}/api/config`).then(r => r.json()).then(setCfg);
  }, [API]);

  if (!cfg) return null;

  const portfolio = cfg.portfolio as Record<string, unknown>;
  const rebalance = cfg.rebalance as Record<string, unknown>;
  const assets    = portfolio.assets as Array<{ symbol: string; allocation_pct: number }>;
  const mode      = rebalance.mode as string;
  const prop      = rebalance.proportional as Record<string, number>;
  const timed     = rebalance.timed as Record<string, string>;

  const setAssetPct = (i: number, v: number) => {
    const next = assets.map((a, idx) => idx === i ? { ...a, allocation_pct: v } : a);
    setCfg({ ...cfg, portfolio: { ...portfolio, assets: next } });
  };

  const equalAlloc = () => {
    const pct = parseFloat((100 / assets.length).toFixed(4));
    const next = assets.map((a, i) =>
      ({ ...a, allocation_pct: i === assets.length - 1 ? parseFloat((100 - pct * (assets.length - 1)).toFixed(4)) : pct })
    );
    setCfg({ ...cfg, portfolio: { ...portfolio, assets: next } });
  };

  const save = async () => {
    setSaving(true);
    await fetch(`${API}/api/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bot_name: (cfg.bot as Record<string, string>).name,
        assets: assets,
        total_usdt: portfolio.total_usdt,
        rebalance_mode: mode,
        threshold_pct: prop.threshold_pct,
        frequency: timed.frequency,
        sell_at_termination: (cfg.termination as Record<string, boolean>).sell_at_termination,
        enable_asset_transfer: (cfg.asset_transfer as Record<string, boolean>).enable_asset_transfer,
        paper_trading: cfg.paper_trading,
      }),
    });
    setSaving(false);
    onSaved();
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto space-y-5">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">⚙️ الإعدادات</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl">✕</button>
        </div>

        {/* Bot name */}
        <div>
          <label className="label">اسم البوت</label>
          <input
            className="input"
            value={(cfg.bot as Record<string, string>).name}
            onChange={e => setCfg({ ...cfg, bot: { name: e.target.value } })}
          />
        </div>

        {/* Assets */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="label">الأصول والنسب</label>
            <button onClick={equalAlloc} className="text-xs text-brand hover:underline">
              📐 توزيع متساوي
            </button>
          </div>
          {assets.map((a, i) => (
            <div key={i} className="flex items-center gap-2 mb-2">
              <span className="w-16 text-sm font-mono text-gray-300">{a.symbol}</span>
              <input
                type="number"
                className="input flex-1"
                value={a.allocation_pct}
                min={0} max={100} step={0.01}
                onChange={e => setAssetPct(i, parseFloat(e.target.value))}
              />
              <span className="text-gray-400 text-sm">%</span>
            </div>
          ))}
          <p className="text-xs text-gray-500 mt-1">
            المجموع: {assets.reduce((s, a) => s + a.allocation_pct, 0).toFixed(2)}%
          </p>
        </div>

        {/* USDT */}
        <div>
          <label className="label">المبلغ الإجمالي (USDT)</label>
          <input
            type="number"
            className="input"
            value={portfolio.total_usdt as number}
            onChange={e => setCfg({ ...cfg, portfolio: { ...portfolio, total_usdt: parseFloat(e.target.value) } })}
          />
        </div>

        {/* Mode */}
        <div>
          <label className="label">وضع إعادة التوازن</label>
          <select
            className="input"
            value={mode}
            onChange={e => setCfg({ ...cfg, rebalance: { ...rebalance, mode: e.target.value } })}
          >
            <option value="proportional">Proportional (نسبي)</option>
            <option value="timed">Timed (زمني)</option>
            <option value="unbalanced">Unbalanced (يدوي)</option>
          </select>
        </div>

        {mode === 'proportional' && (
          <div>
            <label className="label">عتبة الانحراف</label>
            <div className="flex gap-2">
              {[1, 3, 5].map(t => (
                <button
                  key={t}
                  onClick={() => setCfg({ ...cfg, rebalance: { ...rebalance, proportional: { ...prop, threshold_pct: t } } })}
                  className={clsx('px-4 py-2 rounded-lg text-sm font-semibold border',
                    prop.threshold_pct === t
                      ? 'bg-brand text-black border-brand'
                      : 'border-gray-700 text-gray-300 hover:border-brand'
                  )}
                >
                  {t}%
                </button>
              ))}
            </div>
          </div>
        )}

        {mode === 'timed' && (
          <div>
            <label className="label">التكرار</label>
            <select
              className="input"
              value={timed.frequency}
              onChange={e => setCfg({ ...cfg, rebalance: { ...rebalance, timed: { frequency: e.target.value } } })}
            >
              <option value="daily">يومي</option>
              <option value="weekly">أسبوعي</option>
              <option value="monthly">شهري</option>
            </select>
          </div>
        )}

        {/* Toggles */}
        <div className="space-y-3">
          {[
            { key: 'sell_at_termination', label: 'بيع عند الإيقاف', path: 'termination' },
            { key: 'enable_asset_transfer', label: 'تمكين تحويل الأصول', path: 'asset_transfer' },
          ].map(({ key, label, path }) => (
            <label key={key} className="flex items-center justify-between cursor-pointer">
              <span className="text-sm text-gray-300">{label}</span>
              <input
                type="checkbox"
                className="w-4 h-4 accent-brand"
                checked={(cfg[path] as Record<string, boolean>)[key]}
                onChange={e => setCfg({ ...cfg, [path]: { ...cfg[path] as object, [key]: e.target.checked } })}
              />
            </label>
          ))}
          <label className="flex items-center justify-between cursor-pointer">
            <span className="text-sm text-gray-300">🧪 وضع تجريبي (Paper Trading)</span>
            <input
              type="checkbox"
              className="w-4 h-4 accent-brand"
              checked={cfg.paper_trading as boolean}
              onChange={e => setCfg({ ...cfg, paper_trading: e.target.checked })}
            />
          </label>
        </div>

        <button onClick={save} disabled={saving} className="btn-primary w-full">
          {saving ? 'جاري الحفظ...' : '💾 حفظ الإعدادات'}
        </button>
      </div>
    </div>
  );
}
