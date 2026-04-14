'use client';

import { Sun, Moon, Globe, LayoutDashboard, Briefcase, PlusCircle, Settings, Grid3x3 } from 'lucide-react';
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
      <header className="navbar sticky top-0 z-50 h-14">
        <div className="h-full px-4 lg:pl-4 flex items-center justify-between gap-3">
          {/* Mobile logo */}
          <div className="flex items-center gap-2 lg:hidden">
            <span className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>Smart Portfolio</span>
          </div>

          {/* Desktop page title */}
          <div className="hidden lg:block">
            <span className="font-semibold text-sm" style={{ color: 'var(--text-muted)' }}>
              {tr(
                active === 'dashboard'  ? 'dashboard'  :
                active === 'portfolios' ? 'myPortfolios' :
                active === 'create'     ? 'createBot'  :
                active === 'grid'       ? 'gridBot'    : 'settings',
                lang
              )}
            </span>
          </div>

          {/* Right controls */}
          <div className="flex items-center gap-2">
            <div className={`badge ${botRunning ? 'badge-running' : 'badge-stopped'} hidden sm:flex`}>
              <span className={`w-1.5 h-1.5 rounded-full ${botRunning ? 'pulse-dot' : ''}`}
                    style={{ background: botRunning ? 'var(--accent)' : 'var(--text-muted)' }} />
              <span>{botRunning ? tr('running', lang) : tr('stopped', lang)}</span>
            </div>

            <button onClick={onLangToggle} className="btn-secondary !px-3 !min-h-[36px] !text-xs !font-bold gap-1.5">
              <Globe size={13} />
              {lang === 'ar' ? 'EN' : 'ع'}
            </button>

            <button onClick={onThemeToggle} className="btn-secondary !px-3 !min-h-[36px]">
              {dark ? <Sun size={15} /> : <Moon size={15} />}
            </button>
          </div>
        </div>
      </header>

      {/* Mobile bottom nav */}
      <nav className="lg:hidden fixed bottom-0 inset-x-0 z-50 border-t glass"
           style={{ background: 'var(--bg-nav)', borderColor: 'var(--border)', paddingBottom: 'env(safe-area-inset-bottom)' }}>
        <div className="flex">
          {TABS.map(({ key, icon: Icon, labelKey, color, glow }) => {
            const isActive = active === key;
            return (
              <button key={key} onClick={() => onNav(key)}
                className="flex-1 flex flex-col items-center justify-center py-3 gap-1.5 transition-all active:scale-90 relative"
                style={{ color: isActive ? color : 'var(--text-muted)' }}>
                {/* Active top indicator */}
                {isActive && (
                  <span
                    className="absolute top-0 w-10 h-0.5 rounded-full"
                    style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }}
                  />
                )}
                {/* 3D icon container */}
                <span
                  className="flex items-center justify-center rounded-2xl transition-all duration-300"
                  style={{
                    width: 44,
                    height: 44,
                    background: isActive
                      ? `linear-gradient(145deg, ${color}33, ${color}11)`
                      : 'transparent',
                    boxShadow: isActive
                      ? `0 4px 16px ${glow}, 0 2px 4px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.15), inset 0 -1px 0 rgba(0,0,0,0.2)`
                      : 'none',
                    border: isActive ? `1px solid ${color}55` : '1px solid transparent',
                    transform: isActive ? 'translateY(-2px) scale(1.08)' : 'translateY(0) scale(1)',
                  }}
                >
                  <Icon
                    size={isActive ? 24 : 22}
                    strokeWidth={isActive ? 2.5 : 1.8}
                    style={{
                      filter: isActive
                        ? `drop-shadow(0 0 6px ${glow}) drop-shadow(0 2px 4px rgba(0,0,0,0.4))`
                        : 'none',
                    }}
                  />
                </span>
                <span
                  className="leading-none tracking-wide"
                  style={{
                    fontSize: '10px',
                    fontWeight: isActive ? 800 : 600,
                    textShadow: isActive ? `0 0 8px ${glow}, 0 1px 2px rgba(0,0,0,0.5)` : 'none',
                    letterSpacing: '0.03em',
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
