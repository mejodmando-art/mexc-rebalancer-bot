'use client';

import { useState, useEffect } from 'react';
import { Moon, Sun, Globe, Bell, RefreshCw, Shield, Palette, Info } from 'lucide-react';
import { Lang } from '../lib/i18n';
import { getNotifConfig, updateNotifConfig, testDiscord } from '../lib/api';

interface Props {
  lang: Lang;
  dark: boolean;
  onLangToggle: () => void;
  onThemeToggle: () => void;
  onSaved: () => void;
}

export default function Settings({ lang, dark, onLangToggle, onThemeToggle }: Props) {
  const ar = lang === 'ar';

  const [telegramToken,  setTelegramToken]  = useState('');
  const [telegramChatId, setTelegramChatId] = useState('');
  const [discordWebhook, setDiscordWebhook] = useState('');
  const [notifLoading,   setNotifLoading]   = useState(false);
  const [notifSaving,    setNotifSaving]    = useState(false);
  const [testingDiscord, setTestingDiscord] = useState(false);
  const [msg,            setMsg]            = useState('');

  const [refreshInterval, setRefreshInterval] = useState<number>(() => {
    if (typeof window !== 'undefined') {
      return parseInt(localStorage.getItem('refreshInterval') || '15', 10);
    }
    return 15;
  });

  useEffect(() => {
    setNotifLoading(true);
    getNotifConfig()
      .then((c: any) => {
        setTelegramToken(c.telegram_token   ?? '');
        setTelegramChatId(c.telegram_chat_id ?? '');
        setDiscordWebhook(c.discord_webhook  ?? '');
      })
      .catch(() => {})
      .finally(() => setNotifLoading(false));
  }, []);

  const saveNotifications = async () => {
    setNotifSaving(true); setMsg('');
    try {
      await updateNotifConfig({
        telegram_token:   telegramToken  || null,
        telegram_chat_id: telegramChatId || null,
        discord_webhook:  discordWebhook || null,
      });
      setMsg('✅ ' + (ar ? 'تم حفظ إعدادات الإشعارات' : 'Notification settings saved'));
    } catch (e: any) {
      setMsg('❌ ' + e.message);
    } finally {
      setNotifSaving(false);
    }
  };

  const handleTestDiscord = async () => {
    setTestingDiscord(true); setMsg('');
    try {
      await testDiscord();
      setMsg('✅ ' + (ar ? 'تم إرسال رسالة تجريبية إلى Discord' : 'Test message sent to Discord'));
    } catch (e: any) {
      setMsg('❌ ' + e.message);
    } finally {
      setTestingDiscord(false);
    }
  };

  const handleRefreshChange = (val: number) => {
    setRefreshInterval(val);
    localStorage.setItem('refreshInterval', String(val));
  };

  function Section({
    icon: Icon, color, title, desc, children,
  }: {
    icon: React.ElementType; color: string; title: string; desc?: string; children: React.ReactNode;
  }) {
    return (
      <div className="card space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: `${color}20`, border: `1px solid ${color}40` }}>
            <Icon size={18} strokeWidth={2.5} style={{ color }} />
          </div>
          <div>
            <div className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>{title}</div>
            {desc && <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{desc}</div>}
          </div>
        </div>
        {children}
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--text-main)' }}>
          {ar ? 'الإعدادات' : 'Settings'}
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          {ar ? 'تخصيص تجربة الاستخدام والإشعارات' : 'Customize your experience and notifications'}
        </p>
      </div>

      {/* Appearance */}
      <Section icon={Palette} color="#A78BFA"
        title={ar ? 'المظهر' : 'Appearance'}
        desc={ar ? 'السمة واللغة' : 'Theme and language'}>
        <div className="grid grid-cols-2 gap-3">
          <button onClick={onThemeToggle}
            className="flex items-center justify-between px-4 py-3 rounded-xl transition-all"
            style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}>
            <div className="text-start">
              <div className="text-xs font-bold" style={{ color: 'var(--text-muted)' }}>{ar ? 'السمة' : 'Theme'}</div>
              <div className="text-sm font-bold mt-0.5" style={{ color: 'var(--text-main)' }}>
                {dark ? (ar ? 'داكن' : 'Dark') : (ar ? 'فاتح' : 'Light')}
              </div>
            </div>
            <div className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: dark ? 'rgba(167,139,250,0.15)' : 'rgba(251,191,36,0.15)' }}>
              {dark ? <Moon size={18} strokeWidth={2.5} style={{ color: '#A78BFA' }} />
                    : <Sun  size={18} strokeWidth={2.5} style={{ color: '#FBBF24' }} />}
            </div>
          </button>

          <button onClick={onLangToggle}
            className="flex items-center justify-between px-4 py-3 rounded-xl transition-all"
            style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}>
            <div className="text-start">
              <div className="text-xs font-bold" style={{ color: 'var(--text-muted)' }}>{ar ? 'اللغة' : 'Language'}</div>
              <div className="text-sm font-bold mt-0.5" style={{ color: 'var(--text-main)' }}>
                {ar ? 'العربية' : 'English'}
              </div>
            </div>
            <div className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(96,165,250,0.15)' }}>
              <Globe size={18} strokeWidth={2.5} style={{ color: '#60A5FA' }} />
            </div>
          </button>
        </div>
      </Section>

      {/* Data refresh */}
      <Section icon={RefreshCw} color="#00D4AA"
        title={ar ? 'تحديث البيانات' : 'Data Refresh'}
        desc={ar ? 'معدل تحديث لوحة التحكم تلقائياً' : 'Dashboard auto-refresh interval'}>
        <div className="flex gap-2 flex-wrap">
          {[5, 10, 15, 30, 60].map(v => (
            <button key={v} onClick={() => handleRefreshChange(v)}
              className="flex-1 min-w-[52px] py-2 rounded-xl text-sm font-bold transition-all"
              style={{
                background: refreshInterval === v ? 'rgba(0,212,170,0.15)' : 'var(--bg-input)',
                color: refreshInterval === v ? '#00D4AA' : 'var(--text-muted)',
                border: `1px solid ${refreshInterval === v ? 'rgba(0,212,170,0.4)' : 'var(--border)'}`,
              }}>
              {v}{ar ? 'ث' : 's'}
            </button>
          ))}
        </div>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {ar ? `يتم تحديث البيانات كل ${refreshInterval} ثانية` : `Refreshes every ${refreshInterval} seconds`}
        </p>
      </Section>

      {/* Notifications */}
      <Section icon={Bell} color="#F0B90B"
        title={ar ? 'الإشعارات' : 'Notifications'}
        desc={ar ? 'Telegram و Discord' : 'Telegram & Discord alerts'}>
        {notifLoading ? (
          <div className="text-center py-4 animate-pulse text-sm" style={{ color: 'var(--text-muted)' }}>
            {ar ? 'جاري التحميل...' : 'Loading...'}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <div className="text-xs font-bold" style={{ color: 'var(--text-muted)' }}>Telegram Bot Token</div>
              <input className="input text-sm font-mono" value={telegramToken}
                onChange={e => setTelegramToken(e.target.value)}
                placeholder="123456:ABC-DEF..." dir="ltr" />
            </div>
            <div className="space-y-1.5">
              <div className="text-xs font-bold" style={{ color: 'var(--text-muted)' }}>Telegram Chat ID</div>
              <input className="input text-sm font-mono" value={telegramChatId}
                onChange={e => setTelegramChatId(e.target.value)}
                placeholder="-100123456789" dir="ltr" />
            </div>
            <div className="space-y-1.5">
              <div className="text-xs font-bold" style={{ color: 'var(--text-muted)' }}>Discord Webhook URL</div>
              <input className="input text-sm font-mono" value={discordWebhook}
                onChange={e => setDiscordWebhook(e.target.value)}
                placeholder="https://discord.com/api/webhooks/..." dir="ltr" />
            </div>
            <div className="flex gap-2 pt-1">
              <button onClick={saveNotifications} disabled={notifSaving}
                className="flex-1 py-2.5 rounded-xl text-sm font-bold transition-all"
                style={{
                  background: 'rgba(240,185,11,0.15)', color: '#F0B90B',
                  border: '1px solid rgba(240,185,11,0.35)', opacity: notifSaving ? 0.6 : 1,
                }}>
                {notifSaving ? (ar ? '⏳ حفظ...' : '⏳ Saving...') : (ar ? '💾 حفظ' : '💾 Save')}
              </button>
              {discordWebhook && (
                <button onClick={handleTestDiscord} disabled={testingDiscord}
                  className="px-4 py-2.5 rounded-xl text-sm font-bold transition-all"
                  style={{
                    background: 'rgba(96,165,250,0.12)', color: '#60A5FA',
                    border: '1px solid rgba(96,165,250,0.3)', opacity: testingDiscord ? 0.6 : 1,
                  }}>
                  {testingDiscord ? '...' : (ar ? 'اختبار' : 'Test')}
                </button>
              )}
            </div>
          </div>
        )}
      </Section>

      {/* Security */}
      <Section icon={Shield} color="#34D399"
        title={ar ? 'الأمان' : 'Security'}
        desc={ar ? 'معلومات الاتصال بـ MEXC' : 'MEXC connection info'}>
        <div className="rounded-xl p-3 space-y-2"
          style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}>
          <div className="flex items-center justify-between text-sm">
            <span style={{ color: 'var(--text-muted)' }}>API Key</span>
            <span className="font-mono text-xs px-2 py-0.5 rounded-lg"
              style={{ background: 'rgba(52,211,153,0.1)', color: '#34D399', border: '1px solid rgba(52,211,153,0.25)' }}>
              {ar ? '● متصل' : '● Connected'}
            </span>
          </div>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {ar
              ? 'مفاتيح API محفوظة كمتغيرات بيئة على الخادم ولا تُعرض في الواجهة.'
              : 'API keys are stored as server environment variables and never exposed in the UI.'}
          </p>
        </div>
      </Section>

      {/* About */}
      <Section icon={Info} color="#60A5FA" title={ar ? 'عن التطبيق' : 'About'}>
        <div className="space-y-2 text-sm" style={{ color: 'var(--text-muted)' }}>
          <div className="flex justify-between">
            <span>{ar ? 'الإصدار' : 'Version'}</span>
            <span className="font-mono font-bold" style={{ color: 'var(--text-main)' }}>2.0.0</span>
          </div>
          <div className="flex justify-between">
            <span>{ar ? 'البورصة' : 'Exchange'}</span>
            <span className="font-bold" style={{ color: '#00D4AA' }}>MEXC Spot</span>
          </div>
          <div className="flex justify-between">
            <span>{ar ? 'الخادم' : 'Backend'}</span>
            <span className="font-bold" style={{ color: 'var(--text-main)' }}>FastAPI + Python 3.11</span>
          </div>
        </div>
      </Section>

      {msg && (
        <div className={`card text-sm ${msg.startsWith('❌') ? 'border-red-700 text-red-400' : 'border-green-700 text-green-400'}`}>
          {msg}
        </div>
      )}
    </div>
  );
}
