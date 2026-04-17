'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Plus, Square, Play, Trash2, RefreshCw,
  TrendingUp, AlertCircle, CheckCircle2, Circle, Zap,
} from 'lucide-react';
import { Lang, tr } from '../lib/i18n';
import {
  listOBScanners, createOBScanner, stopOBScanner,
  resumeOBScanner, deleteOBScanner, getOBScanner, getSymbols,
} from '../lib/api';
import { useToast } from './Toast';

interface Props { lang: Lang; }

const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d'];

// ── Condition badge ──────────────────────────────────────────────────────────
function CondBadge({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span
      className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold"
      style={{
        background: ok ? 'rgba(0,212,170,0.12)' : 'rgba(123,92,245,0.08)',
        border: `1px solid ${ok ? 'rgba(0,212,170,0.3)' : 'rgba(123,92,245,0.15)'}`,
        color: ok ? '#00D4AA' : 'var(--text-muted)',
      }}
    >
      {ok
        ? <CheckCircle2 size={9} style={{ color: '#00D4AA' }} />
        : <Circle size={9} style={{ color: 'var(--text-muted)' }} />}
      {label}
    </span>
  );
}

// ── Single scanner card ──────────────────────────────────────────────────────
function ScannerCard({ scanner, lang, onRefresh }: {
  scanner: any; lang: Lang; onRefresh: () => void;
}) {
  const toast = useToast();
  const ar = lang === 'ar';
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const fetchDetail = useCallback(async () => {
    try {
      const d = await getOBScanner(scanner.id);
      setDetail(d);
    } catch { /* silent */ }
  }, [scanner.id]);

  useEffect(() => {
    fetchDetail();
    const t = setInterval(fetchDetail, 15000);
    return () => clearInterval(t);
  }, [fetchDetail]);

  const running  = scanner.running;
  const status   = detail?.status ?? scanner.status ?? 'stopped';
  const inPos    = status === 'in_position';
  const conds    = detail?.conditions ?? {};
  const trades   = detail?.trades ?? [];

  const statusColor = inPos ? '#F0B90B' : running ? '#00D4AA' : 'var(--text-muted)';
  const statusLabel = inPos
    ? tr('scannerInPosition', lang)
    : running
      ? tr('scannerScanning', lang)
      : tr('scannerStopped', lang);

  async function handleStop() {
    setLoading(true);
    try { await stopOBScanner(scanner.id); onRefresh(); toast.success(ar ? 'تم الإيقاف' : 'Stopped'); }
    catch (e: any) { toast.error(e.message); }
    finally { setLoading(false); }
  }

  async function handleResume() {
    setLoading(true);
    try { await resumeOBScanner(scanner.id); onRefresh(); toast.success(ar ? 'تم الاستئناف' : 'Resumed'); }
    catch (e: any) { toast.error(e.message); }
    finally { setLoading(false); }
  }

  async function handleDelete() {
    if (!confirm(ar ? 'حذف هذا السكانر؟' : 'Delete this scanner?')) return;
    setLoading(true);
    try { await deleteOBScanner(scanner.id); onRefresh(); toast.success(ar ? 'تم الحذف' : 'Deleted'); }
    catch (e: any) { toast.error(e.message); }
    finally { setLoading(false); }
  }

  return (
    <div
      className="card p-4 flex flex-col gap-3"
      style={{ borderColor: inPos ? 'rgba(240,185,11,0.3)' : running ? 'rgba(0,212,170,0.2)' : 'var(--border)' }}
    >
      {/* Header row */}
      <div className="flex items-center gap-3">
        <div
          className="flex items-center justify-center rounded-xl shrink-0 font-black text-sm"
          style={{
            width: 38, height: 38,
            background: `${statusColor}18`,
            border: `1px solid ${statusColor}30`,
            color: statusColor,
          }}
        >
          {scanner.symbol.replace('USDT', '')}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>
              {scanner.symbol}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full"
              style={{ background: 'rgba(123,92,245,0.12)', color: '#A78BFA', border: '1px solid rgba(123,92,245,0.2)' }}>
              {scanner.timeframe}
            </span>
          </div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className={`w-1.5 h-1.5 rounded-full ${running ? 'pulse-dot' : ''}`}
              style={{ background: statusColor }} />
            <span className="text-[11px]" style={{ color: statusColor }}>{statusLabel}</span>
          </div>
        </div>
        {/* Action buttons */}
        <div className="flex items-center gap-1.5">
          <button onClick={fetchDetail} className="btn-secondary !px-2 !min-h-[30px]" title="Refresh">
            <RefreshCw size={12} />
          </button>
          {running
            ? <button onClick={handleStop} disabled={loading} className="btn-secondary !px-2 !min-h-[30px]" title={tr('scannerStop', lang)}>
                <Square size={12} style={{ color: '#FF7B72' }} />
              </button>
            : <button onClick={handleResume} disabled={loading} className="btn-secondary !px-2 !min-h-[30px]" title={tr('scannerResume', lang)}>
                <Play size={12} style={{ color: '#00D4AA' }} />
              </button>
          }
          <button onClick={handleDelete} disabled={loading} className="btn-secondary !px-2 !min-h-[30px]" title={tr('scannerDelete', lang)}>
            <Trash2 size={12} style={{ color: '#FF7B72' }} />
          </button>
        </div>
      </div>

      {/* Config row */}
      <div className="flex flex-wrap gap-2">
        {[
          { label: ar ? 'دخول' : 'Entry', value: `$${scanner.entry_usdt}` },
          { label: 'TP1', value: `+${scanner.tp1_pct}%`, color: '#00D4AA' },
          { label: 'TP2', value: `+${scanner.tp2_pct}%`, color: '#60A5FA' },
        ].map(({ label, value, color }) => (
          <div key={label} className="flex items-center gap-1 px-2 py-1 rounded-lg"
            style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}>
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{label}</span>
            <span className="text-[11px] font-bold" style={{ color: color ?? 'var(--text-main)' }}>{value}</span>
          </div>
        ))}
      </div>

      {/* Conditions */}
      {Object.keys(conds).length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[10px] font-semibold" style={{ color: 'var(--text-muted)' }}>
            {tr('scannerConditions', lang)}
          </span>
          <div className="flex flex-wrap gap-1.5">
            <CondBadge label={tr('condSweepShort', lang)} ok={!!conds.liquidity_sweep} />
            <CondBadge label={tr('condBOSShort', lang)}   ok={!!conds.bos_choch} />
            <CondBadge label={tr('condFreshShort', lang)} ok={!!conds.fresh_ob} />
            <CondBadge label={tr('condFFGShort', lang)}   ok={!!conds.ffg} />
          </div>
          {conds.swept_level > 0 && (
            <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
              {ar ? 'مستوى السيولة:' : 'Swept level:'} <span className="num" style={{ color: '#F0B90B' }}>{conds.swept_level}</span>
            </span>
          )}
        </div>
      )}

      {/* Position info */}
      {inPos && detail && (
        <div className="grid grid-cols-2 gap-2 p-3 rounded-xl"
          style={{ background: 'rgba(240,185,11,0.06)', border: '1px solid rgba(240,185,11,0.2)' }}>
          <div>
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{tr('scannerEntry2', lang)}</div>
            <div className="num text-xs font-bold" style={{ color: '#F0B90B' }}>{Number(detail.entry_price).toFixed(6)}</div>
          </div>
          <div>
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{tr('scannerQty', lang)}</div>
            <div className="num text-xs font-bold" style={{ color: 'var(--text-main)' }}>{Number(detail.base_qty).toFixed(6)}</div>
          </div>
          <div>
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{tr('scannerPnl', lang)}</div>
            <div className="num text-xs font-bold" style={{ color: detail.realised_pnl >= 0 ? '#00D4AA' : '#FF7B72' }}>
              {Number(detail.realised_pnl).toFixed(4)} USDT
            </div>
          </div>
          <div>
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>TP1</div>
            <div className="text-xs font-bold" style={{ color: detail.tp1_hit ? '#00D4AA' : '#F0B90B' }}>
              {detail.tp1_hit ? tr('scannerTP1Hit', lang) : tr('scannerTP1Pending', lang)}
            </div>
          </div>
        </div>
      )}

      {/* Realised PnL when not in position */}
      {!inPos && detail && Number(detail.realised_pnl) !== 0 && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-xl"
          style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}>
          <TrendingUp size={13} style={{ color: detail.realised_pnl >= 0 ? '#00D4AA' : '#FF7B72' }} />
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{tr('scannerPnl', lang)}:</span>
          <span className="num text-xs font-bold" style={{ color: detail.realised_pnl >= 0 ? '#00D4AA' : '#FF7B72' }}>
            {Number(detail.realised_pnl).toFixed(4)} USDT
          </span>
        </div>
      )}

      {/* Recent trades */}
      {trades.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold" style={{ color: 'var(--text-muted)' }}>
            {tr('scannerTrades', lang)}
          </span>
          {trades.slice(0, 4).map((t: any) => (
            <div key={t.id} className="flex items-center justify-between px-2 py-1.5 rounded-lg"
              style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                  style={{
                    background: t.side === 'BUY' ? 'rgba(0,212,170,0.12)' : 'rgba(255,123,114,0.12)',
                    color: t.side === 'BUY' ? '#00D4AA' : '#FF7B72',
                  }}>
                  {t.side}
                </span>
                <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{t.label}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="num text-[10px]" style={{ color: 'var(--text-main)' }}>{Number(t.price).toFixed(4)}</span>
                {t.pnl !== 0 && (
                  <span className="num text-[10px] font-bold" style={{ color: t.pnl >= 0 ? '#00D4AA' : '#FF7B72' }}>
                    {t.pnl >= 0 ? '+' : ''}{Number(t.pnl).toFixed(4)}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Create form ──────────────────────────────────────────────────────────────
function CreateForm({ lang, onCreated }: { lang: Lang; onCreated: () => void }) {
  const toast = useToast();
  const ar = lang === 'ar';
  const [symbol, setSymbol]       = useState('BTC');
  const [timeframe, setTimeframe] = useState('15m');
  const [entryUsdt, setEntryUsdt] = useState('15');
  const [tp1, setTp1]             = useState('5');
  const [tp2, setTp2]             = useState('5');
  const [creating, setCreating]   = useState(false);
  const [allSymbols, setAllSymbols] = useState<string[]>([]);
  const [symSearch, setSymSearch] = useState('');
  const [showPicker, setShowPicker] = useState(false);

  const FALLBACK = ['BTC','ETH','SOL','BNB','XRP','ADA','DOGE','AVAX','DOT','LINK'];

  useEffect(() => {
    getSymbols().then(setAllSymbols).catch(() => setAllSymbols(FALLBACK));
  }, []);

  const filtered = (allSymbols.length ? allSymbols : FALLBACK)
    .filter(s => s.toLowerCase().includes(symSearch.toLowerCase()))
    .slice(0, 30);

  async function handleCreate() {
    const entry = parseFloat(entryUsdt);
    if (!symbol || entry < 5) {
      toast.error(ar ? 'أدخل عملة ومبلغ صحيح (5$ على الأقل)' : 'Enter a symbol and valid amount (min $5)');
      return;
    }
    setCreating(true);
    try {
      await createOBScanner({
        symbol: symbol + 'USDT',
        timeframe,
        entry_usdt: entry,
        tp1_pct: parseFloat(tp1) || 5,
        tp2_pct: parseFloat(tp2) || 5,
      });
      toast.success(ar ? 'تم إنشاء السكانر وتشغيله' : 'Scanner created and running');
      onCreated();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="card p-4 flex flex-col gap-3"
      style={{ borderColor: 'rgba(244,114,182,0.25)' }}>
      <div className="flex items-center gap-2 mb-1">
        <Plus size={15} style={{ color: '#F472B6' }} />
        <span className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>
          {tr('newScanner', lang)}
        </span>
      </div>

      {/* Symbol picker */}
      <div className="relative">
        <label className="label">{tr('scannerSymbol', lang)}</label>
        <button
          className="input w-full text-start flex items-center justify-between mt-1"
          onClick={() => setShowPicker(v => !v)}
        >
          <span className="font-bold" style={{ color: 'var(--text-main)' }}>{symbol}/USDT</span>
          <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>▾</span>
        </button>
        {showPicker && (
          <div className="absolute z-50 top-full mt-1 left-0 right-0 rounded-xl overflow-hidden"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', boxShadow: 'var(--shadow)' }}>
            <div className="p-2">
              <input className="input w-full text-xs" placeholder={ar ? 'بحث...' : 'Search...'}
                value={symSearch} onChange={e => setSymSearch(e.target.value)} autoFocus />
            </div>
            <div className="overflow-y-auto" style={{ maxHeight: 180 }}>
              {filtered.map(s => (
                <button key={s} className="w-full text-start px-3 py-2 text-xs hover:bg-white/5 transition-colors"
                  style={{ color: s === symbol ? '#F472B6' : 'var(--text-main)' }}
                  onClick={() => { setSymbol(s); setShowPicker(false); setSymSearch(''); }}>
                  {s}/USDT
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Timeframe */}
      <div>
        <label className="label">{tr('scannerTimeframe', lang)}</label>
        <div className="flex flex-wrap gap-1.5 mt-1">
          {TIMEFRAMES.map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)}
              className="px-2.5 py-1 rounded-lg text-xs font-bold transition-all"
              style={{
                background: timeframe === tf ? 'rgba(244,114,182,0.15)' : 'var(--bg-input)',
                border: `1px solid ${timeframe === tf ? 'rgba(244,114,182,0.4)' : 'var(--border)'}`,
                color: timeframe === tf ? '#F472B6' : 'var(--text-muted)',
              }}>
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* Entry + TPs */}
      <div className="grid grid-cols-3 gap-2">
        <div>
          <label className="label">{tr('scannerEntry', lang)}</label>
          <input className="input w-full mt-1" type="number" min="5" step="1"
            value={entryUsdt} onChange={e => setEntryUsdt(e.target.value)} />
        </div>
        <div>
          <label className="label">{tr('scannerTP1', lang)}</label>
          <input className="input w-full mt-1" type="number" min="0.5" step="0.5"
            value={tp1} onChange={e => setTp1(e.target.value)} />
        </div>
        <div>
          <label className="label">{tr('scannerTP2', lang)}</label>
          <input className="input w-full mt-1" type="number" min="0.5" step="0.5"
            value={tp2} onChange={e => setTp2(e.target.value)} />
        </div>
      </div>

      {/* TP visual */}
      <div className="flex items-center gap-2 text-[10px]" style={{ color: 'var(--text-muted)' }}>
        <span style={{ color: '#F472B6' }}>$15</span>
        <div className="flex-1 h-px" style={{ background: 'var(--border)' }} />
        <span style={{ color: '#00D4AA' }}>TP1 +{tp1}% → 50%</span>
        <div className="flex-1 h-px" style={{ background: 'var(--border)' }} />
        <span style={{ color: '#60A5FA' }}>TP2 +{tp2}% → 50%</span>
      </div>

      <button onClick={handleCreate} disabled={creating} className="btn-primary w-full">
        {creating ? (ar ? 'جاري الإنشاء...' : 'Creating...') : tr('scannerCreate', lang)}
      </button>
    </div>
  );
}

// ── Main panel ───────────────────────────────────────────────────────────────
export default function OBScannerPanel({ lang }: Props) {
  const ar = lang === 'ar';
  const [scanners, setScanners] = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await listOBScanners();
      setScanners(data);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Zap size={16} style={{ color: '#F472B6' }} />
            <span className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>
              {tr('obScannerTitle', lang)}
            </span>
            {scanners.length > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full font-bold"
                style={{ background: 'rgba(244,114,182,0.12)', color: '#F472B6', border: '1px solid rgba(244,114,182,0.2)' }}>
                {scanners.length}
              </span>
            )}
          </div>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {tr('obScannerDesc', lang)}
          </p>
        </div>
        <button
          onClick={() => setShowCreate(v => !v)}
          className="btn-secondary !px-3 !min-h-[34px] !text-xs flex items-center gap-1.5"
          style={{ borderColor: 'rgba(244,114,182,0.35)', color: '#F472B6' }}
        >
          <Plus size={13} />
          {ar ? 'جديد' : 'New'}
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <CreateForm lang={lang} onCreated={() => { setShowCreate(false); load(); }} />
      )}

      {/* Scanner list */}
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <RefreshCw size={18} className="spin" style={{ color: 'var(--text-muted)' }} />
        </div>
      ) : scanners.length === 0 && !showCreate ? (
        <div className="flex flex-col items-center gap-2 py-8 text-center">
          <AlertCircle size={28} style={{ color: 'var(--text-muted)', opacity: 0.4 }} />
          <div className="text-sm font-semibold" style={{ color: 'var(--text-muted)' }}>
            {tr('noScanners', lang)}
          </div>
          <div className="text-xs" style={{ color: 'var(--text-muted)', opacity: 0.7 }}>
            {tr('noScannersDesc', lang)}
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {scanners.map(s => (
            <ScannerCard key={s.id} scanner={s} lang={lang} onRefresh={load} />
          ))}
        </div>
      )}
    </div>
  );
}
