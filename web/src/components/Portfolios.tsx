'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  listPortfolios, activatePortfolio, deletePortfolio,
  rebalancePortfolio, getRebalanceJobStatus, cancelRebalance,
  stopAndSellPortfolio, startPortfolio, stopPortfolio,
  savePortfolio, getPortfolio,
} from '../lib/api';
import { Lang, tr } from '../lib/i18n';

interface Props { lang: Lang; onActivated: () => void; onCreateBot?: () => void; }

type RebalanceType = 'market_value' | 'equal';

const MODE_ICON: Record<string, string> = {
  proportional: '📊',
  timed:        '⏰',
  unbalanced:   '🔓',
};

const COLORS = ['#f0b90b','#3b82f6','#10b981','#8b5cf6','#ef4444','#f97316','#06b6d4','#ec4899','#84cc16','#a78bfa'];

// ── Rebalance modal ──────────────────────────────────────────────────────────
interface RebalanceModalProps {
  portfolioId: number;
  portfolioName: string;
  isActive: boolean;
  lang: Lang;
  onClose: () => void;
  onDone: (msg: string) => void;
}

function RebalanceModal({ portfolioId, portfolioName, isActive, lang, onClose, onDone }: RebalanceModalProps) {
  const [type, setType]           = useState<RebalanceType>('market_value');
  const [phase, setPhase]         = useState<'pick' | 'countdown' | 'running'>('pick');
  const [countdown, setCountdown] = useState(10);
  const [jobId, setJobId]         = useState('');
  const [error, setError]         = useState('');

  const startRebalance = async () => {
    setError('');
    try {
      const res = await rebalancePortfolio(portfolioId, type);
      setJobId(res.job_id);
      setCountdown(res.cancel_window_seconds);
      setPhase('countdown');
    } catch (e: any) {
      setError('❌ ' + e.message);
    }
  };

  // Countdown timer
  useEffect(() => {
    if (phase !== 'countdown') return;
    if (countdown <= 0) { setPhase('running'); return; }
    const t = setTimeout(() => setCountdown(c => c - 1), 1000);
    return () => clearTimeout(t);
  }, [phase, countdown]);

  // Poll job status once running
  useEffect(() => {
    if (phase !== 'running' || !jobId) return;
    let active = true;
    const poll = async () => {
      try {
        const s = await getRebalanceJobStatus(jobId);
        if (!active) return;
        if (s.cancelled) { onDone(tr('rebalanceCancelled', lang)); onClose(); }
        else if (s.done)  { onDone(tr('rebalanceSuccess', lang));   onClose(); }
        else setTimeout(poll, 1500);
      } catch { if (active) setTimeout(poll, 2000); }
    };
    poll();
    return () => { active = false; };
  }, [phase, jobId, lang, onDone, onClose]);

  const handleCancel = async () => {
    if (jobId) { try { await cancelRebalance(jobId); } catch {} }
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
      <div className="card w-full max-w-md space-y-5" style={{ background: 'var(--bg-card)' }}>
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold" style={{ color: 'var(--text-main)' }}>
            ⚖️ {tr('rebalancePortfolio', lang)}
          </h2>
          <button onClick={handleCancel} className="text-xl" style={{ color: 'var(--text-muted)' }}>✖</button>
        </div>

        <p className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>{portfolioName}</p>

        {!isActive && (
          <div className="text-sm text-yellow-400 bg-yellow-900/30 rounded-xl px-3 py-2">
            ⚠️ {tr('activateFirst', lang)}
          </div>
        )}

        {/* Type picker */}
        {phase === 'pick' && (
          <>
            <div className="label">{tr('rebalanceType', lang)}</div>
            <div className="grid grid-cols-2 gap-3">
              {([
                { key: 'market_value' as RebalanceType, label: tr('rebalanceMarketValue', lang), desc: tr('rebalanceMarketDesc', lang), icon: '📊' },
                { key: 'equal'        as RebalanceType, label: tr('rebalanceEqual', lang),       desc: tr('rebalanceEqualDesc', lang),  icon: '⚖️' },
              ]).map(opt => (
                <button
                  key={opt.key}
                  onClick={() => setType(opt.key)}
                  className={`p-4 rounded-xl border-2 text-start transition-colors ${type === opt.key ? 'border-brand bg-brand/10' : 'border-gray-700 hover:border-gray-600'}`}
                >
                  <div className="text-2xl mb-1">{opt.icon}</div>
                  <div className="text-sm font-semibold" style={{ color: 'var(--text-main)' }}>{opt.label}</div>
                  <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{opt.desc}</div>
                </button>
              ))}
            </div>

            {error && <div className="text-sm text-red-400">{error}</div>}

            <div className="flex gap-2 pt-1">
              <button onClick={handleCancel} className="btn-secondary flex-1">
                {tr('rebalanceCancelBtn', lang)}
              </button>
              <button
                onClick={startRebalance}
                disabled={!isActive}
                className="btn-primary flex-1 disabled:opacity-40"
              >
                {tr('rebalanceConfirm', lang)}
              </button>
            </div>
          </>
        )}

        {/* Countdown */}
        {phase === 'countdown' && (
          <div className="text-center space-y-4 py-4">
            <div className="text-6xl font-bold text-brand">{countdown}</div>
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
              {tr('cancelWindow', lang)} {countdown} {tr('seconds', lang)}
            </p>
            <button onClick={handleCancel} className="btn-danger px-8 py-2">
              ✖ {tr('cancelRebalance', lang)}
            </button>
          </div>
        )}

        {/* Running */}
        {phase === 'running' && (
          <div className="text-center py-8 space-y-3">
            <div className="text-4xl animate-spin inline-block">⚙️</div>
            <p className="text-sm font-semibold" style={{ color: 'var(--text-main)' }}>
              {tr('rebalanceRunning', lang)}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Stop & Sell modal ────────────────────────────────────────────────────────
interface StopAndSellModalProps {
  portfolioId: number;
  portfolioName: string;
  lang: Lang;
  onClose: () => void;
  onDone: (msg: string) => void;
}

function StopAndSellModal({ portfolioId, portfolioName, lang, onClose, onDone }: StopAndSellModalProps) {
  const [phase, setPhase] = useState<'confirm' | 'running' | 'done'>('confirm');
  const [results, setResults] = useState<{ symbol: string; action: string; qty?: number; error?: string }[]>([]);
  const [error, setError] = useState('');

  const handleConfirm = async () => {
    setPhase('running');
    setError('');
    try {
      const res = await stopAndSellPortfolio(portfolioId);
      setResults(res.results);
      setPhase('done');
    } catch (e: any) {
      setError('❌ ' + e.message);
      setPhase('confirm');
    }
  };

  const handleClose = () => {
    if (phase === 'done') onDone(tr('stopAndSellSuccess', lang));
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
      <div className="card w-full max-w-md space-y-5" style={{ background: 'var(--bg-card)' }}>
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-red-400">
            🛑 {tr('stopAndSell', lang)}
          </h2>
          <button onClick={handleClose} className="text-xl" style={{ color: 'var(--text-muted)' }}>✖</button>
        </div>

        <p className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>{portfolioName}</p>

        {/* Confirm phase */}
        {phase === 'confirm' && (
          <>
            <div className="text-sm text-red-300 bg-red-900/30 rounded-xl px-4 py-3 leading-relaxed">
              ⚠️ {tr('stopAndSellDesc', lang)}
            </div>
            {error && <div className="text-sm text-red-400">{error}</div>}
            <div className="flex gap-2 pt-1">
              <button onClick={onClose} className="btn-secondary flex-1">
                {tr('stopAndSellCancel', lang)}
              </button>
              <button onClick={handleConfirm} className="btn-danger flex-1">
                🛑 {tr('stopAndSellConfirm', lang)}
              </button>
            </div>
          </>
        )}

        {/* Running phase */}
        {phase === 'running' && (
          <div className="text-center py-8 space-y-3">
            <div className="text-4xl animate-spin inline-block">⚙️</div>
            <p className="text-sm font-semibold" style={{ color: 'var(--text-main)' }}>
              {tr('stopAndSellRunning', lang)}
            </p>
          </div>
        )}

        {/* Done phase */}
        {phase === 'done' && (
          <>
            <div className="text-sm text-green-400 bg-green-900/20 rounded-xl px-4 py-3">
              ✅ {tr('stopAndSellSuccess', lang)}
            </div>
            <div className="space-y-2">
              {results.map((r) => (
                <div key={r.symbol} className="flex items-center justify-between text-sm px-3 py-2 rounded-xl" style={{ background: 'var(--bg-input)' }}>
                  <span className="font-semibold" style={{ color: 'var(--text-main)' }}>{r.symbol}</span>
                  <span className={r.action === 'SOLD' ? 'text-green-400' : r.action === 'ERROR' ? 'text-red-400' : 'text-gray-500'}>
                    {r.action === 'SOLD' ? `✅ بيع ${r.qty?.toFixed(6)}` : r.action === 'ERROR' ? `❌ ${r.error}` : '— لا رصيد'}
                  </span>
                </div>
              ))}
            </div>
            <button onClick={handleClose} className="btn-primary w-full">
              {tr('stopAndSellCancel', lang)}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ── Copy Portfolio Modal ─────────────────────────────────────────────────────
interface CopyModalProps {
  source: any; // summary object from listPortfolios (has id, name, total_usdt)
  lang: Lang;
  onClose: () => void;
  onDone: () => void;
}

function CopyModal({ source, lang, onClose, onDone }: CopyModalProps) {
  const srcName: string = source?.name ?? '';
  const srcUsdt: number = source?.total_usdt ?? 0;

  const [newName,    setNewName]    = useState((lang === 'ar' ? 'نسخة من ' : 'Copy of ') + srcName);
  const [customUsdt, setCustomUsdt] = useState('');
  const [saving,     setSaving]     = useState(false);
  const [error,      setError]      = useState('');

  const handleClone = async () => {
    const name = newName.trim();
    if (!name) {
      setError(lang === 'ar' ? 'أدخل اسم المحفظة الجديدة' : 'Enter a name for the new portfolio');
      return;
    }
    const usdtVal = customUsdt.trim() !== '' ? parseFloat(customUsdt) : srcUsdt;
    if (isNaN(usdtVal) || usdtVal <= 0) {
      setError(lang === 'ar' ? 'أدخل مبلغ صحيح' : 'Enter a valid amount');
      return;
    }

    setSaving(true);
    setError('');
    try {
      // Fetch full config from backend (returns raw config JSON), then deep-clone with overrides
      const full = await getPortfolio(source.id);
      const cfg: any = full;
      const cloned = JSON.parse(JSON.stringify(cfg));
      cloned.bot = { ...(cloned.bot ?? {}), name };
      cloned.portfolio = {
        ...(cloned.portfolio ?? {}),
        total_usdt: usdtVal,
        initial_value_usdt: usdtVal,
      };
      cloned.last_rebalance = null;

      await savePortfolio(cloned);
      onDone();
    } catch (e: any) {
      setError(lang === 'ar' ? 'فشل النسخ: ' + e.message : 'Clone failed: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
      <div className="card w-full max-w-md space-y-5" style={{ background: 'var(--bg-card)' }}>
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold" style={{ color: 'var(--text-main)' }}>
            📋 {tr('copyPortfolio', lang)}
          </h2>
          <button onClick={onClose} className="text-xl" style={{ color: 'var(--text-muted)' }}>✖</button>
        </div>

        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {lang === 'ar' ? 'المصدر: ' : 'Source: '}<strong>{srcName}</strong>
          {' · '}${srcUsdt.toLocaleString('en-US', { maximumFractionDigits: 2 })}
        </p>

        {/* New name */}
        <div className="space-y-1.5">
          <label className="label">
            {lang === 'ar' ? 'اسم المحفظة الجديدة (اختياري)' : 'New Portfolio Name (optional)'}
          </label>
          <input
            className="input"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            placeholder={lang === 'ar' ? 'اسم المحفظة الجديدة' : 'New portfolio name'}
          />
        </div>

        {/* Custom USDT */}
        <div className="space-y-1.5">
          <label className="label">
            {lang === 'ar' ? 'مبلغ الاستثمار (اختياري)' : 'Investment Amount (optional)'}
          </label>
          <div className="relative">
            <span
              className="absolute inset-y-0 start-3 flex items-center text-sm font-bold pointer-events-none"
              style={{ color: 'var(--text-muted)' }}
            >$</span>
            <input
              className="input !ps-7 num"
              type="number"
              min="0"
              step="any"
              value={customUsdt}
              onChange={e => setCustomUsdt(e.target.value)}
              placeholder={srcUsdt > 0 ? srcUsdt.toFixed(2) : '0.00'}
            />
          </div>
          <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {lang === 'ar'
              ? 'اتركه فارغاً للإبقاء على نفس مبلغ المصدر — رصيد كل محفظة مستقل'
              : 'Leave empty to keep source amount — each portfolio has its own isolated balance'}
          </p>
        </div>

        {error && <div className="text-sm text-red-400">{error}</div>}

        <div className="flex gap-2 pt-1">
          <button onClick={onClose} className="btn-secondary flex-1">
            {lang === 'ar' ? 'إلغاء' : 'Cancel'}
          </button>
          <button onClick={handleClone} disabled={saving} className="btn-accent flex-1 disabled:opacity-40">
            {saving
              ? (lang === 'ar' ? '⏳ جاري النسخ...' : '⏳ Cloning...')
              : `📋 ${tr('copyBtn', lang)}`}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────
export default function Portfolios({ lang, onActivated, onCreateBot }: Props) {
  const [portfolios, setPortfolios]       = useState<any[]>([]);
  const [loading, setLoading]             = useState(true);
  const [msg, setMsg]                     = useState('');
  const [activating, setActivating]         = useState<number | null>(null);
  const [deleting, setDeleting]             = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete]   = useState<number | null>(null);
  const [rebalModal, setRebalModal]         = useState<{ id: number; name: string; active: boolean } | null>(null);
  const [stopSellModal, setStopSellModal]   = useState<{ id: number; name: string } | null>(null);
  const [togglingLoop, setTogglingLoop]     = useState<number | null>(null);
  const [copyModal, setCopyModal]           = useState<any | null>(null);

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

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

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

  const handleBuyAndActivate = async (p: any) => {
    setActivating(p.id); setMsg('');
    try {
      await activatePortfolio(p.id);
      await load();
      // Open rebalance modal with equal type pre-selected for the now-active portfolio
      setRebalModal({ id: p.id, name: p.name, active: true });
    } catch (e: any) {
      setMsg('❌ ' + e.message);
    } finally {
      setActivating(null);
    }
  };

  const handleToggleLoop = async (p: any) => {
    setTogglingLoop(p.id); setMsg('');
    try {
      if (p.running) {
        const r = await stopPortfolio(p.id);
        setMsg('⏹ ' + r.message);
      } else {
        const r = await startPortfolio(p.id);
        setMsg('▶️ ' + r.message);
      }
      await load();
    } catch (e: any) {
      setMsg('❌ ' + e.message);
    } finally {
      setTogglingLoop(null);
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
    <>
      {rebalModal && (
        <RebalanceModal
          portfolioId={rebalModal.id}
          portfolioName={rebalModal.name}
          isActive={rebalModal.active}
          lang={lang}
          onClose={() => setRebalModal(null)}
          onDone={(m) => { setMsg('✅ ' + m); load(); }}
        />
      )}
      {stopSellModal && (
        <StopAndSellModal
          portfolioId={stopSellModal.id}
          portfolioName={stopSellModal.name}
          lang={lang}
          onClose={() => setStopSellModal(null)}
          onDone={(m) => { setMsg('✅ ' + m); load(); }}
        />
      )}
      {copyModal && (
        <CopyModal
          source={copyModal}
          lang={lang}
          onClose={() => setCopyModal(null)}
          onDone={() => {
            setCopyModal(null);
            setMsg('✅ ' + tr('copySuccess', lang));
            load();
          }}
        />
      )}

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
          <div className="flex items-center gap-2">
            <div className="text-sm font-semibold px-3 py-1 rounded-xl" style={{ background: 'var(--bg-card)', color: 'var(--text-muted)' }}>
              {portfolios.length} / 10 {tr('portfolioCount', lang)}
            </div>
            {onCreateBot && (
              <button
                onClick={onCreateBot}
                className="flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-sm transition-all active:scale-95"
                style={{
                  background: 'linear-gradient(135deg, #7B5CF5, #3B82F6)',
                  color: '#fff',
                  boxShadow: '0 4px 16px rgba(123,92,245,0.45)',
                  border: '1px solid rgba(255,255,255,0.15)',
                }}
              >
                <span className="text-lg leading-none">+</span>
                <span>{lang === 'ar' ? 'إنشاء محفظة' : 'New Portfolio'}</span>
              </button>
            )}
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
                className={`card flex flex-col gap-3 relative transition-all ${p.running ? 'border-green-500' : ''}`}
                style={p.running ? { borderColor: '#22c55e', borderWidth: 2 } : {}}
              >
                {/* Running badge */}
                {p.running && (
                  <div className="absolute top-3 left-3 badge bg-green-900/40 text-green-400 text-xs font-bold animate-pulse">
                    ✅ {tr('portfolioRunning', lang)}
                  </div>
                )}

                {/* Name + mode */}
                <div className={`${p.running ? 'mt-6' : ''}`}>
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
                <div className="grid grid-cols-3 gap-2 rounded-xl p-3" style={{ background: 'var(--bg-input)' }}>
                  <div className="flex flex-col items-center text-center">
                    <span className="text-[10px] font-bold uppercase tracking-wide mb-0.5" style={{ color: 'var(--text-muted)' }}>
                      {lang === 'ar' ? 'المبلغ' : 'Budget'}
                    </span>
                    <span className="num font-bold text-sm" style={{ color: 'var(--text-main)' }}>
                      ${p.total_usdt.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                    </span>
                  </div>
                  <div className="flex flex-col items-center text-center border-x" style={{ borderColor: 'var(--border)' }}>
                    <span className="text-[10px] font-bold uppercase tracking-wide mb-0.5" style={{ color: 'var(--text-muted)' }}>
                      {tr('mode', lang)}
                    </span>
                    <span className="font-semibold text-xs" style={{ color: 'var(--accent)' }}>
                      {MODE_ICON[p.mode] ?? '📁'} {p.mode}
                    </span>
                  </div>
                  <div className="flex flex-col items-center text-center">
                    <span className="text-[10px] font-bold uppercase tracking-wide mb-0.5" style={{ color: 'var(--text-muted)' }}>
                      {tr('assetCount', lang)}
                    </span>
                    <span className="num font-bold text-sm" style={{ color: 'var(--text-main)' }}>
                      {p.assets.length}
                    </span>
                  </div>
                </div>

                {/* Asset allocation bar */}
                <div>
                  <div className="flex rounded-full overflow-hidden h-1.5 w-full gap-px mb-2">
                    {p.assets.map((a: any, i: number) => (
                      <div
                        key={a.symbol}
                        style={{ width: `${a.allocation_pct}%`, background: COLORS[i % COLORS.length] }}
                        title={`${a.symbol}: ${a.allocation_pct}%`}
                      />
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {p.assets.map((a: any, i: number) => (
                      <span key={a.symbol}
                        className="flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[11px] font-semibold"
                        style={{ background: `${COLORS[i % COLORS.length]}18`, color: COLORS[i % COLORS.length] }}>
                        <img
                          src={`https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/32/color/${a.symbol.toLowerCase()}.png`}
                          alt={a.symbol}
                          className="w-3 h-3 rounded-full"
                          onError={(e) => { e.currentTarget.style.display = 'none'; }}
                        />
                        {a.symbol} {a.allocation_pct}%
                      </span>
                    ))}
                  </div>
                </div>

                {/* Buy & Activate button — only for non-active portfolios */}
                {!p.running && (
                  <button
                    onClick={() => handleBuyAndActivate(p)}
                    disabled={activating === p.id}
                    className="w-full py-2 rounded-xl text-sm font-semibold transition-all disabled:opacity-40 btn-primary"
                  >
                    {activating === p.id ? '⏳' : `🛒 ${tr('buyAndActivate', lang)}`}
                  </button>
                )}

                {/* Copy portfolio button */}
                <button
                  onClick={() => setCopyModal(p)}
                  className="w-full py-2 rounded-xl text-sm font-semibold transition-colors"
                  style={{
                    background: 'var(--bg-input)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-muted)',
                  }}
                >
                  📋 {tr('copyPortfolio', lang)}
                </button>

                {/* Rebalance button */}
                <button
                  onClick={() => setRebalModal({ id: p.id, name: p.name, active: true })}
                  className="w-full py-2 rounded-xl border-2 border-brand text-brand text-sm font-semibold hover:bg-brand/10 transition-colors"
                >
                  ⚖️ {tr('rebalancePortfolio', lang)}
                </button>

                {/* Stop & Sell button — all portfolios */}
                <button
                  onClick={() => setStopSellModal({ id: p.id, name: p.name })}
                  className="w-full py-2 rounded-xl border-2 border-red-700 text-red-400 text-sm font-semibold hover:bg-red-900/20 transition-colors"
                >
                  🛑 {tr('stopAndSell', lang)}
                </button>

                {/* Start / Stop / Delete actions */}
                <div className="flex gap-2 pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
                  {/* Start / Stop toggle */}
                  <button
                    onClick={() => handleToggleLoop(p)}
                    disabled={togglingLoop === p.id}
                    className={`flex-1 text-sm py-1.5 rounded-xl font-semibold transition-colors ${
                      p.running
                        ? 'bg-gray-700 text-gray-200 hover:bg-gray-600'
                        : 'btn-primary'
                    }`}
                  >
                    {togglingLoop === p.id ? '⏳' : p.running ? `⏹ ${tr('stopPortfolio', lang)}` : `▶️ ${tr('startPortfolio', lang)}`}
                  </button>

                  {/* Delete */}
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
                      disabled={p.running}
                      className="btn-secondary text-sm px-3 py-1.5 disabled:opacity-30"
                      title={p.running ? tr('cantDeleteActive', lang) : tr('deletePortfolio', lang)}
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
    </>
  );
}
