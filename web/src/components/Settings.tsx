'use client';

import { useEffect, useState, useCallback } from 'react';
import { getConfig, updateConfig, listPortfolios, getPortfolio, updatePortfolio } from '../lib/api';
import { Lang, tr } from '../lib/i18n';

interface Asset { symbol: string; allocation_pct: number; }
interface Props { lang: Lang; onSaved: () => void; }

export default function Settings({ lang, onSaved }: Props) {
  const [portfolios, setPortfolios]   = useState<any[]>([]);
  const [selectedId, setSelectedId]   = useState<number | null>(null);
  const [cfg, setCfg]                 = useState<any>(null);
  const [assets, setAssets]           = useState<Asset[]>([]);
  const [totalUsdt, setTotalUsdt]     = useState(0);
  const [rebalMode, setRebalMode]     = useState('proportional');
  const [threshold, setThreshold]     = useState(5);
  const [frequency, setFrequency]     = useState('daily');
  const [timedHour, setTimedHour]     = useState(10);
  const [sellTerm, setSellTerm]       = useState(false);
  const [assetTransfer, setAssetTransfer] = useState(false);
  const [paperTrading, setPaperTrading]   = useState(false);
  const [saving, setSaving]           = useState(false);
  const [msg, setMsg]                 = useState('');

  const applyConfig = (c: any) => {
    setCfg(c);
    setAssets(c.portfolio.assets.map((a: any) => ({ ...a })));
    setTotalUsdt(c.portfolio.total_usdt);
    setRebalMode(c.rebalance.mode);
    setThreshold(c.rebalance.proportional.threshold_pct);
    setFrequency(c.rebalance.timed.frequency);
    setTimedHour(c.rebalance.timed.hour ?? 10);
    setSellTerm(c.termination.sell_at_termination);
    setAssetTransfer(c.asset_transfer.enable_asset_transfer);
    setPaperTrading(c.paper_trading ?? false);
  };

  // Load portfolio list + default to active portfolio
  useEffect(() => {
    Promise.all([listPortfolios(), getConfig()]).then(([list, activeCfg]) => {
      setPortfolios(list);
      // Find the active portfolio id from the list
      const active = list.find((p: any) => p.active);
      if (active) {
        setSelectedId(active.id);
        // Load that portfolio's config
        getPortfolio(active.id).then(applyConfig).catch(() => applyConfig(activeCfg));
      } else {
        applyConfig(activeCfg);
      }
    }).catch(() => {
      getConfig().then(applyConfig);
    });
  }, []);

  // When user picks a different portfolio, load its config
  const handleSelectPortfolio = useCallback(async (id: number) => {
    setSelectedId(id);
    setMsg('');
    setCfg(null);
    try {
      const c = await getPortfolio(id);
      applyConfig(c);
    } catch (e: any) {
      setMsg('❌ ' + e.message);
    }
  }, []);

  const totalPct = assets.reduce((s, a) => s + a.allocation_pct, 0);

  const allocateEqually = () => {
    const n = assets.length;
    const base = Math.floor((100 / n) * 100) / 100;
    const rem  = parseFloat((100 - base * (n - 1)).toFixed(2));
    setAssets(assets.map((a, i) => ({ ...a, allocation_pct: i === n - 1 ? rem : base })));
  };

  const addAsset = () => {
    if (assets.length >= 10) return;
    setAssets([...assets, { symbol: '', allocation_pct: 0 }]);
  };

  const removeAsset = (i: number) => {
    if (assets.length <= 2) return;
    setAssets(assets.filter((_, idx) => idx !== i));
  };

  const updateSymbol = (i: number, val: string) => {
    const up = [...assets];
    up[i] = { ...up[i], symbol: val.toUpperCase() };
    setAssets(up);
    setMsg('');
  };

  const updatePct = (i: number, val: number) => {
    const up = [...assets];
    up[i] = { ...up[i], allocation_pct: val };
    setAssets(up);
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
        termination: { sell_at_termination: sellTerm },
        asset_transfer: { enable_asset_transfer: assetTransfer },
        paper_trading: paperTrading,
      };

      if (selectedId !== null) {
        // Save to specific portfolio in DB
        await updatePortfolio(selectedId, updatedCfg);
      } else {
        // Fallback: save via legacy config endpoint
        await updateConfig({
          assets: assets.map((a, i) => ({ symbol: symbols[i], allocation_pct: a.allocation_pct })),
          total_usdt: totalUsdt,
          rebalance_mode: rebalMode,
          threshold_pct: threshold,
          frequency,
          timed_hour: timedHour,
          sell_at_termination: sellTerm,
          enable_asset_transfer: assetTransfer,
          paper_trading: paperTrading,
        });
      }
      setMsg('✅ ' + tr('successSaved', lang));
      setTimeout(onSaved, 1000);
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
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--text-main)' }}>{tr('settingsTitle', lang)}</h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>{tr('settingsDesc', lang)}</p>
      </div>

      {/* Portfolio selector */}
      {portfolios.length > 0 && (
        <div className="card">
          <div className="label">{tr('selectPortfolio', lang)}</div>
          <div className="flex flex-col gap-2">
            {portfolios.map(p => (
              <button
                key={p.id}
                onClick={() => handleSelectPortfolio(p.id)}
                className={`flex items-center justify-between px-4 py-3 rounded-xl border-2 text-sm font-semibold transition-colors text-start ${
                  selectedId === p.id
                    ? 'border-brand bg-brand/10 text-brand'
                    : 'border-gray-700 hover:border-gray-500'
                }`}
              >
                <span style={{ color: selectedId === p.id ? 'var(--brand)' : 'var(--text-main)' }}>
                  {p.name}
                  <span className="font-normal text-xs ms-2" style={{ color: 'var(--text-muted)' }}>
                    {p.assets?.length ?? 0} {tr('assetCount', lang)} · ${p.total_usdt}
                  </span>
                </span>
                {p.running && (
                  <span className="text-xs text-green-400 font-bold">● {tr('portfolioRunning', lang)}</span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Bot name (read-only) */}
      <div className="card">
        <div className="label">{tr('botNameReadonly', lang)}</div>
        <div className="input opacity-50 cursor-not-allowed">{cfg.bot.name}</div>
      </div>

      {/* Assets */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <div className="label mb-0">{tr('assetsAndAlloc', lang)} ({assets.length}/10)</div>
          <div className="flex gap-2">
            <button onClick={allocateEqually} className="btn-secondary text-xs px-3 py-1">{tr('equalAlloc', lang)}</button>
            <button onClick={addAsset} disabled={assets.length >= 10} className="btn-primary text-xs px-3 py-1">{tr('addAsset', lang)}</button>
          </div>
        </div>
        <div className="space-y-2">
          {assets.map((a, i) => {
            const syms = assets.map(x => x.symbol.trim().toUpperCase());
            const isDup = a.symbol.trim() !== '' && syms.filter(s => s === a.symbol.trim().toUpperCase()).length > 1;
            return (
              <div key={i} className="flex items-center gap-2">
                <div className="flex flex-col">
                  <input
                    className={`input w-28 font-mono uppercase ${isDup ? 'border-red-500' : ''}`}
                    value={a.symbol}
                    onChange={e => updateSymbol(i, e.target.value)}
                    placeholder="BTC"
                    maxLength={10}
                  />
                  {isDup && <span className="text-red-400 text-xs mt-0.5">⚠️ {tr('errDuplicate', lang)}</span>}
                </div>
                <div className="flex-1 relative">
                  <input type="number" min={0} max={100} step={0.1} className="input"
                    value={a.allocation_pct}
                    onChange={e => updatePct(i, parseFloat(e.target.value) || 0)} />
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm" style={{ color: 'var(--text-muted)' }}>%</span>
                </div>
                <button onClick={() => removeAsset(i)} disabled={assets.length <= 2}
                  className="text-red-500 hover:text-red-400 disabled:opacity-30 p-1">🗑️</button>
              </div>
            );
          })}
        </div>
        <div className={`mt-3 text-sm font-semibold ${Math.abs(totalPct - 100) < 0.1 ? 'text-green-400' : 'text-red-400'}`}>
          {tr('totalSum', lang)}: {totalPct.toFixed(1)}% {Math.abs(totalPct - 100) < 0.1 ? '✅' : tr('mustBe100', lang)}
        </div>
      </div>

      {/* Rebalance mode */}
      <div className="card">
        <div className="label mb-3">{tr('rebalanceMode', lang)}</div>
        <div className="grid grid-cols-3 gap-2 mb-4">
          {(['proportional', 'timed', 'unbalanced'] as const).map(m => (
            <button key={m} onClick={() => setRebalMode(m)}
              className={`p-3 rounded-xl border-2 text-center transition-colors ${rebalMode === m ? 'border-brand bg-brand/10' : 'border-gray-700 hover:border-gray-600'}`}>
              <div className="text-lg">{m === 'proportional' ? '📊' : m === 'timed' ? '⏰' : '🔓'}</div>
              <div className="text-xs font-semibold mt-1" style={{ color: 'var(--text-main)' }}>
                {tr(m === 'proportional' ? 'proportional' : m === 'timed' ? 'timed' : 'manual', lang)}
              </div>
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
                {['daily', 'weekly', 'monthly'].map(f => (
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

      {/* Investment amount */}
      <div className="card">
        <label className="label">{tr('investedUsdt', lang)}</label>
        <div className="relative">
          <input type="number" min={1} className="input pl-16" value={totalUsdt}
            onChange={e => setTotalUsdt(parseFloat(e.target.value) || 0)} />
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm" style={{ color: 'var(--text-muted)' }}>USDT</span>
        </div>
      </div>

      {/* Toggles */}
      <div className="card space-y-4">
        <div className="label mb-0">{tr('extraOptions', lang)}</div>
        {[
          { key: 'sell',     label: tr('sellOnStop', lang),      desc: tr('sellOnStopDesc', lang),    val: sellTerm,      set: setSellTerm,      color: 'bg-brand' },
          { key: 'transfer', label: tr('assetTransfer', lang),   desc: tr('assetTransferDesc', lang), val: assetTransfer, set: setAssetTransfer, color: 'bg-brand' },
          { key: 'paper',    label: '🧪 ' + tr('paperMode', lang), desc: tr('paperModeDesc', lang),  val: paperTrading,  set: setPaperTrading,  color: 'bg-yellow-500' },
        ].map(({ key, label, desc, val, set, color }) => (
          <label key={key} className="flex items-center justify-between cursor-pointer">
            <div>
              <div className="text-sm font-medium" style={{ color: 'var(--text-main)' }}>{label}</div>
              <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{desc}</div>
            </div>
            <div className={`w-11 h-6 rounded-full transition-colors relative cursor-pointer ${val ? color : 'bg-gray-700'}`}
              onClick={() => set(!val)}>
              <div className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${val ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </div>
          </label>
        ))}
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
