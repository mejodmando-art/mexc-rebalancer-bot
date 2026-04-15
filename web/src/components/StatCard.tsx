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
  const color = iconColor ?? '#7B5CF5';

  return (
    <div
      className="card card-hover p-4 cursor-default animate-fade-up"
      style={{
        animationDelay: `${delay}s`,
        background: `linear-gradient(135deg, rgba(15,10,40,0.9) 0%, rgba(20,14,55,0.7) 100%)`,
      }}
    >
      {/* Top accent line */}
      <div
        className="absolute top-0 left-0 right-0 h-px rounded-t-2xl"
        style={{ background: `linear-gradient(90deg, transparent, ${color}60, transparent)` }}
      />

      {/* Subtle corner glow */}
      <div
        className="absolute top-0 right-0 w-20 h-20 pointer-events-none"
        style={{ background: `radial-gradient(circle at top right, ${color}15, transparent 70%)` }}
      />

      {/* Icon + title */}
      <div className="flex items-center justify-between mb-3 relative">
        <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
          {title}
        </span>
        <div
          className="w-9 h-9 rounded-2xl flex items-center justify-center shrink-0"
          style={{
            background: `linear-gradient(145deg, ${color}28, ${color}10)`,
            border: `1px solid ${color}30`,
            boxShadow: `0 4px 14px ${color}25, inset 0 1px 0 rgba(255,255,255,0.1)`,
          }}
        >
          <Icon size={16} style={{ color, filter: `drop-shadow(0 0 4px ${color}80)` }} />
        </div>
      </div>

      {/* Value */}
      <div
        className="stat-value mb-2.5 relative"
        style={{ color: 'var(--text-main)', letterSpacing: '-0.03em' }}
      >
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
              : { color: 'var(--text-muted)', background: 'rgba(123,92,245,0.08)', border: '1px solid rgba(123,92,245,0.15)' }
          }
        >
          <TrendIcon size={10} />
          {change}
        </div>
      )}
    </div>
  );
}
