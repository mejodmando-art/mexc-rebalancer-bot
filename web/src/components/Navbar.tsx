'use client';

import { Moon, Sun, LayoutDashboard, Briefcase, PlusCircle, Settings, Grid3x3 } from 'lucide-react';
import { Lang, tr } from '../lib/i18n';

type Tab = 'dashboard' | 'portfolios' | 'create' | 'settings' | 'copy' | 'grid';

interface NavbarProps {
  active: Tab;
  onNav: (tab: Tab) => void;
  botRunning: boolean;
  lang: Lang;
  onLangToggle: () => void;
  dark: boolean;
  onThemeToggle: () => void;
}

const TABS: { key: Tab; icon: React.ElementType; labelKey: string; color: string; glow: string }[] = [
  { key: 'dashboard',  icon: LayoutDashboard, labelKey: 'dashboard',    color: '#00D4AA', glow: 'rgba(0,212,170,0.5)' },
  { key: 'portfolios', icon: Briefcase,        labelKey: 'myPortfolios', color: '#60A5FA', glow: 'rgba(96,165,250,0.5)' },
  { key: 'create',     icon: PlusCircle,       labelKey: 'createBot',    color: '#A78BFA', glow: 'rgba(167,139,250,0.5)' },
  { key: 'grid',       icon: Grid3x3,          labelKey: 'gridBot',      color: '#F0B90B', glow: 'rgba(240,185,11,0.5)' },
  { key: 'settings',   icon: Settings,         labelKey: 'settings',     color: '#FB923C', glow: 'rgba(251,146,60,0.5)' },
];

export default function Navbar({ active, onNav, botRunning, lang, onLangToggle, dark, onThemeToggle }: NavbarProps) {
  return (
    <>
      {/* Top header */}
      <header className="navbar sticky top-0 z-50 h-14" style={{ position: 'relative', zIndex: 50 }}>
        <div className="h-full px-4 flex items-center justify-between gap-3">
          {/* Mobile: Logo */}
          <div className="flex items-center gap-2.5 lg:hidden">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center font-black text-sm shrink-0"
              style={{
                background: 'linear-gradient(135deg, #7B5CF5, #3B82F6)',
                boxShadow: '0 4px 16px rgba(123,92,245,0.5), inset 0 1px 0 rgba(255,255,255,0.2)',
                color: '#fff',
              }}
            >
              M
            </div>
            <div>
              <div className="font-bold text-sm leading-tight" style={{ color: 'var(--text-main)' }}>Smart Portfolio</div>
              <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>MEXC · محفظة ذكية</div>
            </div>
          </div>

          {/* Desktop: page title */}
          <div className="hidden lg:flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-xl flex items-center justify-center font-black text-sm"
              style={{
                background: 'linear-gradient(135deg, #7B5CF5, #3B82F6)',
                boxShadow: '0 4px 14px rgba(123,92,245,0.45)',
                color: '#fff',
              }}
            >
              M
            </div>
            <div>
              <div className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>Smart Portfolio</div>
              <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>MEXC · محفظة ذكية</div>
            </div>
          </div>

          {/* Right controls */}
          <div className="flex items-center gap-2">
            {/* Bot status badge */}
            <div className={`badge ${botRunning ? 'badge-running' : 'badge-stopped'} hidden sm:flex`}>
              <span
                className={`w-1.5 h-1.5 rounded-full ${botRunning ? 'pulse-dot' : ''}`}
                style={{ background: botRunning ? '#00D4AA' : 'var(--text-muted)' }}
              />
              <span>{botRunning ? tr('running', lang) : tr('stopped', lang)}</span>
            </div>

            {/* Language toggle */}
            <button
              onClick={onLangToggle}
              className="btn-secondary !px-3 !min-h-[36px] !text-xs !font-bold"
              style={{ borderColor: 'rgba(123,92,245,0.35)' }}
            >
              {lang === 'ar' ? 'EN' : 'ع'}
            </button>

            {/* Theme toggle */}
            <button
              onClick={onThemeToggle}
              className="btn-secondary !px-3 !min-h-[36px]"
              style={{ borderColor: 'rgba(123,92,245,0.35)' }}
            >
              {dark ? <Sun size={15} style={{ color: '#F0B90B' }} /> : <Moon size={15} style={{ color: '#A78BFA' }} />}
            </button>
          </div>
        </div>
      </header>

      {/* Mobile bottom nav */}
      <nav
        className="lg:hidden fixed bottom-0 inset-x-0 z-50"
        style={{
          background: 'rgba(8,4,20,0.96)',
          borderTop: '1px solid rgba(123,92,245,0.2)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          paddingBottom: 'env(safe-area-inset-bottom)',
          boxShadow: '0 -8px 32px rgba(0,0,0,0.5)',
        }}
      >
        <div className="flex">
          {TABS.map(({ key, icon: Icon, labelKey, color, glow }) => {
            const isActive = active === key;
            const isCreate = key === 'create';
            return (
              <button
                key={key}
                onClick={() => onNav(key)}
                className="flex-1 flex flex-col items-center justify-center py-2 gap-1 transition-all active:scale-90 relative"
                style={{ color: isActive ? color : 'var(--text-muted)' }}
              >
                {/* Active top glow line */}
                {isActive && (
                  <span
                    className="absolute top-0 w-8 h-0.5 rounded-full"
                    style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }}
                  />
                )}

                {/* Icon container */}
                <span
                  className="flex items-center justify-center transition-all duration-300"
                  style={{
                    width: isCreate ? 48 : 42,
                    height: isCreate ? 48 : 42,
                    borderRadius: isCreate ? '16px' : '14px',
                    background: isCreate
                      ? 'linear-gradient(135deg, #7B5CF5, #3B82F6)'
                      : isActive
                        ? `linear-gradient(145deg, ${color}30, ${color}12)`
                        : 'transparent',
                    boxShadow: isCreate
                      ? '0 4px 20px rgba(123,92,245,0.55), inset 0 1px 0 rgba(255,255,255,0.2)'
                      : isActive
                        ? `0 4px 16px ${glow}, inset 0 1px 0 rgba(255,255,255,0.12)`
                        : 'none',
                    border: isCreate
                      ? '1px solid rgba(255,255,255,0.15)'
                      : isActive
                        ? `1px solid ${color}44`
                        : '1px solid transparent',
                    transform: isActive ? 'translateY(-2px) scale(1.06)' : 'translateY(0) scale(1)',
                    marginTop: isCreate ? '-8px' : '0',
                  }}
                >
                  <Icon
                    size={isCreate ? 22 : isActive ? 22 : 20}
                    strokeWidth={isActive || isCreate ? 2.5 : 1.8}
                    style={{
                      color: isCreate ? '#fff' : isActive ? color : 'var(--text-muted)',
                      filter: isActive && !isCreate ? `drop-shadow(0 0 6px ${glow})` : 'none',
                    }}
                  />
                </span>

                <span
                  style={{
                    fontSize: '9px',
                    fontWeight: isActive ? 800 : 500,
                    color: isActive ? color : 'var(--text-muted)',
                    textShadow: isActive ? `0 0 8px ${glow}` : 'none',
                    letterSpacing: '0.02em',
                  }}
                >
                  {tr(labelKey, lang)}
                </span>
              </button>
            );
          })}
        </div>
      </nav>
    </>
  );
}
