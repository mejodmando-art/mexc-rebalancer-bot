'use client';

import { useEffect, useState, useCallback } from 'react';
import { listPortfolios, activatePortfolio, deletePortfolio } from '../lib/api';
import { Lang, tr } from '../lib/i18n';

interface Props { lang: Lang; onActivated: () => void; }

const MODE_ICON: Record<string, string> = {
  proportional: '📊',
  timed:        '⏰',
  unbalanced:   '🔓',
};

const COLORS = ['#f0b90b','#3b82f6','#10b981','#8b5cf6','#ef4444','#f97316','#06b6d4','#ec4899','#84cc16','#a78bfa'];

export default function Portfolios({ lang, onActivated }: Props) {
  const [portfolios, setPortfolios] = useState<any[]>([]);
  const [loading, setLoading]       = useState(true);
  const [msg, setMsg]               = useState('');
  const [activating, setActivating] = useState<number | null>(null);
  const [deleting, setDeleting]     = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await listPortfolios();
      setPortfolios(data);
    } catch (e: any) {
      setMsg('❌ ' + e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleActivate = async (id: number) => {
    setActivating(id); setMsg('');
    try {
      const r = await activatePortfolio(id);
      setMsg('✅ ' + r.message);
      await load();
      setTimeout(onActivated, 1200);
    } catch (e: any) {
      setMsg('❌ ' + e.message);
    } finally {
      setActivating(null);
    }
  };

  const handleDelete = async (id: number) => {
    setDeleting(id); setMsg('');
    try {
      await deletePortfolio(id);
      setConfirmDelete(null);
      await load();
    } catch (e: any) {
      setMsg('❌ ' + e.message);
    } finally {
      setDeleting(null);
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-pulse text-lg" style={{ color: 'var(--text-muted)' }}>
        {tr('loadingData', lang)}
      </div>
    </div>
  );

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-main)' }}>
            {tr('myPortfolios', lang)}
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
            {tr('myPortfoliosDesc', lang)}
          </p>
        </div>
        <div className="text-sm font-semibold px-3 py-1 rounded-xl" style={{ background: 'var(--bg-card)', color: 'var(--text-muted)' }}>
          {portfolios.length} / 10 {tr('portfolioCount', lang)}
        </div>
      </div>

      {msg && (
        <div className={`card text-sm ${msg.startsWith('❌') ? 'border-red-700 text-red-400' : 'border-green-700 text-green-400'}`}>
          {msg}
        </div>
      )}

      {portfolios.length === 0 ? (
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <div className="text-5xl">📂</div>
          <div className="text-lg font-semibold" style={{ color: 'var(--text-main)' }}>
            {tr('noPortfolios', lang)}
          </div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>
            {tr('noPortfoliosDesc', lang)}
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {portfolios.map((p) => (
            <div
              key={p.id}
              className={`card flex flex-col gap-3 relative transition-all ${p.active ? 'border-brand' : ''}`}
              style={p.active ? { borderColor: 'var(--brand)', borderWidth: 2 } : {}}
            >
              {/* Active badge */}
              {p.active && (
                <div className="absolute top-3 left-3 badge bg-brand/20 text-brand text-xs font-bold">
                  ✅ {tr('activePortfolio', lang)}
                </div>
              )}

              {/* Name + mode */}
              <div className={`${p.active ? 'mt-6' : ''}`}>
                <div className="flex items-center gap-2">
                  <span className="text-xl">{MODE_ICON[p.mode] ?? '📁'}</span>
                  <span className="font-bold text-base" style={{ color: 'var(--text-main)' }}>{p.name}</span>
                  {p.paper_trading && (
                    <span className="badge bg-yellow-900 text-yellow-400 text-xs">🧪</span>
                  )}
                </div>
                <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                  {tr('createdAt', lang)}: {p.ts_created.slice(0, 16)}
                </div>
              </div>

              {/* Stats row */}
              <div className="flex gap-3 text-sm flex-wrap">
                <div className="flex flex-col">
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{tr('totalPortfolio', lang)}</span>
                  <span className="font-semibold" style={{ color: 'var(--text-main)' }}>${p.total_usdt.toLocaleString()}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{tr('mode', lang)}</span>
                  <span className="font-semibold" style={{ color: 'var(--text-main)' }}>{p.mode}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{tr('assetCount', lang)}</span>
                  <span className="font-semibold" style={{ color: 'var(--text-main)' }}>{p.assets.length}</span>
                </div>
              </div>

              {/* Asset allocation bar */}
              <div>
                <div className="flex rounded-full overflow-hidden h-2 w-full gap-px">
                  {p.assets.map((a: any, i: number) => (
                    <div
                      key={a.symbol}
                      style={{ width: `${a.allocation_pct}%`, background: COLORS[i % COLORS.length] }}
                      title={`${a.symbol}: ${a.allocation_pct}%`}
                    />
                  ))}
                </div>
                <div className="flex flex-wrap gap-2 mt-2">
                  {p.assets.map((a: any, i: number) => (
                    <span key={a.symbol} className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                      <span className="w-2 h-2 rounded-full inline-block" style={{ background: COLORS[i % COLORS.length] }} />
                      {a.symbol} {a.allocation_pct}%
                    </span>
                  ))}
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-2 mt-auto pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
                {!p.active && (
                  <button
                    onClick={() => handleActivate(p.id)}
                    disabled={activating === p.id}
                    className="btn-primary flex-1 text-sm py-1.5"
                  >
                    {activating === p.id ? '⏳' : '▶️'} {tr('activatePortfolio', lang)}
                  </button>
                )}
                {p.active && (
                  <div className="flex-1 text-center text-sm py-1.5 rounded-xl font-semibold text-brand" style={{ background: 'var(--bg-input)' }}>
                    ✅ {tr('currentlyActive', lang)}
                  </div>
                )}
                {confirmDelete === p.id ? (
                  <div className="flex gap-1">
                    <button
                      onClick={() => handleDelete(p.id)}
                      disabled={deleting === p.id}
                      className="btn-danger text-xs px-3 py-1.5"
                    >
                      {deleting === p.id ? '⏳' : tr('confirmDelete', lang)}
                    </button>
                    <button
                      onClick={() => setConfirmDelete(null)}
                      className="btn-secondary text-xs px-3 py-1.5"
                    >
                      ✖
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmDelete(p.id)}
                    disabled={p.active}
                    className="btn-secondary text-sm px-3 py-1.5 disabled:opacity-30"
                    title={p.active ? tr('cantDeleteActive', lang) : tr('deletePortfolio', lang)}
                  >
                    🗑️
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
