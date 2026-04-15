'use client';

import { useRef } from 'react';
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

export default function StatCard({
  title,
  value,
  change,
  changePositive,
  icon: Icon,
  iconColor,
  loading,
  delay = 0,
}: StatCardProps) {
  if (loading) return <StatCardSkeleton />;

  const cardRef = useRef<HTMLDivElement>(null);
  const rafRef  = useRef<number | null>(null);

  const isPositive = changePositive === true;
  const isNegative = changePositive === false;
  const TrendIcon  = isPositive ? TrendingUp : isNegative ? TrendingDown : Minus;
  const color      = iconColor ?? '#7B5CF5';

  // Perspective tilt — runs in rAF to avoid layout thrashing
  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      const el = cardRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const x = (e.clientX - rect.left)  / rect.width  - 0.5; // -0.5 → 0.5
      const y = (e.clientY - rect.top)   / rect.height - 0.5;
      el.style.transform = `perspective(700px) rotateX(${-y * 7}deg) rotateY(${x * 7}deg) translateY(-4px)`;
    });
  };

  const handleMouseLeave = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    const el = cardRef.current;
    if (!el) return;
    el.style.transition = 'transform 0.45s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.3s ease, border-color 0.25s ease';
    el.style.transform  = '';
    setTimeout(() => { if (el) el.style.transition = ''; }, 450);
  };

  const handleMouseEnter = () => {
    const el = cardRef.current;
    if (!el) return;
    el.style.transition = 'transform 0.08s ease-out, box-shadow 0.3s ease, border-color 0.25s ease';
  };

  return (
    <div
      ref={cardRef}
      className="card card-hover p-4 cursor-default animate-fade-up"
      style={{
        animationDelay: `${delay}s`,
        background: `linear-gradient(135deg, rgba(15,10,40,0.9) 0%, rgba(20,14,55,0.7) 100%)`,
      }}
      onMouseMove={handleMouseMove}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Per-card accent line keyed to icon color */}
      <div
        className="absolute top-0 left-0 right-0 h-px rounded-t-2xl"
        style={{ background: `linear-gradient(90deg, transparent, ${color}70, transparent)` }}
      />

      {/* Corner ambient glow */}
      <div
        className="absolute top-0 right-0 w-24 h-24 pointer-events-none"
        style={{ background: `radial-gradient(circle at top right, ${color}18, transparent 70%)` }}
      />

      {/* Icon + title row */}
      <div className="flex items-center justify-between mb-3 relative">
        <span
          className="text-[10px] font-bold uppercase tracking-widest"
          style={{ color: 'var(--text-muted)' }}
        >
          {title}
        </span>

        {/* 3-layer icon badge: gradient fill + specular highlight + drop shadow */}
        <div
          className="flex items-center justify-center shrink-0 relative"
          style={{
            width: 38,
            height: 38,
            borderRadius: 13,
            background: `linear-gradient(145deg, ${color}32, ${color}12)`,
            border: `1px solid ${color}38`,
            boxShadow: `0 6px 20px ${color}2e, 0 2px 6px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.16), inset 0 -1px 0 rgba(0,0,0,0.2)`,
          }}
        >
          {/* Specular highlight arc */}
          <div
            style={{
              position: 'absolute',
              top: 2, left: 5, right: 5,
              height: '38%',
              background: 'linear-gradient(180deg, rgba(255,255,255,0.2) 0%, transparent 100%)',
              borderRadius: '8px 8px 50% 50%',
              pointerEvents: 'none',
            }}
          />
          <Icon
            size={16}
            style={{ color, filter: `drop-shadow(0 2px 5px ${color}88)`, position: 'relative' }}
          />
        </div>
      </div>

      {/* Value */}
      <div
        className="stat-value mb-2.5 relative"
        style={{ color: 'var(--text-main)', letterSpacing: '-0.03em' }}
      >
        {value}
      </div>

      {/* Trend badge */}
      {change && (
        <div
          className="trend-badge"
          style={
            isPositive
              ? { color: '#00D4AA', background: 'rgba(0,212,170,0.1)', border: '1px solid rgba(0,212,170,0.22)' }
              : isNegative
              ? { color: '#FF7B72', background: 'rgba(255,123,114,0.1)', border: '1px solid rgba(255,123,114,0.22)' }
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
