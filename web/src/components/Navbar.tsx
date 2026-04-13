'use client';

import { motion } from 'framer-motion';
import { Sun, Moon, Globe, LayoutDashboard, Briefcase, PlusCircle, Settings, Bell } from 'lucide-react';
import { Lang, tr } from '../lib/i18n';

type Tab = 'dashboard' | 'portfolios' | 'create' | 'settings' | 'notifications';

interface NavbarProps {
  active: Tab;
  onNav: (tab: Tab) => void;
  botRunning: boolean;
  lang: Lang;
  onLangToggle: () => void;
  dark: boolean;
  onThemeToggle: () => void;
}

const TABS: { key: Tab; icon: React.ElementType; labelKey: string }[] = [
  { key: 'dashboard',     icon: LayoutDashboard, labelKey: 'dashboard' },
  { key: 'portfolios',    icon: Briefcase,        labelKey: 'myPortfolios' },
  { key: 'create',        icon: PlusCircle,       labelKey: 'createBot' },
  { key: 'settings',      icon: Settings,         labelKey: 'settings' },
  { key: 'notifications', icon: Bell,             labelKey: 'notifications' },
];

export default function Navbar({ active, onNav, botRunning, lang, onLangToggle, dark, onThemeToggle }: NavbarProps) {
  return (
    <>
      {/* Top navbar — visible on all sizes, but on desktop it's just the top bar */}
      <header className="navbar sticky top-0 z-50 h-14">
        <div className="h-full px-4 lg:ps-72 flex items-center justify-between gap-3">
          {/* Mobile logo */}
          <div className="flex items-center gap-2 lg:hidden">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs text-[#0D1117] accent-gradient">
              SP
            </div>
            <span className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>Smart Portfolio</span>
          </div>

          {/* Desktop page title */}
          <div className="hidden lg:block">
            <span className="font-semibold text-sm" style={{ color: 'var(--text-muted)' }}>
              {tr(active === 'dashboard' ? 'dashboard' : active === 'portfolios' ? 'myPortfolios' : active === 'create' ? 'createBot' : active === 'settings' ? 'settings' : 'notifications', lang)}
            </span>
          </div>

          {/* Right controls */}
          <div className="flex items-center gap-2">
            {/* Bot status badge */}
            <div className={`badge ${botRunning ? 'badge-running' : 'badge-stopped'} hidden sm:flex`}>
              <span className={`w-1.5 h-1.5 rounded-full ${botRunning ? 'pulse-dot' : ''}`}
                    style={{ background: botRunning ? 'var(--accent)' : 'var(--text-muted)' }} />
              <span>{botRunning ? tr('running', lang) : tr('stopped', lang)}</span>
            </div>

            {/* Lang toggle */}
            <motion.button
              onClick={onLangToggle}
              className="btn-secondary !px-3 !min-h-[36px] !text-xs !font-bold gap-1.5"
              whileTap={{ scale: 0.95 }}
              title="Toggle language"
            >
              <Globe size={13} />
              {lang === 'ar' ? 'EN' : 'ع'}
            </motion.button>

            {/* Theme toggle */}
            <motion.button
              onClick={onThemeToggle}
              className="btn-secondary !px-3 !min-h-[36px]"
              whileTap={{ scale: 0.95, rotate: 15 }}
              title="Toggle theme"
            >
              <motion.div
                key={dark ? 'sun' : 'moon'}
                initial={{ rotate: -30, opacity: 0 }}
                animate={{ rotate: 0, opacity: 1 }}
                transition={{ duration: 0.2 }}
              >
                {dark ? <Sun size={15} /> : <Moon size={15} />}
              </motion.div>
            </motion.button>
          </div>
        </div>
      </header>

      {/* Mobile bottom nav */}
      <nav
        className="lg:hidden fixed bottom-0 inset-x-0 z-50 border-t glass"
        style={{
          background: 'var(--bg-nav)',
          borderColor: 'var(--border)',
          paddingBottom: 'env(safe-area-inset-bottom)',
        }}
      >
        <div className="flex">
          {TABS.map(({ key, icon: Icon, labelKey }) => (
            <button
              key={key}
              onClick={() => onNav(key)}
              className="flex-1 flex flex-col items-center justify-center py-2.5 gap-1 transition-all active:scale-90"
              style={{ color: active === key ? 'var(--accent)' : 'var(--text-muted)' }}
            >
              {active === key && (
                <motion.div
                  layoutId="bottom-nav-indicator"
                  className="absolute top-0 w-8 h-0.5 rounded-full accent-gradient"
                />
              )}
              <Icon size={19} strokeWidth={active === key ? 2.5 : 1.8} />
              <span className="text-[10px] font-semibold leading-none">{tr(labelKey, lang)}</span>
            </button>
          ))}
        </div>
      </nav>
    </>
  );
}
