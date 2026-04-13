'use client';

import { useState, useEffect } from 'react';
import Navbar from '../components/Navbar';
import Dashboard from '../components/Dashboard';
import Portfolios from '../components/Portfolios';
import CreateBot from '../components/CreateBot';
import Settings from '../components/Settings';
import Notifications from '../components/Notifications';
import { getBotStatus } from '../lib/api';
import { Lang } from '../lib/i18n';

type Tab = 'dashboard' | 'portfolios' | 'create' | 'settings' | 'notifications';

export default function App() {
  const [tab, setTab]               = useState<Tab>('dashboard');
  const [botRunning, setBotRunning] = useState(false);
  const [lang, setLang]             = useState<Lang>('ar');
  const [dark, setDark]             = useState(true);

  // Apply dark/light class to <html>
  useEffect(() => {
    const html = document.documentElement;
    if (dark) {
      html.classList.add('dark');
      html.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');
      html.setAttribute('lang', lang);
    } else {
      html.classList.remove('dark');
      html.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');
      html.setAttribute('lang', lang);
    }
  }, [dark, lang]);

  // Restore preferences from localStorage
  useEffect(() => {
    const savedLang  = localStorage.getItem('lang') as Lang | null;
    const savedTheme = localStorage.getItem('theme');
    if (savedLang)  setLang(savedLang);
    if (savedTheme) setDark(savedTheme === 'dark');
  }, []);

  const toggleLang = () => {
    const next = lang === 'ar' ? 'en' : 'ar';
    setLang(next);
    localStorage.setItem('lang', next);
  };

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
  };

  useEffect(() => {
    const check = () => getBotStatus().then(s => setBotRunning(s.running)).catch(() => {});
    check();
    const t = setInterval(check, 15000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Navbar
        active={tab}
        onNav={setTab}
        botRunning={botRunning}
        lang={lang}
        onLangToggle={toggleLang}
        dark={dark}
        onThemeToggle={toggleTheme}
      />
      <main className="max-w-7xl mx-auto px-4 py-6">
        {tab === 'dashboard'     && <Dashboard     lang={lang} />}
        {tab === 'portfolios'    && <Portfolios    lang={lang} onActivated={() => setTab('dashboard')} />}
        {tab === 'create'        && <CreateBot     lang={lang} onCreated={() => setTab('portfolios')} />}
        {tab === 'settings'      && <Settings      lang={lang} onSaved={() => setTab('dashboard')} />}
        {tab === 'notifications' && <Notifications lang={lang} />}
      </main>
    </div>
  );
}
