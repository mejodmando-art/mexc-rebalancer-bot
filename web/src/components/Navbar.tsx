'use client';

import { Lang, tr } from '../lib/i18n';

interface NavbarProps {
  active: 'dashboard' | 'create' | 'settings' | 'notifications';
  onNav: (tab: 'dashboard' | 'create' | 'settings' | 'notifications') => void;
  botRunning: boolean;
  lang: Lang;
  onLangToggle: () => void;
  dark: boolean;
  onThemeToggle: () => void;
}

export default function Navbar({
  active, onNav, botRunning, lang, onLangToggle, dark, onThemeToggle,
}: NavbarProps) {
  const tabs = [
    { key: 'dashboard'     as const, label: tr('dashboard', lang),     icon: '📊' },
    { key: 'create'        as const, label: tr('createBot', lang),      icon: '➕' },
    { key: 'settings'      as const, label: tr('settings', lang),       icon: '⚙️' },
    { key: 'notifications' as const, label: tr('notifications', lang),  icon: '🔔' },
  ];

  return (
    <nav className="nav-bg border-b px-4 py-3 flex items-center justify-between sticky top-0 z-50">
      {/* Logo */}
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 bg-brand rounded-lg flex items-center justify-center text-black font-bold text-sm">
          SP
        </div>
        <span className="font-bold text-lg" style={{ color: 'var(--text-main)' }}>
          Smart Portfolio
        </span>
        <span className="text-xs hidden sm:block" style={{ color: 'var(--text-muted)' }}>
          MEXC Spot
        </span>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 rounded-xl p-1" style={{ background: 'var(--bg-input)' }}>
        {tabs.map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => onNav(key)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              active === key ? 'bg-brand text-black' : 'hover:opacity-80'
            }`}
            style={active !== key ? { color: 'var(--text-muted)' } : {}}
          >
            <span className="hidden sm:inline">{icon} </span>{label}
          </button>
        ))}
      </div>

      {/* Right controls */}
      <div className="flex items-center gap-2">
        {/* Bot status */}
        <span className={`badge ${botRunning ? 'bg-green-900 text-green-400' : 'bg-gray-800 text-gray-500'}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${botRunning ? 'bg-green-400' : 'bg-gray-500'}`} />
          {botRunning ? tr('running', lang) : tr('stopped', lang)}
        </span>

        {/* Language toggle */}
        <button
          onClick={onLangToggle}
          className="btn-secondary text-xs px-2 py-1 font-bold"
          title="Toggle language"
        >
          {lang === 'ar' ? 'EN' : 'ع'}
        </button>

        {/* Dark/Light toggle */}
        <button
          onClick={onThemeToggle}
          className="btn-secondary text-sm px-2 py-1"
          title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {dark ? '☀️' : '🌙'}
        </button>
      </div>
    </nav>
  );
}
