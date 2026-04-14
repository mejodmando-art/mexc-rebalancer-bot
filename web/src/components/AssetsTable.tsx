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
  '#00D4AA','#58A6FF','#A78BFA','#F472B6',
  '#FB923C','#FACC15','#00A88F','#3B82F6',
  '#8B5CF6','#EC4899','#F97316','#EAB308',
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
              className="rounded-xl overflow-hidden"
              style={{
                border: `1px solid ${showActions ? color + '55' : 'var(--border)'}`,
                transition: 'border-color 0.2s',
              }}
            >
              {/* Main row */}
              <div className="flex items-center gap-3 px-3 py-2.5" style={{ background: 'var(--bg-input)' }}>
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
                  <div className="relative h-1.5 rounded-full mb-1" style={{ background: 'var(--border)' }}>
                    <div
                      className="absolute inset-y-0 start-0 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(a.current_pct, 100)}%`, background: color }}
                    />
                    <div
                      className="absolute top-1/2 -translate-y-1/2 w-px h-3 opacity-50"
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
                  className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center transition-all"
                  style={{
                    background: showActions ? `${color}22` : 'var(--border)',
                    color: showActions ? color : 'var(--text-muted)',
                  }}
                >
                  {showActions
                    ? <X size={13} />
                    : <span className="text-[15px] leading-none font-bold tracking-widest">···</span>
                  }
                </button>
              </div>

              {/* Action bar */}
              {showActions && (
                <div
                  className="flex items-center gap-2 px-3 py-2"
                  style={{ background: `${color}0d`, borderTop: `1px solid ${color}33` }}
                >
                  <span className="text-[11px] flex-1" style={{ color: 'var(--text-muted)' }}>
                    {lang === 'ar' ? `إجراء على ${a.symbol}` : `Action on ${a.symbol}`}
                  </span>

                  <button
                    onClick={() => { setReplaceSymbol(a.symbol); setActionSymbol(null); }}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold"
                    style={{ background: '#58A6FF1a', color: '#58A6FF', border: '1px solid #58A6FF33' }}
                  >
                    <RefreshCw size={11} />
                    {lang === 'ar' ? 'استبدال' : 'Replace'}
                  </button>

                  <button
                    onClick={() => handleDelete(a.symbol)}
                    disabled={isDeleting}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold"
                    style={{ background: '#F473681a', color: '#F47368', border: '1px solid #F4736833' }}
                  >
                    {isDeleting
                      ? <RefreshCw size={11} className="spin" />
                      : <Trash2 size={11} />
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
