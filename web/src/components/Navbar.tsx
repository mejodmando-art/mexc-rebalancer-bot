'use client';

import { Moon, Sun, BarChart2, Wallet, Settings, Bot } from 'lucide-react';
import { Lang, tr } from '../lib/i18n';

type Tab = 'dashboard' | 'portfolios' | 'create' | 'settings' | 'copy' | 'grid' | 'portfolio-settings';

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
  { key: 'dashboard',  icon: BarChart2, labelKey: 'dashboard',    color: '#00D4AA', glow: 'rgba(0,212,170,0.5)' },
  { key: 'portfolios', icon: Wallet,    labelKey: 'myPortfolios', color: '#60A5FA', glow: 'rgba(96,165,250,0.5)' },
  { key: 'grid',       icon: Bot,       labelKey: 'gridBot',      color: '#F0B90B', glow: 'rgba(240,185,11,0.5)' },
  { key: 'settings',   icon: Settings,  labelKey: 'settings',     color: '#FB923C', glow: 'rgba(251,146,60,0.5)' },
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
          background: 'rgba(6,3,18,0.97)',
          borderTop: '1px solid rgba(255,255,255,0.07)',
          backdropFilter: 'blur(28px)',
          WebkitBackdropFilter: 'blur(28px)',
          paddingBottom: 'env(safe-area-inset-bottom)',
          boxShadow: '0 -12px 40px rgba(0,0,0,0.6)',
        }}
      >
        <div className="flex">
          {TABS.map(({ key, icon: Icon, labelKey, color, glow }) => {
            const isActive = active === key;
            return (
              <button
                key={key}
                onClick={() => onNav(key)}
                className="flex-1 flex flex-col items-center justify-center py-2.5 gap-1 transition-all active:scale-90 relative"
              >
                {/* Active top glow bar */}
                {isActive && (
                  <span
                    className="absolute top-0 inset-x-4 h-0.5 rounded-full"
                    style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }}
                  />
                )}

                {/* Icon pill */}
                <span
                  className="flex items-center justify-center transition-all duration-300"
                  style={{
                    width: 44,
                    height: 36,
                    borderRadius: '12px',
                    background: isActive
                      ? `linear-gradient(145deg, ${color}28, ${color}10)`
                      : 'transparent',
                    boxShadow: isActive
                      ? `0 2px 14px ${glow}, inset 0 1px 0 rgba(255,255,255,0.1)`
                      : 'none',
                    border: isActive ? `1px solid ${color}50` : '1px solid transparent',
                    transform: isActive ? 'translateY(-3px) scale(1.08)' : 'translateY(0) scale(1)',
                  }}
                >
                  <Icon
                    size={isActive ? 21 : 19}
                    strokeWidth={isActive ? 2.8 : 1.7}
                    style={{
                      color: isActive ? color : 'rgba(255,255,255,0.28)',
                      filter: isActive ? `drop-shadow(0 0 8px ${glow})` : 'none',
                      transition: 'all 0.2s',
                    }}
                  />
                </span>

                {/* Label */}
                <span
                  style={{
                    fontSize: '9px',
                    fontWeight: isActive ? 900 : 500,
                    color: isActive ? color : 'rgba(255,255,255,0.28)',
                    textShadow: isActive ? `0 0 10px ${glow}` : 'none',
                    letterSpacing: isActive ? '0.03em' : '0.01em',
                    transition: 'all 0.2s',
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
