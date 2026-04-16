'use client';

import { useState, useEffect } from 'react';
import { ArrowRight } from 'lucide-react';
import { getPortfolio, updatePortfolio } from '../lib/api';
import { Lang, tr } from '../lib/i18n';

interface Asset { symbol: string; allocation_pct: number; }
type RebalanceMode = 'proportional' | 'timed' | 'unbalanced';
type TimedFrequency = 'daily' | 'weekly' | 'monthly';

interface Props {
  lang: Lang;
  portfolioId: number;
  onBack: () => void;
}

const COLORS = ['#f0b90b','#3b82f6','#10b981','#8b5cf6','#ef4444','#f97316','#06b6d4','#ec4899','#84cc16','#a78bfa'];

export default function PortfolioSettings({ lang, portfolioId, onBack }: Props) {
  const ar = lang === 'ar';

  const [cfg,        setCfg]        = useState<any>(null);
  const [assets,     setAssets]     = useState<Asset[]>([]);
  const [totalUsdt,  setTotalUsdt]  = useState(0);
  const [rebalMode,  setRebalMode]  = useState<RebalanceMode>('proportional');
  const [threshold,  setThreshold]  = useState(5);
  const [frequency,  setFrequency]  = useState<TimedFrequency>('daily');
  const [timedHour,  setTimedHour]  = useState(10);
  const [saving,     setSaving]     = useState(false);
  const [msg,        setMsg]        = useState('');

  useEffect(() => {
    getPortfolio(portfolioId).then((c: any) => {
      setCfg(c);
      setAssets(c.portfolio.assets.map((a: any) => ({ ...a })));
      setTotalUsdt(c.portfolio.total_usdt);
      setRebalMode(c.rebalance.mode);
      setThreshold(c.rebalance.proportional.threshold_pct);
      setFrequency(c.rebalance.timed.frequency);
      setTimedHour(c.rebalance.timed.hour ?? 10);
    }).catch((e: any) => setMsg('❌ ' + e.message));
  }, [portfolioId]);

  const totalPct = assets.reduce((s, a) => s + a.allocation_pct, 0);

  const allocateEqually = () => {
    const n = assets.length;
    const base = Math.floor((100 / n) * 100) / 100;
    const rem  = parseFloat((100 - base * (n - 1)).toFixed(2));
    setAssets(assets.map((a, i) => ({ ...a, allocation_pct: i === n - 1 ? rem : base })));
  };

  const save = async () => {
    if (Math.abs(totalPct - 100) > 0.1) { setMsg('❌ ' + tr('errSum', lang)); return; }
    const symbols = assets.map(a => a.symbol.trim().toUpperCase());
    if (symbols.some(s => !s)) { setMsg('❌ ' + tr('errSymbol', lang)); return; }
    if (new Set(symbols).size !== symbols.length) { setMsg('❌ ' + tr('errDuplicate', lang)); return; }

    setSaving(true); setMsg('');
    try {
      const updatedCfg = {
        ...cfg,
        portfolio: {
          ...cfg.portfolio,
          assets: assets.map((a, i) => ({ symbol: symbols[i], allocation_pct: a.allocation_pct })),
          total_usdt: totalUsdt,
        },
        rebalance: {
          ...cfg.rebalance,
          mode: rebalMode,
          proportional: { ...cfg.rebalance.proportional, threshold_pct: threshold },
          timed: { ...cfg.rebalance.timed, frequency, hour: timedHour },
        },
        paper_trading: false,
      };
      await updatePortfolio(portfolioId, updatedCfg);
      setMsg('✅ ' + tr('successSaved', lang));
      setTimeout(onBack, 1200);
    } catch (e: any) {
      setMsg('❌ ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  if (!cfg) return (
    <div className="text-center py-20 animate-pulse" style={{ color: 'var(--text-muted)' }}>
      {tr('loadingData', lang)}
    </div>
  );

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button onClick={onBack}
          className="w-9 h-9 rounded-xl flex items-center justify-center transition-all active:scale-90"
          style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}>
          <ArrowRight size={18} style={{ color: 'var(--text-muted)', transform: ar ? 'none' : 'rotate(180deg)' }} />
        </button>
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--text-main)' }}>
            {ar ? 'إعدادات المحفظة' : 'Portfolio Settings'}
          </h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{cfg.bot?.name}</p>
        </div>
      </div>

      {/* Investment amount */}
      <div className="card space-y-2">
        <div className="label">{tr('investedUsdt', lang)}</div>
        <div className="relative">
          <input type="number" min={1} className="input ps-16" value={totalUsdt}
            onChange={e => setTotalUsdt(parseFloat(e.target.value) || 0)} />
          <span className="absolute start-3 top-1/2 -translate-y-1/2 text-sm" style={{ color: 'var(--text-muted)' }}>USDT</span>
        </div>
      </div>

      {/* Assets */}
      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <div className="label mb-0">{tr('assetsAndAlloc', lang)} ({assets.length}/10)</div>
          <div className="flex gap-2">
            <button onClick={allocateEqually} className="btn-secondary text-xs px-3 py-1">{tr('equalAlloc', lang)}</button>
            <button onClick={() => { if (assets.length < 10) setAssets([...assets, { symbol: '', allocation_pct: 0 }]); }}
              disabled={assets.length >= 10} className="btn-primary text-xs px-3 py-1">
              {tr('addAsset', lang)}
            </button>
          </div>
        </div>
        <div className="space-y-2">
          {assets.map((a, i) => {
            const syms = assets.map(x => x.symbol.trim().toUpperCase());
            const isDup = a.symbol.trim() !== '' && syms.filter(s => s === a.symbol.trim().toUpperCase()).length > 1;
            return (
              <div key={i} className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
                <input
                  className={`input w-28 font-mono uppercase text-sm ${isDup ? 'border-red-500' : ''}`}
                  value={a.symbol}
                  onChange={e => { const up = [...assets]; up[i] = { ...up[i], symbol: e.target.value.toUpperCase() }; setAssets(up); }}
                  placeholder="BTC" maxLength={10}
                />
                <div className="flex-1 relative">
                  <input type="number" min={0} max={100} step={0.1} className="input pe-8 text-sm"
                    value={a.allocation_pct}
                    onChange={e => { const up = [...assets]; up[i] = { ...up[i], allocation_pct: parseFloat(e.target.value) || 0 }; setAssets(up); }} />
                  <span className="absolute end-3 top-1/2 -translate-y-1/2 text-xs" style={{ color: 'var(--text-muted)' }}>%</span>
                </div>
                <button onClick={() => { if (assets.length > 2) setAssets(assets.filter((_, idx) => idx !== i)); }}
                  disabled={assets.length <= 2} className="text-red-500 hover:text-red-400 disabled:opacity-30 p-1 text-sm">🗑️</button>
              </div>
            );
          })}
        </div>
        <div className={`text-sm font-semibold ${Math.abs(totalPct - 100) < 0.1 ? 'text-green-400' : 'text-red-400'}`}>
          {tr('totalSum', lang)}: {totalPct.toFixed(1)}% {Math.abs(totalPct - 100) < 0.1 ? '✅' : tr('mustBe100', lang)}
        </div>
      </div>

      {/* Rebalance mode */}
      <div className="card space-y-4">
        <div className="label mb-0">{tr('rebalanceMode', lang)}</div>
        <div className="flex rounded-xl overflow-hidden border" style={{ borderColor: 'var(--border)' }}>
          {([
            { key: 'proportional', icon: '📊', labelKey: 'proportional' },
            { key: 'timed',        icon: '⏰', labelKey: 'timed' },
            { key: 'unbalanced',   icon: '🔓', labelKey: 'manual' },
          ] as const).map((m, i, arr) => (
            <button key={m.key} onClick={() => setRebalMode(m.key)}
              className={`flex-1 flex flex-col items-center justify-center gap-1 py-3 text-xs font-semibold transition-all ${i < arr.length - 1 ? 'border-e' : ''}`}
              style={{
                background: rebalMode === m.key ? 'var(--brand)' : 'var(--bg-input)',
                borderColor: 'var(--border)',
                color: rebalMode === m.key ? '#000' : 'var(--text-muted)',
              }}>
              <span className="text-lg leading-none">{m.icon}</span>
              <span>{tr(m.labelKey, lang)}</span>
            </button>
          ))}
        </div>

        {rebalMode === 'proportional' && (
          <div>
            <div className="label">{tr('deviationThresh', lang)}</div>
            <div className="flex gap-2">
              {[1, 3, 5].map(t => (
                <button key={t} onClick={() => setThreshold(t)}
                  className={`flex-1 py-2 rounded-xl border-2 text-sm font-bold transition-colors ${threshold === t ? 'border-brand bg-brand/10 text-brand' : 'border-gray-700 text-gray-400'}`}>
                  {t}%
                </button>
              ))}
            </div>
          </div>
        )}

        {rebalMode === 'timed' && (
          <div className="space-y-3">
            <div>
              <div className="label">{tr('frequency', lang)}</div>
              <div className="flex gap-2">
                {(['daily', 'weekly', 'monthly'] as TimedFrequency[]).map(f => (
                  <button key={f} onClick={() => setFrequency(f)}
                    className={`flex-1 py-2 rounded-xl border-2 text-sm font-semibold transition-colors ${frequency === f ? 'border-brand bg-brand/10 text-brand' : 'border-gray-700 text-gray-400'}`}>
                    {tr(f, lang)}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="label">{tr('hourUtc', lang)}</div>
              <input type="number" min={0} max={23} className="input w-24" value={timedHour}
                onChange={e => setTimedHour(parseInt(e.target.value) || 0)} />
            </div>
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
