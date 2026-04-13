'use client';

import { Download, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { exportCsvUrl } from '../lib/api';
import { Lang, tr } from '../lib/i18n';

interface Asset {
  symbol: string; target_pct: number; current_pct: number;
  diff_pct: number; value_usdt: number; balance: number; price_usdt: number;
}
interface Props { assets: Asset[]; loading?: boolean; lang: Lang; }

const PALETTE = [
  '#00D4AA','#00A88F','#58A6FF','#3B82F6',
  '#A78BFA','#8B5CF6','#F472B6','#EC4899',
  '#FB923C','#F97316','#FACC15','#EAB308',
];

function TableSkeleton() {
  return (
    <div className="space-y-2">
      {[1,2,3,4].map(i => <div key={i} className="skeleton h-12 w-full rounded-xl" />)}
    </div>
  );
}

function DiffCell({ diff }: { diff: number }) {
  const isPos = diff > 0.05;
  const isNeg = diff < -0.05;
  const Icon = isPos ? TrendingUp : isNeg ? TrendingDown : Minus;
  return (
    <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold num
      ${isPos ? 'trend-up' : isNeg ? 'trend-down' : ''}`}
      style={!isPos && !isNeg ? { color: 'var(--text-muted)', background: 'var(--bg-input)' } : {}}>
      <Icon size={10} />
      {isPos ? '+' : ''}{diff.toFixed(2)}%
    </div>
  );
}

function MiniBar({ pct, color }: { pct: number; color: string }) {
  return (
    <div className="w-full h-1 rounded-full mt-1" style={{ background: 'var(--border)' }}>
      <div className="h-full rounded-full transition-all duration-500"
           style={{ width: `${Math.min(pct, 100)}%`, background: color }} />
    </div>
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

  return (
    <div>
      <div className="flex justify-end mb-3">
        <a href={exportCsvUrl()} download className="btn-secondary !px-3 !min-h-[34px] !text-xs gap-1.5">
          <Download size={13} />
          {tr('exportCsv', lang)}
        </a>
      </div>

      <div className="overflow-x-auto rounded-xl" style={{ border: '1px solid var(--border)' }}>
        <table className="data-table mobile-card-table">
          <thead>
            <tr>
              <th>{tr('coin', lang)}</th>
              <th>{tr('target', lang)}</th>
              <th>{tr('current', lang)}</th>
              <th>{tr('diff', lang)}</th>
              <th>{tr('valueUsdt', lang)}</th>
              <th>{tr('balancePrice', lang)}</th>
            </tr>
          </thead>
          <tbody>
            {assets.map((a, i) => {
              const color = PALETTE[i % PALETTE.length];
              return (
                <tr key={a.symbol} className="animate-fade-up" style={{ animationDelay: `${i * 0.04}s` }}>
                  <td data-label={tr('coin', lang)}>
                    <div className="flex items-center gap-2.5">
                      <div className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold shrink-0"
                           style={{ background: `${color}20`, color }}>
                        {a.symbol.slice(0, 2)}
                      </div>
                      <div>
                        <div className="font-semibold text-sm" style={{ color: 'var(--text-main)' }}>{a.symbol}</div>
                        <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>USDT</div>
                      </div>
                    </div>
                  </td>
                  <td data-label={tr('target', lang)}>
                    <div className="num font-semibold text-sm" style={{ color: 'var(--text-muted)' }}>{a.target_pct.toFixed(1)}%</div>
                    <MiniBar pct={a.target_pct} color="var(--border)" />
                  </td>
                  <td data-label={tr('current', lang)}>
                    <div className="num font-semibold text-sm" style={{ color }}>{a.current_pct.toFixed(1)}%</div>
                    <MiniBar pct={a.current_pct} color={color} />
                  </td>
                  <td data-label={tr('diff', lang)}><DiffCell diff={a.diff_pct} /></td>
                  <td data-label={tr('valueUsdt', lang)}>
                    <div className="num font-semibold text-sm" style={{ color: 'var(--text-main)' }}>
                      ${a.value_usdt.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                  </td>
                  <td data-label={tr('balancePrice', lang)}>
                    <div className="num text-xs" style={{ color: 'var(--text-main)' }}>
                      {a.balance.toLocaleString('en-US', { maximumFractionDigits: 6 })}
                    </div>
                    <div className="num text-[11px]" style={{ color: 'var(--text-muted)' }}>
                      @${a.price_usdt.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
