'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { TrendingUp, TrendingDown, Minus, Trash2, RefreshCw, X, Check } from 'lucide-react';
import { Lang } from '../lib/i18n';
import { getConfig, updateConfig } from '../lib/api';

interface Asset {
  symbol: string; target_pct: number; current_pct: number;
  diff_pct: number; value_usdt: number; balance: number; price_usdt: number;
}
interface Props {
  assets: Asset[];
  loading?: boolean;
  lang: Lang;
  onRefresh?: () => void;
}

const PALETTE = [
  '#F7931A','#627EEA','#9945FF','#F3BA2F',
  '#00D4AA','#60A5FA','#A78BFA','#F472B6',
  '#FB923C','#34D399','#F59E0B','#38BDF8',
];

// Generate sparkline path from price data
function generateSparkline(data: number[], w: number, h: number): { path: string; area: string } {
  if (data.length < 2) return { path: '', area: '' };
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => ({
    x: (i / (data.length - 1)) * w,
    y: h - ((v - min) / range) * h,
  }));
  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const area = `${path} L${w},${h} L0,${h} Z`;
  return { path, area };
}

// Generate random walk data for demo chart
function genData(base: number, points: number): number[] {
  const arr: number[] = [base];
  for (let i = 1; i < points; i++) {
    arr.push(arr[i - 1] * (1 + (Math.random() - 0.48) * 0.03));
  }
  return arr;
}

function LiveChart({ symbol, color, price }: { symbol: string; color: string; price: number }) {
  const [data, setData] = useState<number[]>(() => genData(price, 40));
  const [period, setPeriod] = useState<'1H' | '1D' | '1W' | '1M' | '1Y'>('1D');
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setData(genData(price, 40));
  }, [period, price]);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      setData(prev => {
        const last = prev[prev.length - 1];
        const next = last * (1 + (Math.random() - 0.48) * 0.008);
        return [...prev.slice(1), next];
      });
    }, 1200);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);

  const current = data[data.length - 1];
  const first = data[0];
  const isUp = current >= first;
  const chartColor = isUp ? '#00D4AA' : '#FF7B72';
  const { path, area } = generateSparkline(data, 280, 70);
  const periods: Array<'1H' | '1D' | '1W' | '1M' | '1Y'> = ['1H', '1D', '1W', '1M', '1Y'];

  const fmtPrice = (n: number) =>
    n >= 1000
      ? '$' + n.toLocaleString('en-US', { maximumFractionDigits: 0 })
      : '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });

  // Last point position for live dot
  const lastPt = (() => {
    const pts = data.map((v, i) => {
      const min = Math.min(...data); const max = Math.max(...data);
      const range = max - min || 1;
      return { x: (i / (data.length - 1)) * 280, y: 70 - ((v - min) / range) * 70 };
    });
    return pts[pts.length - 1];
  })();

  return (
    <div
      className="px-3 pb-3 pt-1"
      style={{
        background: `linear-gradient(180deg, ${color}08 0%, transparent 100%)`,
        borderTop: `1px solid ${color}20`,
      }}
    >
      {/* Price + LIVE badge */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="live-badge">
            <span className="w-1.5 h-1.5 rounded-full pulse-dot" style={{ background: '#00D4AA' }} />
            LIVE
          </span>
          <span className="num font-bold text-sm" style={{ color: 'var(--text-main)' }}>
            {fmtPrice(current)}
          </span>
        </div>
        {/* Period tabs */}
        <div className="flex gap-1">
          {periods.map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className="text-[10px] font-bold px-2 py-0.5 rounded-lg transition-all"
              style={{
                background: period === p ? `${color}25` : 'transparent',
                color: period === p ? color : 'var(--text-muted)',
                border: period === p ? `1px solid ${color}40` : '1px solid transparent',
              }}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* SVG Chart */}
      <div className="relative rounded-xl overflow-hidden" style={{ height: 80 }}>
        <svg width="100%" height="80" viewBox="0 0 280 70" preserveAspectRatio="none">
          <defs>
            <linearGradient id={`grad-${symbol}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={chartColor} stopOpacity="0.35" />
              <stop offset="100%" stopColor={chartColor} stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {/* Area fill */}
          <path d={area} fill={`url(#grad-${symbol})`} />
          {/* Line */}
          <path
            d={path}
            fill="none"
            stroke={chartColor}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ filter: `drop-shadow(0 0 4px ${chartColor}80)` }}
          />
          {/* Live dot */}
          {lastPt && (
            <>
              <circle cx={lastPt.x} cy={lastPt.y} r="6" fill={chartColor} fillOpacity="0.2" className="live-dot-pulse" />
              <circle cx={lastPt.x} cy={lastPt.y} r="3.5" fill={chartColor} style={{ filter: `drop-shadow(0 0 4px ${chartColor})` }} />
            </>
          )}
        </svg>
      </div>
    </div>
  );
}

function MiniSparkline({ data, color, w = 60, h = 24 }: { data: number[]; color: string; w?: number; h?: number }) {
  const { path } = generateSparkline(data, w, h);
  if (!path) return null;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
        style={{ filter: `drop-shadow(0 0 3px ${color}80)` }} />
    </svg>
  );
}

function TableSkeleton() {
  return (
    <div className="space-y-2">
      {[1,2,3,4,5].map(i => (
        <div key={i} className="skeleton h-16 w-full rounded-2xl" />
      ))}
    </div>
  );
}

function DiffBadge({ diff }: { diff: number }) {
  const isPos = diff > 0.05;
  const isNeg = diff < -0.05;
  const Icon = isPos ? TrendingUp : isNeg ? TrendingDown : Minus;
  return (
    <span
      className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-bold num ${isPos ? 'trend-up' : isNeg ? 'trend-down' : ''}`}
      style={!isPos && !isNeg ? { color: 'var(--text-muted)', background: 'rgba(123,92,245,0.08)', border: '1px solid rgba(123,92,245,0.15)' } : {}}
    >
      <Icon size={9} />
      {isPos ? '+' : ''}{diff.toFixed(1)}%
    </span>
  );
}

function ReplaceModal({ symbol, lang, onClose, onDone }: { symbol: string; lang: Lang; onClose: () => void; onDone: () => void }) {
  const [newSymbol, setNewSymbol] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleReplace = async () => {
    const sym = newSymbol.trim().toUpperCase();
    if (!sym) { setError(lang === 'ar' ? 'أدخل رمز العملة' : 'Enter coin symbol'); return; }
    if (sym === symbol) { setError(lang === 'ar' ? 'نفس العملة الحالية' : 'Same symbol'); return; }
    setSaving(true); setError('');
    try {
      const cfg = await getConfig();
      const list: { symbol: string; allocation_pct: number }[] = cfg?.portfolio?.assets ?? [];
      const idx = list.findIndex((a: any) => a.symbol === symbol);
      if (idx === -1) throw new Error('Asset not found');
      if (list.some((a: any) => a.symbol === sym)) {
        setError(lang === 'ar' ? 'العملة موجودة بالفعل' : 'Symbol already exists');
        setSaving(false); return;
      }
      list[idx] = { ...list[idx], symbol: sym };
      await updateConfig({ portfolio: { ...cfg.portfolio, assets: list } });
      onDone();
    } catch (e: any) {
      setError(e?.message ?? 'Error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-t-3xl p-5 space-y-4"
        style={{
          background: 'rgba(15,10,40,0.98)',
          border: '1px solid rgba(123,92,245,0.3)',
          borderBottom: 'none',
          boxShadow: '0 -8px 40px rgba(123,92,245,0.2)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Handle */}
        <div className="w-10 h-1 rounded-full mx-auto" style={{ background: 'rgba(123,92,245,0.4)' }} />

        <div className="flex items-center justify-between">
          <h3 className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>
            🔄 {lang === 'ar' ? `استبدال ${symbol}` : `Replace ${symbol}`}
          </h3>
          <button onClick={onClose} className="p-1 rounded-lg" style={{ color: 'var(--text-muted)' }}>
            <X size={16} />
          </button>
        </div>

        <div>
          <label className="text-xs mb-1.5 block" style={{ color: 'var(--text-muted)' }}>
            {lang === 'ar' ? 'رمز العملة الجديدة' : 'New coin symbol'}
          </label>
          <input
            autoFocus
            value={newSymbol}
            onChange={e => setNewSymbol(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleReplace()}
            placeholder={lang === 'ar' ? 'مثال: SOL' : 'e.g. SOL'}
            className="input uppercase font-bold"
            style={{ borderColor: error ? '#FF7B72' : undefined }}
          />
          {error && <p className="text-[11px] mt-1" style={{ color: '#FF7B72' }}>{error}</p>}
        </div>

        <div className="flex gap-2">
          <button onClick={onClose} className="btn-secondary flex-1 !text-xs !min-h-[40px]">
            {lang === 'ar' ? 'إلغاء' : 'Cancel'}
          </button>
          <button
            onClick={handleReplace}
            disabled={saving}
            className="btn-accent flex-1 !text-xs !min-h-[40px] gap-1"
          >
            {saving
              ? <><RefreshCw size={11} className="spin" /> {lang === 'ar' ? 'جاري...' : 'Saving...'}</>
              : <><Check size={11} /> {lang === 'ar' ? 'استبدال' : 'Replace'}</>
            }
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AssetsTable({ assets, loading, lang, onRefresh }: Props) {
  const [deletingSymbol, setDeletingSymbol] = useState<string | null>(null);
  const [replaceSymbol,  setReplaceSymbol]  = useState<string | null>(null);
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  // Stable sparkline data per symbol
  const sparkRef = useRef<Record<string, number[]>>({});

  const getSparkData = useCallback((symbol: string, price: number) => {
    if (!sparkRef.current[symbol]) {
      sparkRef.current[symbol] = genData(price, 12);
    }
    return sparkRef.current[symbol];
  }, []);

  const handleDelete = async (symbol: string) => {
    setDeletingSymbol(symbol);
    try {
      const cfg = await getConfig();
      const list: { symbol: string; allocation_pct: number }[] = cfg?.portfolio?.assets ?? [];
      const remaining = list.filter((a: any) => a.symbol !== symbol);
      if (remaining.length < 2) {
        alert(lang === 'ar' ? 'يجب أن تبقى عملتان على الأقل' : 'At least 2 assets required');
        return;
      }
      const equalPct = parseFloat((100 / remaining.length).toFixed(2));
      const redistributed = remaining.map((a: any, i: number) => ({
        ...a,
        allocation_pct: i === remaining.length - 1
          ? parseFloat((100 - equalPct * (remaining.length - 1)).toFixed(2))
          : equalPct,
      }));
      await updateConfig({ portfolio: { ...cfg.portfolio, assets: redistributed } });
      setExpandedSymbol(null);
      onRefresh?.();
    } catch (e: any) {
      alert(e?.message ?? 'Error');
    } finally {
      setDeletingSymbol(null);
    }
  };

  if (loading) return <TableSkeleton />;
  if (!assets.length) {
    return (
      <div className="text-center py-10 text-sm" style={{ color: 'var(--text-muted)' }}>
        {lang === 'ar' ? 'لا توجد أصول بعد' : 'No assets yet'}
      </div>
    );
  }

  const fmtPrice = (n: number) =>
    n >= 1000
      ? '$' + n.toLocaleString('en-US', { maximumFractionDigits: 0 })
      : '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });

  return (
    <>
      <div className="space-y-2">
        {assets.map((a, i) => {
          const color = PALETTE[i % PALETTE.length];
          const isExpanded = expandedSymbol === a.symbol;
          const isDeleting = deletingSymbol === a.symbol;
          const sparkData = getSparkData(a.symbol, a.price_usdt);
          const sparkUp = sparkData[sparkData.length - 1] >= sparkData[0];

          return (
            <div
              key={a.symbol}
              className="rounded-2xl overflow-hidden transition-all duration-300"
              style={{
                border: `1px solid ${isExpanded ? color + '40' : 'rgba(123,92,245,0.15)'}`,
                background: isExpanded
                  ? `linear-gradient(135deg, ${color}08, rgba(15,10,40,0.9))`
                  : 'rgba(15,10,40,0.7)',
                boxShadow: isExpanded
                  ? `0 0 24px ${color}18, inset 0 1px 0 rgba(255,255,255,0.05)`
                  : 'inset 0 1px 0 rgba(255,255,255,0.04)',
                backdropFilter: 'blur(16px)',
              }}
            >
              {/* Main row — tap to expand */}
              <button
                className="w-full flex items-center gap-3 px-3 py-3 text-start"
                onClick={() => setExpandedSymbol(isExpanded ? null : a.symbol)}
              >
                {/* Coin icon */}
                <div className="shrink-0 relative w-9 h-9">
                  <img
                    src={`https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/32/color/${a.symbol.toLowerCase()}.png`}
                    alt={a.symbol}
                    className="w-9 h-9 rounded-full absolute inset-0"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none';
                      const fb = e.currentTarget.nextElementSibling as HTMLElement | null;
                      if (fb) fb.style.removeProperty('display');
                    }}
                  />
                  <div
                    className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-black absolute inset-0"
                    style={{
                      background: `linear-gradient(135deg, ${color}30, ${color}15)`,
                      border: `1px solid ${color}40`,
                      color,
                      display: 'none',
                      boxShadow: `0 0 10px ${color}30`,
                    }}
                  >
                    {a.symbol.slice(0, 2)}
                  </div>
                </div>

                {/* Symbol + allocation */}
                <div className="shrink-0 w-16">
                  <div className="font-bold text-sm leading-tight" style={{ color: 'var(--text-main)' }}>
                    {a.symbol}
                  </div>
                  <div className="text-[10px] leading-tight mt-0.5" style={{ color: 'var(--text-muted)' }}>
                    {a.target_pct.toFixed(0)}% {lang === 'ar' ? 'مخصص' : 'target'}
                  </div>
                  {/* Allocation bar */}
                  <div className="mt-1 h-1 rounded-full w-14" style={{ background: 'rgba(123,92,245,0.15)' }}>
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{
                        width: `${Math.min(a.current_pct / a.target_pct * 100, 100)}%`,
                        background: `linear-gradient(90deg, ${color}cc, ${color})`,
                        boxShadow: `0 0 6px ${color}60`,
                      }}
                    />
                  </div>
                </div>

                {/* Mini sparkline */}
                <div className="flex-1 flex justify-center">
                  <MiniSparkline
                    data={sparkData}
                    color={sparkUp ? '#00D4AA' : '#FF7B72'}
                    w={60} h={24}
                  />
                </div>

                {/* Price + change */}
                <div className="shrink-0 text-end">
                  <div className="num font-bold text-sm" style={{ color: 'var(--text-main)' }}>
                    {fmtPrice(a.price_usdt)}
                  </div>
                  <DiffBadge diff={a.diff_pct} />
                </div>
              </button>

              {/* Expanded: live chart + action buttons */}
              {isExpanded && (
                <div className="animate-fade-in">
                  <LiveChart symbol={a.symbol} color={color} price={a.price_usdt} />

                  {/* Action buttons */}
                  <div
                    className="flex items-center gap-2 px-3 py-2.5"
                    style={{ borderTop: `1px solid ${color}20` }}
                  >
                    <div
                      className="w-1 h-4 rounded-full shrink-0"
                      style={{ background: color, boxShadow: `0 0 6px ${color}` }}
                    />
                    <span className="text-[11px] font-bold flex-1" style={{ color }}>
                      {a.symbol}
                    </span>

                    <button
                      onClick={(e) => { e.stopPropagation(); setReplaceSymbol(a.symbol); setExpandedSymbol(null); }}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all"
                      style={{
                        background: 'rgba(96,165,250,0.12)',
                        color: '#60A5FA',
                        border: '1px solid rgba(96,165,250,0.25)',
                        boxShadow: '0 0 12px rgba(96,165,250,0.1)',
                      }}
                    >
                      <RefreshCw size={10} />
                      {lang === 'ar' ? 'استبدال' : 'Replace'}
                    </button>

                    <button
                      onClick={(e) => { e.stopPropagation(); handleDelete(a.symbol); }}
                      disabled={isDeleting}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all"
                      style={{
                        background: 'rgba(255,123,114,0.12)',
                        color: '#FF7B72',
                        border: '1px solid rgba(255,123,114,0.25)',
                        boxShadow: '0 0 12px rgba(255,123,114,0.1)',
                      }}
                    >
                      {isDeleting
                        ? <RefreshCw size={10} className="spin" />
                        : <Trash2 size={10} />
                      }
                      {lang === 'ar' ? 'حذف' : 'Delete'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {replaceSymbol && (
        <ReplaceModal
          symbol={replaceSymbol}
          lang={lang}
          onClose={() => setReplaceSymbol(null)}
          onDone={() => { setReplaceSymbol(null); onRefresh?.(); }}
        />
      )}
    </>
  );
}
