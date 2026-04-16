'use client';

import { useState, useEffect, useCallback } from 'react';
import { Lang } from '../lib/i18n';
import {
  listGridBots, stopGridBot, resumeGridBot, deleteGridBot, getGridOrders, createGridBot, previewGridBot,
} from '../lib/api';

interface Props { lang: Lang; onNavigate?: (tab: any) => void; }

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

function CreateGridBotModal({ ar, onClose, onCreated }: {
  ar: boolean; onClose: () => void; onCreated: () => void;
}) {
  const [symbol,           setSymbol]           = useState('BTC');
  const [symbolSearch,     setSymbolSearch]     = useState('');
  const [showSymbolPicker, setShowSymbolPicker] = useState(false);
  const [investment,       setInvestment]       = useState('');
  const [mode,             setMode]             = useState<'normal' | 'infinity'>('normal');
  const [gridCountManual,  setGridCountManual]  = useState<number | null>(null);
  const [lowerPct,         setLowerPct]         = useState('5');
  const [upperPct,         setUpperPct]         = useState('5');
  const [expandDir,        setExpandDir]        = useState<'both' | 'lower' | 'upper'>('both');
  const [preview,          setPreview]          = useState<any>(null);
  const [loading,          setLoading]          = useState(false);
  const [creating,         setCreating]         = useState(false);
  const [error,            setError]            = useState('');

  useEffect(() => {
    const inv = parseFloat(investment);
    if (!symbol || inv < 1) { setPreview(null); return; }
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        setPreview(await previewGridBot(
          symbol, inv,
          gridCountManual ?? undefined,
          parseFloat(lowerPct) || 5,
          parseFloat(upperPct) || 5,
        ));
        setError('');
      }
      catch (e: any) { setError(e.message); setPreview(null); }
      finally { setLoading(false); }
    }, 700);
    return () => clearTimeout(t);
  }, [symbol, investment, gridCountManual, lowerPct, upperPct]);

  const inv = parseFloat(investment) || 0;
  const freeUsdt: number | null = preview?.free_usdt ?? null;
  const insufficient = freeUsdt !== null && inv > freeUsdt;

  const handleCreate = async () => {
    const invNum = parseFloat(investment);
    if (!symbol || invNum < 1) { setError(ar ? 'أدخل الزوج والمبلغ' : 'Enter symbol and amount'); return; }
    const lp = parseFloat(lowerPct);
    const up = parseFloat(upperPct);
    if (isNaN(lp) || lp <= 0 || isNaN(up) || up <= 0) {
      setError(ar ? 'أدخل نسبة نطاق صحيحة (أكبر من 0)' : 'Enter valid range % (greater than 0)');
      return;
    }
    setCreating(true); setError('');
    try {
      await createGridBot({
        symbol,
        investment: invNum,
        mode,
        grid_count: gridCountManual ?? undefined,
        lower_pct: lp,
        upper_pct: mode === 'infinity' ? 0.1 : up,
        expand_direction: expandDir,
      });
      onCreated();
    }
    catch (e: any) { setError(e.message); }
    finally { setCreating(false); }
  };

  const POPULAR = ['BTC','ETH','SOL','BNB','XRP','TAO','AIA','FET','DOGE','ADA','AVAX','DOT','LINK','UNI','MATIC','LTC','ATOM','NEAR','APT','ARB'];

  const filteredSymbols = symbolSearch.trim()
    ? POPULAR.filter(s => s.includes(symbolSearch.toUpperCase()))
    : POPULAR;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center" style={{ background: 'rgba(0,0,0,0.8)' }} onClick={onClose}>
      <div className="w-full max-w-lg rounded-t-3xl p-5 space-y-4 max-h-[85vh] overflow-y-auto"
        style={{ background: '#0f1923', border: '1px solid rgba(0,245,212,0.2)' }}
        onClick={e => e.stopPropagation()}>

        <div className="flex items-center justify-between">
          <h3 className="font-bold text-base" style={{ color: '#00F5D4' }}>
            {ar ? 'إنشاء بوت شبكي جديد' : 'New Grid Bot'}
          </h3>
          <button onClick={onClose} style={{ color: 'rgba(255,255,255,0.4)', fontSize: 20 }}>✕</button>
        </div>

        {/* العملة */}
        <div className="space-y-2">
          <div className="text-xs font-semibold" style={{ color: 'rgba(255,255,255,0.5)' }}>
            {ar ? 'العملة' : 'Symbol'}
          </div>

          {/* زر اختيار العملة الحالية */}
          <button
            onClick={() => setShowSymbolPicker(v => !v)}
            className="w-full flex items-center justify-between px-4 py-3 rounded-2xl"
            style={{
              background: 'rgba(240,185,11,0.08)',
              border: '1px solid rgba(240,185,11,0.35)',
            }}
          >
            <div className="flex items-center gap-3">
              <img
                src={`https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons/32/color/${symbol.toLowerCase()}.png`}
                alt={symbol}
                className="w-7 h-7 rounded-full"
                onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
              <span className="font-black text-lg" style={{ color: '#F0B90B' }}>{symbol}</span>
              <span className="text-xs font-semibold" style={{ color: 'rgba(255,255,255,0.35)' }}>/USDT</span>
            </div>
            <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: 18 }}>
              {showSymbolPicker ? '▲' : '▼'}
            </span>
          </button>

          {/* قائمة الاختيار */}
          {showSymbolPicker && (
            <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid rgba(0,245,212,0.2)', background: '#0a1018' }}>
              {/* بحث */}
              <div className="p-2 border-b" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
                <input
                  autoFocus
                  value={symbolSearch}
                  onChange={e => setSymbolSearch(e.target.value.toUpperCase())}
                  placeholder={ar ? 'ابحث عن عملة...' : 'Search coin...'}
                  className="w-full rounded-xl px-3 py-2 text-sm outline-none"
                  style={{ background: 'rgba(255,255,255,0.06)', color: '#fff', border: '1px solid rgba(0,245,212,0.15)' }}
                />
              </div>
              {/* مقترحات */}
              <div className="grid grid-cols-4 gap-1 p-2 max-h-48 overflow-y-auto">
                {filteredSymbols.map(s => (
                  <button
                    key={s}
                    onClick={() => { setSymbol(s); setShowSymbolPicker(false); setSymbolSearch(''); }}
                    className="flex flex-col items-center gap-1 py-2 px-1 rounded-xl"
                    style={{
                      background: symbol === s ? 'rgba(240,185,11,0.15)' : 'rgba(255,255,255,0.04)',
                      border: `1px solid ${symbol === s ? 'rgba(240,185,11,0.4)' : 'rgba(255,255,255,0.08)'}`,
                    }}
                  >
                    <img
                      src={`https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons/32/color/${s.toLowerCase()}.png`}
                      alt={s}
                      className="w-6 h-6 rounded-full"
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                    <span className="text-[10px] font-bold" style={{ color: symbol === s ? '#F0B90B' : 'rgba(255,255,255,0.6)' }}>{s}</span>
                  </button>
                ))}
              </div>
              {/* إدخال يدوي */}
              <div className="p-2 border-t" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
                <input
                  value={symbolSearch}
                  onChange={e => setSymbolSearch(e.target.value.toUpperCase().replace('USDT', ''))}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && symbolSearch.trim()) {
                      setSymbol(symbolSearch.trim());
                      setShowSymbolPicker(false);
                      setSymbolSearch('');
                    }
                  }}
                  placeholder={ar ? 'أو اكتب رمز العملة واضغط Enter' : 'Or type symbol + Enter'}
                  className="w-full rounded-xl px-3 py-2 text-xs outline-none uppercase"
                  style={{ background: 'rgba(255,255,255,0.06)', color: '#fff', border: '1px solid rgba(0,245,212,0.15)' }}
                />
              </div>
            </div>
          )}
        </div>

        {/* المبلغ */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-xs font-semibold" style={{ color: 'rgba(255,255,255,0.5)' }}>
              {ar ? 'مبلغ الاستثمار (USDT)' : 'Investment (USDT)'}
            </div>
            {/* Free balance badge */}
            {freeUsdt !== null && (
              <div className="flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-lg"
                style={{
                  background: insufficient ? 'rgba(239,68,68,0.12)' : 'rgba(0,212,170,0.1)',
                  color: insufficient ? '#EF4444' : '#00D4AA',
                  border: `1px solid ${insufficient ? 'rgba(239,68,68,0.35)' : 'rgba(0,212,170,0.25)'}`,
                }}>
                <span>{ar ? 'الحر:' : 'Free:'}</span>
                <span>${freeUsdt.toFixed(2)}</span>
              </div>
            )}
          </div>
          <input type="number" min={10} value={investment} onChange={e => setInvestment(e.target.value)}
            placeholder="100"
            className="w-full rounded-xl px-3 py-2 text-lg font-bold outline-none"
            style={{
              background: 'rgba(255,255,255,0.06)', color: '#fff',
              border: `1px solid ${insufficient ? 'rgba(239,68,68,0.5)' : 'rgba(0,245,212,0.2)'}`,
            }} />
          {insufficient && (
            <div className="flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-xl"
              style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#EF4444' }}>
              <span>⚠</span>
              <span>{ar ? `رصيد غير كافٍ — المتاح ${freeUsdt!.toFixed(2)} USDT` : `Insufficient — available $${freeUsdt!.toFixed(2)}`}</span>
            </div>
          )}
          <div className="flex gap-2">
            {[30, 50, 100, 200].map(v => (
              <button key={v} onClick={() => setInvestment(String(v))}
                className="flex-1 py-1.5 rounded-xl text-xs font-bold"
                style={{
                  background: investment === String(v) ? 'rgba(240,185,11,0.12)' : 'rgba(255,255,255,0.06)',
                  color: investment === String(v) ? '#F0B90B' : 'rgba(255,255,255,0.4)',
                  border: `1px solid ${investment === String(v) ? 'rgba(240,185,11,0.3)' : 'rgba(255,255,255,0.1)'}`,
                }}>
                ${v}
              </button>
            ))}
          </div>
        </div>

        {/* عدد الشبكات */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-xs font-semibold" style={{ color: 'rgba(255,255,255,0.5)' }}>
              {ar ? 'عدد الشبكات' : 'Grid Count'}
            </div>
            <button onClick={() => setGridCountManual(null)}
              className="text-xs px-2 py-0.5 rounded-lg font-bold"
              style={{
                background: gridCountManual === null ? 'rgba(96,165,250,0.15)' : 'rgba(255,255,255,0.06)',
                color: gridCountManual === null ? '#60A5FA' : 'rgba(255,255,255,0.4)',
                border: `1px solid ${gridCountManual === null ? 'rgba(96,165,250,0.4)' : 'rgba(255,255,255,0.1)'}`,
              }}>
              {ar ? 'تلقائي' : 'Auto'}
            </button>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setGridCountManual(v => Math.max(2, (v ?? preview?.grid_count ?? 10) - 1))}
              className="w-10 h-10 rounded-xl text-lg font-bold flex items-center justify-center shrink-0"
              style={{ background: 'rgba(255,82,82,0.15)', color: '#FF5252', border: '1px solid rgba(255,82,82,0.3)' }}>
              −
            </button>
            <input
              type="number" min={2} max={50}
              value={gridCountManual ?? (preview?.grid_count ?? '')}
              placeholder={gridCountManual === null ? (preview?.grid_count ? String(preview.grid_count) : ar ? 'تلقائي' : 'Auto') : ''}
              onChange={e => {
                const v = parseInt(e.target.value);
                if (!e.target.value) { setGridCountManual(null); return; }
                if (!isNaN(v)) setGridCountManual(Math.min(50, Math.max(2, v)));
              }}
              className="flex-1 text-center font-black text-2xl rounded-xl px-3 py-2 outline-none"
              style={{ background: 'rgba(255,255,255,0.06)', color: '#60A5FA', border: '1px solid rgba(96,165,250,0.3)' }}
            />
            <button
              onClick={() => setGridCountManual(v => Math.min(50, (v ?? preview?.grid_count ?? 10) + 1))}
              className="w-10 h-10 rounded-xl text-lg font-bold flex items-center justify-center shrink-0"
              style={{ background: 'rgba(0,230,118,0.15)', color: '#00E676', border: '1px solid rgba(0,230,118,0.3)' }}>
              +
            </button>
          </div>
          {gridCountManual === null && (
            <div className="text-[10px] text-center" style={{ color: 'rgba(255,255,255,0.3)' }}>
              {ar ? 'سيتم الحساب تلقائياً حسب المبلغ' : 'Auto-calculated from investment amount'}
            </div>
          )}
        </div>

        {/* نطاق الشبكة % */}
        <div className="space-y-2">
          <div className="text-xs font-semibold" style={{ color: 'rgba(255,255,255,0.5)' }}>
            {ar ? 'نطاق الشبكة (%)' : 'Grid Range (%)'}
          </div>

          {/* معاينة السعر المحسوب */}
          {preview && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs"
              style={{ background: 'rgba(0,245,212,0.06)', border: '1px solid rgba(0,245,212,0.15)' }}>
              <span style={{ color: '#00E676', fontWeight: 700 }}>↓ ${preview.price_low?.toFixed(4)}</span>
              <span style={{ color: 'rgba(255,255,255,0.3)' }}>→</span>
              <span style={{ color: '#FF5252', fontWeight: 700 }}>
                {mode === 'infinity' ? '∞' : `↑ $${preview.price_high?.toFixed(4)}`}
              </span>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            {/* نطاق أسفل */}
            <div className="space-y-1">
              <div className="text-[10px] font-semibold" style={{ color: 'rgba(0,230,118,0.7)' }}>
                ↓ {ar ? 'نطاق أسفل' : 'Lower Range'}
              </div>
              <div className="relative">
                <input
                  type="number" min={0.1} max={50} step={0.5}
                  value={lowerPct}
                  onChange={e => setLowerPct(e.target.value)}
                  className="w-full rounded-xl px-3 py-2 text-sm font-bold outline-none pe-6"
                  style={{ background: 'rgba(0,230,118,0.06)', color: '#00E676', border: '1px solid rgba(0,230,118,0.25)' }}
                />
                <span className="absolute end-2 top-1/2 -translate-y-1/2 text-[10px] font-bold pointer-events-none" style={{ color: '#00E676' }}>%</span>
              </div>
              <div className="flex gap-1">
                {[2, 5, 10].map(v => (
                  <button key={v} onClick={() => setLowerPct(String(v))}
                    className="flex-1 py-1 rounded-lg text-[9px] font-bold"
                    style={{
                      background: lowerPct === String(v) ? 'rgba(0,230,118,0.15)' : 'rgba(255,255,255,0.04)',
                      color: lowerPct === String(v) ? '#00E676' : 'rgba(255,255,255,0.3)',
                      border: `1px solid ${lowerPct === String(v) ? 'rgba(0,230,118,0.3)' : 'rgba(255,255,255,0.08)'}`,
                    }}>
                    {v}%
                  </button>
                ))}
              </div>
            </div>

            {/* نطاق أعلى */}
            <div className="space-y-1">
              <div className="text-[10px] font-semibold" style={{ color: mode === 'infinity' ? 'rgba(255,255,255,0.2)' : 'rgba(255,82,82,0.7)' }}>
                ↑ {ar ? 'نطاق أعلى' : 'Upper Range'}
                {mode === 'infinity' && <span className="ms-1">∞</span>}
              </div>
              <div className="relative">
                <input
                  type="number" min={0.1} max={50} step={0.5}
                  value={mode === 'infinity' ? '' : upperPct}
                  onChange={e => setUpperPct(e.target.value)}
                  disabled={mode === 'infinity'}
                  placeholder={mode === 'infinity' ? '∞' : undefined}
                  className="w-full rounded-xl px-3 py-2 text-sm font-bold outline-none pe-6"
                  style={{
                    background: mode === 'infinity' ? 'rgba(255,255,255,0.03)' : 'rgba(255,82,82,0.06)',
                    color: mode === 'infinity' ? 'rgba(255,255,255,0.2)' : '#FF5252',
                    border: `1px solid ${mode === 'infinity' ? 'rgba(255,255,255,0.08)' : 'rgba(255,82,82,0.25)'}`,
                  }}
                />
                {mode !== 'infinity' && (
                  <span className="absolute end-2 top-1/2 -translate-y-1/2 text-[10px] font-bold pointer-events-none" style={{ color: '#FF5252' }}>%</span>
                )}
              </div>
              {mode !== 'infinity' && (
                <div className="flex gap-1">
                  {[2, 5, 10].map(v => (
                    <button key={v} onClick={() => setUpperPct(String(v))}
                      className="flex-1 py-1 rounded-lg text-[9px] font-bold"
                      style={{
                        background: upperPct === String(v) ? 'rgba(255,82,82,0.15)' : 'rgba(255,255,255,0.04)',
                        color: upperPct === String(v) ? '#FF5252' : 'rgba(255,255,255,0.3)',
                        border: `1px solid ${upperPct === String(v) ? 'rgba(255,82,82,0.3)' : 'rgba(255,255,255,0.08)'}`,
                      }}>
                      {v}%
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* اتجاه التوسع */}
          <div className="space-y-1.5 pt-1">
            <div className="text-[10px] font-semibold" style={{ color: 'rgba(255,255,255,0.35)' }}>
              {ar ? 'عند تجاوز النطاق — وسّع:' : 'When price exits range — expand:'}
            </div>
            <div className="grid grid-cols-3 gap-1.5">
              {([
                ['both',  ar ? 'الجهتين'  : 'Both',  '↕'],
                ['lower', ar ? 'أسفل فقط' : 'Lower', '↓'],
                ['upper', ar ? 'أعلى فقط' : 'Upper', '↑'],
              ] as const).map(([val, label, icon]) => (
                <button key={val} onClick={() => setExpandDir(val)}
                  className="flex flex-col items-center gap-0.5 py-2 rounded-xl"
                  style={{
                    background: expandDir === val ? 'rgba(240,185,11,0.12)' : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${expandDir === val ? 'rgba(240,185,11,0.4)' : 'rgba(255,255,255,0.08)'}`,
                  }}>
                  <span className="text-sm leading-none" style={{ color: expandDir === val ? '#F0B90B' : 'rgba(255,255,255,0.3)' }}>{icon}</span>
                  <span className="text-[9px] font-bold" style={{ color: expandDir === val ? '#F0B90B' : 'rgba(255,255,255,0.3)' }}>{label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* النوع */}
        <div className="space-y-2">
          <div className="text-xs font-semibold" style={{ color: 'rgba(255,255,255,0.5)' }}>
            {ar ? 'نوع الشبكة' : 'Grid Mode'}
          </div>
          <div className="grid grid-cols-2 gap-2">
            {([['normal', ar ? 'عادي' : 'Normal'], ['infinity', ar ? 'لامحدود ∞' : 'Infinity ∞']] as const).map(([val, label]) => (
              <button key={val} onClick={() => setMode(val)}
                className="py-2.5 rounded-xl text-sm font-bold"
                style={{
                  background: mode === val ? 'rgba(240,185,11,0.12)' : 'rgba(255,255,255,0.06)',
                  color: mode === val ? '#F0B90B' : 'rgba(255,255,255,0.5)',
                  border: `1px solid ${mode === val ? 'rgba(240,185,11,0.4)' : 'rgba(255,255,255,0.1)'}`,
                }}>
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Preview */}
        {loading && <div className="text-center text-xs py-2" style={{ color: 'rgba(255,255,255,0.4)' }}>
          {ar ? 'جاري الحساب...' : 'Calculating...'}
        </div>}
        {preview && !loading && (
          <div className="rounded-xl p-3 space-y-2" style={{ background: 'rgba(0,245,212,0.06)', border: '1px solid rgba(0,245,212,0.15)' }}>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>{ar ? 'السعر الحالي' : 'Price'}: </span><span style={{ color: '#F0B90B', fontWeight: 700 }}>${preview.current_price?.toFixed(4)}</span></div>
              <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>{ar ? 'عدد الشبكات' : 'Grids'}: </span><span style={{ color: '#60A5FA', fontWeight: 700 }}>{preview.grid_count}</span></div>
              <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>{ar ? 'لكل شبكة' : 'Per grid'}: </span><span style={{ color: '#A78BFA', fontWeight: 700 }}>${preview.usdt_per_grid?.toFixed(2)}</span></div>
              <div><span style={{ color: 'rgba(255,255,255,0.4)' }}>{ar ? 'ربح/دورة' : 'Profit'}: </span><span style={{ color: '#00D4AA', fontWeight: 700 }}>${(preview.est_profit_per_grid ?? 0).toFixed(4)}</span></div>
            </div>
          </div>
        )}

        {error && <div className="text-xs text-center py-1" style={{ color: '#FF5252' }}>{error}</div>}

        <div className="flex gap-3 pt-1">
          <button onClick={onClose} className="flex-1 py-3 rounded-2xl text-sm font-bold"
            style={{ background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.5)', border: '1px solid rgba(255,255,255,0.1)' }}>
            {ar ? 'إلغاء' : 'Cancel'}
          </button>
          <button onClick={handleCreate} disabled={creating || !investment || insufficient}
            className="flex-1 py-3 rounded-2xl text-sm font-bold"
            style={{
              background: insufficient ? 'rgba(239,68,68,0.12)' : (creating || !investment ? 'rgba(255,255,255,0.06)' : 'rgba(0,245,212,0.15)'),
              color: insufficient ? '#EF4444' : (creating || !investment ? 'rgba(255,255,255,0.3)' : '#00F5D4'),
              border: `1px solid ${insufficient ? 'rgba(239,68,68,0.35)' : (creating || !investment ? 'rgba(255,255,255,0.1)' : 'rgba(0,245,212,0.35)')}`,
            }}>
            {creating ? '...' : insufficient ? (ar ? '⚠ رصيد غير كافٍ' : '⚠ Insufficient') : (ar ? 'إنشاء' : 'Create')}
          </button>
        </div>
      </div>
    </div>
  );
}

function SettingsModal({ bot, ar, onClose, onSave }: {
  bot: any; ar: boolean;
  onClose: () => void;
  onSave: (investment: number, gridCount: number) => void;
}) {
  const [investment, setInvestment] = useState(String(Number(bot.investment ?? bot.invested_usdt ?? 50)));
  const [gridCount,  setGridCount]  = useState(String(Number(bot.grid_count ?? 20)));

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center" style={{ background: 'rgba(0,0,0,0.75)' }} onClick={onClose}>
      <div className="w-full max-w-lg rounded-t-3xl p-5 space-y-4"
        style={{ background: '#0f1923', border: '1px solid rgba(0,245,212,0.2)' }}
        onClick={e => e.stopPropagation()}>
        <h3 className="font-bold text-base text-center" style={{ color: '#00F5D4' }}>
          {ar ? 'إعدادات الشبكة' : 'Grid Settings'}
        </h3>

        {/* قيمة الدخول */}
        <div className="space-y-1">
          <label className="text-xs font-semibold" style={{ color: 'rgba(255,255,255,0.5)' }}>
            {ar ? 'قيمة الدخول (USDT)' : 'Investment (USDT)'}
          </label>
          <div className="flex items-center gap-2">
            <button onClick={() => setInvestment(v => String(Math.max(1, Number(v) - 10)))}
              className="w-10 h-10 rounded-xl text-lg font-bold flex items-center justify-center"
              style={{ background: 'rgba(255,82,82,0.15)', color: '#FF5252', border: '1px solid rgba(255,82,82,0.3)' }}>−</button>
            <input type="number" value={investment} onChange={e => setInvestment(e.target.value)}
              className="flex-1 text-center font-bold text-base rounded-xl px-3 py-2 outline-none"
              style={{ background: 'rgba(255,255,255,0.06)', color: '#fff', border: '1px solid rgba(0,245,212,0.2)' }} />
            <button onClick={() => setInvestment(v => String(Number(v) + 10))}
              className="w-10 h-10 rounded-xl text-lg font-bold flex items-center justify-center"
              style={{ background: 'rgba(0,230,118,0.15)', color: '#00E676', border: '1px solid rgba(0,230,118,0.3)' }}>+</button>
          </div>
        </div>

        {/* عدد الشبكات */}
        <div className="space-y-1">
          <label className="text-xs font-semibold" style={{ color: 'rgba(255,255,255,0.5)' }}>
            {ar ? 'عدد الشبكات' : 'Grid Count'}
          </label>
          <div className="flex items-center gap-2">
            <button onClick={() => setGridCount(v => String(Math.max(2, Number(v) - 1)))}
              className="w-10 h-10 rounded-xl text-lg font-bold flex items-center justify-center"
              style={{ background: 'rgba(255,82,82,0.15)', color: '#FF5252', border: '1px solid rgba(255,82,82,0.3)' }}>−</button>
            <input type="number" value={gridCount} onChange={e => setGridCount(e.target.value)}
              className="flex-1 text-center font-bold text-base rounded-xl px-3 py-2 outline-none"
              style={{ background: 'rgba(255,255,255,0.06)', color: '#fff', border: '1px solid rgba(0,245,212,0.2)' }} />
            <button onClick={() => setGridCount(v => String(Number(v) + 1))}
              className="w-10 h-10 rounded-xl text-lg font-bold flex items-center justify-center"
              style={{ background: 'rgba(0,230,118,0.15)', color: '#00E676', border: '1px solid rgba(0,230,118,0.3)' }}>+</button>
          </div>
        </div>

        <div className="flex gap-3 pt-1">
          <button onClick={onClose} className="flex-1 py-3 rounded-2xl text-sm font-bold"
            style={{ background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.5)', border: '1px solid rgba(255,255,255,0.1)' }}>
            {ar ? 'إلغاء' : 'Cancel'}
          </button>
          <button onClick={() => onSave(Number(investment), Number(gridCount))}
            className="flex-1 py-3 rounded-2xl text-sm font-bold"
            style={{ background: 'rgba(0,245,212,0.15)', color: '#00F5D4', border: '1px solid rgba(0,245,212,0.35)' }}>
            {ar ? 'حفظ' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}

function BotCard({ bot, lang, onRefresh }: { bot: any; lang: Lang; onRefresh: () => void }) {
  const ar = lang === 'ar';
  const [orders, setOrders]           = useState<any[]>([]);
  const [stopping, setStopping]       = useState(false);
  const [deleting, setDeleting]       = useState(false);
  const [rebuilding, setRebuilding]   = useState(false);
  const [showOrders, setShowOrders]   = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const isRunning = bot.status === 'running';
  const invested  = Number(bot.investment ?? bot.invested_usdt ?? 50);
  const realPnl   = Number(bot.realized_pnl   ?? 0);
  const unrealPnl = Number(bot.unrealized_pnl ?? 0);
  const realPct   = invested > 0 ? (realPnl / invested) * 100 : 0;
  const unrealPct = invested > 0 ? (unrealPnl / invested) * 100 : 0;
  const utilPct   = Math.min(Math.abs(invested > 0 ? (invested / (invested + 30)) * 100 : 70), 100);

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
    if (!confirm(ar ? 'إغلاق طارئ وحذف البوت؟' : 'Emergency close & delete bot?')) return;
    setDeleting(true);
    try { await deleteGridBot(bot.id); onRefresh(); } finally { setDeleting(false); }
  };
  const handleRebuild = async (investment?: number, gridCount?: number) => {
    setRebuilding(true);
    setShowSettings(false);
    try {
      await stopGridBot(bot.id);
      await deleteGridBot(bot.id);
      await createGridBot({
        symbol: bot.symbol,
        investment: investment ?? invested,
        grid_count: gridCount ?? Number(bot.grid_count ?? 20),
        mode: bot.mode ?? 'normal',
      });
      onRefresh();
    } finally { setRebuilding(false); }
  };
  const handleSaveSettings = (investment: number, gridCount: number) => {
    handleRebuild(investment, gridCount);
  };

  // Symbol display: remove USDT suffix for cleaner look
  const symbolDisplay = (bot.symbol ?? 'BTC/USDT').replace('USDT', '');

  return (
    <div className="mgb-card">

      {/* ── Header: symbol bold + invested USDT ── */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span style={{ fontSize: 22, fontWeight: 900, color: '#fff', letterSpacing: -0.5 }}>
            {symbolDisplay}
          </span>
          <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.35)', fontWeight: 600 }}>/ USDT</span>
          <div className="mgb-status-pill" style={{ background: isRunning ? 'rgba(0,230,118,0.15)' : 'rgba(255,82,82,0.12)' }}>
            <PulsingDot color={isRunning ? '#00E676' : '#FF5252'} />
            <span style={{ color: isRunning ? '#00E676' : '#FF5252', fontSize: 11, fontWeight: 600 }}>
              {isRunning ? (ar ? 'يعمل' : 'Running') : (ar ? 'متوقف' : 'Stopped')}
            </span>
          </div>
        </div>
        <div className="text-end">
          <div style={{ fontSize: 20, fontWeight: 900, color: '#00F5D4' }}>
            ${invested.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', fontWeight: 600 }}>USDT</div>
        </div>
      </div>

      {/* ── PnL row (2 cards, no ring) ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}>
        <div className="mgb-pnl-card">
          <span className="mgb-pnl-label">{ar ? 'ربح محقق' : 'Realized PnL'}</span>
          <span style={{ fontSize: 18, fontWeight: 900, color: realPnl >= 0 ? '#00E676' : '#FF5252' }}>
            {realPnl >= 0 ? '+' : ''}${realPnl.toFixed(2)}
          </span>
          <span className="mgb-pnl-pct" style={{ color: realPnl >= 0 ? '#00E676' : '#FF5252' }}>
            ({realPct >= 0 ? '+' : ''}{realPct.toFixed(2)}%)
          </span>
        </div>
        <div className="mgb-pnl-card">
          <span className="mgb-pnl-label">{ar ? 'ربح غير محقق' : 'Unrealized PnL'}</span>
          <span style={{ fontSize: 18, fontWeight: 900, color: unrealPnl >= 0 ? '#00F5D4' : '#FF5252' }}>
            {unrealPnl >= 0 ? '+' : ''}${unrealPnl.toFixed(2)}
          </span>
          <span className="mgb-pnl-pct" style={{ color: unrealPnl >= 0 ? '#00F5D4' : '#FF5252' }}>
            ({unrealPct >= 0 ? '+' : ''}{unrealPct.toFixed(2)}%)
          </span>
        </div>
      </div>

      {/* ── Orders toggle ── */}
      <button className="mgb-orders-toggle" onClick={() => setShowOrders(v => !v)}>
        <span>{ar ? 'الأوامر النشطة' : 'Active Orders'}</span>
        <span className="mgb-chevron" style={{ transform: showOrders ? 'rotate(180deg)' : 'none' }}>▾</span>
      </button>
      {showOrders && <OrdersTable orders={orders} ar={ar} />}

      {/* ── 4 buttons 2×2 ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 12 }}>
        {/* إيقاف / تشغيل */}
        {isRunning ? (
          <button className="mgb-btn mgb-btn-stop" onClick={handleStop} disabled={stopping}>
            {stopping ? '…' : (ar ? 'إيقاف' : 'Stop')}
          </button>
        ) : (
          <button className="mgb-btn mgb-btn-start" onClick={handleResume} disabled={stopping}>
            {stopping ? '…' : (ar ? 'تشغيل' : 'Start')}
          </button>
        )}

        {/* إغلاق طارئ */}
        <button className="mgb-btn mgb-btn-emergency" onClick={handleDelete} disabled={deleting}>
          {deleting ? '…' : (ar ? 'إغلاق طارئ' : 'Emergency Close')}
        </button>

        {/* إعدادات */}
        <button className="mgb-btn mgb-btn-settings" onClick={() => setShowSettings(true)}>
          {ar ? 'إعدادات' : 'Settings'}
        </button>

        {/* إعادة بناء */}
        <button className="mgb-btn mgb-btn-rebuild" onClick={() => handleRebuild()} disabled={rebuilding}>
          {rebuilding ? '…' : (ar ? 'إعادة بناء' : 'Rebuild')}
        </button>
      </div>

      {/* Settings modal */}
      {showSettings && (
        <SettingsModal
          bot={bot}
          ar={ar}
          onClose={() => setShowSettings(false)}
          onSave={handleSaveSettings}
        />
      )}

    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function MobileGridBot({ lang, onNavigate }: Props) {
  const ar = lang === 'ar';
  const [bots, setBots]             = useState<any[]>([]);
  const [loading, setLoading]       = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showCreate, setShowCreate] = useState(false);

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

      {/* ── Create new bot button ── */}
      <button
        onClick={() => setShowCreate(true)}
        style={{
          width: '100%',
          padding: '14px',
          borderRadius: 16,
          fontSize: 15,
          fontWeight: 800,
          background: 'linear-gradient(135deg, rgba(0,245,212,0.2), rgba(123,92,245,0.2))',
          color: '#00F5D4',
          border: '1px solid rgba(0,245,212,0.4)',
          boxShadow: '0 0 20px rgba(0,245,212,0.15)',
          marginBottom: 12,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          cursor: 'pointer',
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="16" /><line x1="8" y1="12" x2="16" y2="12" />
        </svg>
        {ar ? 'إنشاء بوت جديد' : 'Create New Bot'}
      </button>

      {showCreate && (
        <CreateGridBotModal
          ar={ar}
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); load(true); }}
        />
      )}

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
