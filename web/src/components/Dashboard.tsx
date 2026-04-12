'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import AssetRow from './AssetRow';
import { getStatus, getHistory, getSnapshots, getBotStatus, startBot, stopBot, triggerRebalance, exportCsvUrl } from '../lib/api';

const COLORS = ['#f0b90b','#3b82f6','#10b981','#8b5cf6','#ef4444','#f97316','#06b6d4','#ec4899','#84cc16','#a78bfa'];

export default function Dashboard() {
  const [status, setStatus]       = useState<any>(null);
  const [history, setHistory]     = useState<any[]>([]);
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [botSt, setBotSt]         = useState<any>(null);
  const [loading, setLoading]     = useState(true);
  const [rebalancing, setRebalancing] = useState(false);
  const [msg, setMsg]             = useState('');
  const [activeTab, setActiveTab] = useState<'overview'|'history'>('overview');

  const load = useCallback(async () => {
    try {
      const [s, h, sn, b] = await Promise.all([
        getStatus(), getHistory(50), getSnapshots(90), getBotStatus(),
      ]);
      setStatus(s); setHistory(h); setSnapshots(sn); setBotSt(b);
    } catch (e: any) {
      setMsg('خطأ في تحميل البيانات: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, [load]);

  const handleRebalance = async () => {
    setRebalancing(true); setMsg('');
    try {
      const r = await triggerRebalance();
      setMsg('✅ تم تنفيذ إعادة التوازن بنجاح');
      await load();
    } catch (e: any) { setMsg('❌ ' + e.message); }
    finally { setRebalancing(false); }
  };

  const handleBotToggle = async () => {
    try {
      if (botSt?.running) { await stopBot(); setMsg('⏸️ تم إيقاف البوت'); }
      else                { await startBot(); setMsg('▶️ تم تشغيل البوت'); }
      await load();
    } catch (e: any) { setMsg('❌ ' + e.message); }
  };

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="text-gray-400 animate-pulse text-lg">جاري التحميل...</div>
    </div>
  );

  const assets = status?.assets ?? [];
  const pnl    = status?.pnl ?? {};
  const pnlPos = (pnl.pnl_usdt ?? 0) >= 0;

  const pieData = assets.map((a: any) => ({ name: a.symbol, value: a.value_usdt }));

  const modeLabel: Record<string, string> = {
    proportional: '📊 نسبة مئوية',
    timed:        '⏰ زمني',
    unbalanced:   '🔓 يدوي',
  };

  return (
    <div className="space-y-5">
      {/* Top bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">{status?.bot_name ?? 'المحفظة الذكية'}</h1>
          <div className="flex items-center gap-2 mt-1">
            <span className="badge bg-gray-800 text-gray-400">{modeLabel[status?.mode] ?? status?.mode}</span>
            {status?.paper_trading && <span className="badge bg-yellow-900 text-yellow-400">🧪 تجريبي</span>}
            {status?.warning && <span className="badge bg-orange-900 text-orange-400">⚠️ {status.warning}</span>}
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={handleBotToggle} className={botSt?.running ? 'btn-danger' : 'btn-secondary'}>
            {botSt?.running ? '⏸️ إيقاف مؤقت' : '▶️ تشغيل'}
          </button>
          <button onClick={handleRebalance} disabled={rebalancing} className="btn-primary">
            {rebalancing ? '⏳ جاري...' : '🔄 Rebalance يدوي'}
          </button>
          <a href={exportCsvUrl()} className="btn-secondary text-sm flex items-center gap-1">
            ⬇️ CSV
          </a>
        </div>
      </div>

      {msg && (
        <div className={`card text-sm ${msg.startsWith('❌') ? 'border-red-700 text-red-400' : 'border-green-700 text-green-400'}`}>
          {msg}
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card">
          <div className="label">إجمالي المحفظة</div>
          <div className="text-2xl font-bold text-white">${(status?.total_usdt ?? 0).toFixed(2)}</div>
          <div className="text-xs text-gray-500 mt-1">USDT</div>
        </div>
        <div className="card">
          <div className="label">الربح / الخسارة</div>
          <div className={`text-2xl font-bold ${pnlPos ? 'text-green-400' : 'text-red-400'}`}>
            {pnlPos ? '+' : ''}{(pnl.pnl_usdt ?? 0).toFixed(2)} $
          </div>
          <div className={`text-xs mt-1 ${pnlPos ? 'text-green-500' : 'text-red-500'}`}>
            {pnlPos ? '+' : ''}{(pnl.pnl_pct ?? 0).toFixed(2)}%
          </div>
        </div>
        <div className="card">
          <div className="label">آخر Rebalance</div>
          <div className="text-sm font-semibold text-white">{status?.last_rebalance ?? 'لم يتم بعد'}</div>
        </div>
        <div className="card">
          <div className="label">عدد الأصول</div>
          <div className="text-2xl font-bold text-white">{assets.length}</div>
          <div className="text-xs text-gray-500 mt-1">عملة</div>
        </div>
      </div>

      {/* Charts + table */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Pie chart */}
        <div className="card flex flex-col items-center">
          <div className="label w-full mb-3">توزيع الأصول الحالي</div>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={90} dataKey="value" paddingAngle={2}>
                {pieData.map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip formatter={(v: any) => `$${Number(v).toFixed(2)}`} contentStyle={{ background: '#111827', border: '1px solid #374151' }} />
              <Legend formatter={(v) => <span className="text-xs text-gray-300">{v}</span>} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Line chart */}
        <div className="card lg:col-span-2">
          <div className="label mb-3">أداء المحفظة (USDT)</div>
          {snapshots.length > 1 ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={snapshots}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="ts" tick={{ fontSize: 10, fill: '#6b7280' }} tickFormatter={(v) => v.slice(5, 16)} />
                <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
                <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151' }} formatter={(v: any) => `$${Number(v).toFixed(2)}`} />
                <Line type="monotone" dataKey="total_usdt" stroke="#f0b90b" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-48 text-gray-600 text-sm">لا توجد بيانات كافية بعد</div>
          )}
        </div>
      </div>

      {/* Tabs: Assets table / History */}
      <div className="card">
        <div className="flex gap-2 mb-4 border-b border-gray-800 pb-3">
          <button onClick={() => setActiveTab('overview')} className={`text-sm font-medium px-3 py-1 rounded-lg transition-colors ${activeTab === 'overview' ? 'bg-brand text-black' : 'text-gray-400 hover:text-white'}`}>
            📋 جدول الأصول
          </button>
          <button onClick={() => setActiveTab('history')} className={`text-sm font-medium px-3 py-1 rounded-lg transition-colors ${activeTab === 'history' ? 'bg-brand text-black' : 'text-gray-400 hover:text-white'}`}>
            📜 سجل العمليات
          </button>
        </div>

        {activeTab === 'overview' && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 text-xs border-b border-gray-800">
                  <th className="text-right py-2 px-4">العملة</th>
                  <th className="text-right py-2 px-4">الهدف%</th>
                  <th className="text-right py-2 px-4">الحالي%</th>
                  <th className="text-right py-2 px-4">الفرق</th>
                  <th className="text-right py-2 px-4">القيمة (USDT)</th>
                  <th className="text-right py-2 px-4">الرصيد / السعر</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((a: any) => (
                  <AssetRow key={a.symbol} symbol={a.symbol} targetPct={a.target_pct} actualPct={a.actual_pct}
                    deviation={a.deviation} valueUsdt={a.value_usdt} balance={a.balance} price={a.price} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'history' && (
          <div className="overflow-x-auto">
            {history.length === 0 ? (
              <div className="text-center text-gray-600 py-10">لا توجد عمليات بعد</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-500 text-xs border-b border-gray-800">
                    <th className="text-right py-2 px-4">الوقت</th>
                    <th className="text-right py-2 px-4">الوضع</th>
                    <th className="text-right py-2 px-4">الإجمالي</th>
                    <th className="text-right py-2 px-4">العمليات</th>
                    <th className="text-right py-2 px-4">تجريبي</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h: any) => (
                    <tr key={h.id} className="border-b border-gray-800 hover:bg-gray-800/40">
                      <td className="py-2 px-4 text-gray-400 text-xs">{h.ts}</td>
                      <td className="py-2 px-4">
                        <span className="badge bg-gray-800 text-gray-300">{h.mode}</span>
                      </td>
                      <td className="py-2 px-4 text-white">${Number(h.total_usdt).toFixed(2)}</td>
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
                        {h.paper ? <span className="badge bg-yellow-900 text-yellow-400">تجريبي</span> : <span className="text-gray-600">—</span>}
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
