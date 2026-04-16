'use client';

import { useState } from 'react';
import { savePortfolio } from '../lib/api';
import { Lang, tr } from '../lib/i18n';

interface Asset {
  symbol: string;
  allocation_pct: number;
  entry_price_usdt: number | null;
}

type RebalanceMode   = 'proportional' | 'timed' | 'unbalanced';
type AllocationMode  = 'ai_balance' | 'equal' | 'market_cap';
type TimedFrequency  = '30min' | '1h' | '4h' | '8h' | '12h' | 'daily' | 'weekly' | 'monthly';

interface Props { lang: Lang; onCreated: () => void; }

const TIMED_OPTIONS: { value: TimedFrequency; labelKey: string }[] = [
  { value: '30min',   labelKey: 'interval30m' },
  { value: '1h',      labelKey: 'interval1h'  },
  { value: '4h',      labelKey: 'interval4h'  },
  { value: '8h',      labelKey: 'interval8h'  },
  { value: '12h',     labelKey: 'interval12h' },
  { value: 'daily',   labelKey: 'interval1d'  },
  { value: 'weekly',  labelKey: 'weekly'      },
  { value: 'monthly', labelKey: 'monthly'     },
];

const ALLOC_MODES: { value: AllocationMode; labelKey: string; descKey: string }[] = [
  { value: 'ai_balance',  labelKey: 'allocAiBalance',  descKey: 'allocAiDesc'     },
  { value: 'equal',       labelKey: 'allocEqual',      descKey: 'allocEqualDesc'  },
  { value: 'market_cap',  labelKey: 'allocMarketCap',  descKey: 'allocMktCapDesc' },
];

export default function CreateBot({ lang, onCreated }: Props) {
  const [assets, setAssets]             = useState<Asset[]>([
    { symbol: 'BTC', allocation_pct: 70, entry_price_usdt: null },
    { symbol: 'ETH', allocation_pct: 30, entry_price_usdt: null },
  ]);
  const [botName, setBotName]           = useState('My MEXC Portfolio');
  const [totalUsdt, setTotalUsdt]       = useState(1000);
  const [allocMode, setAllocMode]       = useState<AllocationMode>('ai_balance');
  const [rebalMode, setRebalMode]       = useState<RebalanceMode>('proportional');
  const [threshold, setThreshold]       = useState(5);
  const [timedFreq, setTimedFreq]       = useState<TimedFrequency>('daily');
  const [timedHour, setTimedHour]       = useState(10);


  const [saving, setSaving]             = useState(false);
  const [error, setError]               = useState('');
  const [success, setSuccess]           = useState('');

  const totalPct = assets.reduce((s, a) => s + a.allocation_pct, 0);

  // ── Allocation helpers ──────────────────────────────────────────────────

  const applyEqualAlloc = (list: Asset[]) => {
    const n = list.length;
    const base = Math.floor((100 / n) * 100) / 100;
    const rem  = parseFloat((100 - base * (n - 1)).toFixed(2));
    return list.map((a, i) => ({ ...a, allocation_pct: i === n - 1 ? rem : base }));
  };

  const handleAllocModeChange = (mode: AllocationMode) => {
    setAllocMode(mode);
    if (mode === 'equal') setAssets(prev => applyEqualAlloc(prev));
  };

  // ── Asset CRUD ──────────────────────────────────────────────────────────

  const addAsset = () => {
    if (assets.length >= 12) return;
    const next = [...assets, { symbol: '', allocation_pct: 0, entry_price_usdt: null }];
    setAssets(allocMode === 'equal' ? applyEqualAlloc(next) : next);
  };

  const removeAsset = (i: number) => {
    if (assets.length <= 1) return;
    const next = assets.filter((_, idx) => idx !== i);
    setAssets(allocMode === 'equal' ? applyEqualAlloc(next) : next);
  };

  const updateSymbol = (i: number, val: string) => {
    const up = [...assets];
    up[i] = { ...up[i], symbol: val.toUpperCase() };
    setAssets(up);
    setError('');
  };

  const updatePct = (i: number, val: number) => {
    const up = [...assets];
    up[i] = { ...up[i], allocation_pct: val };
    setAssets(up);
  };

  const updateEntryPrice = (i: number, val: string) => {
    const up = [...assets];
    up[i] = { ...up[i], entry_price_usdt: val === '' ? null : parseFloat(val) };
    setAssets(up);
  };

  // ── Validation ──────────────────────────────────────────────────────────

  const validate = (): string | null => {
    if (!botName.trim()) return tr('errBotName', lang);
    if (assets.length < 1 || assets.length > 12) return tr('errAssetCount', lang);
    const symbols = assets.map(a => a.symbol.trim().toUpperCase());
    if (symbols.some(s => !s)) return tr('errSymbol', lang);
    if (new Set(symbols).size !== symbols.length) return tr('errDuplicate', lang);
    if (Math.abs(totalPct - 100) > 0.1) return tr('errSum', lang);
    if (totalUsdt <= 0) return tr('errAmount', lang);

    return null;
  };

  // ── Save ────────────────────────────────────────────────────────────────

  const handleSave = async () => {
    const err = validate();
    if (err) { setError('❌ ' + err); return; }
    setError(''); setSaving(true);
    try {
      const fullConfig = {
        bot: { name: botName.trim() },
        portfolio: {
          assets: assets.map(a => ({
            symbol: a.symbol.trim().toUpperCase(),
            allocation_pct: a.allocation_pct,
            entry_price_usdt: a.entry_price_usdt ?? null,
          })),
          total_usdt: totalUsdt,
          initial_value_usdt: totalUsdt,
          allocation_mode: allocMode,
        },
        rebalance: {
          mode: rebalMode,
          proportional: { threshold_pct: threshold, check_interval_minutes: 5, min_deviation_to_execute_pct: 3 },
          timed: { frequency: timedFreq, hour: timedHour },
          unbalanced: {},
        },
        termination: { sell_at_termination: false },
        asset_transfer: { enable_asset_transfer: false },
        paper_trading: false,
        last_rebalance: null,
      };
      await savePortfolio(fullConfig);
      setSuccess('✅ ' + tr('successCreated', lang));
      setTimeout(onCreated, 1500);
    } catch (e: any) {
      setError('❌ ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--text-main)' }}>
          {tr('createBotTitle', lang)}
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          {tr('createBotSubtitle', lang)}
        </p>
      </div>

      {/* ── Bot name ── */}
      <div className="card">
        <label className="label">{tr('botName', lang)}</label>
        <input
          className="input"
          value={botName}
          onChange={e => setBotName(e.target.value)}
          placeholder="My MEXC Portfolio"
        />
      </div>

      {/* ── Token allocation ── */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <div className="label mb-0">{tr('assetsAndAlloc', lang)} ({assets.length}/12)</div>
          <button
            onClick={addAsset}
            disabled={assets.length >= 12}
            className="btn-primary text-xs px-3 py-1"
          >
            + {tr('addAsset', lang)}
          </button>
        </div>

        {/* Allocation mode selector */}
        <div className="flex gap-2 mb-4">
          {ALLOC_MODES.map(m => (
            <button
              key={m.value}
              onClick={() => handleAllocModeChange(m.value)}
              title={tr(m.descKey, lang)}
              className={`flex-1 py-2 rounded-xl border-2 text-xs font-semibold transition-colors ${
                allocMode === m.value
                  ? 'border-brand bg-brand/10 text-brand'
                  : 'border-gray-700 text-gray-400 hover:border-gray-600'
              }`}
            >
              {tr(m.labelKey, lang)}
            </button>
          ))}
        </div>

        {/* Allocation mode description */}
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
          {tr(ALLOC_MODES.find(m => m.value === allocMode)!.descKey, lang)}
        </p>

        {/* Asset rows */}
        <div className="space-y-3">
          {assets.map((a, i) => {
            const syms  = assets.map(x => x.symbol.trim().toUpperCase());
            const isDup = a.symbol.trim() !== '' && syms.filter(s => s === a.symbol.trim().toUpperCase()).length > 1;
            return (
              <div key={i} className="rounded-xl border border-gray-700 p-3 space-y-2">
                {/* Symbol + allocation row */}
                <div className="flex items-center gap-2">
                  <div className="flex flex-col">
                    <input
                      className={`input w-24 font-mono uppercase ${isDup ? 'border-red-500' : ''}`}
                      value={a.symbol}
                      onChange={e => updateSymbol(i, e.target.value)}
                      placeholder="BTC"
                      maxLength={10}
                    />
                    {isDup && (
                      <span className="text-red-400 text-xs mt-0.5">
                        ⚠️ {tr('errDuplicate', lang)}
                      </span>
                    )}
                  </div>

                  <div className="flex-1 relative">
                    <span
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-sm pointer-events-none"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      %
                    </span>
                    <input
                      type="number" min={0} max={100} step={0.1}
                      className="input pr-8"
                      value={a.allocation_pct}
                      onChange={e => updatePct(i, parseFloat(e.target.value) || 0)}
                      disabled={allocMode === 'equal'}
                    />
                  </div>

                  <button
                    onClick={() => removeAsset(i)}
                    disabled={assets.length <= 1}
                    className="text-red-500 hover:text-red-400 disabled:opacity-30 p-1 text-xl leading-none"
                  >
                    ×
                  </button>
                </div>

                {/* Entry price (optional) */}
                <div className="flex items-center gap-2">
                  <span className="text-xs w-28 shrink-0" style={{ color: 'var(--text-muted)' }}>
                    {tr('entryPrice', lang)}
                  </span>
                  <div className="flex-1 relative">
                    <span
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-xs pointer-events-none"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      USDT
                    </span>
                    <input
                      type="number" min={0} step="any"
                      className="input pr-14 text-sm"
                      placeholder={tr('entryPriceOpt', lang)}
                      value={a.entry_price_usdt ?? ''}
                      onChange={e => updateEntryPrice(i, e.target.value)}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Allocation total */}
        <div
          className={`mt-3 text-sm font-semibold ${
            Math.abs(totalPct - 100) < 0.1 ? 'text-green-400' : 'text-red-400'
          }`}
        >
          {tr('totalSum', lang)}: {totalPct.toFixed(1)}%{' '}
          {Math.abs(totalPct - 100) < 0.1 ? '✅' : tr('mustBe100', lang)}
        </div>
      </div>

      {/* ── Investment amount ── */}
      <div className="card">
        <label className="label">{tr('investedUsdt', lang)}</label>
        <div className="relative">
          <span
            className="absolute left-3 top-1/2 -translate-y-1/2 text-sm pointer-events-none"
            style={{ color: 'var(--text-muted)' }}
          >
            USDT
          </span>
          <input
            type="number" min={1}
            className="input pl-16"
            value={totalUsdt}
            onChange={e => setTotalUsdt(parseFloat(e.target.value) || 0)}
          />
        </div>
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
          {tr('minRecommended', lang)}: {(assets.length * 10).toFixed(0)} USDT
        </p>
      </div>

      {/* ── Rebalance mode ── */}
      <div className="card">
        <div className="label mb-3">{tr('rebalanceMode', lang)}</div>
        <div className="grid grid-cols-3 gap-2 mb-4">
          {(['proportional', 'timed', 'unbalanced'] as RebalanceMode[]).map(m => (
            <button
              key={m}
              onClick={() => setRebalMode(m)}
              className={`p-3 rounded-xl border-2 text-center transition-colors ${
                rebalMode === m
                  ? 'border-brand bg-brand/10'
                  : 'border-gray-700 hover:border-gray-600'
              }`}
            >
              <div className="text-lg">
                {m === 'proportional' ? '📊' : m === 'timed' ? '⏰' : '🔓'}
              </div>
              <div className="text-xs font-semibold mt-1" style={{ color: 'var(--text-main)' }}>
                {tr(m === 'proportional' ? 'proportional' : m === 'timed' ? 'timed' : 'manual', lang)}
              </div>
            </button>
          ))}
        </div>

        {/* Proportional settings */}
        {rebalMode === 'proportional' && (
          <div className="space-y-3">
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {tr('proportionalModeDesc', lang)}
            </p>
            <div>
              <div className="label">{tr('deviationThresh', lang)}</div>
              <div className="flex gap-2">
                {[1, 3, 5].map(t => (
                  <button
                    key={t}
                    onClick={() => setThreshold(t)}
                    className={`flex-1 py-2 rounded-xl border-2 text-sm font-bold transition-colors ${
                      threshold === t
                        ? 'border-brand bg-brand/10 text-brand'
                        : 'border-gray-700 text-gray-400 hover:border-gray-600'
                    }`}
                  >
                    {t}%
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Timed settings */}
        {rebalMode === 'timed' && (
          <div className="space-y-3">
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {tr('timedModeDesc', lang)}
            </p>
            <div>
              <div className="label">{tr('frequency', lang)}</div>
              <div className="grid grid-cols-4 gap-2">
                {TIMED_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => setTimedFreq(opt.value)}
                    className={`py-2 rounded-xl border-2 text-xs font-semibold transition-colors ${
                      timedFreq === opt.value
                        ? 'border-brand bg-brand/10 text-brand'
                        : 'border-gray-700 text-gray-400 hover:border-gray-600'
                    }`}
                  >
                    {tr(opt.labelKey, lang)}
                  </button>
                ))}
              </div>
            </div>
            {['daily', 'weekly', 'monthly'].includes(timedFreq) && (
              <div>
                <div className="label">{tr('hourUtc', lang)}</div>
                <input
                  type="number" min={0} max={23}
                  className="input w-24"
                  value={timedHour}
                  onChange={e => setTimedHour(parseInt(e.target.value) || 0)}
                />
              </div>
            )}
          </div>
        )}
      </div>





      {error   && <div className="card border-red-700 text-red-400 text-sm">{error}</div>}
      {success && <div className="card border-green-700 text-green-400 text-sm">{success}</div>}

      <button
        onClick={handleSave}
        disabled={saving}
        className="btn-primary w-full py-3 text-base"
      >
        {saving ? '⏳ ' + tr('saving', lang) : '🚀 ' + tr('createBotBtn', lang)}
      </button>
    </div>
  );
}
