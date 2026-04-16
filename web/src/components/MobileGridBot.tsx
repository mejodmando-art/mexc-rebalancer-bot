'use client';

import { useState, useEffect, useCallback } from 'react';
import { Lang } from '../lib/i18n';
import {
  listGridBots, stopGridBot, resumeGridBot, deleteGridBot, getGridOrders,
} from '../lib/api';

interface Props { lang: Lang; }

// ── Sub-components ────────────────────────────────────────────────────────────

function PulsingDot({ color }: { color: string }) {
  return (
    <span className="relative flex h-2.5 w-2.5">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: color }} />
      <span className="relative inline-flex rounded-full h-2.5 w-2.5" style={{ background: color }} />
    </span>
  );
}

function RangeBar({ low, high, current }: { low: number; high: number; current: number }) {
  const pct = high > low ? Math.min(Math.max(((current - low) / (high - low)) * 100, 0), 100) : 50;
  return (
    <div className="mgb-range-wrap">
      <div className="mgb-range-track">
        <div className="mgb-range-fill" style={{ width: `${pct}%` }} />
        <div className="mgb-range-thumb" style={{ left: `${pct}%` }}>
          <span className="mgb-range-price">${(current / 1000).toFixed(1)}K</span>
        </div>
      </div>
      <div className="mgb-range-labels">
        <span>${(low / 1000).toFixed(0)}K</span>
        <span>${(high / 1000).toFixed(0)}K</span>
      </div>
    </div>
  );
}

function GridLadderChart({ low, high, current, gridCount }: { low: number; high: number; current: number; gridCount: number }) {
  const W = 360; const H = 180;
  const pad = { t: 12, b: 12, l: 8, r: 8 };
  const innerH = H - pad.t - pad.b;
  const innerW = W - pad.l - pad.r;

  // price → y (inverted: high price = top)
  const py = (p: number) => pad.t + ((high - p) / (high - low)) * innerH;
  // x positions for area chart (fake wave)
  const pts = Array.from({ length: 9 }, (_, i) => {
    const x = pad.l + (i / 8) * innerW;
    const noise = Math.sin(i * 1.3) * 0.04;
    const mid = (low + high) / 2;
    const y = py(mid + (high - low) * noise);
    return `${x},${y}`;
  });
  const areaPath = `M${pts[0]} L${pts.slice(1).join(' L')} L${pad.l + innerW},${H - pad.b} L${pad.l},${H - pad.b} Z`;
  const linePath = `M${pts[0]} L${pts.slice(1).join(' L')}`;

  // grid levels
  const levels = Array.from({ length: gridCount }, (_, i) => low + (i / (gridCount - 1)) * (high - low));
  const curY = py(current);
  const buyLevels  = levels.filter(p => p < current).slice(-5);
  const sellLevels = levels.filter(p => p > current).slice(0, 3);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mgb-chart-svg" preserveAspectRatio="none">
      <defs>
        <linearGradient id="mgb-area-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#00F5D4" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#00F5D4" stopOpacity="0.01" />
        </linearGradient>
        <filter id="mgb-glow">
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      {/* area fill */}
      <path d={areaPath} fill="url(#mgb-area-grad)" />
      {/* area line */}
      <path d={linePath} fill="none" stroke="#00F5D4" strokeWidth="1.5" strokeLinejoin="round" />

      {/* BUY dashed levels */}
      {buyLevels.map((p, i) => (
        <line key={`b${i}`} x1={pad.l} y1={py(p)} x2={pad.l + innerW} y2={py(p)}
          stroke="#00E676" strokeWidth="1" strokeDasharray="4 3" opacity="0.7" />
      ))}
      {/* SELL dashed levels */}
      {sellLevels.map((p, i) => (
        <line key={`s${i}`} x1={pad.l} y1={py(p)} x2={pad.l + innerW} y2={py(p)}
          stroke="#FF5252" strokeWidth="1" strokeDasharray="4 3" opacity="0.7" />
      ))}

      {/* current price line */}
      <line x1={pad.l} y1={curY} x2={pad.l + innerW} y2={curY}
        stroke="#00F5D4" strokeWidth="1.5" filter="url(#mgb-glow)" />
      {/* pulsing dot */}
      <circle cx={pad.l + innerW * 0.72} cy={curY} r="5" fill="#00F5D4" opacity="0.25">
        <animate attributeName="r" values="5;9;5" dur="2s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.25;0;0.25" dur="2s" repeatCount="indefinite" />
      </circle>
      <circle cx={pad.l + innerW * 0.72} cy={curY} r="3.5" fill="#00F5D4" filter="url(#mgb-glow)" />

      {/* legend */}
      <g transform={`translate(${pad.l + 6}, ${pad.t + 6})`}>
        <line x1="0" y1="5" x2="14" y2="5" stroke="#00E676" strokeWidth="1.5" strokeDasharray="4 3" />
        <text x="18" y="9" fill="#00E676" fontSize="9" fontFamily="JetBrains Mono">BUY</text>
        <line x1="44" y1="5" x2="58" y2="5" stroke="#FF5252" strokeWidth="1.5" strokeDasharray="4 3" />
        <text x="62" y="9" fill="#FF5252" fontSize="9" fontFamily="JetBrains Mono">SELL</text>
      </g>
    </svg>
  );
}

function PnlRing({ pct }: { pct: number }) {
  const r = 28; const circ = 2 * Math.PI * r;
  const clamped = Math.min(Math.max(pct, 0), 100);
  const dash = (clamped / 100) * circ;
  return (
    <svg width="72" height="72" viewBox="0 0 72 72">
      <circle cx="36" cy="36" r={r} fill="none" stroke="rgba(0,245,212,0.1)" strokeWidth="6" />
      <circle cx="36" cy="36" r={r} fill="none" stroke="#00F5D4" strokeWidth="6"
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
        transform="rotate(-90 36 36)" />
      <text x="36" y="40" textAnchor="middle" fill="#00F5D4"
        fontSize="13" fontFamily="JetBrains Mono" fontWeight="600">
        {clamped.toFixed(0)}%
      </text>
    </svg>
  );
}

function RiskBar({ value, max }: { value: number; max: number }) {
  const pct = Math.min((value / max) * 100, 100);
  const color = pct > 80 ? '#FF5252' : pct > 50 ? '#FF9800' : '#00E676';
  return (
    <div className="mgb-risk-bar-wrap">
      <div className="mgb-risk-track">
        <div className="mgb-risk-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="mgb-risk-labels">
        <span style={{ color }}>{value.toFixed(1)}%</span>
        <span className="mgb-muted">/ {max}%</span>
      </div>
    </div>
  );
}

const STATUS_STYLE: Record<string, { bg: string; color: string }> = {
  open:    { bg: 'rgba(0,230,118,0.12)',  color: '#00E676' },
  filled:  { bg: 'rgba(0,245,212,0.12)',  color: '#00F5D4' },
  partial: { bg: 'rgba(255,152,0,0.12)',  color: '#FF9800' },
  cancelled:{ bg: 'rgba(255,82,82,0.10)', color: '#FF5252' },
};

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLE[status?.toLowerCase()] ?? STATUS_STYLE.open;
  return (
    <span className="mgb-badge" style={{ background: s.bg, color: s.color }}>
      {status}
    </span>
  );
}

function OrdersTable({ orders, ar }: { orders: any[]; ar: boolean }) {
  const cols = ar
    ? ['الجانب', 'السعر', 'الكمية', 'الحالة']
    : ['Side', 'Price', 'Qty', 'Status'];
  return (
    <div className="mgb-orders-wrap">
      <table className="mgb-orders-table">
        <thead>
          <tr>{cols.map(c => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {orders.slice(0, 8).map((o, i) => (
            <tr key={i}>
              <td>
                <span className="mgb-side" style={{ color: o.side === 'BUY' ? '#00E676' : '#FF5252' }}>
                  {o.side}
                </span>
              </td>
              <td className="mgb-mono">${Number(o.price).toLocaleString()}</td>
              <td className="mgb-mono">{Number(o.qty ?? o.quantity ?? 0).toFixed(4)}</td>
              <td><StatusBadge status={o.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BotCard({ bot, lang, onRefresh }: { bot: any; lang: Lang; onRefresh: () => void }) {
  const ar = lang === 'ar';
  const [orders, setOrders]         = useState<any[]>([]);
  const [stopping, setStopping]     = useState(false);
  const [deleting, setDeleting]     = useState(false);
  const [riskOn, setRiskOn]         = useState(true);
  const [showOrders, setShowOrders] = useState(false);

  const isRunning = bot.status === 'running';
  const low       = Number(bot.price_low  ?? 72000);
  const high      = Number(bot.price_high ?? 96000);
  const current   = Number(bot.current_price ?? bot.last_price ?? 84372.5);
  const gridCount = Number(bot.grid_count ?? 24);
  const invested  = Number(bot.investment ?? bot.invested_usdt ?? 1000);
  const realPnl   = Number(bot.realized_pnl   ?? 248.75);
  const unrealPnl = Number(bot.unrealized_pnl ?? 86.20);
  const realPct   = invested > 0 ? (realPnl / invested) * 100 : 12.44;
  const unrealPct = invested > 0 ? (unrealPnl / invested) * 100 : 4.31;
  const utilPct   = Math.min(70, 100);
  const drawdown  = 15;
  const stopLoss  = low;

  useEffect(() => {
    if (!showOrders) return;
    getGridOrders(bot.id).then(setOrders).catch(() => {});
  }, [showOrders, bot.id]);

  const handleStop = async () => {
    setStopping(true);
    try { await stopGridBot(bot.id); onRefresh(); } finally { setStopping(false); }
  };
  const handleResume = async () => {
    setStopping(true);
    try { await resumeGridBot(bot.id); onRefresh(); } finally { setStopping(false); }
  };
  const handleDelete = async () => {
    if (!confirm(ar ? 'حذف البوت؟' : 'Delete this bot?')) return;
    setDeleting(true);
    try { await deleteGridBot(bot.id); onRefresh(); } finally { setDeleting(false); }
  };

  const modeTags = [
    bot.mode === 'infinity' ? (ar ? 'لانهائي' : 'Infinity') : (ar ? 'عادي' : 'Normal'),
    ar ? 'استثمار تلقائي' : 'Auto-Invest',
  ];

  return (
    <div className="mgb-card">

      {/* ── Header: pair + status ── */}
      <div className="mgb-card-header">
        <div className="mgb-pair-block">
          <span className="mgb-pair">{bot.symbol ?? 'BTC/USDT'}</span>
          <div className="mgb-status-pill" style={{ background: isRunning ? 'rgba(0,230,118,0.15)' : 'rgba(255,82,82,0.12)' }}>
            <PulsingDot color={isRunning ? '#00E676' : '#FF5252'} />
            <span style={{ color: isRunning ? '#00E676' : '#FF5252', fontSize: 11, fontWeight: 600 }}>
              {isRunning ? (ar ? 'يعمل' : 'Running') : (ar ? 'متوقف' : 'Stopped')}
            </span>
          </div>
        </div>
        <div className="mgb-price-block">
          <span className="mgb-current-price">${current.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          <span className="mgb-price-change" style={{ color: '#00E676' }}>+2.34%</span>
        </div>
      </div>

      {/* ── Mode tags ── */}
      <div className="mgb-tags">
        {modeTags.map(tag => (
          <span key={tag} className="mgb-tag">{tag}</span>
        ))}
        <span className="mgb-tag mgb-tag-grids">{gridCount} {ar ? 'شبكة' : 'Grids'}</span>
      </div>

      {/* ── Range bar ── */}
      <RangeBar low={low} high={high} current={current} />

      {/* ── PnL cards ── */}
      <div className="mgb-pnl-row">
        <div className="mgb-pnl-card">
          <span className="mgb-pnl-label">{ar ? 'ربح محقق' : 'Realized PnL'}</span>
          <span className="mgb-pnl-value" style={{ color: realPnl >= 0 ? '#00E676' : '#FF5252' }}>
            {realPnl >= 0 ? '+' : ''}${realPnl.toFixed(2)}
          </span>
          <span className="mgb-pnl-pct" style={{ color: realPnl >= 0 ? '#00E676' : '#FF5252' }}>
            ({realPct >= 0 ? '+' : ''}{realPct.toFixed(2)}%)
          </span>
        </div>
        <div className="mgb-pnl-card">
          <span className="mgb-pnl-label">{ar ? 'ربح غير محقق' : 'Unrealized PnL'}</span>
          <span className="mgb-pnl-value" style={{ color: unrealPnl >= 0 ? '#00F5D4' : '#FF5252' }}>
            {unrealPnl >= 0 ? '+' : ''}${unrealPnl.toFixed(2)}
          </span>
          <span className="mgb-pnl-pct" style={{ color: unrealPnl >= 0 ? '#00F5D4' : '#FF5252' }}>
            ({unrealPct >= 0 ? '+' : ''}{unrealPct.toFixed(2)}%)
          </span>
        </div>
        <div className="mgb-pnl-card mgb-pnl-ring-card">
          <span className="mgb-pnl-label">{ar ? 'المستثمر' : 'Invested'}</span>
          <PnlRing pct={utilPct} />
          <span className="mgb-pnl-usdt">${invested.toLocaleString()}</span>
        </div>
      </div>

      {/* ── Orders toggle ── */}
      <button className="mgb-orders-toggle" onClick={() => setShowOrders(v => !v)}>
        <span>{ar ? 'الأوامر النشطة' : 'Active Orders'}</span>
        <span className="mgb-chevron" style={{ transform: showOrders ? 'rotate(180deg)' : 'none' }}>▾</span>
      </button>
      {showOrders && <OrdersTable orders={orders} ar={ar} />}

      {/* ── Quick controls ── */}
      <div className="mgb-controls">
        {isRunning ? (
          <button className="mgb-btn mgb-btn-stop" onClick={handleStop} disabled={stopping}>
            {stopping ? '…' : (ar ? 'إيقاف' : 'Stop')}
          </button>
        ) : (
          <button className="mgb-btn mgb-btn-start" onClick={handleResume} disabled={stopping}>
            {stopping ? '…' : (ar ? 'تشغيل' : 'Start')}
          </button>
        )}
        <button className="mgb-btn mgb-btn-rebuild" onClick={onRefresh}>
          {ar ? 'إعادة بناء' : 'Rebuild'}
        </button>
        <button className="mgb-btn mgb-btn-settings">
          {ar ? 'إعدادات' : 'Settings'}
        </button>
        <button className="mgb-btn mgb-btn-emergency" onClick={handleDelete} disabled={deleting}>
          {deleting ? '…' : (ar ? 'إغلاق طارئ' : 'Emergency Close')}
        </button>
      </div>

      {/* ── Risk management ── */}
      <div className="mgb-risk-section">
        <div className="mgb-risk-header">
          <span className="mgb-section-label">{ar ? 'إدارة المخاطر' : 'Risk Management'}</span>
          <button
            className="mgb-toggle"
            onClick={() => setRiskOn(v => !v)}
            aria-pressed={riskOn}
            style={{ background: riskOn ? '#00F5D4' : 'rgba(255,255,255,0.1)' }}
          >
            <span className="mgb-toggle-thumb" style={{ transform: riskOn ? 'translateX(18px)' : 'translateX(2px)' }} />
          </button>
        </div>
        {riskOn && (
          <div className="mgb-risk-body">
            <div className="mgb-risk-row">
              <span className="mgb-muted">{ar ? 'الحد الأقصى للخسارة' : 'Max Drawdown'}</span>
              <RiskBar value={drawdown} max={20} />
            </div>
            <div className="mgb-risk-row">
              <span className="mgb-muted">{ar ? 'وقف الخسارة' : 'Stop-Loss'}</span>
              <span className="mgb-mono" style={{ color: '#FF9800' }}>${stopLoss.toLocaleString()}</span>
            </div>
          </div>
        )}
      </div>

    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function MobileGridBot({ lang }: Props) {
  const ar = lang === 'ar';
  const [bots, setBots]       = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    try {
      const data = await listGridBots();
      setBots(data);
    } catch { /* ignore */ } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(() => load(), 15000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="mgb-root" dir={ar ? 'rtl' : 'ltr'}>
      <div className="mgb-page-header">
        <h2 className="mgb-page-title">{ar ? 'بوت الشبكات' : 'Grid Bot'}</h2>
        <button className="mgb-refresh-btn" onClick={() => load(true)} disabled={refreshing}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
            strokeLinecap="round" strokeLinejoin="round"
            style={{ animation: refreshing ? 'mgb-spin 0.8s linear infinite' : 'none' }}>
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
          {ar ? 'تحديث' : 'Refresh'}
        </button>
      </div>

      {loading ? (
        <div className="mgb-loading">
          <div className="mgb-spinner" />
          <span>{ar ? 'جاري التحميل…' : 'Loading…'}</span>
        </div>
      ) : bots.length === 0 ? (
        <div className="mgb-empty">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="rgba(0,245,212,0.3)" strokeWidth="1.5">
            <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" />
          </svg>
          <span>{ar ? 'لا توجد بوتات شبكة نشطة' : 'No active grid bots'}</span>
        </div>
      ) : (
        bots.map(b => <BotCard key={b.id} bot={b} lang={lang} onRefresh={() => load()} />)
      )}
    </div>
  );
}
