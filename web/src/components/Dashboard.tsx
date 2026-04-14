'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  DollarSign, Layers,
  Play, Square, RefreshCw, Zap, Timer,
  CheckCircle2, XCircle,
} from 'lucide-react';
import {
  getStatus, getBotStatus,
  startBot, stopBot, triggerRebalance, cancelRebalance,
  getRebalanceJobStatus, getAccountTotal,
} from '../lib/api';
import { Lang, tr } from '../lib/i18n';
import { useToast } from './Toast';
import StatCard from './StatCard';
import PortfolioPieChart from './PortfolioPieChart';
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
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const autoRefreshRef = useRef(autoRefresh);
  autoRefreshRef.current = autoRefresh;

  const [rebalancing,  setRebalancing]  = useState(false);
  const [jobId,        setJobId]        = useState<string | null>(null);
  const [cancelWindow, setCancelWindow] = useState(0);
  const [cancelTimer,  setCancelTimer]  = useState(0);
  const cancelIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [botLoading, setBotLoading] = useState(false);

  const fetchAll = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const [s, bot] = await Promise.all([
        getStatus(), getBotStatus(),
      ]);
      setStatus(s);
      setBotRunning(bot?.running ?? false);
      // Fetch full account total separately (non-blocking)
      getAccountTotal().then(r => setAccountTotal(r.total_usdt)).catch(() => {});
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



  return (
    <div className="space-y-6">

      {/* Top action bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 animate-fade-up">
        <div>
          <h1 className="font-bold text-xl" style={{ color: 'var(--text-main)' }}>
            {status?.bot_name ?? (lang === 'ar' ? 'لوحة التحكم' : 'Dashboard')}
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {lang === 'ar' ? 'MEXC Spot · محفظة ذكية' : 'MEXC Spot · Smart Portfolio'}
            {status?.mode && (
              <span className="ms-2 px-1.5 py-0.5 rounded text-[10px] font-semibold"
                    style={{ background: 'var(--bg-input)', color: 'var(--accent)' }}>
                {status.mode}
              </span>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Auto-refresh toggle */}
          <button
            onClick={() => setAutoRefresh(v => !v)}
            className="btn-secondary !px-3 !min-h-[36px] !text-xs gap-1.5"
          >
            <Timer size={13} style={{ color: autoRefresh ? 'var(--accent)' : 'var(--text-muted)' }} />
            <span style={{ color: autoRefresh ? 'var(--accent)' : 'var(--text-muted)' }}>
              {autoRefresh ? '30s' : lang === 'ar' ? 'متوقف' : 'Off'}
            </span>
          </button>

          {/* Manual refresh */}
          <button onClick={() => fetchAll(true)} disabled={refreshing} className="btn-secondary !px-3 !min-h-[36px]">
            <RefreshCw size={14} className={refreshing ? 'spin' : ''} />
          </button>

          {/* Bot start/stop */}
          <button
            onClick={handleBotToggle}
            disabled={botLoading}
            className={botRunning ? 'btn-danger !px-4 !min-h-[36px] !text-xs' : 'btn-secondary !px-4 !min-h-[36px] !text-xs'}
          >
            {botLoading
              ? <RefreshCw size={13} className="spin" />
              : botRunning
                ? <><Square size={13} /> {tr('pause', lang)}</>
                : <><Play size={13} /> {tr('start', lang)}</>
            }
          </button>

          {/* Rebalance button */}
          {rebalancing && cancelTimer > 0 ? (
            <button onClick={handleCancel} className="btn-danger !px-4 !min-h-[36px] !text-xs relative overflow-hidden">
              <XCircle size={13} />
              {tr('cancelRebalance', lang)} ({cancelTimer}s)
            </button>
          ) : rebalancing ? (
            <button disabled className="btn-accent !px-4 !min-h-[36px] !text-xs">
              <RefreshCw size={13} className="spin" />
              {lang === 'ar' ? 'جاري...' : 'Running...'}
            </button>
          ) : (
            <button
              onClick={handleRebalance}
              className="btn-accent !px-4 !min-h-[36px] !text-xs relative overflow-hidden"
            >
              <Zap size={13} />
              {tr('rebalanceNow', lang)}
            </button>
          )}
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4">
        <StatCard
          title={lang === 'ar' ? 'إجمالي الحساب' : 'Account Total'}
          value={accountTotal === null ? '—' : `$${accountTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          change={lang === 'ar' ? 'كل الأصول على MEXC' : 'All MEXC assets'}
          changePositive={null}
          icon={DollarSign} iconColor="#58A6FF"
          loading={loading && accountTotal === null} delay={0}
        />
        <StatCard
          title={tr('totalPortfolio', lang)}
          value={loading ? '—' : `$${(status?.total_usdt ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          change={loading ? undefined : `${(status?.assets?.length ?? 0)} ${tr('currency', lang)}`}
          changePositive={null}
          icon={Layers} iconColor="#A78BFA"
          loading={loading} delay={0.05}
        />
      </div>

      {/* Charts row */}
      <div className="card p-5 animate-fade-up" style={{ animationDelay: '0.2s' }}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="section-title">{tr('assetDist', lang)}</h2>
        </div>
        <PortfolioPieChart
          assets={status?.assets ?? []}
          totalUsdt={status?.total_usdt ?? 0}
          loading={loading} lang={lang}
        />
      </div>

      {/* Assets table */}
      <div className="card p-5 animate-fade-up" style={{ animationDelay: '0.3s' }}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="section-title">{tr('assetTable', lang)}</h2>
          {!loading && status?.assets?.length ? (
            <span className="badge" style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
              {status.assets.length} {lang === 'ar' ? 'عملة' : 'coins'}
            </span>
          ) : null}
        </div>
        <AssetsTable assets={status?.assets ?? []} loading={loading} lang={lang} />
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
            : (lang === 'ar' ? `تحديث تلقائي كل 30 ثانية${autoRefresh ? '' : ' (متوقف)'}` : `Auto-refresh every 30s${autoRefresh ? '' : ' (paused)'}`)}
        </span>
      </div>
    </div>
  );
}
