'use client';

import { useState, useEffect } from 'react';
import { getRecommended, updateConfig, startBot } from '../lib/api';

const RECOMMENDED_PORTFOLIOS = [
  {
    name: 'Top 3 Coins',
    description: 'BTC + ETH + BNB – أكثر العملات استقراراً',
    assets: [
      { symbol: 'BTC', allocation_pct: 50 },
      { symbol: 'ETH', allocation_pct: 30 },
      { symbol: 'BNB', allocation_pct: 20 },
    ],
  },
  {
    name: 'DeFi Portfolio',
    description: 'عملات DeFi الرائدة',
    assets: [
      { symbol: 'ETH', allocation_pct: 40 },
      { symbol: 'SOL', allocation_pct: 30 },
      { symbol: 'AVAX', allocation_pct: 30 },
    ],
  },
  {
    name: 'Layer 1 Mix',
    description: 'تنويع على شبكات Layer 1',
    assets: [
      { symbol: 'BTC', allocation_pct: 35 },
      { symbol: 'ETH', allocation_pct: 25 },
      { symbol: 'SOL', allocation_pct: 20 },
      { symbol: 'AVAX', allocation_pct: 20 },
    ],
  },
  {
    name: 'Balanced 5',
    description: 'محفظة متوازنة من 5 عملات',
    assets: [
      { symbol: 'BTC', allocation_pct: 30 },
      { symbol: 'ETH', allocation_pct: 25 },
      { symbol: 'SOL', allocation_pct: 20 },
      { symbol: 'BNB', allocation_pct: 15 },
      { symbol: 'AVAX', allocation_pct: 10 },
    ],
  },
];

interface Asset { symbol: string; allocation_pct: number; }

type Mode = 'recommended' | 'manual';
type RebalanceMode = 'proportional' | 'timed' | 'unbalanced';

export default function CreateBot({ onCreated }: { onCreated: () => void }) {
  const [mode, setMode]           = useState<Mode>('recommended');
  const [selectedRec, setSelectedRec] = useState<number | null>(null);
  const [assets, setAssets]       = useState<Asset[]>([
    { symbol: 'BTC', allocation_pct: 50 },
    { symbol: 'ETH', allocation_pct: 50 },
  ]);
  const [botName, setBotName]     = useState('My MEXC Portfolio');
  const [totalUsdt, setTotalUsdt] = useState(1000);
  const [rebalMode, setRebalMode] = useState<RebalanceMode>('proportional');
  const [threshold, setThreshold] = useState(5);
  const [frequency, setFrequency] = useState('daily');
  const [timedHour, setTimedHour] = useState(10);
  const [sellTerm, setSellTerm]   = useState(false);
  const [assetTransfer, setAssetTransfer] = useState(false);
  const [paperTrading, setPaperTrading]   = useState(false);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState('');
  const [success, setSuccess]     = useState('');

  // ── Asset helpers ──────────────────────────────────────────────────────────
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
  };

  const updatePct = (i: number, val: number) => {
    const up = [...assets];
    up[i] = { ...up[i], allocation_pct: val };
    setAssets(up);
  };

  const applyRecommended = (idx: number) => {
    setSelectedRec(idx);
    setAssets(RECOMMENDED_PORTFOLIOS[idx].assets.map(a => ({ ...a })));
  };

  // ── Validation ─────────────────────────────────────────────────────────────
  const validate = (): string | null => {
    if (!botName.trim()) return 'أدخل اسم البوت';
    if (assets.length < 2 || assets.length > 10) return 'عدد العملات يجب أن يكون بين 2 و 10';
    const symbols = assets.map(a => a.symbol.trim().toUpperCase());
    if (symbols.some(s => !s)) return 'أدخل رمز كل عملة';
    if (new Set(symbols).size !== symbols.length) return 'لا يمكن تكرار العملات';
    if (Math.abs(totalPct - 100) > 0.1) return `مجموع النسب يجب أن يساوي 100% (الحالي: ${totalPct.toFixed(1)}%)`;
    if (totalUsdt <= 0) return 'أدخل مبلغ استثمار صحيح';
    return null;
  };

  // ── Save ───────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    const err = validate();
    if (err) { setError(err); return; }
    setError(''); setSaving(true);
    try {
      await updateConfig({
        bot_name: botName.trim(),
        assets: assets.map(a => ({ symbol: a.symbol.trim().toUpperCase(), allocation_pct: a.allocation_pct })),
        total_usdt: totalUsdt,
        rebalance_mode: rebalMode,
        threshold_pct: threshold,
        frequency,
        sell_at_termination: sellTerm,
        enable_asset_transfer: assetTransfer,
        paper_trading: paperTrading,
      });
      await startBot();
      setSuccess('✅ تم إنشاء البوت وتشغيله بنجاح!');
      setTimeout(onCreated, 1500);
    } catch (e: any) {
      setError('❌ ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">إنشاء محفظة ذكية</h1>
        <p className="text-gray-400 text-sm mt-1">Spot – MEXC Exchange</p>
      </div>

      {/* Mode selector */}
      <div className="card">
        <div className="label mb-3">طريقة الإنشاء</div>
        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={() => setMode('recommended')}
            className={`p-4 rounded-xl border-2 text-right transition-colors ${mode === 'recommended' ? 'border-brand bg-brand/10' : 'border-gray-700 hover:border-gray-600'}`}
          >
            <div className="font-bold text-white">⭐ Recommended</div>
            <div className="text-xs text-gray-400 mt-1">محافظ جاهزة موصى بها</div>
          </button>
          <button
            onClick={() => setMode('manual')}
            className={`p-4 rounded-xl border-2 text-right transition-colors ${mode === 'manual' ? 'border-brand bg-brand/10' : 'border-gray-700 hover:border-gray-600'}`}
          >
            <div className="font-bold text-white">🛠️ Manual</div>
            <div className="text-xs text-gray-400 mt-1">إعداد يدوي كامل</div>
          </button>
        </div>
      </div>

      {/* Recommended portfolios */}
      {mode === 'recommended' && (
        <div className="card">
          <div className="label mb-3">اختر محفظة جاهزة</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {RECOMMENDED_PORTFOLIOS.map((p, i) => (
              <button
                key={i}
                onClick={() => applyRecommended(i)}
                className={`p-4 rounded-xl border-2 text-right transition-colors ${selectedRec === i ? 'border-brand bg-brand/10' : 'border-gray-700 hover:border-gray-600'}`}
              >
                <div className="font-bold text-white text-sm">{p.name}</div>
                <div className="text-xs text-gray-400 mt-1">{p.description}</div>
                <div className="flex flex-wrap gap-1 mt-2">
                  {p.assets.map(a => (
                    <span key={a.symbol} className="badge bg-gray-800 text-gray-300 text-xs">
                      {a.symbol} {a.allocation_pct}%
                    </span>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Bot name */}
      <div className="card">
        <label className="label">اسم البوت (لا يمكن تغييره لاحقاً)</label>
        <input className="input" value={botName} onChange={e => setBotName(e.target.value)} placeholder="My MEXC Portfolio" />
      </div>

      {/* Assets */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <div className="label mb-0">الأصول والنسب ({assets.length}/10)</div>
          <div className="flex gap-2">
            <button onClick={allocateEqually} className="btn-secondary text-xs px-3 py-1">توزيع متساوي</button>
            <button onClick={addAsset} disabled={assets.length >= 10} className="btn-primary text-xs px-3 py-1">+ إضافة</button>
          </div>
        </div>

        <div className="space-y-2">
          {assets.map((a, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                className="input w-28 font-mono uppercase"
                value={a.symbol}
                onChange={e => updateSymbol(i, e.target.value)}
                placeholder="BTC"
                maxLength={10}
              />
              <div className="flex-1 relative">
                <input
                  type="number" min={0} max={100} step={0.1}
                  className="input pr-8"
                  value={a.allocation_pct}
                  onChange={e => updatePct(i, parseFloat(e.target.value) || 0)}
                />
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm">%</span>
              </div>
              <button onClick={() => removeAsset(i)} disabled={assets.length <= 2} className="text-red-500 hover:text-red-400 disabled:opacity-30 p-1">🗑️</button>
            </div>
          ))}
        </div>

        <div className={`mt-3 text-sm font-semibold ${Math.abs(totalPct - 100) < 0.1 ? 'text-green-400' : 'text-red-400'}`}>
          المجموع: {totalPct.toFixed(1)}% {Math.abs(totalPct - 100) < 0.1 ? '✅' : '(يجب أن يساوي 100%)'}
        </div>
      </div>

      {/* Rebalance mode */}
      <div className="card">
        <div className="label mb-3">وضع إعادة التوازن</div>
        <div className="grid grid-cols-3 gap-2 mb-4">
          {(['proportional', 'timed', 'unbalanced'] as RebalanceMode[]).map(m => (
            <button
              key={m}
              onClick={() => setRebalMode(m)}
              className={`p-3 rounded-xl border-2 text-center transition-colors ${rebalMode === m ? 'border-brand bg-brand/10' : 'border-gray-700 hover:border-gray-600'}`}
            >
              <div className="text-lg">{m === 'proportional' ? '📊' : m === 'timed' ? '⏰' : '🔓'}</div>
              <div className="text-xs font-semibold text-white mt-1">
                {m === 'proportional' ? 'نسبة مئوية' : m === 'timed' ? 'زمني' : 'يدوي'}
              </div>
            </button>
          ))}
        </div>

        {rebalMode === 'proportional' && (
          <div>
            <div className="label">عتبة الانحراف</div>
            <div className="flex gap-2">
              {[1, 3, 5].map(t => (
                <button key={t} onClick={() => setThreshold(t)}
                  className={`flex-1 py-2 rounded-xl border-2 text-sm font-bold transition-colors ${threshold === t ? 'border-brand bg-brand/10 text-brand' : 'border-gray-700 text-gray-400 hover:border-gray-600'}`}>
                  {t}%
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-500 mt-2">البوت يفحص كل 5 دقائق، ولا ينفذ إلا إذا كان الانحراف ≥ 3%</p>
          </div>
        )}

        {rebalMode === 'timed' && (
          <div className="space-y-3">
            <div>
              <div className="label">التكرار</div>
              <div className="flex gap-2">
                {['daily', 'weekly', 'monthly'].map(f => (
                  <button key={f} onClick={() => setFrequency(f)}
                    className={`flex-1 py-2 rounded-xl border-2 text-sm font-semibold transition-colors ${frequency === f ? 'border-brand bg-brand/10 text-brand' : 'border-gray-700 text-gray-400 hover:border-gray-600'}`}>
                    {f === 'daily' ? 'يومي' : f === 'weekly' ? 'أسبوعي' : 'شهري'}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="label">الساعة (UTC)</div>
              <input type="number" min={0} max={23} className="input w-24" value={timedHour}
                onChange={e => setTimedHour(parseInt(e.target.value) || 0)} />
            </div>
          </div>
        )}

        {rebalMode === 'unbalanced' && (
          <p className="text-xs text-gray-500">لا يوجد إعادة توازن تلقائي. يمكنك تنفيذه يدوياً من لوحة التحكم.</p>
        )}
      </div>

      {/* Investment amount */}
      <div className="card">
        <label className="label">المبلغ المستثمر (USDT)</label>
        <div className="relative">
          <input type="number" min={1} className="input pl-16" value={totalUsdt}
            onChange={e => setTotalUsdt(parseFloat(e.target.value) || 0)} />
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm">USDT</span>
        </div>
        <p className="text-xs text-gray-500 mt-1">الحد الأدنى الموصى به: {(assets.length * 10).toFixed(0)} USDT ({assets.length} عملات × 10 USDT)</p>
      </div>

      {/* Options */}
      <div className="card space-y-4">
        <div className="label mb-0">خيارات إضافية</div>

        <label className="flex items-center justify-between cursor-pointer">
          <div>
            <div className="text-sm font-medium text-white">البيع عند الإنهاء</div>
            <div className="text-xs text-gray-500">تحويل كل الأصول إلى USDT عند إيقاف البوت</div>
          </div>
          <div className={`w-11 h-6 rounded-full transition-colors relative cursor-pointer ${sellTerm ? 'bg-brand' : 'bg-gray-700'}`}
            onClick={() => setSellTerm(!sellTerm)}>
            <div className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${sellTerm ? 'translate-x-5' : 'translate-x-0.5'}`} />
          </div>
        </label>

        <label className="flex items-center justify-between cursor-pointer">
          <div>
            <div className="text-sm font-medium text-white">تمكين تحويل الأصول</div>
            <div className="text-xs text-gray-500">استخدام رصيد المحفظة الحالي أولاً قبل الشراء</div>
          </div>
          <div className={`w-11 h-6 rounded-full transition-colors relative cursor-pointer ${assetTransfer ? 'bg-brand' : 'bg-gray-700'}`}
            onClick={() => setAssetTransfer(!assetTransfer)}>
            <div className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${assetTransfer ? 'translate-x-5' : 'translate-x-0.5'}`} />
          </div>
        </label>

        <label className="flex items-center justify-between cursor-pointer">
          <div>
            <div className="text-sm font-medium text-white">🧪 وضع تجريبي (Paper Trading)</div>
            <div className="text-xs text-gray-500">تشغيل البوت بأموال وهمية بدون تداول حقيقي</div>
          </div>
          <div className={`w-11 h-6 rounded-full transition-colors relative cursor-pointer ${paperTrading ? 'bg-yellow-500' : 'bg-gray-700'}`}
            onClick={() => setPaperTrading(!paperTrading)}>
            <div className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${paperTrading ? 'translate-x-5' : 'translate-x-0.5'}`} />
          </div>
        </label>
      </div>

      {error   && <div className="card border-red-700 text-red-400 text-sm">{error}</div>}
      {success && <div className="card border-green-700 text-green-400 text-sm">{success}</div>}

      <button onClick={handleSave} disabled={saving} className="btn-primary w-full py-3 text-base">
        {saving ? '⏳ جاري الحفظ...' : '🚀 حفظ وإنشاء البوت'}
      </button>
    </div>
  );
}
