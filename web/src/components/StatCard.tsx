'use client';

import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string;
  change?: string;
  changePositive?: boolean | null;
  icon: React.ElementType;
  iconColor?: string;
  loading?: boolean;
  delay?: number;
}

export function StatCardSkeleton() {
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between mb-4">
        <div className="skeleton h-3 w-20 rounded-full" />
        <div className="skeleton w-10 h-10 rounded-2xl" />
      </div>
      <div className="skeleton h-8 w-28 rounded-lg mb-3" />
      <div className="skeleton h-5 w-16 rounded-full" />
    </div>
  );
}

export default function StatCard({ title, value, change, changePositive, icon: Icon, iconColor, loading, delay = 0 }: StatCardProps) {
  if (loading) return <StatCardSkeleton />;

  const isPositive = changePositive === true;
  const isNegative = changePositive === false;
  const TrendIcon = isPositive ? TrendingUp : isNegative ? TrendingDown : Minus;
  const color = iconColor ?? 'var(--accent)';

  return (
    <div
      className="card card-hover p-4 cursor-default animate-fade-up relative overflow-hidden"
      style={{ animationDelay: `${delay}s` }}
    >
      {/* Top accent line */}
      <div
        className="absolute top-0 left-0 right-0 h-px"
        style={{ background: `linear-gradient(90deg, transparent, ${color}55, transparent)` }}
      />

      {/* Icon + title */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
          {title}
        </span>
        <div
          className="w-9 h-9 rounded-2xl flex items-center justify-center shrink-0"
          style={{ background: `${color}18`, border: `1px solid ${color}28`, boxShadow: `0 0 14px ${color}18` }}
        >
          <Icon size={16} style={{ color }} />
        </div>
      </div>

      {/* Value */}
      <div className="stat-value mb-2.5" style={{ color: 'var(--text-main)', letterSpacing: '-0.03em' }}>
        {value}
      </div>

      {/* Badge */}
      {change && (
        <div
          className="trend-badge"
          style={
            isPositive
              ? { color: '#00D4AA', background: 'rgba(0,212,170,0.1)', border: '1px solid rgba(0,212,170,0.2)' }
              : isNegative
              ? { color: '#FF7B72', background: 'rgba(255,123,114,0.1)', border: '1px solid rgba(255,123,114,0.2)' }
              : { color: 'var(--text-muted)', background: 'var(--bg-input)', border: '1px solid var(--border)' }
          }
        >
          <TrendIcon size={10} />
          {change}
        </div>
      )}
    </div>
  );
}
