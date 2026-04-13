'use client';

import { motion } from 'framer-motion';
import {
  LayoutDashboard, Briefcase, PlusCircle, Settings, Bell,
  TrendingUp, ChevronRight,
} from 'lucide-react';
import { Lang, tr } from '../lib/i18n';

type Tab = 'dashboard' | 'portfolios' | 'create' | 'settings' | 'notifications';

interface SidebarProps {
  active: Tab;
  onNav: (tab: Tab) => void;
  botRunning: boolean;
  lang: Lang;
}

const TABS: { key: Tab; icon: React.ElementType; labelKey: string }[] = [
  { key: 'dashboard',     icon: LayoutDashboard, labelKey: 'dashboard' },
  { key: 'portfolios',    icon: Briefcase,        labelKey: 'myPortfolios' },
  { key: 'create',        icon: PlusCircle,       labelKey: 'createBot' },
  { key: 'settings',      icon: Settings,         labelKey: 'settings' },
  { key: 'notifications', icon: Bell,             labelKey: 'notifications' },
];

export default function Sidebar({ active, onNav, botRunning, lang }: SidebarProps) {
  return (
    <aside className="sidebar hidden lg:flex flex-col w-60 xl:w-64 fixed top-0 bottom-0 start-0 z-40 py-5 px-3">
      {/* Logo */}
      <div className="flex items-center gap-3 px-3 mb-8">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center font-bold text-sm text-[#0D1117] accent-gradient shrink-0 shadow-glow-sm">
          SP
        </div>
        <div>
          <div className="font-bold text-sm leading-tight" style={{ color: 'var(--text-main)' }}>
            Smart Portfolio
          </div>
          <div className="text-[10px] font-medium" style={{ color: 'var(--text-muted)' }}>
            MEXC Exchange
          </div>
        </div>
      </div>

      {/* Nav items */}
      <nav className="flex flex-col gap-1 flex-1">
        <div className="px-3 mb-2">
          <span className="label">{lang === 'ar' ? 'القائمة' : 'Menu'}</span>
        </div>
        {TABS.map(({ key, icon: Icon, labelKey }, i) => (
          <motion.button
            key={key}
            onClick={() => onNav(key)}
            className={`sidebar-item w-full text-start ${active === key ? 'active' : ''}`}
            whileHover={{ x: lang === 'ar' ? -2 : 2 }}
            whileTap={{ scale: 0.98 }}
            initial={{ opacity: 0, x: lang === 'ar' ? 10 : -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05, duration: 0.2 }}
          >
            <Icon size={16} strokeWidth={active === key ? 2.5 : 1.8} />
            <span className="flex-1">{tr(labelKey, lang)}</span>
            {active === key && (
              <ChevronRight size={14} className="opacity-60" style={{ transform: lang === 'ar' ? 'rotate(180deg)' : 'none' }} />
            )}
          </motion.button>
        ))}
      </nav>

      {/* Bot status */}
      <div className="mt-auto px-1">
        <div className="card p-3 flex items-center gap-3">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${botRunning ? 'bg-[rgba(0,212,170,0.12)]' : 'bg-[var(--bg-input)]'}`}>
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
