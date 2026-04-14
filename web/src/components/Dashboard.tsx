'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  DollarSign, Wallet, TrendingUp, TrendingDown,
  Play, Square, RefreshCw, Zap,
  CheckCircle2, XCircle,
} from 'lucide-react';
import {
  getStatus, getBotStatus,
  startBot, stopBot, triggerRebalance, cancelRebalance,
  getRebalanceJobStatus, getAccountTotal, getConfig,
  listPortfolios, activatePortfolio, rebalancePortfolio, startPortfolio,
  stopPortfolio, getPortfolioAssets,
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
      getAccountTotal().then(r => setAccountTotal(r.total_usdt)).catch(() => {});
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
    <div className="space-y-5">

      {/* Buy & Activate modal */}
      {showBuyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
          <div className="card w-full max-w-md space-y-4" style={{ background: 'var(--bg-card)' }}>
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold" style={{ color: 'var(--text-main)' }}>
                🛒 {lang === 'ar' ? 'اختر المحفظة للشراء والتفعيل' : 'Select Portfolio to Buy & Activate'}
              </h2>
              <button onClick={() => setShowBuyModal(false)} className="text-xl" style={{ color: 'var(--text-muted)' }}>✖</button>
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
                  className="w-full flex items-center justify-between gap-3 px-4 py-3 rounded-xl text-sm text-start transition-all"
                  style={{
                    background: selectedPortId === p.id ? 'rgba(0,212,170,0.1)' : 'var(--bg-input)',
                    border: `1px solid ${selectedPortId === p.id ? 'rgba(0,212,170,0.4)' : 'var(--border)'}`,
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
                    <div className="num text-xs font-bold" style={{ color: 'var(--accent)' }}>${p.total_usdt?.toLocaleString('en-US', { maximumFractionDigits: 0 })}</div>
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

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 animate-fade-up">
        <div>
          <h1 className="font-bold text-xl" style={{ color: 'var(--text-main)' }}>
            {status?.bot_name ?? (lang === 'ar' ? 'لوحة التحكم' : 'Dashboard')}
          </h1>
          <p className="text-xs mt-1 flex items-center gap-2 flex-wrap" style={{ color: 'var(--text-muted)' }}>
            {lang === 'ar' ? 'MEXC Spot · محفظة ذكية' : 'MEXC Spot · Smart Portfolio'}
            {status?.mode && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold"
                    style={{ background: 'var(--bg-input)', color: 'var(--accent)' }}>
                {status.mode}
              </span>
            )}
            <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${botRunning ? 'badge-running' : 'badge-stopped'}`}>
              <span className="w-1.5 h-1.5 rounded-full inline-block"
                    style={{ background: botRunning ? 'var(--accent)' : '#8B949E' }} />
              {botRunning ? tr('running', lang) : tr('stopped', lang)}
            </span>
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setShowBuyModal(true)}
            disabled={buyActivating || portfolios.length === 0}
            className="btn-secondary !px-3 !min-h-[36px] !text-xs gap-1.5"
            style={{ borderColor: '#00D4AA', color: '#00D4AA' }}
          >
            {buyActivating
              ? <><RefreshCw size={12} className="spin" /> {lang === 'ar' ? 'جاري...' : 'Working...'}</>
              : <>{lang === 'ar' ? '🛒 شراء وتفعيل' : '🛒 Buy & Activate'}</>
            }
          </button>

          <button
            onClick={handleBotToggle}
            disabled={botLoading}
            className={botRunning ? 'btn-danger !px-3 !min-h-[36px] !text-xs' : 'btn-secondary !px-3 !min-h-[36px] !text-xs'}
          >
            {botLoading
              ? <RefreshCw size={12} className="spin" />
              : botRunning
                ? <><Square size={12} /> {tr('pause', lang)}</>
                : <><Play size={12} /> {tr('start', lang)}</>
            }
          </button>

          {rebalancing && cancelTimer > 0 ? (
            <button onClick={handleCancel} className="btn-danger !px-3 !min-h-[36px] !text-xs relative overflow-hidden">
              <XCircle size={12} /> {tr('cancelRebalance', lang)} ({cancelTimer}s)
            </button>
          ) : rebalancing ? (
            <button disabled className="btn-accent !px-3 !min-h-[36px] !text-xs">
              <RefreshCw size={12} className="spin" /> {lang === 'ar' ? 'جاري...' : 'Running...'}
            </button>
          ) : (
            <button onClick={handleRebalance} className="btn-accent !px-3 !min-h-[36px] !text-xs relative overflow-hidden">
              <Zap size={12} /> {tr('rebalanceNow', lang)}
            </button>
          )}
        </div>
      </div>

      {/* Stat Cards — 2 columns */}
      <div className="grid grid-cols-2 gap-3 animate-fade-up" style={{ animationDelay: '0.05s' }}>
        <StatCard
          title={lang === 'ar' ? 'إجمالي الحساب' : 'Account Total'}
          value={accountTotal === null ? '—' : fmtUsd(accountTotal)}
          change={lang === 'ar' ? 'كل الأصول على MEXC' : 'All MEXC assets'}
          changePositive={null}
          icon={DollarSign} iconColor="#58A6FF"
          loading={loading && accountTotal === null}
          delay={0}
        />
        <StatCard
          title={lang === 'ar' ? 'قيمة المحفظة' : 'Portfolio Value'}
          value={status?.total_usdt == null ? '—' : fmtUsd(status.total_usdt)}
          change={lang === 'ar'
            ? `${status?.assets?.length ?? 0} عملة مخصصة`
            : `${status?.assets?.length ?? 0} tracked coins`}
          changePositive={null}
          icon={Wallet} iconColor="#00D4AA"
          loading={loading}
          delay={0.05}
        />
      </div>

      {/* P&L Card */}
      {(() => {
        // P&L = portfolio value (tracked coins only) minus the configured invested amount
        const current  = status?.total_usdt ?? null;
        const invested = investedUsdt;
        const pnl      = current !== null && invested !== null && invested > 0 ? current - invested : null;
        const pnlPct   = pnl !== null && invested && invested > 0 ? (pnl / invested) * 100 : null;
        const isProfit = pnl !== null && pnl >= 0;
        const pnlColor = isProfit ? '#00D4AA' : '#FF7B72';
        const pnlBg    = isProfit ? 'rgba(0,212,170,0.08)' : 'rgba(255,123,114,0.08)';
        const pnlBorder= isProfit ? 'rgba(0,212,170,0.2)'  : 'rgba(255,123,114,0.2)';

        return (
          <div
            className="animate-fade-up rounded-2xl overflow-hidden"
            style={{ animationDelay: '0.08s', border: `1px solid ${pnl !== null ? pnlBorder : 'var(--border)'}`, background: 'var(--bg-card)' }}
          >
            {/* Top accent bar */}
            {pnl !== null && (
              <div className="h-0.5 w-full" style={{ background: `linear-gradient(90deg, ${pnlColor}, transparent)` }} />
            )}

            <div className="p-4">
              {/* Row: labels */}
              <div className="flex items-center justify-between mb-3">
                <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                  {lang === 'ar' ? 'المبلغ المستثمر' : 'Invested'}
                </span>
                <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                  {lang === 'ar' ? 'الربح / الخسارة' : 'P&L'}
                </span>
              </div>

              {/* Row: values */}
              <div className="flex items-center justify-between gap-3">
                {/* Invested value */}
                {loading ? (
                  <div className="skeleton h-7 w-24 rounded-lg" />
                ) : (
                  <div>
                    <span className="num font-bold text-xl" style={{ color: 'var(--text-main)' }}>
                      {invested !== null ? fmtUsd(invested) : '—'}
                    </span>
                    <p className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                      {lang === 'ar' ? 'رأس المال' : 'Capital'}
                    </p>
                  </div>
                )}

                {/* Arrow divider */}
                <div className="flex items-center gap-1 shrink-0" style={{ color: 'var(--border)' }}>
                  <div className="h-px w-6" style={{ background: 'var(--border)' }} />
                  <div className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--border)' }} />
                </div>

                {/* P&L value */}
                {loading ? (
                  <div className="skeleton h-7 w-28 rounded-lg" />
                ) : pnl !== null ? (
                  <div
                    className="flex items-center gap-2 px-3 py-2 rounded-xl"
                    style={{ background: pnlBg, border: `1px solid ${pnlBorder}` }}
                  >
                    <div
                      className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                      style={{ background: `${pnlColor}22` }}
                    >
                      {isProfit
                        ? <TrendingUp  size={14} style={{ color: pnlColor }} />
                        : <TrendingDown size={14} style={{ color: pnlColor }} />
                      }
                    </div>
                    <div>
                      <p className="num font-bold text-base leading-tight" style={{ color: pnlColor }}>
                        {isProfit ? '+' : ''}{fmtUsd(pnl)}
                      </p>
                      {pnlPct !== null && (
                        <p className="num text-[11px] font-semibold leading-tight" style={{ color: pnlColor }}>
                          {isProfit ? '+' : ''}{pnlPct.toFixed(2)}%
                        </p>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="px-3 py-2 rounded-xl text-end" style={{ background: 'var(--bg-input)' }}>
                    <p className="num text-base font-bold" style={{ color: 'var(--text-muted)' }}>—</p>
                    <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                      {lang === 'ar' ? 'فعّل محفظة لعرض الربح/الخسارة' : 'Activate a portfolio to see P&L'}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })()}

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

      {/* Portfolio view selector + Assets */}
      <div className="animate-fade-up space-y-3" style={{ animationDelay: '0.15s' }}>

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
                background: viewPortId === 'all' ? 'var(--brand)' : 'var(--bg-input)',
                color: viewPortId === 'all' ? '#000' : 'var(--text-muted)',
                border: `1px solid ${viewPortId === 'all' ? 'var(--brand)' : 'var(--border)'}`,
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
                  background: viewPortId === p.id ? 'var(--brand)' : 'var(--bg-input)',
                  color: viewPortId === p.id ? '#000' : 'var(--text-muted)',
                  border: `1px solid ${viewPortId === p.id ? 'var(--brand)' : 'var(--border)'}`,
                  maxWidth: 140,
                }}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ background: p.running ? '#22c55e' : 'var(--text-muted)' }}
                />
                <span className="truncate">{p.name}</span>
              </button>
            ))}
          </div>
        )}

        {/* ── Single portfolio view ── */}
        {viewPortId !== 'all' && (
          <div className="card p-5">
            {(() => {
              const portData = allPortAssets[viewPortId as number];
              const port = portfolios.find(p => p.id === viewPortId);
              return (
                <>
                  <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <h2 className="section-title mb-0">{port?.name ?? tr('assetTable', lang)}</h2>
                      {portData?.running && (
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
                      {/* Start / Stop toggle */}
                      {port && (
                        <button
                          onClick={() => handlePortfolioToggle(portData ?? port)}
                          disabled={togglingLoop === (viewPortId as number)}
                          className={`flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                            portData?.running ? 'bg-gray-700 text-gray-200' : 'btn-primary'
                          }`}
                        >
                          {togglingLoop === viewPortId
                            ? <RefreshCw size={11} className="spin" />
                            : portData?.running
                              ? <><Square size={11} /> {lang === 'ar' ? 'إيقاف' : 'Stop'}</>
                              : <><Play size={11} /> {lang === 'ar' ? 'تشغيل' : 'Start'}</>
                          }
                        </button>
                      )}
                      <span className="badge" style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
                        {portData?.assets?.length ?? 0} {lang === 'ar' ? 'عملة' : 'coins'}
                      </span>
                    </div>
                  </div>
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
              <div className="card p-5">
                <AssetsTable assets={status?.assets ?? []} loading={loading} lang={lang} onRefresh={() => fetchAll(true)} />
              </div>
            ) : (
              portfolios.map(p => {
                const portData = allPortAssets[p.id];
                return (
                  <div key={p.id} className="card p-5"
                    style={p.running ? { border: '1px solid rgba(34,197,94,0.35)' } : {}}>
                    {/* Portfolio header */}
                    <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h2 className="section-title mb-0">{p.name}</h2>
                        {p.running && (
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
                        {/* Start / Stop toggle */}
                        <button
                          onClick={() => handlePortfolioToggle(portData ?? p)}
                          disabled={togglingLoop === p.id}
                          className={`flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                            p.running ? 'bg-gray-700 text-gray-200' : 'btn-primary'
                          }`}
                        >
                          {togglingLoop === p.id
                            ? <RefreshCw size={11} className="spin" />
                            : p.running
                              ? <><Square size={11} /> {lang === 'ar' ? 'إيقاف' : 'Stop'}</>
                              : <><Play size={11} /> {lang === 'ar' ? 'تشغيل' : 'Start'}</>
                          }
                        </button>
                        <span className="badge" style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
                          {portData?.assets?.length ?? p.assets?.length ?? 0} {lang === 'ar' ? 'عملة' : 'coins'}
                        </span>
                      </div>
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
      </div>

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
