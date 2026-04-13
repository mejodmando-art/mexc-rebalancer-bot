'use client';

import { useState, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import Navbar from '../components/Navbar';
import Sidebar from '../components/Sidebar';
import Dashboard from '../components/Dashboard';
import Portfolios from '../components/Portfolios';
import CreateBot from '../components/CreateBot';
import Settings from '../components/Settings';
import Notifications from '../components/Notifications';
import { ToastProvider } from '../components/Toast';
import { getBotStatus } from '../lib/api';
import { Lang } from '../lib/i18n';

type Tab = 'dashboard' | 'portfolios' | 'create' | 'settings' | 'notifications';

export default function App() {
  const [tab,        setTab]        = useState<Tab>('dashboard');
  const [botRunning, setBotRunning] = useState(false);
  const [lang,       setLang]       = useState<Lang>('ar');
  const [dark,       setDark]       = useState(true);

  // Apply dark/light + RTL/LTR
  useEffect(() => {
    const html = document.documentElement;
    dark ? html.classList.add('dark') : html.classList.remove('dark');
    html.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');
    html.setAttribute('lang', lang);
  }, [dark, lang]);

  // Restore preferences
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

  // Poll bot status
  useEffect(() => {
    const check = () => getBotStatus().then(s => setBotRunning(s.running)).catch(() => {});
    check();
    const t = setInterval(check, 15000);
    return () => clearInterval(t);
  }, []);

  return (
    <ToastProvider>
      <div className="min-h-screen" style={{ background: 'var(--bg-base)' }}>
        {/* Sidebar — desktop only */}
        <Sidebar active={tab} onNav={setTab} botRunning={botRunning} lang={lang} />

        {/* Right side: navbar + content */}
        <div className="lg:ps-60 xl:ps-64 flex flex-col min-h-screen">
          <Navbar
            active={tab}
            onNav={setTab}
            botRunning={botRunning}
            lang={lang}
            onLangToggle={toggleLang}
            dark={dark}
            onThemeToggle={toggleTheme}
          />

          <main className="flex-1 px-4 sm:px-6 py-6 pb-24 lg:pb-8 max-w-screen-xl mx-auto w-full">
            <AnimatePresence mode="wait">
              <motion.div
                key={tab}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
              >
                {tab === 'dashboard'     && <Dashboard     lang={lang} />}
                {tab === 'portfolios'    && <Portfolios    lang={lang} onActivated={() => setTab('dashboard')} />}
                {tab === 'create'        && <CreateBot     lang={lang} onCreated={() => setTab('portfolios')} />}
                {tab === 'settings'      && <Settings      lang={lang} onSaved={() => setTab('dashboard')} />}
                {tab === 'notifications' && <Notifications lang={lang} />}
              </motion.div>
            </AnimatePresence>
          </main>
        </div>
      </div>
    </ToastProvider>
  );
}
