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
  getRebalanceJobStatus, getAccountTotal,
  listPortfolios, activatePortfolio, rebalancePortfolio, startPortfolio,
  stopPortfolio, getPortfolioAssets, stopAndSellPortfolio, getHistory,
} from '../lib/api';
import { Lang, tr } from '../lib/i18n';
import { useToast } from './Toast';

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
