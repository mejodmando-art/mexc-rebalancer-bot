'use client';

import { useState, useRef, useCallback } from 'react';

interface Snapshot { ts: string; total_usdt: number; }
interface Props { snapshots: Snapshot[]; loading?: boolean; lang?: 'ar' | 'en'; }
type Range = '7d' | '30d' | '90d' | 'all';

const RANGES: { key: Range; label: string }[] = [
  { key: '7d', label: '7D' }, { key: '30d', label: '30D' },
  { key: '90d', label: '90D' }, { key: 'all', label: 'All' },
];

function ChartSkeleton() {
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {[1,2,3,4].map(i => <div key={i} className="skeleton h-7 w-12 rounded-lg" />)}
      </div>
      <div className="skeleton w-full rounded-xl" style={{ height: 180 }} />
    </div>
  );
}

function filterByRange(data: Snapshot[], range: Range): Snapshot[] {
  if (range === 'all' || !data.length) return data;
  const days = range === '7d' ? 7 : range === '30d' ? 30 : 90;
  const cutoff = Date.now() - days * 86400000;
  const filtered = data.filter(s => new Date(s.ts).getTime() >= cutoff);
  return filtered.length >= 2 ? filtered : data.slice(-Math.min(data.length, days * 2));
}

function formatTs(ts: string): string {
  try { return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); }
  catch { return ts; }
}

// Pure SVG area chart — zero dependencies
function SVGAreaChart({ data, color }: { data: { time: string; value: number }[]; color: string }) {
  const [tooltip, setTooltip] = useState<{ x: number; y: number; value: number; time: string } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const W = 600; const H = 160;
  const PAD = { top: 10, right: 10, bottom: 24, left: 50 };
  const chartW = W - PAD.left - PAD.right;
  const chartH = H - PAD.top - PAD.bottom;

  const values = data.map(d => d.value);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const range = maxV - minV || 1;

  const toX = (i: number) => PAD.left + (i / (data.length - 1)) * chartW;
  const toY = (v: number) => PAD.top + chartH - ((v - minV) / range) * chartH;

  const points = data.map((d, i) => `${toX(i)},${toY(d.value)}`).join(' ');
  const areaPath = `M ${toX(0)},${toY(data[0].value)} ` +
    data.slice(1).map((d, i) => `L ${toX(i+1)},${toY(d.value)}`).join(' ') +
    ` L ${toX(data.length-1)},${PAD.top + chartH} L ${toX(0)},${PAD.top + chartH} Z`;
  const linePath = `M ${points.split(' ').join(' L ')}`;

  // Y axis labels
  const yTicks = [minV, minV + range * 0.5, maxV];
  const fmt = (v: number) => v >= 1000 ? `$${(v/1000).toFixed(1)}K` : `$${v.toFixed(0)}`;

  // X axis labels (show ~4)
  const xStep = Math.max(1, Math.floor(data.length / 4));
  const xTicks = data.filter((_, i) => i % xStep === 0 || i === data.length - 1);

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const scaleX = W / rect.width;
    const mx = (e.clientX - rect.left) * scaleX;
    const idx = Math.round(((mx - PAD.left) / chartW) * (data.length - 1));
    const clamped = Math.max(0, Math.min(data.length - 1, idx));
    setTooltip({ x: toX(clamped), y: toY(data[clamped].value), value: data[clamped].value, time: data[clamped].time });
  }, [data]);

  return (
    <div className="relative w-full" style={{ aspectRatio: `${W}/${H}` }}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-full"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setTooltip(null)}
      >
        <defs>
          <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.3" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {yTicks.map((v, i) => (
          <line key={i} x1={PAD.left} y1={toY(v)} x2={W - PAD.right} y2={toY(v)}
                stroke="var(--border)" strokeOpacity="0.4" strokeDasharray="3 3" />
        ))}

        {/* Area fill */}
        <path d={areaPath} fill="url(#grad)" />

        {/* Line */}
        <polyline points={points} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />

        {/* Y axis labels */}
        {yTicks.map((v, i) => (
          <text key={i} x={PAD.left - 4} y={toY(v) + 4} textAnchor="end"
                fontSize="9" fill="var(--text-muted)">{fmt(v)}</text>
        ))}

        {/* X axis labels */}
        {xTicks.map((d, i) => {
          const idx = data.indexOf(d);
          return (
            <text key={i} x={toX(idx)} y={H - 4} textAnchor="middle"
                  fontSize="9" fill="var(--text-muted)">{d.time}</text>
          );
        })}

        {/* Tooltip */}
        {tooltip && (
          <>
            <line x1={tooltip.x} y1={PAD.top} x2={tooltip.x} y2={PAD.top + chartH}
                  stroke={color} strokeWidth="1" strokeDasharray="4 4" strokeOpacity="0.6" />
            <circle cx={tooltip.x} cy={tooltip.y} r="4" fill={color} stroke="var(--bg-card)" strokeWidth="2" />
          </>
        )}
      </svg>

      {/* Tooltip box */}
      {tooltip && (
        <div className="absolute pointer-events-none card p-2 text-xs"
             style={{
               left: `${(tooltip.x / W) * 100}%`,
               top: `${(tooltip.y / H) * 100}%`,
               transform: 'translate(-50%, -110%)',
               minWidth: 110,
             }}>
          <div style={{ color: 'var(--text-muted)' }}>{tooltip.time}</div>
          <div className="num font-bold" style={{ color: 'var(--accent)' }}>
            ${tooltip.value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
      )}
    </div>
  );
}

export default function PerformanceChart({ snapshots, loading, lang = 'ar' }: Props) {
  const [range, setRange] = useState<Range>('30d');

  if (loading) return <ChartSkeleton />;

  const filtered = filterByRange(snapshots, range);
  if (filtered.length < 2) {
    return (
      <div className="flex flex-col items-center justify-center h-48 gap-2">
        <div className="text-sm" style={{ color: 'var(--text-muted)' }}>
          {lang === 'ar' ? 'لا توجد بيانات كافية بعد' : 'Not enough data yet'}
        </div>
      </div>
    );
  }

  const chartData = filtered.map(s => ({ time: formatTs(s.ts), value: s.total_usdt }));
  const first = chartData[0].value;
  const last  = chartData[chartData.length - 1].value;
  const isUp  = last >= first;
  const pct   = first > 0 ? ((last - first) / first * 100).toFixed(2) : '0.00';
  const color = isUp ? '#00D4AA' : '#FF7B72';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <span className="num font-bold text-lg" style={{ color: 'var(--text-main)' }}>
            ${last.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          <span className={`trend-badge ${isUp ? 'trend-up' : 'trend-down'}`}>
            {isUp ? '+' : ''}{pct}%
          </span>
        </div>
        <div className="flex gap-1 p-1 rounded-lg" style={{ background: 'var(--bg-input)' }}>
          {RANGES.map(r => (
            <button key={r.key} onClick={() => setRange(r.key)}
              className="px-3 py-1 rounded-md text-xs font-semibold transition-all"
              style={{
                background: range === r.key ? 'var(--bg-card)' : 'transparent',
                color: range === r.key ? 'var(--accent)' : 'var(--text-muted)',
                boxShadow: range === r.key ? 'var(--shadow-card)' : 'none',
              }}>
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <SVGAreaChart data={chartData} color={color} />
    </div>
  );
}
