'use client';

import { useState } from 'react';
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
  '#00D4AA','#60A5FA','#A78BFA','#F472B6',
  '#FB923C','#34D399','#F59E0B','#38BDF8',
  '#C084FC','#F87171','#4ADE80','#FBBF24',
];

function TableSkeleton() {
  return (
    <div className="space-y-2">
      {[1,2,3,4,5].map(i => (
        <div key={i} className="skeleton h-16 w-full rounded-xl" />
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
      style={!isPos && !isNeg ? { color: 'var(--text-muted)', background: 'var(--bg-input)' } : {}}
    >
      <Icon size={9} />
      {isPos ? '+' : ''}{diff.toFixed(1)}%
    </span>
  );
}

function ReplaceModal({
  symbol, lang, onClose, onDone,
}: { symbol: string; lang: Lang; onClose: () => void; onDone: () => void }) {
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
      style={{ background: 'rgba(0,0,0,0.6)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-t-2xl p-5 space-y-4"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>
            {lang === 'ar' ? `استبدال ${symbol}` : `Replace ${symbol}`}
          </h3>
          <button onClick={onClose} className="p-1 rounded-lg" style={{ color: 'var(--text-muted)' }}>
            <X size={16} />
          </button>
        </div>
        <div>
          <label className="text-xs mb-1 block" style={{ color: 'var(--text-muted)' }}>
            {lang === 'ar' ? 'رمز العملة الجديدة' : 'New coin symbol'}
          </label>
          <input
            autoFocus
            value={newSymbol}
            onChange={e => setNewSymbol(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleReplace()}
            placeholder={lang === 'ar' ? 'مثال: SOL' : 'e.g. SOL'}
            className="w-full px-3 py-2 rounded-xl text-sm font-bold uppercase"
            style={{
              background: 'var(--bg-input)',
              border: `1px solid ${error ? '#F47368' : 'var(--border)'}`,
              color: 'var(--text-main)',
              outline: 'none',
            }}
          />
          {error && <p className="text-[11px] mt-1" style={{ color: '#F47368' }}>{error}</p>}
        </div>
        <div className="flex gap-2">
          <button onClick={onClose} className="btn-secondary flex-1 !text-xs !min-h-[38px]">
            {lang === 'ar' ? 'إلغاء' : 'Cancel'}
          </button>
          <button
            onClick={handleReplace}
            disabled={saving}
            className="btn-accent flex-1 !text-xs !min-h-[38px] gap-1"
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
  const [actionSymbol,   setActionSymbol]   = useState<string | null>(null);

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
      setActionSymbol(null);
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

  const fmtVal   = (n: number) => '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtPrice = (n: number) =>
    n >= 1000
      ? '$' + n.toLocaleString('en-US', { maximumFractionDigits: 0 })
      : '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });

  return (
    <>
      <div className="space-y-2">
        {assets.map((a, i) => {
          const color = PALETTE[i % PALETTE.length];
          const showActions = actionSymbol === a.symbol;
          const isDeleting = deletingSymbol === a.symbol;

          return (
            <div
              key={a.symbol}
              className="rounded-2xl overflow-hidden"
              style={{
                border: `1px solid ${showActions ? color + '50' : 'var(--border)'}`,
                transition: 'all 0.2s ease',
                boxShadow: showActions ? `0 0 16px ${color}18` : 'none',
              }}
            >
              {/* Main row */}
              <div
                className="flex items-center gap-3 px-3 py-3"
                style={{
                  background: showActions
                    ? `linear-gradient(135deg, ${color}08, var(--bg-input))`
                    : 'var(--bg-input)',
                  transition: 'background 0.2s ease',
                }}
              >
                {/* Coin icon */}
                <div className="shrink-0 relative w-8 h-8">
                  <img
                    src={`https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/32/color/${a.symbol.toLowerCase()}.png`}
                    alt={a.symbol}
                    className="w-8 h-8 rounded-full absolute inset-0"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none';
                      const fb = e.currentTarget.nextElementSibling as HTMLElement | null;
                      if (fb) fb.style.removeProperty('display');
                    }}
                  />
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold absolute inset-0"
                    style={{ background: `${color}22`, color, display: 'none' }}
                  >
                    {a.symbol.slice(0, 2)}
                  </div>
                </div>

                {/* Symbol + price */}
                <div className="shrink-0 w-14">
                  <div className="font-bold text-sm leading-tight" style={{ color: 'var(--text-main)' }}>
                    {a.symbol}
                  </div>
                  <div className="num text-[10px] leading-tight" style={{ color: 'var(--text-muted)' }}>
                    {fmtPrice(a.price_usdt)}
                  </div>
                </div>

                {/* Bar + percentages */}
                <div className="flex-1 min-w-0">
                  <div className="relative h-2 rounded-full mb-1.5" style={{ background: 'var(--border)' }}>
                    <div
                      className="absolute inset-y-0 start-0 rounded-full transition-all duration-700"
                      style={{
                        width: `${Math.min(a.current_pct, 100)}%`,
                        background: `linear-gradient(90deg, ${color}cc, ${color})`,
                        boxShadow: a.current_pct > 0 ? `0 0 8px ${color}60` : 'none',
                      }}
                    />
                    <div
                      className="absolute top-1/2 -translate-y-1/2 w-0.5 h-3.5 rounded-full opacity-60"
                      style={{ insetInlineStart: `${Math.min(a.target_pct, 100)}%`, background: 'var(--text-muted)' }}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="num text-[11px] font-bold" style={{ color }}>
                      {a.current_pct.toFixed(1)}%
                    </span>
                    <span className="num text-[10px]" style={{ color: 'var(--text-muted)' }}>
                      /{a.target_pct.toFixed(0)}%
                    </span>
                  </div>
                </div>

                {/* Value + diff */}
                <div className="shrink-0 flex flex-col items-end gap-0.5">
                  <span className="num font-bold text-sm" style={{ color: 'var(--text-main)' }}>
                    {fmtVal(a.value_usdt)}
                  </span>
                  <DiffBadge diff={a.diff_pct} />
                </div>

                {/* Options toggle */}
                <button
                  onClick={() => setActionSymbol(showActions ? null : a.symbol)}
                  className="shrink-0 w-7 h-7 rounded-xl flex items-center justify-center transition-all"
                  style={{
                    background: showActions ? `${color}25` : 'var(--bg-card)',
                    border: `1px solid ${showActions ? color + '50' : 'var(--border)'}`,
                    color: showActions ? color : 'var(--text-muted)',
                    boxShadow: showActions ? `0 0 10px ${color}30` : 'none',
                  }}
                >
                  {showActions
                    ? <X size={12} />
                    : <span className="text-[13px] leading-none font-bold" style={{ letterSpacing: '1px' }}>···</span>
                  }
                </button>
              </div>

              {/* Action bar */}
              {showActions && (
                <div
                  className="flex items-center gap-2 px-3 py-2.5"
                  style={{
                    background: `linear-gradient(135deg, ${color}10, ${color}06)`,
                    borderTop: `1px solid ${color}25`,
                  }}
                >
                  <div
                    className="w-1 h-4 rounded-full shrink-0"
                    style={{ background: color, boxShadow: `0 0 6px ${color}` }}
                  />
                  <span className="text-[11px] font-semibold flex-1" style={{ color }}>
                    {a.symbol}
                  </span>

                  <button
                    onClick={() => { setReplaceSymbol(a.symbol); setActionSymbol(null); }}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all"
                    style={{
                      background: 'rgba(96,165,250,0.12)',
                      color: '#60A5FA',
                      border: '1px solid rgba(96,165,250,0.25)',
                    }}
                  >
                    <RefreshCw size={10} />
                    {lang === 'ar' ? 'استبدال' : 'Replace'}
                  </button>

                  <button
                    onClick={() => handleDelete(a.symbol)}
                    disabled={isDeleting}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all"
                    style={{
                      background: 'rgba(255,123,114,0.12)',
                      color: '#FF7B72',
                      border: '1px solid rgba(255,123,114,0.25)',
                    }}
                  >
                    {isDeleting
                      ? <RefreshCw size={10} className="spin" />
                      : <Trash2 size={10} />
                    }
                    {lang === 'ar' ? 'حذف' : 'Delete'}
                  </button>
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
