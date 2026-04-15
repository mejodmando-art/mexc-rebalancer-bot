'use client';

import { useState, useEffect, useCallback } from 'react';
import { Grid3x3, TrendingUp, Zap, Info, Plus, Square, Play, Trash2, RefreshCw } from 'lucide-react';
import { Lang } from '../lib/i18n';
import { listGridBots, createGridBot, stopGridBot, resumeGridBot, deleteGridBot, previewGridBot, getGridOrders } from '../lib/api';

interface Props { lang: Lang; }

function WaveChart({ low, high, current }: { low: number; high: number; current: number }) {
  const pct = high > low ? ((current - low) / (high - low)) * 100 : 50;
  const cx = Math.min(Math.max(pct, 2), 98) * 3.6;
  return (
    <div className="relative w-full h-32 rounded-2xl overflow-hidden" style={{ background: 'var(--bg-input)' }}>
      <svg viewBox="0 0 360 100" className="w-full h-full" preserveAspectRatio="none">
        <defs>
          <linearGradient id="wg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#00D4AA" stopOpacity="0.2" />
            <stop offset="100%" stopColor="#00D4AA" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1="0" y1="20" x2="360" y2="20" stroke="#FF7B72" strokeWidth="1" strokeDasharray="4,3" opacity="0.6" />
        <line x1="0" y1="80" x2="360" y2="80" stroke="#00D4AA" strokeWidth="1" strokeDasharray="4,3" opacity="0.6" />
        <path d="M0,80 C50,80 70,20 110,20 C150,20 170,90 210,90 C250,90 270,30 300,30 C330,30 345,55 360,50" fill="none" stroke="#00D4AA" strokeWidth="2.5" strokeLinecap="round" />
        <path d="M0,80 C50,80 70,20 110,20 C150,20 170,90 210,90 C250,90 270,30 300,30 C330,30 345,55 360,50 L360,100 L0,100 Z" fill="url(#wg)" />
        <circle cx={cx} cy="50" r="5" fill="#F0B90B" stroke="#0F1520" strokeWidth="2" />
        <text x="8" y="16" fontSize="8" fill="#FF7B72" fontWeight="700">H: {high > 0 ? high.toFixed(4) : '—'}</text>
        <text x="8" y="96" fontSize="8" fill="#00D4AA" fontWeight="700">L: {low > 0 ? low.toFixed(4) : '—'}</text>
        {current > 0 && <text x="180" y="48" fontSize="8" fill="#F0B90B" fontWeight="800" textAnchor="middle">● {current.toFixed(4)}</text>}
      </svg>
    </div>
  );
}

function CreateForm({ lang, onCreated }: { lang: Lang; onCreated: () => void }) {
  const ar = lang === 'ar';
  const [symbol, setSymbol]         = useState('BTC');
  const [investment, setInvestment] = useState('');
  const [preview, setPreview]       = useState<any>(null);
  const [loading, setLoading]       = useState(false);
  const [creating, setCreating]     = useState(false);
  const [error, setError]           = useState('');

  const fetchPreview = useCallback(async () => {
    const inv = parseFloat(investment);
    if (!symbol || inv < 1) { setPreview(null); return; }
    setLoading(true);
    try { setPreview(await previewGridBot(symbol, inv)); setError(''); }
    catch (e: any) { setError(e.message); setPreview(null); }
    finally { setLoading(false); }
  }, [symbol, investment]);

  useEffect(() => { const t = setTimeout(fetchPreview, 700); return () => clearTimeout(t); }, [fetchPreview]);

  const handleCreate = async () => {
    const inv = parseFloat(investment);
    if (!symbol || inv < 1) { setError(ar ? 'أدخل الزوج والمبلغ' : 'Enter symbol and amount'); return; }
    setCreating(true); setError('');
    try { await createGridBot({ symbol, investment: inv }); onCreated(); }
    catch (e: any) { setError(e.message); }
    finally { setCreating(false); }
  };

  const POPULAR = ['BTC','ETH','SOL','BNB','XRP','ADA'];

  return (
    <div className="space-y-4">
      <div className="card p-4 space-y-3">
        <div className="label">{ar ? 'الزوج (اختياري)' : 'Trading Pair (optional)'}</div>
        <div className="flex flex-wrap gap-2">
          {POPULAR.map(s => (
            <button key={s} onClick={() => setSymbol(s)}
              className="px-3 py-1.5 rounded-xl text-xs font-bold transition-all"
              style={{ background: symbol===s ? 'rgba(240,185,11,0.15)' : 'var(--bg-input)', color: symbol===s ? '#F0B90B' : 'var(--text-muted)', border: `1px solid ${symbol===s ? 'rgba(240,185,11,0.4)' : 'var(--border)'}`, boxShadow: symbol===s ? '0 2px 8px rgba(240,185,11,0.2)' : 'none' }}>
              {s}
            </button>
          ))}
        </div>
        <input className="input font-mono uppercase" value={symbol}
          onChange={e => setSymbol(e.target.value.toUpperCase().replace('USDT',''))}
          placeholder="BTC" maxLength={10} />
        <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{ar ? 'سيتم إضافة USDT تلقائياً' : 'USDT appended automatically'}</div>
      </div>

      <div className="card p-4 space-y-3">
        <div className="label">{ar ? 'مبلغ الاستثمار (USDT)' : 'Investment Amount (USDT)'}</div>
        <div className="relative">
          <input type="number" min={10} className="input ps-16 text-lg font-bold num"
            value={investment} onChange={e => setInvestment(e.target.value)} placeholder="100" />
          <span className="absolute start-3 top-1/2 -translate-y-1/2 text-sm font-bold" style={{ color: 'var(--text-muted)' }}>USDT</span>
        </div>
        <div className="flex gap-2">
          {[50,100,200,500].map(v => (
            <button key={v} onClick={() => setInvestment(String(v))}
              className="flex-1 py-1.5 rounded-xl text-xs font-bold transition-all"
              style={{ background: investment===String(v) ? 'rgba(240,185,11,0.12)' : 'var(--bg-input)', color: investment===String(v) ? '#F0B90B' : 'var(--text-muted)', border: `1px solid ${investment===String(v) ? 'rgba(240,185,11,0.3)' : 'var(--border)'}` }}>
              ${v}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="card p-4 text-center text-sm animate-pulse" style={{ color: 'var(--text-muted)' }}>{ar ? 'جاري حساب الشبكة...' : 'Calculating grid...'}</div>}

      {preview && !loading && (
        <div className="card p-4 space-y-3 animate-fade-up">
          <WaveChart low={preview.price_low} high={preview.price_high} current={preview.current_price} />
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: ar ? 'السعر الحالي' : 'Current Price', value: `$${preview.current_price.toFixed(4)}`, color: '#F0B90B' },
              { label: ar ? 'عدد الشبكات' : 'Grid Count',    value: preview.grid_count,                     color: '#60A5FA' },
              { label: ar ? 'USDT لكل شبكة' : 'Per Grid',    value: `$${preview.usdt_per_grid.toFixed(2)}`, color: '#A78BFA' },
              { label: ar ? 'ربح لكل شبكة' : 'Grid Profit',  value: `${preview.profit_per_grid_pct}%`,      color: '#00D4AA' },
            ].map(({ label, value, color }) => (
              <div key={label} className="rounded-xl p-3" style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}>
                <div className="text-[10px] font-bold uppercase tracking-wide mb-1" style={{ color: 'var(--text-muted)' }}>{label}</div>
                <div className="num font-bold text-sm" style={{ color }}>{value}</div>
              </div>
            ))}
          </div>
          <div className="flex justify-between text-xs" style={{ color: 'var(--text-muted)' }}>
            <span>{ar ? 'نطاق:' : 'Range:'} ${preview.price_low.toFixed(4)}</span>
            <span>→ ${preview.price_high.toFixed(4)}</span>
          </div>
        </div>
      )}

      {error && <div className="card p-3 text-sm text-red-400 border-red-800">{error}</div>}

      <button onClick={handleCreate} disabled={creating || !investment} className="btn-accent w-full py-4 text-base"
        style={{ background: 'linear-gradient(135deg,#F0B90B,#D4A017)', color: '#000', boxShadow: '0 4px 20px rgba(240,185,11,0.35)' }}>
        {creating ? (ar ? '⏳ جاري الإنشاء...' : '⏳ Creating...') : (ar ? '⚡ إنشاء بوت الشبكات' : '⚡ Create Grid Bot')}
      </button>
    </div>
  );
}

function BotCard({ bot, lang, onRefresh }: { bot: any; lang: Lang; onRefresh: () => void }) {
  const ar = lang === 'ar';
  const [stopping, setStopping]     = useState(false);
  const [deleting, setDeleting]     = useState(false);
  const [confirm, setConfirm]       = useState(false);
  const [orders, setOrders]         = useState<any[]>([]);
  const [showOrders, setShowOrders] = useState(false);

  const loadOrders = async () => { try { setOrders(await getGridOrders(bot.id)); } catch {} };

  const handleStop = async () => {
    setStopping(true);
    try { await stopGridBot(bot.id); onRefresh(); } catch {}
    setStopping(false);
  };
  const handleResume = async () => {
    setStopping(true);
    try { await resumeGridBot(bot.id); onRefresh(); } catch {}
    setStopping(false);
  };
  const handleDelete = async () => {
    setDeleting(true);
    try { await deleteGridBot(bot.id); onRefresh(); } catch {}
    setDeleting(false);
  };

  const profitColor = (bot.profit || 0) >= 0 ? '#00D4AA' : '#FF7B72';

  return (
    <div className="card p-4 space-y-3 animate-fade-up"
      style={bot.running ? { borderColor: 'rgba(240,185,11,0.4)', boxShadow: '0 0 20px rgba(240,185,11,0.08)' } : {}}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-9 h-9 rounded-xl flex items-center justify-center font-bold text-xs"
            style={{ background: 'rgba(240,185,11,0.15)', color: '#F0B90B', border: '1px solid rgba(240,185,11,0.3)' }}>
            {bot.symbol?.replace('USDT','')}
          </span>
          <div>
            <div className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>{bot.symbol}</div>
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{bot.ts_created?.slice(0,16)}</div>
          </div>
        </div>
        <span className="badge text-xs font-bold"
          style={bot.running
            ? { background: 'rgba(240,185,11,0.12)', color: '#F0B90B', border: '1px solid rgba(240,185,11,0.3)' }
            : { background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
          {bot.running ? (ar ? '● شغّال' : '● Running') : (ar ? 'متوقف' : 'Stopped')}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        {[
          { label: ar ? 'الاستثمار' : 'Investment', value: `$${(bot.investment||0).toFixed(0)}`, color: '#60A5FA' },
          { label: ar ? 'الشبكات' : 'Grids',        value: bot.grid_count,                       color: '#A78BFA' },
          { label: ar ? 'الربح' : 'Profit',          value: `$${(bot.profit||0).toFixed(2)}`,     color: profitColor },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded-xl p-2 text-center" style={{ background: 'var(--bg-input)' }}>
            <div className="text-[9px] font-bold uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>{label}</div>
            <div className="num font-bold text-sm mt-0.5" style={{ color }}>{value}</div>
          </div>
        ))}
      </div>

      <div className="flex justify-between text-xs px-1" style={{ color: 'var(--text-muted)' }}>
        <span>↓ ${(bot.price_low||0).toFixed(4)}</span>
        <span style={{ color: 'var(--text-main)', fontWeight: 700 }}>{ar ? 'النطاق' : 'Range'}</span>
        <span>↑ ${(bot.price_high||0).toFixed(4)}</span>
      </div>

      <button onClick={() => { setShowOrders(!showOrders); if (!showOrders) loadOrders(); }}
        className="w-full text-xs py-2 rounded-xl transition-all"
        style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
        {showOrders ? '▲' : '▼'} {ar ? `الأوامر (${bot.open_orders??0} مفتوح)` : `Orders (${bot.open_orders??0} open)`}
      </button>

      {showOrders && orders.length > 0 && (
        <div className="space-y-1 max-h-40 overflow-y-auto">
          {orders.slice(0,20).map(o => (
            <div key={o.id} className="flex justify-between items-center px-3 py-1.5 rounded-xl text-xs"
              style={{ background: 'var(--bg-input)' }}>
              <span style={{ color: o.side==='BUY' ? '#00D4AA' : '#FF7B72', fontWeight: 700 }}>{o.side}</span>
              <span className="num" style={{ color: 'var(--text-main)' }}>${(o.price||0).toFixed(4)}</span>
              <span style={{ color: 'var(--text-muted)' }}>{(o.qty||0).toFixed(6)}</span>
              <span className="px-1.5 py-0.5 rounded-full text-[9px] font-bold"
                style={{ background: o.status==='open' ? 'rgba(96,165,250,0.15)' : 'rgba(0,212,170,0.12)', color: o.status==='open' ? '#60A5FA' : '#00D4AA' }}>
                {o.status}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2 pt-1">
        {bot.running ? (
          <button onClick={handleStop} disabled={stopping}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-sm font-bold disabled:opacity-40"
            style={{ background: 'rgba(255,123,114,0.1)', color: '#FF7B72', border: '1px solid rgba(255,123,114,0.25)' }}>
            <Square size={13} /> {stopping ? '...' : (ar ? 'إيقاف' : 'Stop')}
          </button>
        ) : (
          <button onClick={handleResume} disabled={stopping}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-sm font-bold disabled:opacity-40"
            style={{ background: 'rgba(0,212,170,0.1)', color: '#00D4AA', border: '1px solid rgba(0,212,170,0.25)' }}>
            <Play size={13} /> {stopping ? '...' : (ar ? 'استئناف' : 'Resume')}
          </button>
        )}
        {confirm ? (
          <div className="flex gap-1">
            <button onClick={handleDelete} disabled={deleting}
              className="px-3 py-2 rounded-xl text-xs font-bold"
              style={{ background: 'rgba(255,123,114,0.15)', color: '#FF7B72', border: '1px solid rgba(255,123,114,0.3)' }}>
              {deleting ? '...' : (ar ? 'تأكيد' : 'Confirm')}
            </button>
            <button onClick={() => setConfirm(false)}
              className="px-3 py-2 rounded-xl text-xs font-bold"
              style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
              ✖
            </button>
          </div>
        ) : (
          <button onClick={() => setConfirm(true)}
            className="px-3 py-2 rounded-xl"
            style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
            <Trash2 size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

export default function GridBot({ lang }: Props) {
  const ar = lang === 'ar';
  const [view, setView]       = useState<'list' | 'create'>('list');
  const [bots, setBots]       = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { setBots(await listGridBots()); } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  const totalProfit  = bots.reduce((s, b) => s + (b.profit || 0), 0);
  const runningCount = bots.filter(b => b.running).length;

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-2xl flex items-center justify-center shrink-0"
            style={{ background: 'linear-gradient(145deg,rgba(240,185,11,0.25),rgba(240,185,11,0.08))', border: '1px solid rgba(240,185,11,0.35)', boxShadow: '0 4px 16px rgba(240,185,11,0.2)' }}>
            <Grid3x3 size={22} style={{ color: '#F0B90B', filter: 'drop-shadow(0 0 6px rgba(240,185,11,0.5))' }} />
          </div>
          <div>
            <h1 className="text-xl font-bold" style={{ color: 'var(--text-main)', letterSpacing: '-0.02em' }}>
              {ar ? 'بوت الشبكات' : 'Grid Bot'}
            </h1>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {ar ? 'تداول شبكي ديناميكي على MEXC' : 'Dynamic grid trading on MEXC'}
            </p>
          </div>
        </div>
        <button onClick={() => setView(view === 'create' ? 'list' : 'create')}
          className="flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-sm transition-all"
          style={{ background: view==='create' ? 'var(--bg-input)' : 'linear-gradient(135deg,#F0B90B,#D4A017)', color: view==='create' ? 'var(--text-muted)' : '#000', boxShadow: view==='create' ? 'none' : '0 4px 16px rgba(240,185,11,0.3)', border: '1px solid transparent' }}>
          <Plus size={15} />
          {view==='create' ? (ar ? 'القائمة' : 'List') : (ar ? 'إنشاء شبكة' : 'New Grid')}
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: ar ? 'إجمالي الشبكات' : 'Total Bots',  value: bots.length,                          color: '#F0B90B', icon: Grid3x3 },
          { label: ar ? 'شغّالة الآن' : 'Running',         value: runningCount,                         color: '#00D4AA', icon: Zap },
          { label: ar ? 'إجمالي الربح' : 'Total Profit',   value: `$${totalProfit.toFixed(2)}`,         color: totalProfit >= 0 ? '#00D4AA' : '#FF7B72', icon: TrendingUp },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} className="card p-3 flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5">
              <span className="w-6 h-6 rounded-lg flex items-center justify-center" style={{ background: `${color}18` }}>
                <Icon size={12} style={{ color }} />
              </span>
              <span className="text-[10px] font-bold uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>{label}</span>
            </div>
            <span className="num font-bold text-lg" style={{ color }}>{value}</span>
          </div>
        ))}
      </div>

      <div className="flex items-start gap-2 rounded-2xl p-3"
        style={{ background: 'rgba(240,185,11,0.06)', border: '1px solid rgba(240,185,11,0.2)' }}>
        <Info size={14} className="shrink-0 mt-0.5" style={{ color: '#F0B90B' }} />
        <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {ar
            ? 'البوت يضع أوامر شراء وبيع تلقائياً ضمن نطاق السعر. عند تنفيذ أمر شراء يُوضع أمر بيع أعلى منه، وعند تنفيذ البيع يُوضع شراء جديد — وهكذا تتراكم الأرباح.'
            : 'The bot places buy/sell limit orders within the price range. When a buy fills a sell is placed above it; when a sell fills a new buy is placed below — profits accumulate each cycle.'}
        </p>
      </div>

      <div key={view} className="animate-fade-up">
        {view === 'create' ? (
          <CreateForm lang={lang} onCreated={() => { setView('list'); load(); }} />
        ) : loading ? (
          <div className="text-center py-16 animate-pulse" style={{ color: 'var(--text-muted)' }}>
            {ar ? 'جاري التحميل...' : 'Loading...'}
          </div>
        ) : bots.length === 0 ? (
          <div className="card flex flex-col items-center justify-center py-16 gap-4">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center"
              style={{ background: 'rgba(240,185,11,0.1)', border: '1px solid rgba(240,185,11,0.2)' }}>
              <Grid3x3 size={32} style={{ color: '#F0B90B' }} />
            </div>
            <div className="text-center">
              <div className="font-bold text-base mb-1" style={{ color: 'var(--text-main)' }}>
                {ar ? 'لا توجد شبكات بعد' : 'No grid bots yet'}
              </div>
              <div className="text-sm" style={{ color: 'var(--text-muted)' }}>
                {ar ? 'أنشئ شبكتك الأولى بالضغط على "إنشاء شبكة"' : 'Create your first grid bot above'}
              </div>
            </div>
            <button onClick={() => setView('create')}
              className="px-6 py-2.5 rounded-xl font-bold text-sm"
              style={{ background: 'linear-gradient(135deg,#F0B90B,#D4A017)', color: '#000', boxShadow: '0 4px 16px rgba(240,185,11,0.3)' }}>
              {ar ? '+ إنشاء شبكة' : '+ New Grid'}
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold" style={{ color: 'var(--text-muted)' }}>
                {bots.length} {ar ? 'شبكة' : 'bots'}
              </span>
              <button onClick={load} className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-xl"
                style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
                <RefreshCw size={12} /> {ar ? 'تحديث' : 'Refresh'}
              </button>
            </div>
            {bots.map(b => <BotCard key={b.id} bot={b} lang={lang} onRefresh={load} />)}
          </div>
        )}
      </div>
    </div>
  );
}
