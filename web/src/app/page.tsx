'use client';

import { useState, useEffect } from 'react';
import Navbar from '../components/Navbar';
import Sidebar from '../components/Sidebar';
import Dashboard from '../components/Dashboard';
import Portfolios from '../components/Portfolios';
import CreateBot from '../components/CreateBot';
import Settings from '../components/Settings';
import CopyPortfolio from '../components/CopyPortfolio';
import GridBot from '../components/GridBot';
import MobileGridBot from '../components/MobileGridBot';
import { ToastProvider } from '../components/Toast';
import { getBotStatus } from '../lib/api';
import { Lang } from '../lib/i18n';
import ErrorBoundary from '../components/ErrorBoundary';

type Tab = 'dashboard' | 'portfolios' | 'create' | 'settings' | 'copy' | 'grid';

export default function App() {
  const [tab,        setTab]        = useState<Tab>('dashboard');
  const [botRunning, setBotRunning] = useState(false);
  const [lang,       setLang]       = useState<Lang>('ar');
  const [dark,       setDark]       = useState(true);

  useEffect(() => {
    const html = document.documentElement;
    if (dark) {
      html.classList.add('dark');
      html.classList.remove('light');
    } else {
      html.classList.remove('dark');
      html.classList.add('light');
    }
    html.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');
    html.setAttribute('lang', lang);
  }, [dark, lang]);

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
    <ErrorBoundary>
    <ToastProvider>
      <div className="min-h-screen" style={{ background: 'var(--bg-base)' }}>
        <Sidebar active={tab} onNav={setTab} botRunning={botRunning} lang={lang} />

        <div className="flex flex-col min-h-screen lg:pl-60 xl:pl-64">
          <Navbar
            active={tab} onNav={setTab} botRunning={botRunning}
            lang={lang} onLangToggle={toggleLang}
            dark={dark} onThemeToggle={toggleTheme}
          />
          <main className="flex-1 px-4 sm:px-6 py-6 pb-24 lg:pb-8 max-w-screen-xl mx-auto w-full">
            <div key={tab} className="animate-fade-up">
              {tab === 'dashboard'  && <Dashboard      lang={lang} />}
              {tab === 'portfolios' && <Portfolios     lang={lang} onActivated={() => setTab('dashboard')} onCreateBot={() => setTab('create')} />}
              {tab === 'create'     && <CreateBot      lang={lang} onCreated={() => setTab('portfolios')} />}
              {tab === 'settings'   && <Settings       lang={lang} onSaved={() => setTab('dashboard')} />}
              {tab === 'copy'       && <CopyPortfolio  lang={lang} onCreated={() => setTab('portfolios')} />}
              {tab === 'grid'       && (
                <>
                  {/* Desktop grid bot view */}
                  <div className="hidden lg:block"><GridBot lang={lang} /></div>
                  {/* Mobile grid bot view */}
                  <div className="block lg:hidden -mx-4 sm:-mx-6"><MobileGridBot lang={lang} onNavigate={setTab} /></div>
                </>
              )}
            </div>
          </main>
        </div>
      </div>
    </ToastProvider>
    </ErrorBoundary>
  );
}
