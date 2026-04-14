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
  const [botLoading,    setBotLoading]    = useState(false);
  const [buyActivating, setBuyActivating] = useState(false);
  const [investedUsdt,  setInvestedUsdt]  = useState<number | null>(null);

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
    } catch (err: any) {
      if (!silent) toast.error(tr('errLoad', lang), err?.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [lang, toast]);

  useEffect(() => { fetchAll(); }, [fetchAll]);
  useEffect(() => {
    const t = setInterval(() => { if (autoRefreshRef.current) fetchAll(true); }, 30000);
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

  const handleBuyAndActivate = async () => {
    setBuyActivating(true);
    try {
      const portfolios = await listPortfolios();
      const active = portfolios.find((p: any) => p.active) ?? portfolios[0];
      if (!active) throw new Error(lang === 'ar' ? 'لا توجد محفظة' : 'No portfolio found');
      await activatePortfolio(active.id);
      const job = await rebalancePortfolio(active.id, 'equal');
      let attempts = 0;
      while (attempts < 30) {
        await new Promise(r => setTimeout(r, 2000));
        const s = await getRebalanceJobStatus(job.job_id);
        if (s.done || s.cancelled) break;
        attempts++;
      }
      await startPortfolio(active.id);
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

  return (
    <div className="space-y-5">

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
            onClick={handleBuyAndActivate}
            disabled={buyActivating}
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
                  <div className="px-3 py-2 rounded-xl" style={{ background: 'var(--bg-input)' }}>
                    <p className="num text-base font-bold" style={{ color: 'var(--text-muted)' }}>—</p>
                    <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                      {lang === 'ar' ? 'لا يوجد مبلغ مستثمر' : 'No invested amount set'}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })()}

      {/* Assets table */}
      <div className="card p-5 animate-fade-up" style={{ animationDelay: '0.15s' }}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="section-title">{tr('assetTable', lang)}</h2>
          {!loading && status?.assets?.length ? (
            <span className="badge" style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
              {status.assets.length} {lang === 'ar' ? 'عملة' : 'coins'}
            </span>
          ) : null}
        </div>
        <AssetsTable assets={status?.assets ?? []} loading={loading} lang={lang} onRefresh={() => fetchAll(true)} />
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
            : (lang === 'ar' ? 'تحديث تلقائي كل 30 ثانية' : 'Auto-refresh every 30s')}
        </span>
      </div>
    </div>
  );
}
