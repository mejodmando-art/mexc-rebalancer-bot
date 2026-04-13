'use client';

import { LayoutDashboard, Briefcase, PlusCircle, Settings, Bell } from 'lucide-react';
import { Lang, tr } from '../lib/i18n';

interface NavbarProps {
  active: 'dashboard' | 'portfolios' | 'create' | 'settings' | 'notifications';
  onNav: (tab: 'dashboard' | 'portfolios' | 'create' | 'settings' | 'notifications') => void;
  botRunning: boolean;
  lang: Lang;
  onLangToggle: () => void;
  dark: boolean;
  onThemeToggle: () => void;
}

const TABS = [
  { key: 'dashboard'     as const, icon: LayoutDashboard, labelKey: 'dashboard' },
  { key: 'portfolios'    as const, icon: Briefcase,        labelKey: 'myPortfolios' },
  { key: 'create'        as const, icon: PlusCircle,       labelKey: 'createBot' },
  { key: 'settings'      as const, icon: Settings,         labelKey: 'settings' },
  { key: 'notifications' as const, icon: Bell,             labelKey: 'notifications' },
];

export default function Navbar({
  active, onNav, botRunning, lang, onLangToggle, dark, onThemeToggle,
}: NavbarProps) {
  return (
    <>
      <nav className="nav-bg border-b sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm text-black"
                 style={{ background: 'var(--brand)' }}>SP</div>
            <span className="font-bold text-base hidden sm:block" style={{ color: 'var(--text-main)' }}>
              Smart Portfolio
            </span>
          </div>

          <div className="hidden sm:flex items-center gap-1 rounded-xl p-1" style={{ background: 'var(--bg-input)' }}>
            {TABS.map(({ key, icon: Icon, labelKey }) => (
              <button key={key} onClick={() => onNav(key)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-150 ${active === key ? 'text-black' : 'hover:opacity-80'}`}
                style={active === key ? { background: 'var(--brand)' } : { color: 'var(--text-muted)' }}>
                <Icon size={14} />
                <span>{tr(labelKey, lang)}</span>
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <span className={`badge ${botRunning ? 'bg-green-900/60 text-green-400' : 'bg-gray-800 text-gray-500'}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${botRunning ? 'bg-green-400 pulse-dot' : 'bg-gray-500'}`} />
              <span className="hidden sm:inline">{botRunning ? tr('running', lang) : tr('stopped', lang)}</span>
            </span>
            <button onClick={onLangToggle} className="btn-secondary !px-2.5 !min-h-[36px] text-xs font-bold">
              {lang === 'ar' ? 'EN' : 'ع'}
            </button>
            <button onClick={onThemeToggle} className="btn-secondary !px-2.5 !min-h-[36px] text-sm">
              {dark ? '☀️' : '🌙'}
            </button>
          </div>
        </div>
      </nav>

      {/* Mobile bottom nav */}
      <div className="sm:hidden fixed bottom-0 inset-x-0 z-50 border-t nav-bg"
           style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
        <div className="flex">
          {TABS.map(({ key, icon: Icon, labelKey }) => (
            <button key={key} onClick={() => onNav(key)}
              className="flex-1 flex flex-col items-center justify-center py-2 gap-0.5 transition-colors active:scale-95"
              style={{ color: active === key ? 'var(--brand)' : 'var(--text-muted)' }}>
              <Icon size={20} strokeWidth={active === key ? 2.5 : 1.8} />
              <span className="text-[10px] font-medium leading-none">{tr(labelKey, lang)}</span>
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
