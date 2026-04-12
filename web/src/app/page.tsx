'use client';

import { useState, useEffect } from 'react';
import Navbar from '../components/Navbar';
import Dashboard from '../components/Dashboard';
import CreateBot from '../components/CreateBot';
import Settings from '../components/Settings';
import { getBotStatus } from '../lib/api';

type Tab = 'dashboard' | 'create' | 'settings';

export default function App() {
  const [tab, setTab]           = useState<Tab>('dashboard');
  const [botRunning, setBotRunning] = useState(false);

  useEffect(() => {
    const check = () => getBotStatus().then(s => setBotRunning(s.running)).catch(() => {});
    check();
    const t = setInterval(check, 15000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="min-h-screen bg-gray-950">
      <Navbar active={tab} onNav={setTab} botRunning={botRunning} />
      <main className="max-w-7xl mx-auto px-4 py-6">
        {tab === 'dashboard' && <Dashboard />}
        {tab === 'create'    && <CreateBot onCreated={() => setTab('dashboard')} />}
        {tab === 'settings'  && <Settings  onSaved={() => setTab('dashboard')} />}
      </main>
    </div>
  );
}
