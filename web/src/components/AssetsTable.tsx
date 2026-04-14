'use client';

import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { Lang, tr } from '../lib/i18n';

interface Asset {
  symbol: string; target_pct: number; current_pct: number;
  diff_pct: number; value_usdt: number; balance: number; price_usdt: number;
}
interface Props { assets: Asset[]; loading?: boolean; lang: Lang; }

const PALETTE = [
  '#00D4AA','#58A6FF','#A78BFA','#F472B6',
  '#FB923C','#FACC15','#00A88F','#3B82F6',
  '#8B5CF6','#EC4899','#F97316','#EAB308',
];

function TableSkeleton() {
  return (
    <div className="space-y-2">
      {[1,2,3,4,5].map(i => (
        <div key={i} className="skeleton h-12 w-full rounded-xl" />
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

export default function AssetsTable({ assets, loading, lang }: Props) {
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
    <div className="space-y-2">
      {assets.map((a, i) => {
        const color = PALETTE[i % PALETTE.length];
        return (
          <div
            key={a.symbol}
            className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
            style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}
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
          </div>
        );
      })}
    </div>
  );
}
