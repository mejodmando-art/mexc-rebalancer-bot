'use client';

import { Moon, Sun, BarChart2, Wallet, Bot } from 'lucide-react';
import { Lang, tr } from '../lib/i18n';

type Tab = 'dashboard' | 'portfolios' | 'create' | 'copy' | 'grid';

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
  { key: 'grid',       icon: Bot,       labelKey: 'gridBot',      color: '#818CF8', glow: 'rgba(129,140,248,0.45)' },
  { key: 'portfolios', icon: Wallet,    labelKey: 'myPortfolios', color: '#60A5FA', glow: 'rgba(96,165,250,0.45)' },
  { key: 'dashboard',  icon: BarChart2, labelKey: 'dashboard',    color: '#34D399', glow: 'rgba(52,211,153,0.45)' },
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
          background: 'rgba(8,5,22,0.98)',
          borderTop: '1px solid rgba(167,139,250,0.12)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          paddingBottom: 'env(safe-area-inset-bottom)',
          boxShadow: '0 -8px 32px rgba(0,0,0,0.5)',
        }}
      >
        <div className="flex h-[58px]">
          {TABS.map(({ key, icon: Icon, labelKey, color, glow }) => {
            const isActive = active === key;
            return (
              <button
                key={key}
                onClick={() => onNav(key)}
                className="flex-1 flex flex-col items-center justify-center gap-0.5 transition-all active:scale-90 relative"
              >
                {/* Active indicator bar at top */}
                <span
                  className="absolute top-0 rounded-b-full transition-all duration-300"
                  style={{
                    left: '25%', right: '25%', height: isActive ? 2 : 0,
                    background: color,
                    boxShadow: isActive ? `0 0 8px ${glow}` : 'none',
                  }}
                />

                {/* Icon */}
                <span
                  className="flex items-center justify-center transition-all duration-200"
                  style={{
                    width: 36,
                    height: 30,
                    borderRadius: '10px',
                    background: isActive ? `${color}18` : 'transparent',
                    transform: isActive ? 'translateY(-1px)' : 'none',
                  }}
                >
                  <Icon
                    size={18}
                    strokeWidth={isActive ? 2.5 : 1.8}
                    style={{
                      color: isActive ? color : 'rgba(255,255,255,0.32)',
                      filter: isActive ? `drop-shadow(0 0 6px ${glow})` : 'none',
                      transition: 'all 0.2s',
                    }}
                  />
                </span>

                {/* Label */}
                <span
                  style={{
                    fontSize: '9px',
                    fontWeight: isActive ? 700 : 400,
                    color: isActive ? color : 'rgba(255,255,255,0.3)',
                    letterSpacing: '0.02em',
                    transition: 'all 0.2s',
                    lineHeight: 1,
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
