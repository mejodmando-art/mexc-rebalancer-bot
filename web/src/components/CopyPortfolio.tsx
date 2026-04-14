'use client';

import { useEffect, useState } from 'react';
import { Copy, RefreshCw, Check, ChevronDown, Layers, DollarSign, Tag, AlertCircle } from 'lucide-react';
import { listPortfolios, savePortfolio, activatePortfolio } from '../lib/api';
import { Lang, tr } from '../lib/i18n';
import { useToast } from './Toast';

interface Props { lang: Lang; onCreated: () => void; }

interface Portfolio {
  id: number;
  active: boolean;
  config: any;
}

const PALETTE = [
  '#00D4AA','#60A5FA','#A78BFA','#F472B6',
  '#FB923C','#34D399','#F59E0B','#38BDF8',
];

const MODE_LABEL: Record<string, { ar: string; en: string }> = {
  proportional: { ar: 'نسبة مئوية', en: 'Proportional' },
  timed:        { ar: 'زمني',       en: 'Timed' },
  unbalanced:   { ar: 'يدوي',       en: 'Manual' },
};

export default function CopyPortfolio({ lang, onCreated }: Props) {
  const toast = useToast();

  const [portfolios,   setPortfolios]   = useState<Portfolio[]>([]);
  const [loadingList,  setLoadingList]  = useState(true);
  const [selectedId,   setSelectedId]   = useState<number | null>(null);
  const [newName,      setNewName]      = useState('');
  const [customUsdt,   setCustomUsdt]   = useState('');
  const [saving,       setSaving]       = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  useEffect(() => {
    listPortfolios()
      .then(list => {
        setPortfolios(list);
        if (list.length > 0) {
          setSelectedId(list[0].id);
          const srcName = list[0].config?.bot?.name ?? '';
          setNewName((lang === 'ar' ? 'نسخة من ' : 'Copy of ') + srcName);
        }
      })
      .catch(() => {})
      .finally(() => setLoadingList(false));
  }, [lang]);

  const selected = portfolios.find(p => p.id === selectedId) ?? null;
  const srcAssets: { symbol: string; allocation_pct: number }[] = selected?.config?.portfolio?.assets ?? [];
  const srcMode: string = selected?.config?.rebalance?.mode ?? 'proportional';
  const srcUsdt: number = selected?.config?.portfolio?.total_usdt ?? 0;

  const handleSelect = (p: Portfolio) => {
    setSelectedId(p.id);
    const srcName = p.config?.bot?.name ?? '';
    setNewName((lang === 'ar' ? 'نسخة من ' : 'Copy of ') + srcName);
    setDropdownOpen(false);
  };

  const handleClone = async () => {
    if (!selected) return;
    const name = newName.trim();
    if (!name) {
      toast.error(lang === 'ar' ? 'أدخل اسم المحفظة الجديدة' : 'Enter a name for the new portfolio');
      return;
    }

    const usdtVal = customUsdt.trim() !== '' ? parseFloat(customUsdt) : srcUsdt;
    if (isNaN(usdtVal) || usdtVal <= 0) {
      toast.error(lang === 'ar' ? 'أدخل مبلغ صحيح' : 'Enter a valid amount');
      return;
    }

    setSaving(true);
    try {
      // Deep-clone config, override name + usdt
      const cloned = JSON.parse(JSON.stringify(selected.config));
      cloned.bot = { ...cloned.bot, name };
      cloned.portfolio = {
        ...cloned.portfolio,
        total_usdt: usdtVal,
        initial_value_usdt: usdtVal,
      };
      // Clear runtime state
      cloned.last_rebalance = null;

      const saved = await savePortfolio(cloned);
      await activatePortfolio(saved.id);

      toast.success(tr('copySuccess', lang));
      setTimeout(onCreated, 1200);
    } catch (e: any) {
      toast.error(lang === 'ar' ? 'فشل النسخ' : 'Clone failed', e?.message);
    } finally {
      setSaving(false);
    }
  };

  if (loadingList) {
    return (
      <div className="max-w-2xl mx-auto space-y-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="skeleton h-20 rounded-2xl" />
        ))}
      </div>
    );
  }

  if (portfolios.length === 0) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="card p-10 text-center space-y-3">
          <div className="w-14 h-14 rounded-2xl mx-auto flex items-center justify-center"
               style={{ background: 'var(--bg-input)' }}>
            <Layers size={24} style={{ color: 'var(--text-muted)' }} />
          </div>
          <p className="font-semibold" style={{ color: 'var(--text-main)' }}>
            {tr('copyNoPortfolios', lang)}
          </p>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            {lang === 'ar' ? 'أنشئ محفظة أولاً من تبويب "إنشاء بوت"' : 'Create a portfolio first from the "Create Bot" tab'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-5">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--text-main)' }}>
          {tr('copyPortfolio', lang)}
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          {tr('copyPortfolioDesc', lang)}
        </p>
      </div>

      {/* Source selector */}
      <div className="card p-5 space-y-3">
        <label className="label">{tr('copySource', lang)}</label>

        {/* Custom dropdown */}
        <div className="relative">
          <button
            onClick={() => setDropdownOpen(o => !o)}
            className="w-full flex items-center justify-between gap-3 px-4 py-3 rounded-xl text-sm font-semibold transition-all"
            style={{
              background: 'var(--bg-input)',
              border: `1px solid ${dropdownOpen ? 'var(--accent)' : 'var(--border)'}`,
              color: 'var(--text-main)',
              boxShadow: dropdownOpen ? '0 0 0 3px rgba(0,212,170,0.12)' : 'none',
            }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-2 h-2 rounded-full shrink-0" style={{ background: selected?.active ? 'var(--accent)' : 'var(--text-muted)' }} />
              <span className="truncate">{selected?.config?.bot?.name ?? '—'}</span>
              {selected?.active && (
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full shrink-0"
                      style={{ background: 'rgba(0,212,170,0.15)', color: 'var(--accent)' }}>
                  {lang === 'ar' ? 'نشطة' : 'Active'}
                </span>
              )}
            </div>
            <ChevronDown size={15} className={`shrink-0 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`}
                         style={{ color: 'var(--text-muted)' }} />
          </button>

          {dropdownOpen && (
            <div
              className="absolute top-full mt-1 w-full rounded-xl overflow-hidden z-20 shadow-xl"
              style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
            >
              {portfolios.map(p => (
                <button
                  key={p.id}
                  onClick={() => handleSelect(p)}
                  className="w-full flex items-center gap-3 px-4 py-3 text-sm text-start transition-colors"
                  style={{
                    background: p.id === selectedId ? 'rgba(0,212,170,0.08)' : 'transparent',
                    color: 'var(--text-main)',
                    borderBottom: '1px solid var(--border)',
                  }}
                >
                  <div className="w-2 h-2 rounded-full shrink-0"
                       style={{ background: p.active ? 'var(--accent)' : 'var(--text-muted)' }} />
                  <span className="flex-1 font-medium truncate">{p.config?.bot?.name ?? `Portfolio #${p.id}`}</span>
                  <span className="text-[11px] shrink-0" style={{ color: 'var(--text-muted)' }}>
                    {p.config?.portfolio?.assets?.length ?? 0} {lang === 'ar' ? 'عملة' : 'coins'}
                  </span>
                  {p.id === selectedId && <Check size={13} style={{ color: 'var(--accent)' }} />}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Preview of source */}
        {selected && (
          <div
            className="rounded-xl p-4 space-y-3"
            style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}
          >
            {/* Mode + USDT */}
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                {lang === 'ar' ? 'وضع إعادة التوازن' : 'Rebalance Mode'}
              </span>
              <span className="text-xs font-bold px-2 py-0.5 rounded-full"
                    style={{ background: 'rgba(0,212,170,0.12)', color: 'var(--accent)' }}>
                {MODE_LABEL[srcMode]?.[lang] ?? srcMode}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                {lang === 'ar' ? 'المبلغ المستثمر' : 'Invested'}
              </span>
              <span className="num text-sm font-bold" style={{ color: 'var(--text-main)' }}>
                ${srcUsdt.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </span>
            </div>

            {/* Assets chips */}
            <div>
              <span className="text-[11px] font-bold uppercase tracking-wider block mb-2" style={{ color: 'var(--text-muted)' }}>
                {lang === 'ar' ? 'العملات' : 'Assets'} ({srcAssets.length})
              </span>
              <div className="flex flex-wrap gap-1.5">
                {srcAssets.map((a, i) => (
                  <div
                    key={a.symbol}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl text-[11px] font-bold"
                    style={{
                      background: `${PALETTE[i % PALETTE.length]}18`,
                      border: `1px solid ${PALETTE[i % PALETTE.length]}35`,
                      color: PALETTE[i % PALETTE.length],
                    }}
                  >
                    <span>{a.symbol}</span>
                    <span className="opacity-70">{a.allocation_pct}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* New portfolio name */}
      <div className="card p-5 space-y-3">
        <label className="label flex items-center gap-2">
          <Tag size={13} />
          {tr('copyNewName', lang)}
        </label>
        <input
          className="input"
          value={newName}
          onChange={e => setNewName(e.target.value)}
          placeholder={lang === 'ar' ? 'اسم المحفظة الجديدة' : 'New portfolio name'}
        />
      </div>

      {/* Custom USDT (optional) */}
      <div className="card p-5 space-y-3">
        <label className="label flex items-center gap-2">
          <DollarSign size={13} />
          {tr('copyUsdt', lang)}
        </label>
        <div className="relative">
          <span
            className="absolute inset-y-0 start-3 flex items-center text-sm font-bold pointer-events-none"
            style={{ color: 'var(--text-muted)' }}
          >
            $
          </span>
          <input
            className="input !ps-7 num"
            type="number"
            min="0"
            step="any"
            value={customUsdt}
            onChange={e => setCustomUsdt(e.target.value)}
            placeholder={srcUsdt > 0 ? srcUsdt.toFixed(2) : '0.00'}
          />
        </div>
        <div className="flex items-start gap-2 text-[11px]" style={{ color: 'var(--text-muted)' }}>
          <AlertCircle size={12} className="shrink-0 mt-0.5" />
          <span>{tr('copyUsdtHint', lang)}</span>
        </div>
      </div>

      {/* Clone button */}
      <button
        onClick={handleClone}
        disabled={saving || !selected}
        className="btn-accent w-full py-3.5 text-base gap-2"
      >
        {saving
          ? <><RefreshCw size={16} className="spin" /> {lang === 'ar' ? 'جاري النسخ...' : 'Cloning...'}</>
          : <><Copy size={16} /> {tr('copyBtn', lang)}</>
        }
      </button>

    </div>
  );
}
