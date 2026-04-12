'use client';

import { useEffect, useState } from 'react';
import { getNotifConfig, updateNotifConfig, testDiscord } from '../lib/api';
import { Lang, tr } from '../lib/i18n';

interface Props { lang: Lang; }

export default function Notifications({ lang }: Props) {
  const [discordEnabled,    setDiscordEnabled]    = useState(false);
  const [discordWebhook,    setDiscordWebhook]    = useState('');
  const [telegramEnabled,   setTelegramEnabled]   = useState(false);
  const [saving,            setSaving]            = useState(false);
  const [testing,           setTesting]           = useState(false);
  const [msg,               setMsg]               = useState('');
  const [loaded,            setLoaded]            = useState(false);

  useEffect(() => {
    getNotifConfig().then(c => {
      setDiscordEnabled(c.discord_enabled ?? false);
      setDiscordWebhook(c.discord_webhook_url ?? '');
      setTelegramEnabled(c.telegram_enabled ?? false);
      setLoaded(true);
    }).catch(() => setLoaded(true));
  }, []);

  const save = async () => {
    setSaving(true); setMsg('');
    try {
      await updateNotifConfig({
        discord_enabled: discordEnabled,
        discord_webhook_url: discordWebhook.trim(),
        telegram_enabled: telegramEnabled,
      });
      setMsg('✅ ' + tr('successSaved', lang));
    } catch (e: any) {
      setMsg('❌ ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleTestDiscord = async () => {
    if (!discordWebhook.trim()) { setMsg('❌ ' + tr('discordWebhook', lang) + ' ' + tr('errSymbol', lang)); return; }
    setTesting(true); setMsg('');
    try {
      // Save first so the backend uses the latest webhook
      await updateNotifConfig({ discord_webhook_url: discordWebhook.trim(), discord_enabled: discordEnabled });
      await testDiscord();
      setMsg('✅ ' + (lang === 'ar' ? 'تم إرسال رسالة اختبار إلى Discord' : 'Test message sent to Discord'));
    } catch (e: any) {
      setMsg('❌ ' + e.message);
    } finally {
      setTesting(false);
    }
  };

  if (!loaded) return (
    <div className="text-center py-20 animate-pulse" style={{ color: 'var(--text-muted)' }}>
      {tr('loadingData', lang)}
    </div>
  );

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--text-main)' }}>{tr('notifTitle', lang)}</h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          {lang === 'ar'
            ? 'اختر قنوات الإشعارات التي تريد تفعيلها'
            : 'Choose which notification channels to enable'}
        </p>
      </div>

      {/* Telegram */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-semibold flex items-center gap-2" style={{ color: 'var(--text-main)' }}>
              <span className="text-xl">📱</span> Telegram
            </div>
            <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
              {lang === 'ar'
                ? 'يتطلب ضبط TELEGRAM_BOT_TOKEN في متغيرات البيئة'
                : 'Requires TELEGRAM_BOT_TOKEN environment variable'}
            </div>
          </div>
          <div className={`w-11 h-6 rounded-full transition-colors relative cursor-pointer ${telegramEnabled ? 'bg-brand' : 'bg-gray-700'}`}
            onClick={() => setTelegramEnabled(!telegramEnabled)}>
            <div className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${telegramEnabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
          </div>
        </div>
        {telegramEnabled && (
          <div className="mt-3 p-3 rounded-xl text-xs" style={{ background: 'var(--bg-input)', color: 'var(--text-muted)' }}>
            {lang === 'ar'
              ? 'الأوامر المتاحة: /start /status /rebalance /history /stats /export /stop /help'
              : 'Available commands: /start /status /rebalance /history /stats /export /stop /help'}
          </div>
        )}
      </div>

      {/* Discord */}
      <div className="card space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-semibold flex items-center gap-2" style={{ color: 'var(--text-main)' }}>
              <span className="text-xl">🎮</span> Discord
            </div>
            <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
              {lang === 'ar'
                ? 'إشعارات اختيارية عبر Discord Webhook'
                : 'Optional notifications via Discord Webhook'}
            </div>
          </div>
          <div className={`w-11 h-6 rounded-full transition-colors relative cursor-pointer ${discordEnabled ? 'bg-brand' : 'bg-gray-700'}`}
            onClick={() => setDiscordEnabled(!discordEnabled)}>
            <div className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${discordEnabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
          </div>
        </div>

        {discordEnabled && (
          <div className="space-y-3">
            <div>
              <label className="label">{tr('discordWebhook', lang)}</label>
              <input
                className="input font-mono text-xs"
                value={discordWebhook}
                onChange={e => setDiscordWebhook(e.target.value)}
                placeholder="https://discord.com/api/webhooks/..."
              />
              <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                {tr('discordDesc', lang)}
              </p>
            </div>
            <button onClick={handleTestDiscord} disabled={testing} className="btn-secondary text-sm">
              {testing ? '⏳ ...' : '🧪 ' + tr('testDiscord', lang)}
            </button>
          </div>
        )}
      </div>

      {msg && (
        <div className={`card text-sm ${msg.startsWith('❌') ? 'border-red-700 text-red-400' : 'border-green-700 text-green-400'}`}>
          {msg}
        </div>
      )}

      <button onClick={save} disabled={saving} className="btn-primary w-full py-3 text-base">
        {saving ? '⏳ ' + tr('saving', lang) : '💾 ' + tr('save', lang)}
      </button>
    </div>
  );
}
