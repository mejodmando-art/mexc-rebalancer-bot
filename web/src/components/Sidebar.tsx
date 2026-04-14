'use client';

import { TrendingUp, ChevronRight, LayoutDashboard, Briefcase, PlusCircle, Settings, Copy } from 'lucide-react';
import { Lang, tr } from '../lib/i18n';

type Tab = 'dashboard' | 'portfolios' | 'create' | 'settings' | 'copy';

interface SidebarProps {
  active: Tab;
  onNav: (tab: Tab) => void;
  botRunning: boolean;
  lang: Lang;
}

const TABS: { key: Tab; icon: React.ElementType; labelKey: string }[] = [
  { key: 'dashboard',  icon: LayoutDashboard, labelKey: 'dashboard' },
  { key: 'portfolios', icon: Briefcase,        labelKey: 'myPortfolios' },
  { key: 'create',     icon: PlusCircle,       labelKey: 'createBot' },
  { key: 'settings',   icon: Settings,         labelKey: 'settings' },
  { key: 'copy',       icon: Copy,             labelKey: 'copyPortfolio' },
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
      <nav className="flex flex-col gap-1 flex-1">
        <div className="px-3 mb-2">
          <span className="label">{lang === 'ar' ? 'القائمة' : 'Menu'}</span>
        </div>
        {TABS.map(({ key, icon: Icon, labelKey }) => (
          <button
            key={key}
            onClick={() => onNav(key)}
            className={`sidebar-item w-full text-start animate-fade-up ${active === key ? 'active' : ''}`}
          >
            <Icon size={16} strokeWidth={active === key ? 2.5 : 1.8} />
            <span className="flex-1">{tr(labelKey, lang)}</span>
            {active === key && <ChevronRight size={14} className="opacity-50" />}
          </button>
        ))}
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
