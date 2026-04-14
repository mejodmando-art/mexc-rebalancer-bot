'use client';

import { TrendingUp, ChevronRight, LayoutDashboard, Briefcase, PlusCircle, Settings, Grid3x3 } from 'lucide-react';
import { Lang, tr } from '../lib/i18n';

type Tab = 'dashboard' | 'portfolios' | 'create' | 'settings' | 'copy' | 'grid';

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
  { key: 'settings',   icon: Settings,         labelKey: 'settings',     color: '#FB923C', glow: 'rgba(251,146,60,0.4)' },
];

export default function Sidebar({ active, onNav, botRunning, lang }: SidebarProps) {
  return (
    <aside className="sidebar hidden lg:flex flex-col w-60 xl:w-64 fixed top-0 bottom-0 left-0 z-40 py-5 px-3">
      {/* Logo */}
      <div className="flex items-center gap-3 px-3 mb-8">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center font-bold text-sm shrink-0 accent-gradient"
             style={{ color: '#0D1117' }}>
          SP
        </div>
        <div>
          <div className="font-bold text-sm leading-tight" style={{ color: 'var(--text-main)' }}>Smart Portfolio</div>
          <div className="text-[10px] font-medium" style={{ color: 'var(--text-muted)' }}>MEXC Exchange</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-1.5 flex-1">
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
                background: isActive ? `linear-gradient(135deg, ${color}18, ${color}08)` : undefined,
                borderColor: isActive ? `${color}44` : 'transparent',
                boxShadow: isActive
                  ? `0 2px 12px ${glow}, inset 0 1px 0 rgba(255,255,255,0.08)`
                  : 'none',
              }}
            >
              {/* 3D icon wrapper */}
              <span
                className="flex items-center justify-center rounded-xl shrink-0 transition-all duration-200"
                style={{
                  width: 34,
                  height: 34,
                  background: isActive
                    ? `linear-gradient(145deg, ${color}33, ${color}11)`
                    : 'var(--bg-input)',
                  boxShadow: isActive
                    ? `0 4px 12px ${glow}, inset 0 1px 0 rgba(255,255,255,0.2), inset 0 -1px 0 rgba(0,0,0,0.15)`
                    : '0 2px 4px rgba(0,0,0,0.15), inset 0 1px 0 rgba(255,255,255,0.06)',
                  border: isActive ? `1px solid ${color}44` : '1px solid var(--border)',
                }}
              >
                <Icon
                  size={17}
                  strokeWidth={isActive ? 2.5 : 1.8}
                  style={{
                    filter: isActive
                      ? `drop-shadow(0 0 4px ${glow}) drop-shadow(0 1px 3px rgba(0,0,0,0.4))`
                      : 'none',
                    color: isActive ? color : 'var(--text-muted)',
                  }}
                />
              </span>
              <span
                className="flex-1 text-sm"
                style={{
                  fontWeight: isActive ? 700 : 500,
                  textShadow: isActive ? `0 0 12px ${glow}` : 'none',
                  letterSpacing: isActive ? '-0.01em' : 'normal',
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

      {/* Bot status */}
      <div className="mt-auto px-1">
        <div className="card p-3 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
               style={{ background: botRunning ? 'rgba(0,212,170,0.12)' : 'var(--bg-input)' }}>
            <TrendingUp size={15} style={{ color: botRunning ? 'var(--accent)' : 'var(--text-muted)' }} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold" style={{ color: 'var(--text-main)' }}>
              {lang === 'ar' ? 'حالة البوت' : 'Bot Status'}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className={`w-1.5 h-1.5 rounded-full ${botRunning ? 'pulse-dot' : ''}`}
                    style={{ background: botRunning ? 'var(--accent)' : 'var(--text-muted)' }} />
              <span className="text-[11px]" style={{ color: botRunning ? 'var(--accent)' : 'var(--text-muted)' }}>
                {botRunning ? tr('running', lang) : tr('stopped', lang)}
              </span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
