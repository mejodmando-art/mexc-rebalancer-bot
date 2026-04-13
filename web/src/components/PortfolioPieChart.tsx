'use client';

import { useState, useEffect } from 'react';

interface Asset { symbol: string; current_pct: number; value_usdt: number; }
interface Props { assets: Asset[]; totalUsdt: number; loading?: boolean; lang?: 'ar' | 'en'; }

const PALETTE = [
  '#00D4AA','#00A88F','#58A6FF','#3B82F6',
  '#A78BFA','#8B5CF6','#F472B6','#EC4899',
  '#FB923C','#F97316','#FACC15','#EAB308',
];

function PieChartSkeleton() {
  return (
    <div className="flex flex-col items-center gap-4">
      <div className="skeleton w-48 h-48 rounded-full" />
      <div className="flex flex-wrap gap-2 justify-center">
        {[1,2,3,4].map(i => <div key={i} className="skeleton h-5 w-16 rounded-full" />)}
      </div>
    </div>
  );
}

// Lazy-loaded chart to avoid SSR/hydration issues with Recharts
function PieChartInner({ assets, totalUsdt, lang }: Omit<Props, 'loading'>) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [RC, setRC] = useState<any>(null);

  useEffect(() => {
    // Load recharts only on client after mount
    import('recharts').then(mod => setRC(mod));
  }, []);

  if (!RC) return <PieChartSkeleton />;

  const { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Sector } = RC;

  const data = assets.map((a, i) => ({ ...a, fill: PALETTE[i % PALETTE.length] }));

  const renderActiveShape = (props: any) => {
    const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill } = props;
    return (
      <g>
        <Sector cx={cx} cy={cy} innerRadius={innerRadius - 4} outerRadius={outerRadius + 8}
                startAngle={startAngle} endAngle={endAngle} fill={fill} opacity={0.95} />
      </g>
    );
  };

  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    return (
      <div className="card p-3 text-sm" style={{ minWidth: 140 }}>
        <div className="flex items-center gap-2 mb-1">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: d.fill }} />
          <span className="font-bold" style={{ color: 'var(--text-main)' }}>{d.symbol}</span>
        </div>
        <div className="num font-semibold" style={{ color: 'var(--accent)' }}>{d.current_pct.toFixed(2)}%</div>
        <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
          ${d.value_usdt.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative w-full" style={{ height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data} cx="50%" cy="50%"
              innerRadius={60} outerRadius={90} paddingAngle={2}
              dataKey="current_pct"
              activeIndex={activeIndex ?? undefined}
              activeShape={renderActiveShape}
              onMouseEnter={(_: any, i: number) => setActiveIndex(i)}
              onMouseLeave={() => setActiveIndex(null)}
              animationBegin={0} animationDuration={800}
            >
              {data.map((d, i) => (
                <Cell key={i} fill={d.fill} stroke="transparent"
                      opacity={activeIndex === null || activeIndex === i ? 1 : 0.6} />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <div className="text-[10px] font-semibold uppercase tracking-wider mb-0.5" style={{ color: 'var(--text-muted)' }}>
            {lang === 'ar' ? 'الإجمالي' : 'Total'}
          </div>
          <div className="num font-bold text-lg leading-tight" style={{ color: 'var(--text-main)' }}>
            ${totalUsdt >= 1000 ? `${(totalUsdt / 1000).toFixed(1)}K` : totalUsdt.toFixed(0)}
          </div>
          <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>USDT</div>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 justify-center w-full">
        {data.map((d, i) => (
          <div key={d.symbol}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold cursor-pointer transition-all"
            style={{
              background: activeIndex === i ? `${d.fill}22` : 'var(--bg-input)',
              border: `1px solid ${activeIndex === i ? d.fill : 'var(--border)'}`,
              color: activeIndex === i ? d.fill : 'var(--text-muted)',
            }}
            onMouseEnter={() => setActiveIndex(i)}
            onMouseLeave={() => setActiveIndex(null)}
          >
            <span className="w-2 h-2 rounded-full" style={{ background: d.fill }} />
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
  return <PieChartInner assets={assets} totalUsdt={totalUsdt} lang={lang} />;
}
