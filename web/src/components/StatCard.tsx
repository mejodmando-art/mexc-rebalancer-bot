'use client';

import { motion } from 'framer-motion';
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
      <div className="flex items-start justify-between mb-3">
        <div className="skeleton h-3 w-24 rounded" />
        <div className="skeleton w-9 h-9 rounded-xl" />
      </div>
      <div className="skeleton h-8 w-32 rounded mb-2" />
      <div className="skeleton h-5 w-16 rounded-full" />
    </div>
  );
}

export default function StatCard({
  title, value, change, changePositive, icon: Icon, iconColor, loading, delay = 0,
}: StatCardProps) {
  if (loading) return <StatCardSkeleton />;

  const isPositive = changePositive === true;
  const isNegative = changePositive === false;
  const TrendIcon = isPositive ? TrendingUp : isNegative ? TrendingDown : Minus;

  return (
    <motion.div
      className="card card-hover p-5 cursor-default"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.3, ease: 'easeOut' }}
    >
      <div className="flex items-start justify-between mb-3">
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
          {title}
        </span>
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: `${iconColor ?? 'var(--accent)'}18` }}
        >
          <Icon size={16} style={{ color: iconColor ?? 'var(--accent)' }} />
        </div>
      </div>

      <motion.div
        className="stat-value mb-2"
        key={value}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        style={{ color: 'var(--text-main)' }}
      >
        {value}
      </motion.div>

      {change && (
        <div className={`trend-badge ${isPositive ? 'trend-up' : isNegative ? 'trend-down' : ''}`}
             style={!isPositive && !isNegative ? { color: 'var(--text-muted)', background: 'var(--bg-input)' } : {}}>
          <TrendIcon size={11} />
          {change}
        </div>
      )}
    </motion.div>
  );
}
