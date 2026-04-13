'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts';

interface Snapshot {
  ts: string;
  total_usdt: number;
}

interface Props {
  snapshots: Snapshot[];
  loading?: boolean;
  lang?: 'ar' | 'en';
}

type Range = '7d' | '30d' | '90d' | 'all';

function ChartSkeleton() {
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {[1,2,3,4].map(i => <div key={i} className="skeleton h-7 w-12 rounded-lg" />)}
      </div>
      <div className="skeleton w-full rounded-xl" style={{ height: 200 }} />
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const val: number = payload[0].value;
  return (
    <div className="card p-3 text-sm" style={{ minWidth: 150 }}>
      <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div className="num font-bold text-base" style={{ color: 'var(--accent)' }}>
        ${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
    </div>
  );
};

const RANGES: { key: Range; label: string }[] = [
  { key: '7d',  label: '7D' },
  { key: '30d', label: '30D' },
  { key: '90d', label: '90D' },
  { key: 'all', label: 'All' },
];

function filterByRange(data: Snapshot[], range: Range): Snapshot[] {
  if (range === 'all' || !data.length) return data;
  const days = range === '7d' ? 7 : range === '30d' ? 30 : 90;
  const cutoff = Date.now() - days * 86400000;
  const filtered = data.filter(s => new Date(s.ts).getTime() >= cutoff);
  return filtered.length >= 2 ? filtered : data.slice(-Math.min(data.length, days * 2));
}

function formatTs(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch { return ts; }
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
        <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {lang === 'ar' ? 'ستظهر البيانات بعد أول Rebalance' : 'Data will appear after first rebalance'}
        </div>
      </div>
    );
  }

  const chartData = filtered.map(s => ({
    time: formatTs(s.ts),
    value: s.total_usdt,
  }));

  const first = chartData[0].value;
  const last  = chartData[chartData.length - 1].value;
  const isUp  = last >= first;
  const pct   = first > 0 ? ((last - first) / first * 100).toFixed(2) : '0.00';
  const color = isUp ? '#00D4AA' : '#FF7B72';

  const minVal = Math.min(...chartData.map(d => d.value));
  const maxVal = Math.max(...chartData.map(d => d.value));
  const padding = (maxVal - minVal) * 0.1 || 10;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
      className="space-y-4"
    >
      {/* Header row */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <span className="num font-bold text-lg" style={{ color: 'var(--text-main)' }}>
            ${last.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          <span className={`trend-badge ${isUp ? 'trend-up' : 'trend-down'}`}>
            {isUp ? '+' : ''}{pct}%
          </span>
        </div>
        {/* Range selector */}
        <div className="flex gap-1 p-1 rounded-lg" style={{ background: 'var(--bg-input)' }}>
          {RANGES.map(r => (
            <button
              key={r.key}
              onClick={() => setRange(r.key)}
              className="px-3 py-1 rounded-md text-xs font-semibold transition-all"
              style={{
                background: range === r.key ? 'var(--bg-card)' : 'transparent',
                color: range === r.key ? 'var(--accent)' : 'var(--text-muted)',
                boxShadow: range === r.key ? 'var(--shadow-card)' : 'none',
              }}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div style={{ height: 200 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor={color} stopOpacity={0.3} />
                <stop offset="100%" stopColor={color} stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" strokeOpacity={0.4} vertical={false} />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[minVal - padding, maxVal + padding]}
              tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={v => `$${v >= 1000 ? `${(v/1000).toFixed(1)}K` : v.toFixed(0)}`}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ stroke: color, strokeWidth: 1, strokeDasharray: '4 4' }} />
            <ReferenceLine y={first} stroke="var(--border)" strokeDasharray="4 4" strokeOpacity={0.6} />
            <Area
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              fill="url(#areaGrad)"
              dot={false}
              activeDot={{ r: 5, fill: color, stroke: 'var(--bg-card)', strokeWidth: 2 }}
              animationDuration={600}
              animationEasing="ease-out"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </motion.div>
  );
}
