'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import {
  getStatus, getHistory, getSnapshots, getBotStatus,
  startBot, stopBot, triggerRebalance, cancelRebalance,
  updateConfig, exportCsvUrl, exportExcelUrl,
} from '../lib/api';
import { Lang, tr } from '../lib/i18n';

const COLORS = ['#f0b90b','#3b82f6','#10b981','#8b5cf6','#ef4444','#f97316','#06b6d4','#ec4899','#84cc16','#a78bfa'];

interface Asset { symbol: string; allocation_pct: number; }

interface Props { lang: Lang; }

export default function Dashboard({ lang }: Props) {
  const [status, setStatus]       = useState<any>(null);
  const [history, setHistory]     = useState<any[]>([]);
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [botSt, setBotSt]         = useState<any>(null);
  const [loading, setLoading]     = useState(true);
  const [rebalancing, setRebalancing] = useState(false);
  const [cancelJobId, setCancelJobId] = useState<string | null>(null);
  const [cancelCountdown, setCancelCountdown] = useState(0);
  const [msg, setMsg]             = useState('');
  const [activeTab, setActiveTab] = useState<'overview'|'history'>('overview');

  // Inline asset editor state
  const [editAssets, setEditAssets]   = useState<Asset[]>([]);
  const [editMode, setEditMode]       = useState(false);
  const [editError, setEditError]     = useState('');
  const [editSaving, setEditSaving]   = useState(false);

  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, h, sn, b] = await Promise.all([
        getStatus(), getHistory(50), getSnapshots(90), getBotStatus(),
      ]);
      setStatus(s);
      setHistory(h);
      setSnapshots(sn);
      setBotSt(b);
      if (!editMode) {
        setEditAssets((s.assets ?? []).map((a: any) => ({
          symbol: a.symbol,
          allocation_pct: a.target_pct,
        })));
      }
    } catch (e: any) {
      setMsg(tr('errLoad', lang) + ': ' + e.message);
    } finally {
      setLoading(false);
    }
  }, [lang, editMode]);

  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, [load]);

  // ── Cancel countdown ────────────────────────────────────────────────────
  const startCancelCountdown = (jobId: string) => {
    setCancelJobId(jobId);
    setCancelCountdown(10);
    countdownRef.current = setInterval(() => {
      setCancelCountdown(prev => {
        if (prev <= 1) {
          clearInterval(countdownRef.current!);
          setCancelJobId(null);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  const handleCancel = async () => {
    if (!cancelJobId) return;
    clearInterval(countdownRef.current!);
    try {
      await cancelRebalance(cancelJobId);
      setMsg('⚠️ ' + tr('cancelledRebalance', lang));
    } catch (e: any) {
      setMsg('❌ ' + e.message);
    } finally {
      setCancelJobId(null);
      setCancelCountdown(0);
      setRebalancing(false);
    }
  };

  // ── Rebalance ───────────────────────────────────────────────────────────
  const handleRebalance = async () => {
    setRebalancing(true); setMsg('');
    try {
      const r = await triggerRebalance();
      startCancelCountdown(r.job_id);
      // Poll until done
      const poll = setInterval(async () => {
        try {
          const { done, cancelled, result } = await import('../lib/api').then(m =>
            m.getRebalanceJobStatus(r.job_id)
          );
          if (done || cancelled) {
            clearInterval(poll);
            clearInterval(countdownRef.current!);
            setCancelJobId(null);
            setCancelCountdown(0);
            setRebalancing(false);
            if (!cancelled) {
              setMsg('✅ ' + tr('successRebalance', lang));
              await load();
            }
          }
        } catch {}
      }, 1000);
    } catch (e: any) {
      setMsg('❌ ' + e.message);
      setRebalancing(false);
    }
  };

  const handleBotToggle = async () => {
    try {
      if (botSt?.running) { await stopBot(); setMsg('⏸️ ' + tr('pause', lang)); }
      else                { await startBot(); setMsg('▶️ ' + tr('start', lang)); }
      await load();
    } catch (e: any) { setMsg('❌ ' + e.message); }
  };

  // ── Inline asset editor ─────────────────────────────────────────────────
  const totalEditPct = editAssets.reduce((s, a) => s + a.allocation_pct, 0);

  const addEditAsset = () => {
    if (editAssets.length >= 10) return;
    setEditAssets([...editAssets, { symbol: '', allocation_pct: 0 }]);
    setEditError('');
  };

  const removeEditAsset = (i: number) => {
    if (editAssets.length <= 2) return;
    setEditAssets(editAssets.filter((_, idx) => idx !== i));
    setEditError('');
  };

  const updateEditSymbol = (i: number, val: string) => {
    const up = [...editAssets];
    const sym = val.toUpperCase();
    up[i] = { ...up[i], symbol: sym };
    setEditAssets(up);
    // Duplicate check
    const syms = up.map(a => a.symbol.trim()).filter(Boolean);
    if (new Set(syms).size !== syms.length) {
      setEditError('❌ ' + tr('errDuplicate', lang));
    } else {
      setEditError('');
    }
  };

  const updateEditPct = (i: number, val: number) => {
    const up = [...editAssets];
    up[i] = { ...up[i], allocation_pct: val };
    setEditAssets(up);
    setEditError('');
  };

  const allocateEqually = () => {
    const n = editAssets.length;
    const base = Math.floor((100 / n) * 100) / 100;
    const rem  = parseFloat((100 - base * (n - 1)).toFixed(2));
    setEditAssets(editAssets.map((a, i) => ({ ...a, allocation_pct: i === n - 1 ? rem : base })));
    setEditError('');
  };

  const saveEditAssets = async () => {
    const syms = editAssets.map(a => a.symbol.trim().toUpperCase());
    if (syms.some(s => !s)) { setEditError('❌ ' + tr('errSymbol', lang)); return; }
    if (new Set(syms).size !== syms.length) { setEditError('❌ ' + tr('errDuplicate', lang)); return; }
    if (Math.abs(totalEditPct - 100) > 0.1) { setEditError('❌ ' + tr('errSum', lang)); return; }
    setEditSaving(true); setEditError('');
    try {
      await updateConfig({
        assets: editAssets.map((a, i) => ({ symbol: syms[i], allocation_pct: a.allocation_pct })),
      });
      setEditMode(false);
      setMsg('✅ ' + tr('successSaved', lang));
      await load();
    } catch (e: any) {
      setEditError('❌ ' + e.message);
    } finally {
      setEditSaving(false);
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-pulse text-lg" style={{ color: 'var(--text-muted)' }}>
        {tr('loadingData', lang)}
      </div>
    </div>
  );

  const assets = status?.assets ?? [];
  const pnl    = status?.pnl ?? {};
  const pnlPos = (pnl.pnl_usdt ?? 0) >= 0;
  const pieData = assets.map((a: any) => ({ name: a.symbol, value: a.value_usdt }));

  const modeLabel: Record<string, string> = {
    proportional: '📊 ' + tr('proportional', lang),
    timed:        '⏰ ' + tr('timed', lang),
    unbalanced:   '🔓 ' + tr('manual', lang),
  };

  return (
    <div className="space-y-5">
      {/* Top bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-main)' }}>
            {status?.bot_name ?? 'المحفظة الذكية'}
          </h1>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className="badge bg-gray-800 text-gray-400">{modeLabel[status?.mode] ?? status?.mode}</span>
            {status?.paper_trading && <span className="badge bg-yellow-900 text-yellow-400">🧪 {tr('experimental', lang)}</span>}
            {status?.warning && <span className="badge bg-orange-900 text-orange-400">⚠️ {status.warning}</span>}
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={handleBotToggle} className={botSt?.running ? 'btn-danger' : 'btn-secondary'}>
            {botSt?.running ? '⏸️ ' + tr('pause', lang) : '▶️ ' + tr('start', lang)}
          </button>
          <button onClick={handleRebalance} disabled={rebalancing} className="btn-primary">
            {rebalancing ? '⏳ ' + tr('loading', lang) : '🔄 ' + tr('rebalanceNow', lang)}
          </button>
          {cancelJobId && cancelCountdown > 0 && (
            <button onClick={handleCancel} className="btn-cancel flex items-center gap-1">
              ✖ {tr('cancelRebalance', lang)} ({cancelCountdown}s)
            </button>
          )}
          <a href={exportExcelUrl()} className="btn-secondary text-sm flex items-center gap-1">
            📊 {tr('exportExcel', lang)}
          </a>
          <a href={exportCsvUrl()} className="btn-secondary text-sm flex items-center gap-1">
            ⬇️ {tr('exportCsv', lang)}
          </a>
        </div>
      </div>

      {msg && (
        <div className={`card text-sm ${msg.startsWith('❌') ? 'border-red-700 text-red-400' : msg.startsWith('⚠️') ? 'border-orange-700 text-orange-400' : 'border-green-700 text-green-400'}`}>
          {msg}
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card">
          <div className="label">{tr('totalPortfolio', lang)}</div>
          <div className="text-2xl font-bold" style={{ color: 'var(--text-main)' }}>
            ${(status?.total_usdt ?? 0).toFixed(2)}
          </div>
          <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>USDT</div>
        </div>
        <div className="card">
          <div className="label">{tr('profitLoss', lang)}</div>
          <div className={`text-2xl font-bold ${pnlPos ? 'text-green-400' : 'text-red-400'}`}>
            {pnlPos ? '+' : ''}{(pnl.pnl_usdt ?? 0).toFixed(2)} $
          </div>
          <div className={`text-xs mt-1 ${pnlPos ? 'text-green-500' : 'text-red-500'}`}>
            {pnlPos ? '+' : ''}{(pnl.pnl_pct ?? 0).toFixed(2)}%
          </div>
        </div>
        <div className="card">
          <div className="label">{tr('lastRebalance', lang)}</div>
          <div className="text-sm font-semibold" style={{ color: 'var(--text-main)' }}>
            {status?.last_rebalance ?? tr('notYet', lang)}
          </div>
        </div>
        <div className="card">
          <div className="label">{tr('assetCount', lang)}</div>
          <div className="text-2xl font-bold" style={{ color: 'var(--text-main)' }}>{assets.length}</div>
          <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{tr('currency', lang)}</div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="card flex flex-col items-center">
          <div className="label w-full mb-3">{tr('assetDist', lang)}</div>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={90} dataKey="value" paddingAngle={2}>
                {pieData.map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip formatter={(v: any) => `$${Number(v).toFixed(2)}`}
                contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }} />
              <Legend formatter={(v) => <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{v}</span>} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="card lg:col-span-2">
          <div className="label mb-3">{tr('portfolioPerf', lang)}</div>
          {snapshots.length > 1 ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={snapshots}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="ts" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} tickFormatter={(v) => v.slice(5, 16)} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
                <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
                  formatter={(v: any) => `$${Number(v).toFixed(2)}`} />
                <Line type="monotone" dataKey="total_usdt" stroke="#f0b90b" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-48 text-sm" style={{ color: 'var(--text-muted)' }}>
              {tr('noDataYet', lang)}
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="card">
        <div className="flex gap-2 mb-4 border-b pb-3" style={{ borderColor: 'var(--border)' }}>
          <button onClick={() => setActiveTab('overview')}
            className={`text-sm font-medium px-3 py-1 rounded-lg transition-colors ${activeTab === 'overview' ? 'bg-brand text-black' : ''}`}
            style={activeTab !== 'overview' ? { color: 'var(--text-muted)' } : {}}>
            📋 {tr('assetTable', lang)}
          </button>
          <button onClick={() => setActiveTab('history')}
            className={`text-sm font-medium px-3 py-1 rounded-lg transition-colors ${activeTab === 'history' ? 'bg-brand text-black' : ''}`}
            style={activeTab !== 'history' ? { color: 'var(--text-muted)' } : {}}>
            📜 {tr('history', lang)}
          </button>
        </div>

        {/* ── Assets table with inline editor ── */}
        {activeTab === 'overview' && (
          <div>
            {/* Edit toolbar */}
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
              <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                {editMode ? `${tr('assetsAndAlloc', lang)} (${editAssets.length}/10)` : ''}
              </div>
              <div className="flex gap-2 flex-wrap">
                {editMode ? (
                  <>
                    <button onClick={allocateEqually} className="btn-secondary text-xs px-3 py-1">
                      {tr('equalAlloc', lang)}
                    </button>
                    <button onClick={addEditAsset} disabled={editAssets.length >= 10} className="btn-primary text-xs px-3 py-1">
                      {tr('addAsset', lang)}
                    </button>
                    <button onClick={saveEditAssets} disabled={editSaving} className="btn-primary text-xs px-3 py-1">
                      {editSaving ? tr('saving', lang) : '💾 ' + tr('save', lang)}
                    </button>
                    <button onClick={() => { setEditMode(false); setEditError(''); }} className="btn-secondary text-xs px-3 py-1">
                      ✖
                    </button>
                  </>
                ) : (
                  <button onClick={() => setEditMode(true)} className="btn-secondary text-xs px-3 py-1">
                    ✏️ {lang === 'ar' ? 'تعديل الأصول' : 'Edit Assets'}
                  </button>
                )}
              </div>
            </div>

            {editError && (
              <div className="mb-3 text-sm text-red-400 border border-red-700 rounded-xl px-3 py-2">
                {editError}
              </div>
            )}

            {editMode ? (
              /* Inline editor */
              <div className="space-y-2">
                {editAssets.map((a, i) => {
                  const syms = editAssets.map(x => x.symbol.trim().toUpperCase());
                  const isDup = a.symbol.trim() !== '' && syms.filter(s => s === a.symbol.trim().toUpperCase()).length > 1;
                  return (
                    <div key={i} className="flex items-center gap-2">
                      <input
                        className={`input w-28 font-mono uppercase ${isDup ? 'border-red-500' : ''}`}
                        value={a.symbol}
                        onChange={e => updateEditSymbol(i, e.target.value)}
                        placeholder="BTC"
                        maxLength={10}
                      />
                      {isDup && <span className="text-red-400 text-xs">⚠️ {tr('errDuplicate', lang)}</span>}
                      <div className="flex-1 relative">
                        <input
                          type="number" min={0} max={100} step={0.1}
                          className="input"
                          value={a.allocation_pct}
                          onChange={e => updateEditPct(i, parseFloat(e.target.value) || 0)}
                        />
                        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm" style={{ color: 'var(--text-muted)' }}>%</span>
                      </div>
                      <button onClick={() => removeEditAsset(i)} disabled={editAssets.length <= 2}
                        className="text-red-500 hover:text-red-400 disabled:opacity-30 p-1">🗑️</button>
                    </div>
                  );
                })}
                <div className={`mt-2 text-sm font-semibold ${Math.abs(totalEditPct - 100) < 0.1 ? 'text-green-400' : 'text-red-400'}`}>
                  {tr('totalSum', lang)}: {totalEditPct.toFixed(1)}% {Math.abs(totalEditPct - 100) < 0.1 ? '✅' : tr('mustBe100', lang)}
                </div>
              </div>
            ) : (
              /* Read-only table */
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs border-b" style={{ color: 'var(--text-muted)', borderColor: 'var(--border)' }}>
                      <th className="text-right py-2 px-4">{tr('coin', lang)}</th>
                      <th className="text-right py-2 px-4">{tr('target', lang)}</th>
                      <th className="text-right py-2 px-4">{tr('current', lang)}</th>
                      <th className="text-right py-2 px-4">{tr('diff', lang)}</th>
                      <th className="text-right py-2 px-4">{tr('valueUsdt', lang)}</th>
                      <th className="text-right py-2 px-4">{tr('balancePrice', lang)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assets.map((a: any) => {
                      const dev = a.deviation;
                      const isOver  = dev > 0;
                      const absdev  = Math.abs(dev);
                      return (
                        <tr key={a.symbol} className="border-b hover:opacity-80 transition-colors"
                          style={{ borderColor: 'var(--border)' }}>
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              <div className="w-7 h-7 rounded-full bg-brand/20 flex items-center justify-center text-brand text-xs font-bold">
                                {a.symbol.slice(0, 2)}
                              </div>
                              <span className="font-semibold" style={{ color: 'var(--text-main)' }}>{a.symbol}</span>
                            </div>
                          </td>
                          <td className="py-3 px-4" style={{ color: 'var(--text-muted)' }}>{a.target_pct.toFixed(1)}%</td>
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              <div className="flex-1 rounded-full h-1.5 w-16" style={{ background: 'var(--bg-input)' }}>
                                <div className="h-1.5 rounded-full bg-brand" style={{ width: `${Math.min(a.actual_pct, 100)}%` }} />
                              </div>
                              <span className="text-sm" style={{ color: 'var(--text-main)' }}>{a.actual_pct.toFixed(1)}%</span>
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <span className={`badge ${absdev < 1 ? 'bg-gray-800 text-gray-400' : isOver ? 'bg-red-900/60 text-red-400' : 'bg-green-900/60 text-green-400'}`}>
                              {isOver ? '+' : ''}{dev.toFixed(1)}%
                            </span>
                          </td>
                          <td className="py-3 px-4" style={{ color: 'var(--text-muted)' }}>${a.value_usdt.toFixed(2)}</td>
                          <td className="py-3 px-4 text-xs" style={{ color: 'var(--text-muted)' }}>
                            {a.balance.toFixed(6)} @ ${a.price.toFixed(4)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* History tab */}
        {activeTab === 'history' && (
          <div className="overflow-x-auto">
            {history.length === 0 ? (
              <div className="text-center py-10" style={{ color: 'var(--text-muted)' }}>{tr('noOps', lang)}</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs border-b" style={{ color: 'var(--text-muted)', borderColor: 'var(--border)' }}>
                    <th className="text-right py-2 px-4">{tr('time', lang)}</th>
                    <th className="text-right py-2 px-4">{tr('mode', lang)}</th>
                    <th className="text-right py-2 px-4">{tr('total', lang)}</th>
                    <th className="text-right py-2 px-4">{tr('operations', lang)}</th>
                    <th className="text-right py-2 px-4">{tr('paper', lang)}</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h: any) => (
                    <tr key={h.id} className="border-b hover:opacity-80 transition-colors" style={{ borderColor: 'var(--border)' }}>
                      <td className="py-2 px-4 text-xs" style={{ color: 'var(--text-muted)' }}>{h.ts}</td>
                      <td className="py-2 px-4">
                        <span className="badge bg-gray-800 text-gray-300">{h.mode}</span>
                      </td>
                      <td className="py-2 px-4" style={{ color: 'var(--text-main)' }}>${Number(h.total_usdt).toFixed(2)}</td>
                      <td className="py-2 px-4">
                        <div className="flex flex-wrap gap-1">
                          {(h.details ?? []).filter((d: any) => d.action !== 'SKIP').map((d: any, i: number) => (
                            <span key={i} className={`badge text-xs ${d.action === 'BUY' ? 'bg-green-900 text-green-400' : d.action === 'SELL' ? 'bg-red-900 text-red-400' : 'bg-gray-800 text-gray-400'}`}>
                              {d.action} {d.symbol} {d.diff_usdt > 0 ? `$${d.diff_usdt}` : ''}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-2 px-4">
                        {h.paper
                          ? <span className="badge bg-yellow-900 text-yellow-400">{tr('experimental', lang)}</span>
                          : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
