'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Square, Play, Trash2, RefreshCw,
  TrendingUp, AlertCircle, CheckCircle2, Circle,
  Zap, Radio, BarChart2,
} from 'lucide-react';
import { Lang, tr } from '../lib/i18n';
import {
  listOBScanners, createOBScanner, stopOBScanner,
  resumeOBScanner, deleteOBScanner, getOBScanner,
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

// ── Scanner card ─────────────────────────────────────────────────────────────
function ScannerCard({ scanner, lang, onRefresh }: {
  scanner: any; lang: Lang; onRefresh: () => void;
}) {
  const toast = useToast();
  const ar = lang === 'ar';
  const [detail, setDetail] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const fetchDetail = useCallback(async () => {
    try { setDetail(await getOBScanner(scanner.id)); } catch { /* silent */ }
  }, [scanner.id]);

  useEffect(() => {
    fetchDetail();
    const t = setInterval(fetchDetail, 12000);
    return () => clearInterval(t);
  }, [fetchDetail]);

  const running  = scanner.running;
  const status   = detail?.status ?? scanner.status ?? 'stopped';
  const inPos    = status === 'in_position';
  const conds    = detail?.conditions ?? {};
  const trades   = detail?.trades ?? [];
  const lastSym  = detail?.last_symbol ?? scanner.last_symbol ?? '';
  const scanned  = detail?.scanned ?? scanner.scanned ?? 0;
  const openPos  = detail?.open_positions ?? scanner.open_positions ?? 0;

  const statusColor = inPos ? '#F0B90B' : running ? '#00D4AA' : 'var(--text-muted)';
  const statusLabel = inPos
    ? tr('scannerInPosition', lang)
    : running
      ? tr('scannerScanning', lang)
      : tr('scannerStopped', lang);

  async function handleStop() {
    setBusy(true);
    try { await stopOBScanner(scanner.id); onRefresh(); toast.success(ar ? 'تم الإيقاف' : 'Stopped'); }
    catch (e: any) { toast.error(e.message); }
    finally { setBusy(false); }
  }

  async function handleResume() {
    setBusy(true);
    try { await resumeOBScanner(scanner.id); onRefresh(); toast.success(ar ? 'تم الاستئناف' : 'Resumed'); }
    catch (e: any) { toast.error(e.message); }
    finally { setBusy(false); }
  }

  async function handleDelete() {
    if (!confirm(ar ? 'حذف هذا السكانر؟' : 'Delete this scanner?')) return;
    setBusy(true);
    try { await deleteOBScanner(scanner.id); onRefresh(); }
    catch (e: any) { toast.error(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div
      className="card p-4 flex flex-col gap-3"
      style={{
        borderColor: inPos
          ? 'rgba(240,185,11,0.35)'
          : running
            ? 'rgba(0,212,170,0.25)'
            : 'var(--border)',
        boxShadow: running ? `0 0 20px ${statusColor}10` : 'none',
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-3">
        {/* Animated radar icon when running */}
        <div
          className="flex items-center justify-center rounded-xl shrink-0"
          style={{
            width: 40, height: 40,
            background: `${statusColor}15`,
            border: `1px solid ${statusColor}30`,
            boxShadow: running ? `0 0 12px ${statusColor}25` : 'none',
          }}
        >
          {running
            ? <Radio size={18} style={{ color: statusColor }} className={running ? 'spin' : ''} />
            : <BarChart2 size={18} style={{ color: statusColor }} />}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>
              {tr('scannerMarket', lang)}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full font-bold"
              style={{ background: 'rgba(123,92,245,0.12)', color: '#A78BFA', border: '1px solid rgba(123,92,245,0.2)' }}>
              {scanner.timeframe}
            </span>
            {openPos > 0 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full font-bold"
                style={{ background: 'rgba(240,185,11,0.12)', color: '#F0B90B', border: '1px solid rgba(240,185,11,0.25)' }}>
                {openPos} {tr('scannerOpenPos', lang)}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className={`w-1.5 h-1.5 rounded-full ${running ? 'pulse-dot' : ''}`}
              style={{ background: statusColor }} />
            <span className="text-[11px]" style={{ color: statusColor }}>{statusLabel}</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1.5 shrink-0">
          <button onClick={fetchDetail} className="btn-secondary !px-2 !min-h-[30px]">
            <RefreshCw size={11} />
          </button>
          {running
            ? <button onClick={handleStop} disabled={busy} className="btn-secondary !px-2 !min-h-[30px]">
                <Square size={11} style={{ color: '#FF7B72' }} />
              </button>
            : <button onClick={handleResume} disabled={busy} className="btn-secondary !px-2 !min-h-[30px]">
                <Play size={11} style={{ color: '#00D4AA' }} />
              </button>
          }
          <button onClick={handleDelete} disabled={busy} className="btn-secondary !px-2 !min-h-[30px]">
            <Trash2 size={11} style={{ color: '#FF7B72' }} />
          </button>
        </div>
      </div>

      {/* Config pills */}
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

      {/* Live sweep progress */}
      {running && (
        <div className="flex flex-col gap-1.5 p-3 rounded-xl"
          style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}>
          <div className="flex items-center justify-between text-[10px]">
            <span style={{ color: 'var(--text-muted)' }}>
              {tr('scannerScannedCount', lang)}
            </span>
            <span className="num font-bold" style={{ color: '#A78BFA' }}>{scanned.toLocaleString()}</span>
          </div>
          {lastSym && (
            <div className="flex items-center justify-between text-[10px]">
              <span style={{ color: 'var(--text-muted)' }}>{tr('scannerLastSymbol', lang)}</span>
              <span className="num font-bold" style={{ color: 'var(--text-main)' }}>{lastSym}</span>
            </div>
          )}
        </div>
      )}

      {/* Last checked conditions */}
      {Object.keys(conds).length > 0 && lastSym && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[10px] font-semibold" style={{ color: 'var(--text-muted)' }}>
            {tr('scannerConditions', lang)}{lastSym ? ` — ${lastSym}` : ''}
          </span>
          <div className="flex flex-wrap gap-1.5">
            <CondBadge label={tr('condSweepShort', lang)} ok={!!conds.liquidity_sweep} />
            <CondBadge label={tr('condBOSShort', lang)}   ok={!!conds.bos_choch} />
            <CondBadge label={tr('condFreshShort', lang)} ok={!!conds.fresh_ob} />
            <CondBadge label={tr('condFFGShort', lang)}   ok={!!conds.ffg} />
          </div>
        </div>
      )}

      {/* Open position summary */}
      {inPos && detail && Number(detail.entry_price) > 0 && (
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
            <div className="num text-xs font-bold"
              style={{ color: Number(detail.realised_pnl) >= 0 ? '#00D4AA' : '#FF7B72' }}>
              {Number(detail.realised_pnl).toFixed(4)} USDT
            </div>
          </div>
          <div>
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>TP1</div>
            <div className="text-xs font-bold"
              style={{ color: detail.tp1_hit ? '#00D4AA' : '#F0B90B' }}>
              {detail.tp1_hit ? tr('scannerTP1Hit', lang) : tr('scannerTP1Pending', lang)}
            </div>
          </div>
        </div>
      )}

      {/* Realised PnL when idle */}
      {!inPos && detail && Number(detail.realised_pnl) !== 0 && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-xl"
          style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}>
          <TrendingUp size={13} style={{ color: Number(detail.realised_pnl) >= 0 ? '#00D4AA' : '#FF7B72' }} />
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{tr('scannerPnl', lang)}:</span>
          <span className="num text-xs font-bold"
            style={{ color: Number(detail.realised_pnl) >= 0 ? '#00D4AA' : '#FF7B72' }}>
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
          {trades.slice(0, 5).map((t: any) => (
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
                <span className="text-[10px] truncate max-w-[80px]" style={{ color: 'var(--text-muted)' }}>
                  {t.label}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="num text-[10px]" style={{ color: 'var(--text-main)' }}>
                  {Number(t.price).toFixed(4)}
                </span>
                {t.pnl !== 0 && (
                  <span className="num text-[10px] font-bold"
                    style={{ color: t.pnl >= 0 ? '#00D4AA' : '#FF7B72' }}>
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
  const [timeframe, setTimeframe] = useState('15m');
  const [entryUsdt, setEntryUsdt] = useState('15');
  const [tp1, setTp1]             = useState('5');
  const [tp2, setTp2]             = useState('5');
  const [creating, setCreating]   = useState(false);

  async function handleCreate() {
    const entry = parseFloat(entryUsdt) || 15;
    setCreating(true);
    try {
      await createOBScanner({
        symbol: 'MARKET',
        timeframe,
        entry_usdt: entry,
        tp1_pct: parseFloat(tp1) || 5,
        tp2_pct: parseFloat(tp2) || 5,
      });
      toast.success(ar ? 'تم تشغيل السكانر — يمسح السوق الآن' : 'Scanner started — sweeping market now');
      onCreated();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="card p-4 flex flex-col gap-4"
      style={{ borderColor: 'rgba(244,114,182,0.3)', boxShadow: '0 0 20px rgba(244,114,182,0.06)' }}>

      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="flex items-center justify-center rounded-xl"
          style={{ width: 34, height: 34, background: 'rgba(244,114,182,0.12)', border: '1px solid rgba(244,114,182,0.25)' }}>
          <Radio size={16} style={{ color: '#F472B6' }} />
        </div>
        <div>
          <div className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>
            {tr('obScannerTitle', lang)}
          </div>
          <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            {ar ? 'يمسح كل عملات USDT تلقائياً' : 'Auto-scans all USDT pairs'}
          </div>
        </div>
      </div>

      {/* Timeframe */}
      <div>
        <label className="label">{tr('scannerTimeframe', lang)}</label>
        <div className="flex flex-wrap gap-1.5 mt-1.5">
          {TIMEFRAMES.map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)}
              className="px-3 py-1.5 rounded-lg text-xs font-bold transition-all"
              style={{
                background: timeframe === tf ? 'rgba(244,114,182,0.15)' : 'var(--bg-input)',
                border: `1px solid ${timeframe === tf ? 'rgba(244,114,182,0.45)' : 'var(--border)'}`,
                color: timeframe === tf ? '#F472B6' : 'var(--text-muted)',
                boxShadow: timeframe === tf ? '0 0 8px rgba(244,114,182,0.2)' : 'none',
              }}>
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* Entry + TPs */}
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="label">{tr('scannerEntry', lang)}</label>
          <div className="relative mt-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs font-bold"
              style={{ color: '#F472B6' }}>$</span>
            <input className="input w-full pl-6" type="number" min="5" step="1"
              value={entryUsdt} onChange={e => setEntryUsdt(e.target.value)} />
          </div>
        </div>
        <div>
          <label className="label">TP1 %</label>
          <input className="input w-full mt-1" type="number" min="0.5" step="0.5"
            value={tp1} onChange={e => setTp1(e.target.value)} />
        </div>
        <div>
          <label className="label">TP2 %</label>
          <input className="input w-full mt-1" type="number" min="0.5" step="0.5"
            value={tp2} onChange={e => setTp2(e.target.value)} />
        </div>
      </div>

      {/* Visual summary */}
      <div className="flex items-center gap-2 p-3 rounded-xl text-[11px]"
        style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}>
        <Zap size={12} style={{ color: '#F472B6', flexShrink: 0 }} />
        <span style={{ color: 'var(--text-muted)' }}>
          {ar
            ? `دخول $${entryUsdt || 15} → بيع 50% عند +${tp1}% → بيع 50% عند +${tp2}% إضافية`
            : `Enter $${entryUsdt || 15} → sell 50% at +${tp1}% → sell 50% at +${tp2}% more`}
        </span>
      </div>

      <button onClick={handleCreate} disabled={creating} className="btn-primary w-full"
        style={{ background: 'linear-gradient(135deg, #F472B6, #EC4899)' }}>
        {creating
          ? (ar ? 'جاري التشغيل...' : 'Starting...')
          : tr('scannerCreate', lang)}
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
    try { setScanners(await listOBScanners()); }
    catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  const hasRunning = scanners.some(s => s.running);

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Radio size={16} style={{ color: '#F472B6' }} />
            <span className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>
              {tr('obScannerTitle', lang)}
            </span>
            {hasRunning && (
              <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full font-bold"
                style={{ background: 'rgba(0,212,170,0.1)', color: '#00D4AA', border: '1px solid rgba(0,212,170,0.25)' }}>
                <span className="w-1.5 h-1.5 rounded-full pulse-dot" style={{ background: '#00D4AA' }} />
                {ar ? 'نشط' : 'Live'}
              </span>
            )}
          </div>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {tr('obScannerDesc', lang)}
          </p>
        </div>
        {!showCreate && (
          <button
            onClick={() => setShowCreate(true)}
            className="btn-secondary !px-3 !min-h-[34px] !text-xs flex items-center gap-1.5"
            style={{ borderColor: 'rgba(244,114,182,0.35)', color: '#F472B6' }}
          >
            <Radio size={12} />
            {ar ? 'سكانر جديد' : 'New Scanner'}
          </button>
        )}
      </div>

      {/* Create form */}
      {showCreate && (
        <CreateForm lang={lang} onCreated={() => { setShowCreate(false); load(); }} />
      )}

      {/* List */}
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <RefreshCw size={18} className="spin" style={{ color: 'var(--text-muted)' }} />
        </div>
      ) : scanners.length === 0 && !showCreate ? (
        <div className="flex flex-col items-center gap-3 py-10 text-center">
          <div className="flex items-center justify-center rounded-2xl"
            style={{ width: 52, height: 52, background: 'rgba(244,114,182,0.08)', border: '1px solid rgba(244,114,182,0.15)' }}>
            <AlertCircle size={24} style={{ color: '#F472B6', opacity: 0.5 }} />
          </div>
          <div className="text-sm font-semibold" style={{ color: 'var(--text-muted)' }}>
            {tr('noScanners', lang)}
          </div>
          <div className="text-xs max-w-xs" style={{ color: 'var(--text-muted)', opacity: 0.7 }}>
            {tr('noScannersDesc', lang)}
          </div>
          <button onClick={() => setShowCreate(true)} className="btn-primary !px-5 !min-h-[36px] !text-xs mt-1"
            style={{ background: 'linear-gradient(135deg, #F472B6, #EC4899)' }}>
            {ar ? 'ابدأ الآن' : 'Start Now'}
          </button>
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
