'use client';

import { useState, useEffect, useCallback } from 'react';
import { Lang } from '../lib/i18n';
import { listGridBots, stopGridBot, resumeGridBot, deleteGridBot, getGridOrders } from '../lib/api';

interface Props { lang: Lang; }

function fmt(n: number) {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function RangeBar({ low, high, current }: { low: number; high: number; current: number }) {
  const pct = high > low ? Math.min(Math.max(((current - low) / (high - low)) * 100, 0), 100) : 50;
  return (
    <div className="mgb2-range-wrap">
      <div className="mgb2-range-header">
        <span className="mgb2-label-sm">24 Grids</span>
        <span className="mgb2-label-sm mgb2-muted">نطاق الشبكة <span className="mgb2-muted-en">Grid Range</span></span>
      </div>
      <div className="mgb2-range-track">
        <div className="mgb2-range-fill" style={{ width: `${pct}%` }} />
        <div className="mgb2-range-thumb" style={{ left: `${pct}%` }} />
      </div>
      <div className="mgb2-range-labels">
        <span className="mgb2-range-low">▼ {low.toLocaleString()}</span>
        <span className="mgb2-range-cur">⁚ {Math.round(current).toLocaleString()}</span>
        <span className="mgb2-range-high">▲ {high.toLocaleString()}</span>
      </div>
      <div className="mgb2-grid-stats">
        <div className="mgb2-grid-stat">
          <span className="mgb2-stat-label">فجوة الشبكة <span className="mgb2-muted-en">Grid Gap</span></span>
          <span className="mgb2-stat-val mgb2-orange">1.04%</span>
        </div>
        <div className="mgb2-grid-stat">
          <span className="mgb2-stat-label">عدد الشبكات <span className="mgb2-muted-en">Grid Count</span></span>
          <span className="mgb2-stat-val">24</span>
        </div>
        <div className="mgb2-grid-stat">
          <span className="mgb2-stat-label">نطاق السعر <span className="mgb2-muted-en">Price Range</span></span>
          <span className="mgb2-stat-val mgb2-green">$24,000</span>
        </div>
      </div>
    </div>
  );
}

function GridChart({ low, high, current, gridCount }: { low: number; high: number; current: number; gridCount: number }) {
  const W = 340; const H = 160;
  const pl = 28; const pr = 16; const pt = 12; const pb = 12;
  const iW = W - pl - pr; const iH = H - pt - pb;
  const py = (p: number) => pt + ((high - p) / (high - low)) * iH;
  const levels = Array.from({ length: gridCount }, (_, i) => low + (i / (gridCount - 1)) * (high - low));
  const buyLevels  = levels.filter(p => p < current).slice(-5);
  const sellLevels = levels.filter(p => p > current).slice(0, 3);
  const curY = py(current);
  // wave path
  const wpts = Array.from({ length: 10 }, (_, i) => {
    const x = pl + (i / 9) * iW;
    const base = low + ((current - low) * i) / 9;
    const noise = Math.sin(i * 1.1) * (high - low) * 0.03;
    return [x, py(base + noise)] as [number, number];
  });
  const linePath = wpts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ');
  const areaPath = `${linePath} L${pl + iW},${pt + iH} L${pl},${pt + iH} Z`;
  // y-axis price labels
  const yLabels = [high, (high + current) / 2, current, (current + low) / 2, low];

  return (
    <div className="mgb2-chart-outer">
      <div className="mgb2-chart-header">
        <span className="mgb2-live-dot" />
        <span className="mgb2-label-sm mgb2-green">Live</span>
        <span className="mgb2-label-sm mgb2-muted" style={{ marginInlineStart: 'auto' }}>
          مخطط الشبكة <span className="mgb2-muted-en">Grid Ladder Chart</span>
        </span>
      </div>
      <div className="mgb2-chart-card">
        <div className="mgb2-chart-legend">
          <span><span className="mgb2-dot mgb2-dot-green" />Buy</span>
          <span><span className="mgb2-dot mgb2-dot-red" />Sell</span>
          <span><span className="mgb2-dot mgb2-dot-cyan" />Current</span>
          <span className="mgb2-legend-title">مستويات الشراء / البيع<br /><span className="mgb2-muted-en">Buy / Sell Grid Levels</span></span>
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} className="mgb2-chart-svg" preserveAspectRatio="none">
          <defs>
            <linearGradient id="mgb2-ag" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#00F5D4" stopOpacity="0.22" />
              <stop offset="100%" stopColor="#00F5D4" stopOpacity="0.01" />
            </linearGradient>
            <filter id="mgb2-glow">
              <feGaussianBlur stdDeviation="2" result="b" />
              <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          {/* SELL label */}
          <text x={pl + iW - 2} y={pt + 10} textAnchor="end" fill="#FF5252" fontSize="9" fontFamily="JetBrains Mono">SELL</text>
          {/* BUY label */}
          <text x={pl + iW - 2} y={pt + iH - 4} textAnchor="end" fill="#00E676" fontSize="9" fontFamily="JetBrains Mono">BUY</text>
          {/* y-axis labels */}
          {yLabels.map((p, i) => (
            <text key={i} x={pl - 3} y={py(p) + 3} textAnchor="end" fill="rgba(180,210,220,0.35)" fontSize="7" fontFamily="JetBrains Mono">
              {Math.round(p / 1000)}k
            </text>
          ))}
          {/* sell dashed levels */}
          {sellLevels.map((p, i) => (
            <g key={`s${i}`}>
              <line x1={pl} y1={py(p)} x2={pl + iW} y2={py(p)} stroke="#FF5252" strokeWidth="0.8" strokeDasharray="3 3" opacity="0.6" />
              <circle cx={pl + iW} cy={py(p)} r="3" fill="#FF5252" opacity="0.8" />
            </g>
          ))}
          {/* buy dashed levels */}
          {buyLevels.map((p, i) => (
            <g key={`b${i}`}>
              <line x1={pl} y1={py(p)} x2={pl + iW} y2={py(p)} stroke="#00E676" strokeWidth="0.8" strokeDasharray="3 3" opacity="0.6" />
              <circle cx={pl + iW} cy={py(p)} r="3" fill="#00E676" opacity="0.8" />
            </g>
          ))}
          {/* area + line */}
          <path d={areaPath} fill="url(#mgb2-ag)" />
          <path d={linePath} fill="none" stroke="#00F5D4" strokeWidth="1.8" strokeLinejoin="round" />
          {/* current price line */}
          <line x1={pl} y1={curY} x2={pl + iW} y2={curY} stroke="#00F5D4" strokeWidth="1.2" filter="url(#mgb2-glow)" />
          {/* current price box */}
          <rect x={pl} y={curY - 9} width={36} height={14} rx="3" fill="rgba(0,245,212,0.15)" stroke="#00F5D4" strokeWidth="0.8" />
          <text x={pl + 18} y={curY + 2} textAnchor="middle" fill="#00F5D4" fontSize="7" fontFamily="JetBrains Mono" fontWeight="600">
            {Math.round(current / 1000)}K
          </text>
          {/* pulsing dot on line */}
          <circle cx={pl + iW} cy={curY} r="4" fill="#00F5D4" filter="url(#mgb2-glow)">
            <animate attributeName="r" values="4;7;4" dur="2s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="1;0.3;1" dur="2s" repeatCount="indefinite" />
          </circle>
          <circle cx={pl + iW} cy={curY} r="3" fill="#00F5D4" />
        </svg>
      </div>
    </div>
  );
}

const MOCK_ORDERS = [
  { side: 'SELL', price: 91500, qty: 0.0012, status: 'OPEN' },
  { side: 'SELL', price: 88400, qty: 0.0014, status: 'OPEN' },
  { side: 'SELL', price: 86200, qty: 0.0015, status: 'PART.' },
  { side: 'BUY',  price: 82500, qty: 0.0016, status: 'FILLED' },
  { side: 'BUY',  price: 80200, qty: 0.0017, status: 'OPEN' },
  { side: 'BUY',  price: 78100, qty: 0.0018, status: 'OPEN' },
  { side: 'BUY',  price: 76000, qty: 0.0019, status: 'OPEN' },
  { side: 'BUY',  price: 74200, qty: 0.0021, status: 'OPEN' },
];

function statusStyle(s: string): { bg: string; color: string } {
  if (s === 'FILLED') return { bg: 'rgba(0,245,212,0.15)', color: '#00F5D4' };
  if (s === 'PART.')  return { bg: 'rgba(255,152,0,0.15)',  color: '#FF9800' };
  return { bg: 'rgba(255,255,255,0.07)', color: '#aaa' };
}

function OrdersTable({ orders, ar }: { orders: any[]; ar: boolean }) {
  const rows = orders.length > 0 ? orders : MOCK_ORDERS;
  return (
    <div className="mgb2-orders-section">
      <div className="mgb2-orders-header">
        <span className="mgb2-active-badge">Active {rows.length}</span>
        <span className="mgb2-label-sm mgb2-muted">
          الأوامر المفتوحة <span className="mgb2-muted-en">Open Orders</span>
        </span>
      </div>
      <div className="mgb2-orders-card">
        <table className="mgb2-table">
          <thead>
            <tr>
              <th>SIDE</th><th>PRICE</th><th>QTY</th><th>STATUS</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 8).map((o, i) => {
              const ss = statusStyle(o.status);
              return (
                <tr key={i}>
                  <td style={{ color: o.side === 'BUY' ? '#00E676' : '#FF5252', fontWeight: 700 }}>{o.side}</td>
                  <td className="mgb2-mono">{Number(o.price).toLocaleString()}</td>
                  <td className="mgb2-mono mgb2-muted">{Number(o.qty ?? o.quantity ?? 0).toFixed(4)} BTC</td>
                  <td>
                    <span className="mgb2-status-badge" style={{ background: ss.bg, color: ss.color }}>
                      {o.status}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length > 8 && (
          <div className="mgb2-view-all">
            <span className="mgb2-green">View All {rows.length} Orders +</span>
          </div>
        )}
      </div>
    </div>
  );
}

function PnlRing({ pct }: { pct: number }) {
  const r = 30; const circ = 2 * Math.PI * r;
  const dash = Math.min(pct, 100) / 100 * circ;
  return (
    <svg width="80" height="80" viewBox="0 0 80 80">
      <circle cx="40" cy="40" r={r} fill="none" stroke="rgba(255,152,0,0.15)" strokeWidth="7" />
      <circle cx="40" cy="40" r={r} fill="none" stroke="#FF9800" strokeWidth="7"
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round" transform="rotate(-90 40 40)" />
      <text x="40" y="36" textAnchor="middle" fill="#FF9800" fontSize="14" fontFamily="JetBrains Mono" fontWeight="700">{pct}%</text>
      <text x="40" y="50" textAnchor="middle" fill="rgba(255,152,0,0.6)" fontSize="8" fontFamily="IBM Plex Sans Arabic, sans-serif">In Use</text>
    </svg>
  );
}

function BotCard({ bot, lang, onRefresh }: { bot: any; lang: Lang; onRefresh: () => void }) {
  const ar = lang === 'ar';
  const [orders, setOrders]     = useState<any[]>([]);
  const [stopping, setStopping] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [riskOn, setRiskOn]     = useState(true);

  const isRunning = bot.status === 'running';
  const low       = Number(bot.price_low    ?? 72000);
  const high      = Number(bot.price_high   ?? 96000);
  const current   = Number(bot.current_price ?? bot.last_price ?? 84372.5);
  const gridCount = Number(bot.grid_count   ?? 24);
  const invested  = Number(bot.investment   ?? bot.invested_usdt ?? 2000);
  const realPnl   = Number(bot.realized_pnl   ?? 248.75);
  const unrealPnl = Number(bot.unrealized_pnl ?? 86.20);
  const realPct   = invested > 0 ? (realPnl / invested) * 100 : 12.44;
  const unrealPct = invested > 0 ? (unrealPnl / invested) * 100 : 4.31;
  const botId     = bot.id ? `#GRD-${String(bot.id).padStart(4, '0')}` : '#GRD-0042';

  useEffect(() => {
    getGridOrders(bot.id).then(setOrders).catch(() => {});
  }, [bot.id]);

  const handleStop = async () => {
    setStopping(true);
    try { await stopGridBot(bot.id); onRefresh(); } finally { setStopping(false); }
  };
  const handleResume = async () => {
    setStopping(true);
    try { await resumeGridBot(bot.id); onRefresh(); } finally { setStopping(false); }
  };
  const handleDelete = async () => {
    if (!confirm(ar ? 'إغلاق طارئ؟' : 'Emergency close?')) return;
    setDeleting(true);
    try { await deleteGridBot(bot.id); onRefresh(); } finally { setDeleting(false); }
  };

  return (
    <div className="mgb2-page">

      {/* ── Top header bar ── */}
      <div className="mgb2-topbar">
        <button className="mgb2-bell">🔔</button>
        <div className="mgb2-topbar-center">
          <span className="mgb2-topbar-title">GridBot MEXC</span>
          <span className="mgb2-topbar-sub">LIVE TRADING</span>
        </div>
        <button className="mgb2-bolt-btn">⚡</button>
      </div>

      {/* ── Bot status card ── */}
      <div className="mgb2-section-label-row">
        <span className="mgb2-bot-id">{botId}</span>
        <span className="mgb2-label-sm mgb2-muted">بوت الشبكة النشط <span className="mgb2-muted-en">Active Grid Bot</span></span>
      </div>

      <div className="mgb2-status-card">
        {/* running pill + pair */}
        <div className="mgb2-status-row">
          <div className="mgb2-running-pill" style={{ background: isRunning ? 'rgba(0,230,118,0.18)' : 'rgba(255,82,82,0.15)', borderColor: isRunning ? 'rgba(0,230,118,0.35)' : 'rgba(255,82,82,0.3)' }}>
            <span className="mgb2-pulse-dot" style={{ background: isRunning ? '#00E676' : '#FF5252' }} />
            <span style={{ color: isRunning ? '#00E676' : '#FF5252' }}>
              {isRunning ? (ar ? 'يعمل' : 'Running') : (ar ? 'متوقف' : 'Stopped')}
              {isRunning ? ' Running' : ' Stopped'}
            </span>
          </div>
          <div className="mgb2-pair-row">
            <span className="mgb2-pair-name">{bot.symbol ?? 'BTC/USDT'}</span>
            <span className="mgb2-pair-icon">B</span>
          </div>
        </div>
        <div className="mgb2-pair-sub">Binance Spot · MEXC</div>

        {/* price */}
        <div className="mgb2-price-label">
          السعر الحالي <span className="mgb2-muted-en">Current Price /</span>
        </div>
        <div className="mgb2-price-row">
          <span className="mgb2-price">{current.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          <span className="mgb2-price-chg">+2.34%</span>
        </div>

        {/* mode tags */}
        <div className="mgb2-tags">
          <span className="mgb2-tag mgb2-tag-inf">∞ Infinity Grid</span>
          <span className="mgb2-tag mgb2-tag-norm">○ Normal Mode</span>
          <span className="mgb2-tag mgb2-tag-auto">● Auto-Invest</span>
        </div>

        {/* range bar */}
        <RangeBar low={low} high={high} current={current} />
      </div>

      {/* ── PnL cards ── */}
      <div className="mgb2-pnl-row">
        <div className="mgb2-pnl-card">
          <div className="mgb2-pnl-top">
            <span className="mgb2-pnl-icon">📊</span>
            <span className="mgb2-pnl-title-ar">الربح غير المحقق</span>
          </div>
          <span className="mgb2-pnl-title-en">Unrealized PnL</span>
          <span className="mgb2-pnl-val mgb2-green">+${unrealPnl.toFixed(2)}</span>
          <span className="mgb2-pnl-pct mgb2-green">▲ {unrealPct.toFixed(2)}%+</span>
        </div>
        <div className="mgb2-pnl-card">
          <div className="mgb2-pnl-top">
            <span className="mgb2-pnl-icon">💰</span>
            <span className="mgb2-pnl-title-ar">الربح المحقق</span>
          </div>
          <span className="mgb2-pnl-title-en">Realized PnL</span>
          <span className="mgb2-pnl-val mgb2-green">+${realPnl.toFixed(2)}</span>
          <span className="mgb2-pnl-pct mgb2-green">▲ {realPct.toFixed(2)}%+</span>
        </div>
      </div>

      {/* ── Invested card ── */}
      <div className="mgb2-section-label-row">
        <span className="mgb2-label-sm mgb2-muted">المبلغ المستثمر <span className="mgb2-muted-en">Total Invested</span></span>
      </div>
      <div className="mgb2-invested-card">
        <PnlRing pct={70} />
        <div className="mgb2-invested-info">
          <span className="mgb2-invested-amt">${invested.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          <span className="mgb2-invested-sub">USDT · Spot Grid</span>
        </div>
      </div>

      {/* ── Grid chart ── */}
      <GridChart low={low} high={high} current={current} gridCount={gridCount} />

      {/* ── Orders table ── */}
      <OrdersTable orders={orders} ar={ar} />

      {/* ── Quick controls ── */}
      <div className="mgb2-section-label-row">
        <span className="mgb2-label-sm mgb2-muted">التحكم السريع <span className="mgb2-muted-en">Quick Controls</span></span>
      </div>
      <div className="mgb2-controls-card">
        <div className="mgb2-controls-grid">
          <button className="mgb2-ctrl-btn mgb2-ctrl-stop" onClick={handleStop} disabled={stopping}>
            <span className="mgb2-ctrl-icon">⏸</span>
            <span className="mgb2-ctrl-ar">إيقاف</span>
            <span className="mgb2-ctrl-en">Stop Grid</span>
          </button>
          <button className="mgb2-ctrl-btn mgb2-ctrl-start" onClick={handleResume} disabled={stopping}>
            <span className="mgb2-ctrl-icon">▶</span>
            <span className="mgb2-ctrl-ar">تشغيل</span>
            <span className="mgb2-ctrl-en">Start Grid</span>
          </button>
          <button className="mgb2-ctrl-btn mgb2-ctrl-settings">
            <span className="mgb2-ctrl-icon">⚙</span>
            <span className="mgb2-ctrl-ar">إعدادات</span>
            <span className="mgb2-ctrl-en">Settings</span>
          </button>
          <button className="mgb2-ctrl-btn mgb2-ctrl-rebuild" onClick={onRefresh}>
            <span className="mgb2-ctrl-icon">↺</span>
            <span className="mgb2-ctrl-ar">إعادة بناء</span>
            <span className="mgb2-ctrl-en">Rebuild Grid</span>
          </button>
        </div>
        <button className="mgb2-emergency" onClick={handleDelete} disabled={deleting}>
          <span>⚡ إغلاق طارئ — Emergency Close</span>
        </button>
      </div>

      {/* ── Risk management ── */}
      <div className="mgb2-section-label-row">
        <span className="mgb2-active-badge mgb2-badge-warn">ACTIVE ▲</span>
        <span className="mgb2-label-sm mgb2-muted">إعدادات المخاطر <span className="mgb2-muted-en">Risk Management</span></span>
      </div>
      <div className="mgb2-risk-card">
        {/* Max Drawdown */}
        <div className="mgb2-risk-row">
          <div className="mgb2-risk-vals">
            <span className="mgb2-risk-main">-15% · $300</span>
          </div>
          <span className="mgb2-risk-title-ar">الحد الأقصى للتراجع<br /><span className="mgb2-muted-en">Max Drawdown</span></span>
        </div>
        <div className="mgb2-risk-bar-wrap">
          <div className="mgb2-risk-track">
            <div className="mgb2-risk-fill" style={{ width: '34%', background: '#FF5252' }} />
          </div>
          <div className="mgb2-risk-bar-labels">
            <span className="mgb2-orange">Limit: 15%</span>
            <span className="mgb2-muted-sm">Current: -5.1%</span>
          </div>
        </div>

        <div className="mgb2-risk-divider" />

        {/* Stop Loss */}
        <div className="mgb2-risk-row">
          <span className="mgb2-risk-main mgb2-orange">$72,000</span>
          <span className="mgb2-risk-title-ar">وقف الخسارة<br /><span className="mgb2-muted-en">Stop Loss Trigger</span></span>
        </div>
        <div className="mgb2-risk-bar-wrap">
          <div className="mgb2-risk-track">
            <div className="mgb2-risk-fill" style={{ width: '85%', background: '#FF9800' }} />
          </div>
          <div className="mgb2-risk-bar-labels">
            <span className="mgb2-orange">Distance: $12,372</span>
            <span className="mgb2-muted-sm">from entry 14.6%-</span>
          </div>
        </div>

        <div className="mgb2-risk-divider" />

        {/* Auto-protection toggle */}
        <div className="mgb2-autoprotect-row">
          <button
            className="mgb2-toggle"
            onClick={() => setRiskOn(v => !v)}
            style={{ background: riskOn ? '#00E676' : 'rgba(255,255,255,0.12)' }}
          >
            <span className="mgb2-toggle-thumb" style={{ transform: riskOn ? 'translateX(18px)' : 'translateX(2px)' }} />
          </button>
          <div className="mgb2-autoprotect-text">
            <span className="mgb2-autoprotect-ar">الحماية التلقائية مفعّلة 🛡</span>
            <span className="mgb2-muted-sm">Auto-protection enabled · Grid pauses at trigger</span>
          </div>
        </div>
      </div>

      {/* ── Bottom nav ── */}
      <div className="mgb2-bottom-nav">
        <button className="mgb2-nav-item">
          <span className="mgb2-nav-icon">⚙️</span>
          <span>إعدادات</span>
        </button>
        <button className="mgb2-nav-item">
          <span className="mgb2-nav-icon">📋</span>
          <span>أوامر</span>
        </button>
        <button className="mgb2-nav-item mgb2-nav-active">
          <span className="mgb2-nav-icon-active">⚡</span>
          <span>بوتات</span>
        </button>
        <button className="mgb2-nav-item">
          <span className="mgb2-nav-icon">🏠</span>
          <span>لمحة</span>
        </button>
      </div>

    </div>
  );
}

export default function MobileGridBot({ lang }: Props) {
  const ar = lang === 'ar';
  const [bots, setBots]       = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { const d = await listGridBots(); setBots(d); }
    catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);

  if (loading) return (
    <div className="mgb2-loading">
      <div className="mgb2-spinner" />
      <span>{ar ? 'جاري التحميل…' : 'Loading…'}</span>
    </div>
  );

  // Show demo card if no bots yet
  const demoBot = { id: 42, symbol: 'BTC/USDT', status: 'running', price_low: 72000, price_high: 96000, current_price: 84372.5, grid_count: 24, investment: 2000, realized_pnl: 248.75, unrealized_pnl: 86.20 };
  const list = bots.length > 0 ? bots : [demoBot];

  return (
    <>
      {list.map(b => <BotCard key={b.id} bot={b} lang={lang} onRefresh={load} />)}
    </>
  );
}
