'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { ArrowLeft, Square, Play, Trash2, RefreshCw, Zap } from 'lucide-react';
import { Lang } from '../lib/i18n';
import { getGridBot, getGridOrders, stopGridBot, resumeGridBot, deleteGridBot, rebuildGridBot } from '../lib/api';
import GridControlChart from './GridControlChart';

interface Props {
  botId: number;
  lang: Lang;
  onBack: () => void;
  onDeleted: () => void;
}

// ── WebSocket price hook ────────────────────────────────────────────────────
function useLivePrice(symbol: string): { price: number | null; connected: boolean } {
  const [price, setPrice]         = useState<number | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (!symbol) return;
    const sym = symbol.toUpperCase().endsWith('USDT') ? symbol.toUpperCase() : `${symbol.toUpperCase()}USDT`;
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/price/${sym}`);
    wsRef.current = ws;

    ws.onopen  = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      // Reconnect after 2 s
      retryRef.current = setTimeout(connect, 2000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d.price) setPrice(parseFloat(d.price));
      } catch {}
    };
  }, [symbol]);

  useEffect(() => {
    connect();
    return () => {
      if (retryRef.current) clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { price, connected };
}

// ── Live chart with draggable control ──────────────────────────────────────
function LiveGridChart({
  bot, livePrice, lang,
  onRebuild,
}: {
  bot: any;
  livePrice: number | null;
  lang: Lang;
  onRebuild: (low: number, high: number) => void;
}) {
  const ar = lang === 'ar';
  const [pendingLow,  setPendingLow]  = useState<number | null>(null);
  const [pendingHigh, setPendingHigh] = useState<number | null>(null);
  const [confirming,  setConfirming]  = useState(false);
  const [rebuilding,  setRebuilding]  = useState(false);

  const current = livePrice ?? bot.current_price ?? ((bot.price_low + bot.price_high) / 2);
  const lowerPct = bot.effective_lower_pct ?? bot.lower_pct ?? 5;
  const upperPct = bot.effective_upper_pct ?? bot.upper_pct ?? 5;

  const handleDrag = (nl: number, nu: number) => {
    const newLow  = current * (1 - nl / 100);
    const newHigh = current * (1 + nu / 100);
    setPendingLow(newLow);
    setPendingHigh(newHigh);
    setConfirming(false);
  };

  const handleCommit = (nl: number, nu: number) => {
    const newLow  = current * (1 - nl / 100);
    const newHigh = current * (1 + nu / 100);
    setPendingLow(newLow);
    setPendingHigh(newHigh);
    setConfirming(true);
  };

  const handleRebuild = async () => {
    if (!pendingLow || !pendingHigh) return;
    setRebuilding(true);
    setConfirming(false);
    try {
      await onRebuild(pendingLow, pendingHigh);
    } finally {
      setRebuilding(false);
      setPendingLow(null);
      setPendingHigh(null);
    }
  };

  const dispLow  = pendingLow  ?? bot.price_low;
  const dispHigh = pendingHigh ?? bot.price_high;
  const dispLowerPct = current > 0 ? ((current - dispLow)  / current) * 100 : lowerPct;
  const dispUpperPct = current > 0 ? ((dispHigh - current) / current) * 100 : upperPct;

  return (
    <div className="space-y-2">
      <GridControlChart
        low={dispLow}
        high={dispHigh}
        current={current}
        gridCount={bot.grid_count ?? 10}
        lowerPct={dispLowerPct}
        upperPct={dispUpperPct}
        mode={bot.mode ?? 'normal'}
        lang={lang}
        onDrag={handleDrag}
        onCommit={handleCommit}
      />

      {/* Confirm rebuild banner */}
      {confirming && pendingLow && pendingHigh && (
        <div className="flex items-center gap-2 px-3 py-2.5 rounded-2xl animate-fade-up"
          style={{ background: 'rgba(240,185,11,0.1)', border: '1px solid rgba(240,185,11,0.35)' }}>
          <div className="flex-1 text-xs" style={{ color: 'var(--text-muted)' }}>
            <span style={{ color: '#F0B90B', fontWeight: 700 }}>
              {ar ? 'إعادة بناء الشبكة؟' : 'Rebuild grid?'}
            </span>
            <span className="ms-2 num">
              ${pendingLow.toFixed(4)} → ${pendingHigh.toFixed(4)}
            </span>
          </div>
          <button onClick={handleRebuild} disabled={rebuilding}
            className="px-3 py-1.5 rounded-xl text-xs font-bold"
            style={{ background: 'rgba(240,185,11,0.2)', color: '#F0B90B', border: '1px solid rgba(240,185,11,0.4)' }}>
            {rebuilding ? '⏳' : (ar ? 'تأكيد' : 'Confirm')}
          </button>
          <button onClick={() => { setConfirming(false); setPendingLow(null); setPendingHigh(null); }}
            className="px-2 py-1.5 rounded-xl text-xs"
            style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
            ✕
          </button>
        </div>
      )}

      {rebuilding && (
        <div className="text-center text-xs py-2 animate-pulse" style={{ color: '#F0B90B' }}>
          {ar ? '⏳ جاري إعادة بناء الشبكة...' : '⏳ Rebuilding grid...'}
        </div>
      )}
    </div>
  );
}

// ── Main detail page ────────────────────────────────────────────────────────
export default function GridBotDetail({ botId, lang, onBack, onDeleted }: Props) {
  const ar = lang === 'ar';
  const [bot,     setBot]     = useState<any>(null);
  const [orders,  setOrders]  = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [stopping, setStopping] = useState(false);
  const [confirm,  setConfirm]  = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [newBotId, setNewBotId] = useState<number>(botId);

  const { price: livePrice, connected } = useLivePrice(bot?.symbol ?? '');

  const load = useCallback(async () => {
    try {
      const [b, o] = await Promise.all([getGridBot(newBotId), getGridOrders(newBotId)]);
      setBot(b);
      setOrders(o);
    } catch {}
    setLoading(false);
  }, [newBotId]);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const handleStop = async () => {
    setStopping(true);
    try { await stopGridBot(newBotId); await load(); } catch {}
    setStopping(false);
  };

  const handleResume = async () => {
    setStopping(true);
    try { await resumeGridBot(newBotId); await load(); } catch {}
    setStopping(false);
  };

  const handleDelete = async () => {
    setDeleting(true);
    try { await deleteGridBot(newBotId); onDeleted(); } catch {}
    setDeleting(false);
  };

  const handleRebuild = async (low: number, high: number) => {
    const res = await rebuildGridBot(newBotId, low, high);
    setNewBotId(res.bot_id);
    await load();
  };

  if (loading) return (
    <div className="flex items-center justify-center py-24 animate-pulse" style={{ color: 'var(--text-muted)' }}>
      {ar ? 'جاري التحميل...' : 'Loading...'}
    </div>
  );

  if (!bot) return (
    <div className="text-center py-16" style={{ color: 'var(--text-muted)' }}>
      {ar ? 'البوت غير موجود' : 'Bot not found'}
    </div>
  );

  const profitColor = (bot.profit || 0) >= 0 ? '#00D4AA' : '#FF7B72';
  const openOrders   = orders.filter(o => o.status === 'open');
  const filledOrders = orders.filter(o => o.status === 'filled');
  const buyOrders    = openOrders.filter(o => o.side === 'BUY');
  const sellOrders   = openOrders.filter(o => o.side === 'SELL');

  return (
    <div className="space-y-4 max-w-2xl mx-auto">

      {/* ── Header ── */}
      <div className="flex items-center gap-3">
        <button onClick={onBack}
          className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: 'var(--bg-input)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}>
          <ArrowLeft size={16} />
        </button>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <img
            src={`https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons/32/color/${bot.symbol?.replace('USDT','').toLowerCase()}.png`}
            alt="" className="w-8 h-8 rounded-full shrink-0"
            onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
          <div className="min-w-0">
            <div className="font-bold text-base truncate" style={{ color: 'var(--text-main)' }}>{bot.symbol}</div>
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{bot.ts_created?.slice(0, 16)}</div>
          </div>
        </div>
        {/* Live price badge */}
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl shrink-0"
          style={{ background: connected ? 'rgba(0,212,170,0.1)' : 'rgba(255,255,255,0.05)', border: `1px solid ${connected ? 'rgba(0,212,170,0.3)' : 'var(--border)'}` }}>
          <span className="w-1.5 h-1.5 rounded-full shrink-0"
            style={{ background: connected ? '#00D4AA' : 'var(--text-muted)', boxShadow: connected ? '0 0 6px #00D4AA' : 'none' }} />
          <span className="num font-bold text-sm" style={{ color: connected ? '#00D4AA' : 'var(--text-muted)' }}>
            {livePrice ? `$${livePrice.toFixed(4)}` : '—'}
          </span>
        </div>
      </div>

      {/* ── Live chart with drag control ── */}
      <div className="card p-3">
        <LiveGridChart
          bot={bot}
          livePrice={livePrice}
          lang={lang}
          onRebuild={handleRebuild}
        />
        <div className="mt-2 text-center text-[10px]" style={{ color: 'var(--text-muted)' }}>
          {ar
            ? 'اسحب الدائرة لتعديل النطاق ← سيتم إعادة بناء الشبكة تلقائياً'
            : 'Drag the circle to adjust range → grid will rebuild automatically'}
        </div>
      </div>

      {/* ── Stats grid ── */}
      <div className="grid grid-cols-2 gap-2">
        {[
          { label: ar ? 'الاستثمار'    : 'Investment',   value: `$${(bot.investment||0).toFixed(0)}`,        color: '#60A5FA' },
          { label: ar ? 'عدد الشبكات' : 'Grid Count',   value: bot.grid_count,                              color: '#A78BFA' },
          { label: ar ? 'إجمالي الربح': 'Total P&L',    value: `$${(bot.profit||0).toFixed(4)}`,            color: profitColor },
          { label: ar ? 'ربح محقق'    : 'Realised',     value: `$${(bot.realised_profit||0).toFixed(4)}`,   color: '#00D4AA' },
          { label: ar ? 'غير محقق'    : 'Unrealized',   value: `$${(bot.unrealized_pnl||0).toFixed(4)}`,   color: (bot.unrealized_pnl||0) >= 0 ? '#60A5FA' : '#FF7B72' },
          { label: ar ? 'أوامر مفتوحة': 'Open Orders',  value: openOrders.length,                           color: '#F0B90B' },
        ].map(({ label, value, color }) => (
          <div key={label} className="card p-3">
            <div className="text-[10px] font-bold uppercase tracking-wide mb-1" style={{ color: 'var(--text-muted)' }}>{label}</div>
            <div className="num font-bold text-sm" style={{ color }}>{value}</div>
          </div>
        ))}
      </div>

      {/* ── Range info ── */}
      <div className="card p-3 flex justify-between items-center text-xs">
        <div className="space-y-0.5">
          <div style={{ color: 'var(--text-muted)' }}>{ar ? 'الحد الأدنى' : 'Low'}</div>
          <div className="num font-bold" style={{ color: '#00D4AA' }}>${(bot.price_low||0).toFixed(4)}</div>
        </div>
        <div className="text-center space-y-0.5">
          <div style={{ color: 'var(--text-muted)' }}>{ar ? 'النطاق' : 'Range'}</div>
          <div className="font-bold" style={{ color: 'var(--text-main)' }}>
            ↓{(bot.effective_lower_pct ?? bot.lower_pct ?? 5).toFixed(1)}% · {bot.mode === 'infinity' ? '∞' : `↑${(bot.effective_upper_pct ?? bot.upper_pct ?? 5).toFixed(1)}%`}
          </div>
        </div>
        <div className="text-end space-y-0.5">
          <div style={{ color: 'var(--text-muted)' }}>{ar ? 'الحد الأعلى' : 'High'}</div>
          <div className="num font-bold" style={{ color: '#FF7B72' }}>
            {bot.mode === 'infinity' ? '∞' : `$${(bot.price_high||0).toFixed(4)}`}
          </div>
        </div>
      </div>

      {/* ── Open orders split ── */}
      <div className="grid grid-cols-2 gap-3">
        {/* BUY orders */}
        <div className="card p-3 space-y-2">
          <div className="text-xs font-bold" style={{ color: '#00D4AA' }}>
            ▼ {ar ? 'أوامر شراء' : 'BUY'} ({buyOrders.length})
          </div>
          <div className="space-y-1 max-h-36 overflow-y-auto">
            {buyOrders.length === 0
              ? <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>—</div>
              : buyOrders.slice(0, 10).map((o, i) => (
                <div key={i} className="flex justify-between text-[10px] px-1">
                  <span className="num" style={{ color: 'var(--text-main)' }}>${(o.price||0).toFixed(4)}</span>
                  <span style={{ color: 'var(--text-muted)' }}>{(o.qty||0).toFixed(5)}</span>
                </div>
              ))
            }
          </div>
        </div>
        {/* SELL orders */}
        <div className="card p-3 space-y-2">
          <div className="text-xs font-bold" style={{ color: '#FF7B72' }}>
            ▲ {ar ? 'أوامر بيع' : 'SELL'} ({sellOrders.length})
          </div>
          <div className="space-y-1 max-h-36 overflow-y-auto">
            {sellOrders.length === 0
              ? <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>—</div>
              : sellOrders.slice(0, 10).map((o, i) => (
                <div key={i} className="flex justify-between text-[10px] px-1">
                  <span className="num" style={{ color: 'var(--text-main)' }}>${(o.price||0).toFixed(4)}</span>
                  <span style={{ color: 'var(--text-muted)' }}>{(o.qty||0).toFixed(5)}</span>
                </div>
              ))
            }
          </div>
        </div>
      </div>

      {/* ── Filled orders ── */}
      {filledOrders.length > 0 && (
        <div className="card p-3 space-y-2">
          <div className="text-xs font-bold" style={{ color: 'var(--text-muted)' }}>
            ✓ {ar ? 'أوامر منفّذة' : 'Filled'} ({filledOrders.length})
          </div>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {filledOrders.slice(0, 15).map((o, i) => (
              <div key={i} className="flex justify-between items-center text-[10px] px-1">
                <span style={{ color: o.side === 'BUY' ? '#00D4AA' : '#FF7B72', fontWeight: 700 }}>{o.side}</span>
                <span className="num" style={{ color: 'var(--text-main)' }}>${(o.price||0).toFixed(4)}</span>
                <span style={{ color: 'var(--text-muted)' }}>{(o.qty||0).toFixed(5)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Controls ── */}
      <div className="flex gap-2">
        {bot.running ? (
          <button onClick={handleStop} disabled={stopping}
            className="flex-1 flex items-center justify-center gap-2 py-3 rounded-2xl font-bold text-sm disabled:opacity-40"
            style={{ background: 'rgba(255,123,114,0.1)', color: '#FF7B72', border: '1px solid rgba(255,123,114,0.25)' }}>
            <Square size={14} /> {stopping ? '...' : (ar ? 'إيقاف' : 'Stop')}
          </button>
        ) : (
          <button onClick={handleResume} disabled={stopping}
            className="flex-1 flex items-center justify-center gap-2 py-3 rounded-2xl font-bold text-sm disabled:opacity-40"
            style={{ background: 'rgba(0,212,170,0.1)', color: '#00D4AA', border: '1px solid rgba(0,212,170,0.25)' }}>
            <Play size={14} /> {stopping ? '...' : (ar ? 'استئناف' : 'Resume')}
          </button>
        )}
        <button onClick={load}
          className="w-11 h-11 rounded-2xl flex items-center justify-center shrink-0"
          style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
          <RefreshCw size={14} />
        </button>
        {confirm ? (
          <div className="flex gap-1">
            <button onClick={handleDelete} disabled={deleting}
              className="px-3 py-2 rounded-2xl text-xs font-bold"
              style={{ background: 'rgba(255,123,114,0.15)', color: '#FF7B72', border: '1px solid rgba(255,123,114,0.3)' }}>
              {deleting ? '...' : (ar ? 'تأكيد الحذف' : 'Confirm')}
            </button>
            <button onClick={() => setConfirm(false)}
              className="px-3 py-2 rounded-2xl text-xs"
              style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
              ✕
            </button>
          </div>
        ) : (
          <button onClick={() => setConfirm(true)}
            className="w-11 h-11 rounded-2xl flex items-center justify-center shrink-0"
            style={{ background: 'var(--bg-input)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
            <Trash2 size={14} />
          </button>
        )}
      </div>

    </div>
  );
}
