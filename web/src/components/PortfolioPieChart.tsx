'use client';

import { useState } from 'react';

interface Asset { symbol: string; current_pct: number; value_usdt: number; }
interface Props { assets: Asset[]; totalUsdt: number; loading?: boolean; lang?: 'ar' | 'en'; }

const PALETTE = [
  '#00D4AA','#58A6FF','#A78BFA','#F472B6',
  '#FB923C','#FACC15','#00A88F','#3B82F6',
  '#8B5CF6','#EC4899','#F97316','#EAB308',
];

function PieChartSkeleton() {
  return (
    <div className="flex flex-col items-center gap-4">
      <div className="skeleton w-44 h-44 rounded-full" />
      <div className="flex flex-wrap gap-2 justify-center">
        {[1,2,3,4].map(i => <div key={i} className="skeleton h-5 w-16 rounded-full" />)}
      </div>
    </div>
  );
}

// Pure SVG donut chart — no external dependencies
function DonutChart({ data, total, lang }: { data: any[]; total: number; lang: string }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const size = 200;
  const cx = size / 2;
  const cy = size / 2;
  const outerR = 80;
  const innerR = 52;

  // Build arc paths
  let cumAngle = -90; // start from top
  const slices = data.map((d, i) => {
    const angle = (d.current_pct / 100) * 360;
    const startAngle = cumAngle;
    const endAngle = cumAngle + angle;
    cumAngle += angle;

    const toRad = (deg: number) => (deg * Math.PI) / 180;
    const x1 = cx + outerR * Math.cos(toRad(startAngle));
    const y1 = cy + outerR * Math.sin(toRad(startAngle));
    const x2 = cx + outerR * Math.cos(toRad(endAngle));
    const y2 = cy + outerR * Math.sin(toRad(endAngle));
    const ix1 = cx + innerR * Math.cos(toRad(endAngle));
    const iy1 = cy + innerR * Math.sin(toRad(endAngle));
    const ix2 = cx + innerR * Math.cos(toRad(startAngle));
    const iy2 = cy + innerR * Math.sin(toRad(startAngle));
    const largeArc = angle > 180 ? 1 : 0;

    const path = [
      `M ${x1} ${y1}`,
      `A ${outerR} ${outerR} 0 ${largeArc} 1 ${x2} ${y2}`,
      `L ${ix1} ${iy1}`,
      `A ${innerR} ${innerR} 0 ${largeArc} 0 ${ix2} ${iy2}`,
      'Z',
    ].join(' ');

    return { ...d, path, color: PALETTE[i % PALETTE.length] };
  });

  const fmt = (n: number) => n >= 1000 ? `${(n/1000).toFixed(1)}K` : n.toFixed(0);

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {slices.map((s, i) => (
            <path
              key={i}
              d={s.path}
              fill={s.color}
              opacity={hovered === null || hovered === i ? 1 : 0.5}
              style={{ cursor: 'pointer', transition: 'opacity 0.2s' }}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
            />
          ))}
          {/* Gap between slices */}
          <circle cx={cx} cy={cy} r={innerR} fill="var(--bg-card)" />
        </svg>

        {/* Center text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          {hovered !== null ? (
            <>
              <div className="text-[10px] font-bold uppercase tracking-wider" style={{ color: slices[hovered]?.color }}>
                {slices[hovered]?.symbol}
              </div>
              <div className="num font-bold text-base" style={{ color: 'var(--text-main)' }}>
                {slices[hovered]?.current_pct.toFixed(1)}%
              </div>
              <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                ${fmt(slices[hovered]?.value_usdt)}
              </div>
            </>
          ) : (
            <>
              <div className="text-[10px] font-semibold uppercase tracking-wider mb-0.5" style={{ color: 'var(--text-muted)' }}>
                {lang === 'ar' ? 'الإجمالي' : 'Total'}
              </div>
              <div className="num font-bold text-lg leading-tight" style={{ color: 'var(--text-main)' }}>
                ${fmt(total)}
              </div>
              <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>USDT</div>
            </>
          )}
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-2 justify-center w-full">
        {slices.map((d, i) => (
          <div key={d.symbol}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold cursor-pointer transition-all"
            style={{
              background: hovered === i ? `${d.color}22` : 'var(--bg-input)',
              border: `1px solid ${hovered === i ? d.color : 'var(--border)'}`,
              color: hovered === i ? d.color : 'var(--text-muted)',
            }}
            onMouseEnter={() => setHovered(i)}
            onMouseLeave={() => setHovered(null)}
          >
            <span className="w-2 h-2 rounded-full" style={{ background: d.color }} />
            {d.symbol}
            <span className="num">{d.current_pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function PortfolioPieChart({ assets, totalUsdt, loading, lang = 'ar' }: Props) {
  if (loading) return <PieChartSkeleton />;
  if (!assets.length) {
    return (
      <div className="flex items-center justify-center h-48 text-sm" style={{ color: 'var(--text-muted)' }}>
        {lang === 'ar' ? 'لا توجد بيانات' : 'No data'}
      </div>
    );
  }
  return <DonutChart data={assets} total={totalUsdt} lang={lang} />;
}
