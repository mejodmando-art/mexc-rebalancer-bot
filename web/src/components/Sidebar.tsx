'use client';

import { TrendingUp, ChevronRight, LayoutDashboard, Briefcase, PlusCircle, Grid3x3, BookOpen } from 'lucide-react';
import { Lang, tr } from '../lib/i18n';

type Tab = 'dashboard' | 'portfolios' | 'create' | 'grid' | 'strategy';

interface SidebarProps {
  active: Tab;
  onNav: (tab: Tab) => void;
  botRunning: boolean;
  lang: Lang;
}

const TABS: { key: Tab; icon: React.ElementType; labelKey: string; color: string; glow: string }[] = [
  { key: 'dashboard',  icon: LayoutDashboard, labelKey: 'dashboard',    color: '#00D4AA', glow: 'rgba(0,212,170,0.4)' },
  { key: 'portfolios', icon: Briefcase,        labelKey: 'myPortfolios', color: '#60A5FA', glow: 'rgba(96,165,250,0.4)' },
  { key: 'create',     icon: PlusCircle,       labelKey: 'createBot',    color: '#A78BFA', glow: 'rgba(167,139,250,0.4)' },
  { key: 'grid',       icon: Grid3x3,          labelKey: 'gridBot',      color: '#F0B90B', glow: 'rgba(240,185,11,0.4)' },
  { key: 'strategy',   icon: BookOpen,         labelKey: 'strategyTab',  color: '#F472B6', glow: 'rgba(244,114,182,0.4)' },
];

export default function Sidebar({ active, onNav, botRunning, lang }: SidebarProps) {
  return (
    <aside
      className="sidebar hidden lg:flex flex-col w-60 xl:w-64 fixed top-0 bottom-0 left-0 z-40 py-5 px-3"
      style={{ position: 'relative', zIndex: 40 }}
    >
      {/* Subtle inner glow at top */}
      <div
        className="absolute top-0 left-0 right-0 h-32 pointer-events-none"
        style={{ background: 'radial-gradient(ellipse at 50% 0%, rgba(123,92,245,0.12) 0%, transparent 70%)' }}
      />

      {/* Logo */}
      <div className="flex items-center gap-3 px-3 mb-8 relative">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center font-black text-base shrink-0"
          style={{
            background: 'linear-gradient(135deg, #7B5CF5, #3B82F6)',
            boxShadow: '0 4px 20px rgba(123,92,245,0.5), inset 0 1px 0 rgba(255,255,255,0.2)',
            color: '#fff',
          }}
        >
          M
        </div>
        <div>
          <div className="font-bold text-sm leading-tight" style={{ color: 'var(--text-main)' }}>Smart Portfolio</div>
          <div className="text-[10px] font-medium" style={{ color: 'var(--text-muted)' }}>MEXC · محفظة ذكية</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-1.5 flex-1 relative">
        <div className="px-3 mb-2">
          <span className="label">{lang === 'ar' ? 'القائمة' : 'Menu'}</span>
        </div>

        {TABS.map(({ key, icon: Icon, labelKey, color, glow }) => {
          const isActive = active === key;
          return (
            <button
              key={key}
              onClick={() => onNav(key)}
              className="sidebar-item w-full text-start animate-fade-up"
              style={{
                color: isActive ? color : 'var(--text-muted)',
                background: isActive
                  ? `linear-gradient(135deg, ${color}18, ${color}08)`
                  : undefined,
                borderColor: isActive ? `${color}40` : 'transparent',
                boxShadow: isActive
                  ? `0 2px 16px ${glow}, inset 0 1px 0 rgba(255,255,255,0.06)`
                  : 'none',
              }}
            >
              {/* 3D icon */}
              <span
                className="flex items-center justify-center rounded-xl shrink-0 transition-all duration-200"
                style={{
                  width: 34, height: 34,
                  background: isActive
                    ? `linear-gradient(145deg, ${color}30, ${color}10)`
                    : 'rgba(123,92,245,0.08)',
                  boxShadow: isActive
                    ? `0 4px 14px ${glow}, inset 0 1px 0 rgba(255,255,255,0.18), inset 0 -1px 0 rgba(0,0,0,0.15)`
                    : '0 2px 6px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.05)',
                  border: isActive ? `1px solid ${color}40` : '1px solid rgba(123,92,245,0.15)',
                }}
              >
                <Icon
                  size={17}
                  strokeWidth={isActive ? 2.5 : 1.8}
                  style={{
                    color: isActive ? color : 'var(--text-muted)',
                    filter: isActive ? `drop-shadow(0 0 5px ${glow})` : 'none',
                  }}
                />
              </span>

              <span
                className="flex-1 text-sm"
                style={{
                  fontWeight: isActive ? 700 : 500,
                  textShadow: isActive ? `0 0 12px ${glow}` : 'none',
                }}
              >
                {tr(labelKey, lang)}
              </span>

              {isActive && (
                <ChevronRight
                  size={14}
                  style={{ color, filter: `drop-shadow(0 0 4px ${glow})`, opacity: 0.8 }}
                />
              )}
            </button>
          );
        })}
      </nav>

      {/* Bot status card */}
      <div className="mt-auto px-1 relative">
        <div
          className="p-3 rounded-2xl flex items-center gap-3"
          style={{
            background: 'rgba(123,92,245,0.08)',
            border: '1px solid rgba(123,92,245,0.2)',
            boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05)',
          }}
        >
          <div
            className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
            style={{
              background: botRunning ? 'rgba(0,212,170,0.15)' : 'rgba(123,92,245,0.1)',
              border: `1px solid ${botRunning ? 'rgba(0,212,170,0.3)' : 'rgba(123,92,245,0.2)'}`,
              boxShadow: botRunning ? '0 0 12px rgba(0,212,170,0.2)' : 'none',
            }}
          >
            <TrendingUp size={15} style={{ color: botRunning ? '#00D4AA' : 'var(--text-muted)' }} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold" style={{ color: 'var(--text-main)' }}>
              {lang === 'ar' ? 'حالة البوت' : 'Bot Status'}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span
                className={`w-1.5 h-1.5 rounded-full ${botRunning ? 'pulse-dot' : ''}`}
                style={{ background: botRunning ? '#00D4AA' : 'var(--text-muted)' }}
              />
              <span className="text-[11px]" style={{ color: botRunning ? '#00D4AA' : 'var(--text-muted)' }}>
                {botRunning ? tr('running', lang) : tr('stopped', lang)}
              </span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
