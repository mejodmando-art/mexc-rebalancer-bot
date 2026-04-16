'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  DollarSign, Wallet, TrendingUp, TrendingDown,
  Play, Square, RefreshCw, Zap,
  CheckCircle2, XCircle, ShoppingCart, History,
} from 'lucide-react';
import {
  getStatus, getBotStatus,
  startBot, stopBot, triggerRebalance, cancelRebalance,
  getRebalanceJobStatus, getAccountTotal, getConfig,
  listPortfolios, activatePortfolio, rebalancePortfolio, startPortfolio,
  stopPortfolio, getPortfolioAssets, stopAndSellPortfolio, getHistory,
} from '../lib/api';
import { Lang, tr } from '../lib/i18n';
import { useToast } from './Toast';
import StatCard from './StatCard';
import AssetsTable from './AssetsTable';

interface Asset {
  symbol: string; target_pct: number; current_pct: number;
  diff_pct: number; value_usdt: number; balance: number; price_usdt: number;
}
interface StatusData {
  total_usdt: number; assets: Asset[];
  bot_name?: string; mode?: string;
}
interface Props { lang: Lang }

function createRipple(e: React.MouseEvent<HTMLButtonElement>) {
  const btn = e.currentTarget;
  const rect = btn.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height) * 2;
  const x = e.clientX - rect.left - size / 2;
  const y = e.clientY - rect.top - size / 2;
  const ripple = document.createElement('span');
  ripple.className = 'ripple';
  ripple.style.cssText = `width:${size}px;height:${size}px;left:${x}px;top:${y}px;`;
  btn.appendChild(ripple);
  setTimeout(() => ripple.remove(), 700);
}

export default function Dashboard({ lang }: Props) {
  const toast = useToast();

  const [status,       setStatus]       = useState<StatusData | null>(null);
  const [botRunning,   setBotRunning]   = useState(false);
  const [loading,      setLoading]      = useState(true);
  const [accountTotal, setAccountTotal] = useState<number | null>(null);
  const [freeUsdt,     setFreeUsdt]     = useState<number | null>(null);
  const [lockedUsdt,   setLockedUsdt]   = useState<number | null>(null);
  const [refreshing,   setRefreshing]   = useState(false);
  const autoRefreshRef = useRef(true);

  const [rebalancing,  setRebalancing]  = useState(false);
  const [jobId,        setJobId]        = useState<string | null>(null);
  const [cancelWindow, setCancelWindow] = useState(0);
  const [cancelTimer,  setCancelTimer]  = useState(0);
  const cancelIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [botLoading,      setBotLoading]      = useState(false);
  const [buyActivating,   setBuyActivating]   = useState(false);
  const [investedUsdt,    setInvestedUsdt]    = useState<number | null>(null);
  const [portfolios,      setPortfolios]      = useState<any[]>([]);
  const [showBuyModal,    setShowBuyModal]    = useState(false);
  const [selectedPortId,  setSelectedPortId]  = useState<number | null>(null);

  // Portfolio view selector: null = "all", number = specific portfolio id
  const [viewPortId,      setViewPortId]      = useState<number | 'all'>('all');
  const [showPortPicker,  setShowPortPicker]  = useState(false);
  // Per-portfolio assets data when viewing "all"
  const [allPortAssets,   setAllPortAssets]   = useState<Record<number, any>>({});
  const [loadingPortAssets, setLoadingPortAssets] = useState(false);
  // Per-portfolio loop toggle state
  const [togglingLoop,    setTogglingLoop]    = useState<number | null>(null);
  // Per-portfolio rebalance in progress
  const [rebalancingPort, setRebalancingPort] = useState<number | null>(null);
  // Stop-and-sell in progress
  const [sellingPort,     setSellingPort]     = useState<number | null>(null);
  // History modal
  const [historyPort,     setHistoryPort]     = useState<{ name: string; rows: any[] } | null>(null);


  const fetchPortfolioAssets = useCallback(async (list: any[]) => {
    if (list.length === 0) return;
    setLoadingPortAssets(true);
    const results: Record<number, any> = {};
    await Promise.allSettled(
      list.map(async (p) => {
        try {
          const data = await getPortfolioAssets(p.id);
          results[p.id] = data;
        } catch { /* skip failed */ }
      })
    );
    setAllPortAssets(results);
    setLoadingPortAssets(false);
  }, []);

  const fetchAll = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const [s, bot] = await Promise.all([getStatus(), getBotStatus()]);
      setStatus(s);
      setBotRunning(bot?.running ?? false);
      getAccountTotal().then(r => {
        setAccountTotal(r.total_usdt);
        setFreeUsdt(r.free_usdt   ?? null);
        setLockedUsdt(r.locked_usdt ?? null);
      }).catch(() => {});
      getConfig().then(cfg => {
        const v = cfg?.portfolio?.total_usdt ?? cfg?.total_usdt ?? null;
        setInvestedUsdt(typeof v === 'number' ? v : null);
      }).catch(() => {});
      listPortfolios().then(list => {
        setPortfolios(list);
        if (selectedPortId === null && list.length > 0) {
          const active = list.find((p: any) => p.active) ?? list[0];
          setSelectedPortId(active.id);
        }
        fetchPortfolioAssets(list);
      }).catch(() => {});
    } catch (err: any) {
      if (!silent) toast.error(tr('errLoad', lang), err?.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [lang, toast, selectedPortId, fetchPortfolioAssets]);

  useEffect(() => { fetchAll(); }, [fetchAll]);
  useEffect(() => {
    const t = setInterval(() => { if (autoRefreshRef.current) fetchAll(true); }, 15000);
    return () => clearInterval(t);
  }, [fetchAll]);

  useEffect(() => {
    if (cancelWindow > 0) {
      setCancelTimer(cancelWindow);
      cancelIntervalRef.current = setInterval(() => {
        setCancelTimer(prev => {
          if (prev <= 1) { clearInterval(cancelIntervalRef.current!); return 0; }
          return prev - 1;
        });
      }, 1000);
    }
    return () => { if (cancelIntervalRef.current) clearInterval(cancelIntervalRef.current); };
  }, [cancelWindow]);

  useEffect(() => {
    if (!jobId) return;
    const poll = setInterval(async () => {
      try {
        const res = await getRebalanceJobStatus(jobId);
        if (res.done || res.cancelled) {
          clearInterval(poll);
          setRebalancing(false); setJobId(null); setCancelWindow(0); setCancelTimer(0);
          if (res.cancelled) toast.warning(tr('cancelledRebalance', lang));
          else { toast.success(tr('successRebalance', lang)); fetchAll(true); }
        }
      } catch { clearInterval(poll); setRebalancing(false); setJobId(null); }
    }, 2000);
    return () => clearInterval(poll);
  }, [jobId, lang, toast, fetchAll]);

  const handleRebalance = async (e: React.MouseEvent<HTMLButtonElement>) => {
    createRipple(e);
    setRebalancing(true);
    try {
      const res = await triggerRebalance();
      setJobId(res.job_id);
      setCancelWindow(res.cancel_window_seconds ?? 5);
      toast.info(
        lang === 'ar' ? 'جاري إعادة التوازن...' : 'Rebalancing...',
        lang === 'ar' ? `يمكنك الإلغاء خلال ${res.cancel_window_seconds} ثانية` : `Cancel within ${res.cancel_window_seconds}s`,
      );
    } catch (err: any) {
      setRebalancing(false);
      toast.error(lang === 'ar' ? 'فشل تنفيذ Rebalance' : 'Rebalance failed', err?.message);
    }
  };

  const handleCancel = async () => {
    if (!jobId) return;
    try {
      await cancelRebalance(jobId);
      setRebalancing(false); setJobId(null); setCancelWindow(0); setCancelTimer(0);
      if (cancelIntervalRef.current) clearInterval(cancelIntervalRef.current);
      toast.warning(tr('cancelledRebalance', lang));
    } catch (err: any) {
      toast.error(lang === 'ar' ? 'فشل الإلغاء' : 'Cancel failed', err?.message);
    }
  };

  const handleBuyAndActivate = async (portfolioId: number) => {
    setShowBuyModal(false);
    setBuyActivating(true);
    try {
      await activatePortfolio(portfolioId);
      const job = await rebalancePortfolio(portfolioId, 'equal');
      let attempts = 0;
      while (attempts < 30) {
        await new Promise(r => setTimeout(r, 2000));
        const s = await getRebalanceJobStatus(job.job_id);
        if (s.done || s.cancelled) break;
        attempts++;
      }
      await startPortfolio(portfolioId);
      setBotRunning(true);
      toast.success(
        lang === 'ar' ? 'تم الشراء والتفعيل' : 'Bought & activated',
        lang === 'ar' ? 'تم شراء العملات وتشغيل المحفظة' : 'Assets purchased and portfolio started'
      );
      fetchAll();
    } catch (err: any) {
      toast.error(lang === 'ar' ? 'فشل الشراء والتفعيل' : 'Buy & activate failed', err?.message);
    } finally {
      setBuyActivating(false);
    }
  };



  const handlePortfolioToggle = async (p: any) => {
    setTogglingLoop(p.id);
    try {
      if (p.running) {
        await stopPortfolio(p.id);
        toast.info(lang === 'ar' ? `تم إيقاف ${p.name}` : `${p.name} stopped`);
      } else {
        await startPortfolio(p.id);
        toast.success(lang === 'ar' ? `تم تشغيل ${p.name}` : `${p.name} started`);
      }
      fetchAll(true);
    } catch (err: any) {
      toast.error(lang === 'ar' ? 'فشل تغيير الحالة' : 'Toggle failed', err?.message);
    } finally {
      setTogglingLoop(null);
    }
  };

  const handlePortfolioRebalance = async (p: any) => {
    setRebalancingPort(p.id);
    try {
      const job = await rebalancePortfolio(p.id, 'market_value');
      let attempts = 0;
      while (attempts < 20) {
        await new Promise(r => setTimeout(r, 2000));
        const s = await getRebalanceJobStatus(job.job_id);
        if (s.done || s.cancelled) break;
        attempts++;
      }
      toast.success(lang === 'ar' ? 'تمت إعادة الموازنة' : 'Rebalance done');
      fetchAll(true);
    } catch (err: any) {
      toast.error(lang === 'ar' ? 'فشلت إعادة الموازنة' : 'Rebalance failed', err?.message);
    } finally {
      setRebalancingPort(null);
    }
  };

  const handleStopAndSell = async (p: any) => {
    setSellingPort(p.id);
    try {
      await stopAndSellPortfolio(p.id);
      toast.info(lang === 'ar' ? 'تم الإيقاف والبيع' : 'Stopped & sold');
      fetchAll(true);
    } catch (err: any) {
      toast.error(lang === 'ar' ? 'فشل الإيقاف والبيع' : 'Stop & sell failed', err?.message);
    } finally {
      setSellingPort(null);
    }
  };

  const handleShowHistory = async (p: any) => {
    try {
      const rows = await getHistory(50);
      const filtered = rows.filter((r: any) => r.portfolio_id === p.id || !r.portfolio_id);
      setHistoryPort({ name: p.name, rows: filtered });
    } catch (err: any) {
      toast.error(lang === 'ar' ? 'فشل تحميل السجل' : 'Failed to load history', err?.message);
    }
  };

  const handleBotToggle = async () => {
    setBotLoading(true);
    try {
      if (botRunning) {
        await stopBot(); setBotRunning(false);
        toast.info(lang === 'ar' ? 'تم إيقاف البوت' : 'Bot stopped');
      } else {
        await startBot(); setBotRunning(true);
        toast.success(lang === 'ar' ? 'تم تشغيل البوت' : 'Bot started');
      }
    } catch (err: any) {
      toast.error(lang === 'ar' ? 'فشل تغيير حالة البوت' : 'Bot toggle failed', err?.message);
    } finally {
      setBotLoading(false);
    }
  };

  const fmtUsd = (n: number) =>
    '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const activePortfolio = portfolios.find(p => p.active) ?? null;

  return (
    <div className="space-y-4">

      {/* Buy & Activate modal */}
      {showBuyModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(12px)' }}
        >
          <div
            className="w-full max-w-md space-y-4 rounded-3xl p-5"
            style={{
              background: 'rgba(15,10,40,0.98)',
              border: '1px solid rgba(123,92,245,0.3)',
              boxShadow: '0 0 60px rgba(123,92,245,0.2)',
            }}
          >
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold" style={{ color: 'var(--text-main)' }}>
                🛒 {lang === 'ar' ? 'اختر المحفظة للشراء والتفعيل' : 'Select Portfolio to Buy & Activate'}
              </h2>
              <button
                onClick={() => setShowBuyModal(false)}
                className="w-7 h-7 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(123,92,245,0.15)', color: 'var(--text-muted)' }}
              >✖</button>
            </div>

            <div className="text-xs rounded-xl px-3 py-2" style={{ background: 'rgba(0,212,170,0.08)', border: '1px solid rgba(0,212,170,0.2)', color: '#00D4AA' }}>
              ℹ️ {lang === 'ar'
                ? 'سيتم تفعيل المحفظة المختارة وشراء العملات وعرض الربح/الخسارة'
                : 'Selected portfolio will be activated, assets purchased, and P&L will be tracked'}
            </div>

            <div className="space-y-2 max-h-64 overflow-y-auto">
              {portfolios.map(p => (
                <button
                  key={p.id}
                  onClick={() => { setSelectedPortId(p.id); handleBuyAndActivate(p.id); }}
                  className="w-full flex items-center justify-between gap-3 px-4 py-3 rounded-2xl text-sm text-start transition-all"
                  style={{
                    background: selectedPortId === p.id ? 'rgba(0,212,170,0.1)' : 'rgba(123,92,245,0.08)',
                    border: `1px solid ${selectedPortId === p.id ? 'rgba(0,212,170,0.4)' : 'rgba(123,92,245,0.2)'}`,
                    color: 'var(--text-main)',
                  }}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-2 h-2 rounded-full shrink-0" style={{ background: p.active ? '#00D4AA' : 'var(--text-muted)' }} />
                    <span className="font-semibold truncate">{p.name}</span>
                    {p.active && (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full shrink-0" style={{ background: 'rgba(0,212,170,0.15)', color: '#00D4AA' }}>
                        {lang === 'ar' ? 'نشطة' : 'Active'}
                      </span>
                    )}
                  </div>
                  <div className="text-end shrink-0">
                    <div className="num text-xs font-bold" style={{ color: '#00D4AA' }}>${p.total_usdt?.toLocaleString('en-US', { maximumFractionDigits: 0 })}</div>
                    <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{p.assets?.length} {lang === 'ar' ? 'عملة' : 'coins'}</div>
                  </div>
                </button>
              ))}
            </div>

            <button onClick={() => setShowBuyModal(false)} className="btn-secondary w-full">
              {lang === 'ar' ? 'إلغاء' : 'Cancel'}
            </button>
          </div>
        </div>
      )}

      {/* ── HERO CARD ─────────────────────────────────────────────────────── */}
      <div className="hero-card p-5 animate-fade-up">
        {/* Top row: LIVE badge + bot name + mode */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="live-badge">
              <span className="w-1.5 h-1.5 rounded-full pulse-dot" style={{ background: '#00D4AA' }} />
              LIVE
            </span>
            <span className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
              {status?.bot_name ?? (lang === 'ar' ? 'My MEXC Portfolio' : 'My MEXC Portfolio')}
              {status?.mode && ` · ${status.mode}`}
            </span>
          </div>
          <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${botRunning ? 'badge-running' : 'badge-stopped'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${botRunning ? 'pulse-dot' : ''}`}
                  style={{ background: botRunning ? '#00D4AA' : 'var(--text-muted)' }} />
            {botRunning ? tr('running', lang) : tr('stopped', lang)}
          </span>
        </div>

        {/* Account total */}
        <div className="mb-1">
          <p className="text-xs font-semibold mb-1" style={{ color: 'var(--text-muted)' }}>
            {lang === 'ar' ? 'إجمالي الحساب' : 'Account Total'}
          </p>
          {loading && accountTotal === null ? (
            <div className="skeleton h-10 w-40 rounded-xl" />
          ) : (
            <div className="flex items-baseline gap-1">
              <span className="font-black text-4xl tracking-tight" style={{ color: 'var(--text-main)', fontFamily: "'JetBrains Mono', monospace" }}>
                ${accountTotal !== null ? Math.floor(accountTotal).toLocaleString('en-US') : '—'}
              </span>
              {accountTotal !== null && (
                <span className="font-bold text-xl" style={{ color: 'rgba(240,238,255,0.6)', fontFamily: "'JetBrains Mono', monospace" }}>
                  .{String(accountTotal.toFixed(2)).split('.')[1]}
                </span>
              )}
            </div>
          )}
        </div>

        {/* ── Balance breakdown 2×2 grid ────────────────────────────────── */}
        {(() => {
          const portfolioVal = status?.total_usdt ?? null;
          const invested     = investedUsdt;
          const activePort   = portfolios.find(p => p.active);
          const portName     = activePort?.name ?? (lang === 'ar' ? 'المحفظة' : 'Portfolio');

          const cells: { label: string; sub: string; value: number | null; color: string; glow: string }[] = [
            {
              label: lang === 'ar' ? 'المستثمر' : 'Invested',
              sub:   portName,
              value: invested,
              color: '#A78BFA',
              glow:  'rgba(167,139,250,0.35)',
            },
            {
              label: lang === 'ar' ? 'قيمة المحفظة' : 'Portfolio',
              sub:   `${status?.assets?.length ?? 0} ${lang === 'ar' ? 'عملة' : 'coins'}`,
              value: portfolioVal,
              color: '#00D4AA',
              glow:  'rgba(0,212,170,0.35)',
            },
            {
              label: lang === 'ar' ? 'الرصيد الحر' : 'Free',
              sub:   lang === 'ar' ? 'متاح للتداول' : 'Available',
              value: freeUsdt,
              color: '#60A5FA',
              glow:  'rgba(96,165,250,0.35)',
            },
            {
              label: lang === 'ar' ? 'المحجوز' : 'Reserved',
              sub:   lang === 'ar' ? 'أوردرات مفتوحة' : 'Open orders',
              value: lockedUsdt,
              color: '#F59E0B',
              glow:  'rgba(245,158,11,0.35)',
            },
          ];

          return (
            <div className="grid grid-cols-2 gap-2 mt-3 mb-4">
              {cells.map((cell, idx) => (
                <div
                  key={idx}
                  className="rounded-2xl px-3 py-2.5 relative overflow-hidden"
                  style={{
                    background: `linear-gradient(135deg, ${cell.color}12 0%, rgba(15,10,40,0.7) 100%)`,
                    border: `1px solid ${cell.color}22`,
                    boxShadow: `inset 0 1px 0 rgba(255,255,255,0.06)`,
                  }}
                >
                  {/* Corner glow */}
                  <div className="absolute top-0 right-0 w-12 h-12 pointer-events-none"
                    style={{ background: `radial-gradient(circle at top right, ${cell.color}20, transparent 70%)` }} />

                  {/* Label */}
                  <p className="text-[10px] font-semibold mb-1 truncate" style={{ color: cell.color, opacity: 0.9 }}>
                    {cell.label}
                  </p>

                  {/* Value */}
                  {loading && cell.value === null ? (
                    <div className="skeleton h-5 w-16 rounded-md mb-1" />
                  ) : (
                    <p
                      className="num font-black leading-none mb-1"
                      style={{
                        fontSize: '1.05rem',
                        letterSpacing: '-0.03em',
                        background: `linear-gradient(135deg, #ffffff 30%, ${cell.color} 100%)`,
                        WebkitBackgroundClip: 'text',
                        WebkitTextFillColor: 'transparent',
                        backgroundClip: 'text',
                        filter: `drop-shadow(0 0 6px ${cell.glow})`,
                      }}
                    >
                      {cell.value !== null ? fmtUsd(cell.value) : '—'}
                    </p>
                  )}

                  {/* Sub */}
                  <p className="text-[9px] truncate" style={{ color: 'var(--text-muted)' }}>
                    {cell.sub}
                  </p>

                  {/* Bottom accent line */}
                  <div className="absolute bottom-0 left-0 right-0 h-px"
                    style={{ background: `linear-gradient(90deg, ${cell.color}40, transparent)` }} />
                </div>
              ))}
            </div>
          );
        })()}

        {/* Progress bar */}
        {investedUsdt !== null && accountTotal !== null && accountTotal > 0 && (
          <div className="mb-4">
            <div className="h-1.5 rounded-full w-full" style={{ background: 'rgba(123,92,245,0.15)' }}>
              <div
                className="h-full rounded-full transition-all duration-1000"
                style={{
                  width: `${Math.min((investedUsdt / accountTotal) * 100, 100)}%`,
                  background: 'linear-gradient(90deg, #00D4AA, #7B5CF5)',
                  boxShadow: '0 0 8px rgba(0,212,170,0.5)',
                }}
              />
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>0%</span>
              <span className="text-[10px] font-semibold" style={{ color: '#00D4AA' }}>
                {accountTotal > 0 ? ((investedUsdt / accountTotal) * 100).toFixed(1) : 0}% {lang === 'ar' ? 'مستثمر' : 'invested'}
              </span>
            </div>
          </div>
        )}

      </div>

      {/* No active portfolio banner */}
      {!loading && !activePortfolio && portfolios.length > 0 && (
        <div
          className="animate-fade-up rounded-2xl px-4 py-3 flex items-center justify-between gap-3 flex-wrap"
          style={{ background: 'rgba(248,197,0,0.08)', border: '1px solid rgba(248,197,0,0.25)', animationDelay: '0.1s' }}
        >
          <div className="flex items-center gap-2 text-sm" style={{ color: '#F8C500' }}>
            ⚠️ <span className="font-semibold">
              {lang === 'ar' ? 'لا توجد محفظة مفعّلة — الربح/الخسارة لن يظهر حتى تفعّل محفظة' : 'No active portfolio — P&L will not show until you activate one'}
            </span>
          </div>
          <button
            onClick={() => setShowBuyModal(true)}
            className="text-xs font-bold px-3 py-1.5 rounded-xl shrink-0"
            style={{ background: 'rgba(248,197,0,0.15)', color: '#F8C500', border: '1px solid rgba(248,197,0,0.3)' }}
          >
            🛒 {lang === 'ar' ? 'شراء وتفعيل' : 'Buy & Activate'}
          </button>
        </div>
      )}

      {/* ── Coin list section removed ── */}
      {false && <div className="animate-fade-up space-y-3" style={{ animationDelay: '0.15s' }}>
        <div className="flex items-center justify-between">
          <h2 className="font-bold text-base" style={{ color: 'var(--text-main)' }}>
            {lang === 'ar' ? 'توزيع العملات' : 'Coin Allocation'}
          </h2>
          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {lang === 'ar' ? 'اضغط لعرض الشارت' : 'Tap to view chart'}
          </span>
        </div>

        {/* Selector bar */}
        {portfolios.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
              {lang === 'ar' ? 'عرض:' : 'View:'}
            </span>

            {/* All button */}
            <button
              onClick={() => { setViewPortId('all'); setShowPortPicker(false); }}
              className="px-3 py-1.5 rounded-xl text-xs font-bold transition-all"
              style={{
                background: viewPortId === 'all' ? 'rgba(123,92,245,0.25)' : 'rgba(123,92,245,0.08)',
                color: viewPortId === 'all' ? '#A78BFA' : 'var(--text-muted)',
                border: `1px solid ${viewPortId === 'all' ? 'rgba(123,92,245,0.5)' : 'rgba(123,92,245,0.15)'}`,
                boxShadow: viewPortId === 'all' ? '0 0 12px rgba(123,92,245,0.2)' : 'none',
              }}
            >
              {lang === 'ar' ? '📂 الجميع' : '📂 All'}
            </button>

            {/* Individual portfolio buttons */}
            {portfolios.map(p => (
              <button
                key={p.id}
                onClick={() => { setViewPortId(p.id); setShowPortPicker(false); }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all"
                style={{
                  background: viewPortId === p.id ? 'rgba(123,92,245,0.25)' : 'rgba(123,92,245,0.08)',
                  color: viewPortId === p.id ? '#A78BFA' : 'var(--text-muted)',
                  border: `1px solid ${viewPortId === p.id ? 'rgba(123,92,245,0.5)' : 'rgba(123,92,245,0.15)'}`,
                  boxShadow: viewPortId === p.id ? '0 0 12px rgba(123,92,245,0.2)' : 'none',
                  maxWidth: 140,
                }}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ background: p.running ? '#00D4AA' : 'var(--text-muted)' }}
                />
                <span className="truncate">{p.name}</span>
              </button>
            ))}
          </div>
        )}

        {/* ── Single portfolio view ── */}
        {viewPortId !== 'all' && (
          <div className="card p-4">
            {(() => {
              const portData = allPortAssets[viewPortId as number];
              const port = portfolios.find(p => p.id === viewPortId);
              const isRunning = portData?.running ?? port?.running ?? false;
              const hasBalance = (freeUsdt ?? 0) > 1;
              return (
                <>
                  <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <h2 className="section-title mb-0">{port?.name ?? tr('assetTable', lang)}</h2>
                      {isRunning && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full animate-pulse"
                          style={{ background: 'rgba(34,197,94,0.15)', color: '#22c55e' }}>
                          ▶ {lang === 'ar' ? 'شغّالة' : 'Running'}
                        </span>
                      )}
                      {portData?.mode && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                          style={{ background: 'var(--bg-input)', color: 'var(--accent)' }}>
                          {portData.mode}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {portData?.total_usdt != null && (
                        <span className="num text-sm font-bold" style={{ color: 'var(--accent)' }}>
                          ${portData.total_usdt.toLocaleString('en-US', { maximumFractionDigits: 2 })}
                        </span>
                      )}
                      <span className="badge" style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
                        {portData?.assets?.length ?? 0} {lang === 'ar' ? 'عملة' : 'coins'}
                      </span>
                    </div>
                  </div>

                  {/* ── Action bar ── */}
                  {port && (
                    <div className="flex gap-1.5 mb-3 flex-wrap">
                      <button
                        onClick={() => { setSelectedPortId(port.id); setShowBuyModal(true); }}
                        disabled={!hasBalance || buyActivating}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all flex-1"
                        style={{
                          background: hasBalance ? 'rgba(0,212,170,0.15)' : 'rgba(255,255,255,0.04)',
                          color: hasBalance ? '#00D4AA' : 'var(--text-muted)',
                          border: `1px solid ${hasBalance ? 'rgba(0,212,170,0.35)' : 'rgba(255,255,255,0.08)'}`,
                          opacity: hasBalance ? 1 : 0.45,
                        }}
                      >
                        <ShoppingCart size={11} />
                        {lang === 'ar' ? 'شراء وتفعيل' : 'Buy & Activate'}
                      </button>
                      <button
                        onClick={() => handleStopAndSell(port)}
                        disabled={!isRunning || sellingPort === port.id}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all flex-1"
                        style={{
                          background: isRunning ? 'rgba(255,123,114,0.15)' : 'rgba(255,255,255,0.04)',
                          color: isRunning ? '#FF7B72' : 'var(--text-muted)',
                          border: `1px solid ${isRunning ? 'rgba(255,123,114,0.35)' : 'rgba(255,255,255,0.08)'}`,
                          opacity: isRunning ? 1 : 0.45,
                        }}
                      >
                        {sellingPort === port.id ? <RefreshCw size={11} className="spin" /> : <Square size={11} />}
                        {lang === 'ar' ? 'إيقاف وبيع' : 'Stop & Sell'}
                      </button>
                      <button
                        onClick={() => handlePortfolioRebalance(port)}
                        disabled={rebalancingPort === port.id}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all flex-1"
                        style={{
                          background: 'rgba(123,92,245,0.15)',
                          color: '#A78BFA',
                          border: '1px solid rgba(123,92,245,0.35)',
                        }}
                      >
                        {rebalancingPort === port.id ? <RefreshCw size={11} className="spin" /> : <Zap size={11} />}
                        {lang === 'ar' ? 'موازنة' : 'Rebalance'}
                      </button>
                      <button
                        onClick={() => handleShowHistory(port)}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all flex-1"
                        style={{
                          background: 'rgba(96,165,250,0.12)',
                          color: '#60A5FA',
                          border: '1px solid rgba(96,165,250,0.25)',
                        }}
                      >
                        <History size={11} />
                        {lang === 'ar' ? 'السجل' : 'History'}
                      </button>
                    </div>
                  )}

                  <AssetsTable
                    assets={portData?.assets ?? []}
                    loading={loadingPortAssets && !portData}
                    lang={lang}
                    onRefresh={() => fetchAll(true)}
                  />
                </>
              );
            })()}
          </div>
        )}

        {/* ── All portfolios view ── */}
        {viewPortId === 'all' && (
          <div className="space-y-4">
            {portfolios.length === 0 ? (
              <div className="card p-4">
                <AssetsTable assets={status?.assets ?? []} loading={loading} lang={lang} onRefresh={() => fetchAll(true)} />
              </div>
            ) : (
              portfolios.map(p => {
                const portData = allPortAssets[p.id];
                const hasBalance = (freeUsdt ?? 0) > 1;
                const isRunning = p.running;
                return (
                  <div key={p.id} className="card p-4"
                    style={isRunning ? { border: '1px solid rgba(0,212,170,0.3)', boxShadow: '0 0 20px rgba(0,212,170,0.08)' } : {}}>
                    {/* Portfolio header */}
                    <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h2 className="section-title mb-0">{p.name}</h2>
                        {isRunning && (
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full animate-pulse"
                            style={{ background: 'rgba(34,197,94,0.15)', color: '#22c55e' }}>
                            ▶ {lang === 'ar' ? 'شغّالة' : 'Running'}
                          </span>
                        )}
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                          style={{ background: 'var(--bg-input)', color: 'var(--accent)' }}>
                          {p.mode}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {portData?.total_usdt != null && (
                          <span className="num text-sm font-bold" style={{ color: 'var(--accent)' }}>
                            ${portData.total_usdt.toLocaleString('en-US', { maximumFractionDigits: 2 })}
                          </span>
                        )}
                        <span className="badge" style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
                          {portData?.assets?.length ?? p.assets?.length ?? 0} {lang === 'ar' ? 'عملة' : 'coins'}
                        </span>
                      </div>
                    </div>

                    {/* ── Action bar ── */}
                    <div className="flex gap-1.5 mb-3 flex-wrap">
                      {/* شراء وتفعيل */}
                      <button
                        onClick={() => { setSelectedPortId(p.id); setShowBuyModal(true); }}
                        disabled={!hasBalance || buyActivating}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all flex-1"
                        style={{
                          background: hasBalance ? 'rgba(0,212,170,0.15)' : 'rgba(255,255,255,0.04)',
                          color: hasBalance ? '#00D4AA' : 'var(--text-muted)',
                          border: `1px solid ${hasBalance ? 'rgba(0,212,170,0.35)' : 'rgba(255,255,255,0.08)'}`,
                          opacity: hasBalance ? 1 : 0.45,
                        }}
                      >
                        <ShoppingCart size={11} />
                        {lang === 'ar' ? 'شراء وتفعيل' : 'Buy & Activate'}
                      </button>

                      {/* إيقاف وبيع */}
                      <button
                        onClick={() => handleStopAndSell(p)}
                        disabled={!isRunning || sellingPort === p.id}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all flex-1"
                        style={{
                          background: isRunning ? 'rgba(255,123,114,0.15)' : 'rgba(255,255,255,0.04)',
                          color: isRunning ? '#FF7B72' : 'var(--text-muted)',
                          border: `1px solid ${isRunning ? 'rgba(255,123,114,0.35)' : 'rgba(255,255,255,0.08)'}`,
                          opacity: isRunning ? 1 : 0.45,
                        }}
                      >
                        {sellingPort === p.id
                          ? <RefreshCw size={11} className="spin" />
                          : <Square size={11} />}
                        {lang === 'ar' ? 'إيقاف وبيع' : 'Stop & Sell'}
                      </button>

                      {/* إعادة موازنة */}
                      <button
                        onClick={() => handlePortfolioRebalance(p)}
                        disabled={rebalancingPort === p.id}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all flex-1"
                        style={{
                          background: 'rgba(123,92,245,0.15)',
                          color: '#A78BFA',
                          border: '1px solid rgba(123,92,245,0.35)',
                        }}
                      >
                        {rebalancingPort === p.id
                          ? <RefreshCw size={11} className="spin" />
                          : <Zap size={11} />}
                        {lang === 'ar' ? 'موازنة' : 'Rebalance'}
                      </button>

                      {/* سجل العمليات */}
                      <button
                        onClick={() => handleShowHistory(p)}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all flex-1"
                        style={{
                          background: 'rgba(96,165,250,0.12)',
                          color: '#60A5FA',
                          border: '1px solid rgba(96,165,250,0.25)',
                        }}
                      >
                        <History size={11} />
                        {lang === 'ar' ? 'السجل' : 'History'}
                      </button>
                    </div>

                    <AssetsTable
                      assets={portData?.assets ?? []}
                      loading={loadingPortAssets && !portData}
                      lang={lang}
                      onRefresh={() => fetchAll(true)}
                    />
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>}

      {/* History modal */}
      {historyPort && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center"
          style={{ background: 'rgba(0,0,0,0.7)' }}
          onClick={() => setHistoryPort(null)}
        >
          <div
            className="w-full max-w-lg rounded-t-3xl p-4 space-y-3 max-h-[70vh] overflow-y-auto"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>
                {lang === 'ar' ? `سجل: ${historyPort.name}` : `History: ${historyPort.name}`}
              </h3>
              <button onClick={() => setHistoryPort(null)} style={{ color: 'var(--text-muted)' }}>
                <XCircle size={18} />
              </button>
            </div>
            {historyPort.rows.length === 0 ? (
              <p className="text-xs text-center py-4" style={{ color: 'var(--text-muted)' }}>
                {lang === 'ar' ? 'لا توجد عمليات' : 'No operations yet'}
              </p>
            ) : (
              historyPort.rows.map((r: any, i: number) => (
                <div key={i} className="rounded-xl px-3 py-2 text-xs flex items-center justify-between gap-2"
                  style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}>
                  <span className="font-bold" style={{ color: r.action === 'buy' ? '#00D4AA' : '#FF7B72' }}>
                    {r.action?.toUpperCase()} {r.symbol}
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>{r.qty ?? ''}</span>
                  <span style={{ color: 'var(--text-muted)' }}>{r.timestamp ? new Date(r.timestamp).toLocaleDateString() : ''}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-center gap-2 pb-2">
        {refreshing
          ? <RefreshCw size={11} className="spin" style={{ color: 'var(--text-muted)' }} />
          : <CheckCircle2 size={11} style={{ color: 'var(--accent)' }} />
        }
        <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
          {refreshing
            ? (lang === 'ar' ? 'جاري التحديث...' : 'Refreshing...')
            : (lang === 'ar' ? 'تحديث تلقائي كل 15 ثانية' : 'Auto-refresh every 15s')}
        </span>
      </div>
    </div>
  );
}
