'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Square, Play, Trash2, RefreshCw,
  TrendingUp, AlertCircle, CheckCircle2, Circle,
  Zap, Radio, BarChart2, Activity,
} from 'lucide-react';
import { Lang, tr } from '../lib/i18n';
import {
  listSupertrendScanners, createSupertrendScanner,
  stopSupertrendScanner, resumeSupertrendScanner,
  deleteSupertrendScanner, getSupertrendScanner,
} from '../lib/api';
import { useToast } from './Toast';

interface Props { lang: Lang; }

const ACCENT = '#F59E0B'; // amber — distinct from OB scanner pink

function CondBadge({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span
      className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold"
      style={{
        background: ok ? 'rgba(0,212,170,0.12)' : 'rgba(245,158,11,0.08)',
        border: `1px solid ${ok ? 'rgba(0,212,170,0.3)' : 'rgba(245,158,11,0.15)'}`,
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

function ScannerCard({ scanner, lang, onRefresh }: {
  scanner: any; lang: Lang; onRefresh: () => void;
}) {
  const toast = useToast();
  const ar = lang === 'ar';
  const [detail, setDetail] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const fetchDetail = useCallback(async () => {
    try { setDetail(await getSupertrendScanner(scanner.id)); } catch { /* silent */ }
  }, [scanner.id]);

  useEffect(() => {
    fetchDetail();
    const t = setInterval(fetchDetail, 12000);
    return () => clearInterval(t);
  }, [fetchDetail]);

  const running   = scanner.running;
  const status    = detail?.status ?? scanner.status ?? 'stopped';
  const inPos     = status === 'in_position';
  const conds     = detail?.conditions ?? {};
  const trades    = detail?.trades ?? [];
  const lastSym   = detail?.last_symbol ?? scanner.last_symbol ?? '';
  const scanned   = detail?.scanned ?? scanner.scanned ?? 0;
  const openPos   = detail?.open_positions ?? scanner.open_positions ?? 0;
  const pnl       = detail?.realised_pnl ?? 0;
  const tp1Hit    = detail?.tp1_hit ?? false;
  const tp2Hit    = detail?.tp2_hit ?? false;

  const statusColor = inPos ? '#F59E0B' : running ? '#00D4AA' : 'var(--text-muted)';
  const statusLabel = inPos
    ? (ar ? 'في صفقة' : 'In Position')
    : running
      ? (ar ? 'يمسح السوق...' : 'Scanning...')
      : (ar ? 'متوقف' : 'Stopped');

  async function handleStop() {
    setBusy(true);
    try { await stopSupertrendScanner(scanner.id); onRefresh(); toast.success(ar ? 'تم الإيقاف' : 'Stopped'); }
    catch (e: any) { toast.error(e.message); }
    finally { setBusy(false); }
  }

  async function handleResume() {
    setBusy(true);
    try { await resumeSupertrendScanner(scanner.id); onRefresh(); toast.success(ar ? 'تم الاستئناف' : 'Resumed'); }
    catch (e: any) { toast.error(e.message); }
    finally { setBusy(false); }
  }

  async function handleDelete() {
    if (!confirm(ar ? 'حذف هذا السكانر؟' : 'Delete this scanner?')) return;
    setBusy(true);
    try { await deleteSupertrendScanner(scanner.id); onRefresh(); }
    catch (e: any) { toast.error(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div
      className="card p-4 flex flex-col gap-3"
      style={{
        borderColor: inPos
          ? 'rgba(245,158,11,0.4)'
          : running
            ? 'rgba(0,212,170,0.25)'
            : 'var(--border)',
        boxShadow: running ? `0 0 20px ${statusColor}10` : 'none',
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-3">
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
            ? <Activity size={18} style={{ color: statusColor }} />
            : <Activity size={18} style={{ color: 'var(--text-muted)' }} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>
              {ar ? 'سكانر Supertrend' : 'Supertrend Scanner'} #{scanner.id}
            </span>
            <span
              className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-bold"
              style={{
                background: `${statusColor}15`,
                border: `1px solid ${statusColor}30`,
                color: statusColor,
              }}
            >
              {running && <span className="w-1.5 h-1.5 rounded-full pulse-dot" style={{ background: statusColor }} />}
              {statusLabel}
            </span>
          </div>
          <div className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
            5m · ${detail?.entry_usdt ?? scanner.entry_usdt ?? 5} ·
            TP1 {detail?.tp1_pct ?? 1}% / TP2 {detail?.tp2_pct ?? 1.5}% / TP3 {detail?.tp3_pct ?? 2.5}%
          </div>
        </div>
        {/* Actions */}
        <div className="flex items-center gap-1.5 shrink-0">
          {running
            ? <button onClick={handleStop} disabled={busy} className="btn-secondary !px-2.5 !min-h-[30px] !text-xs flex items-center gap-1">
                <Square size={11} />{ar ? 'إيقاف' : 'Stop'}
              </button>
            : <button onClick={handleResume} disabled={busy} className="btn-secondary !px-2.5 !min-h-[30px] !text-xs flex items-center gap-1"
                style={{ borderColor: 'rgba(0,212,170,0.35)', color: '#00D4AA' }}>
                <Play size={11} />{ar ? 'تشغيل' : 'Start'}
              </button>}
          <button onClick={handleDelete} disabled={busy} className="btn-secondary !px-2 !min-h-[30px]"
            style={{ borderColor: 'rgba(239,68,68,0.3)', color: '#EF4444' }}>
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: ar ? 'مسح' : 'Scanned', value: scanned },
          { label: ar ? 'صفقات مفتوحة' : 'Open', value: openPos },
          { label: ar ? 'ربح محقق' : 'Realised PnL', value: `$${pnl.toFixed(3)}`, color: pnl >= 0 ? '#00D4AA' : '#EF4444' },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded-xl p-2.5 text-center"
            style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}>
            <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{label}</div>
            <div className="text-sm font-bold mt-0.5" style={{ color: color ?? 'var(--text-main)' }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Last scanned symbol */}
      {lastSym && (
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
          <BarChart2 size={11} />
          {ar ? 'آخر عملة:' : 'Last:'} <span style={{ color: 'var(--text-main)', fontWeight: 600 }}>{lastSym}</span>
        </div>
      )}

      {/* Active position */}
      {inPos && detail?.entry_price > 0 && (
        <div className="rounded-xl p-3 flex flex-col gap-2"
          style={{ background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)' }}>
          <div className="text-xs font-bold" style={{ color: ACCENT }}>
            {ar ? 'صفقة مفتوحة' : 'Open Position'} — {detail?.symbol}
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{ar ? 'سعر الدخول' : 'Entry'}: </span>
              <span style={{ color: 'var(--text-main)', fontWeight: 600 }}>${detail.entry_price.toFixed(6)}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{ar ? 'الكمية' : 'Qty'}: </span>
              <span style={{ color: 'var(--text-main)', fontWeight: 600 }}>{detail.base_qty.toFixed(6)}</span>
            </div>
          </div>
          <div className="flex gap-2 flex-wrap">
            <CondBadge label="TP1" ok={tp1Hit} />
            <CondBadge label="TP2" ok={tp2Hit} />
          </div>
        </div>
      )}

      {/* Signal conditions */}
      {Object.keys(conds).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {conds.supertrend_bullish !== undefined && <CondBadge label="Supertrend ↑" ok={conds.supertrend_bullish} />}
          {conds.ema20_rising       !== undefined && <CondBadge label="EMA20 ↑"      ok={conds.ema20_rising} />}
          {conds.close_above_ema20  !== undefined && <CondBadge label="Close>EMA"    ok={conds.close_above_ema20} />}
          {conds.rsi_ok             !== undefined && <CondBadge label={`RSI ${conds.rsi ?? ''}`} ok={conds.rsi_ok} />}
          {conds.volume_ok          !== undefined && <CondBadge label="Vol ✓"        ok={conds.volume_ok} />}
        </div>
      )}

      {/* Recent trades */}
      {trades.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="text-[10px] font-bold uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
            {ar ? 'آخر الصفقات' : 'Recent Trades'}
          </div>
          {trades.slice(0, 5).map((t: any) => (
            <div key={t.id} className="flex items-center justify-between text-[11px] py-1"
              style={{ borderBottom: '1px solid var(--border)' }}>
              <span style={{ color: t.side === 'BUY' ? '#00D4AA' : ACCENT, fontWeight: 700 }}>{t.side}</span>
              <span style={{ color: 'var(--text-muted)' }}>{t.label}</span>
              <span style={{ color: t.pnl >= 0 ? '#00D4AA' : '#EF4444', fontWeight: 600 }}>
                {t.pnl !== 0 ? `${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(4)}` : `$${t.usdt_value.toFixed(2)}`}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CreateForm({ lang, onCreated }: { lang: Lang; onCreated: () => void }) {
  const toast   = useToast();
  const ar      = lang === 'ar';
  const [entry, setEntry]   = useState('5');
  const [tp1,   setTp1]     = useState('1');
  const [tp2,   setTp2]     = useState('1.5');
  const [tp3,   setTp3]     = useState('2.5');
  const [creating, setCreating] = useState(false);

  async function handleCreate() {
    setCreating(true);
    try {
      await createSupertrendScanner({
        entry_usdt: parseFloat(entry) || 5,
        tp1_pct:    parseFloat(tp1)   || 1,
        tp2_pct:    parseFloat(tp2)   || 1.5,
        tp3_pct:    parseFloat(tp3)   || 2.5,
      });
      toast.success(ar ? 'تم تشغيل السكانر' : 'Scanner started');
      onCreated();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="card p-4 flex flex-col gap-3"
      style={{ borderColor: `${ACCENT}30`, boxShadow: `0 0 20px ${ACCENT}08` }}>
      <div className="text-sm font-bold" style={{ color: ACCENT }}>
        {ar ? 'إعدادات السكانر' : 'Scanner Settings'}
      </div>

      <div className="grid grid-cols-2 gap-3">
        {[
          { label: ar ? 'مبلغ الدخول ($)' : 'Entry ($)', val: entry, set: setEntry, placeholder: '5' },
          { label: 'TP1 %',  val: tp1, set: setTp1, placeholder: '1' },
          { label: 'TP2 %',  val: tp2, set: setTp2, placeholder: '1.5' },
          { label: 'TP3 %',  val: tp3, set: setTp3, placeholder: '2.5' },
        ].map(({ label, val, set, placeholder }) => (
          <div key={label} className="flex flex-col gap-1">
            <label className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{label}</label>
            <input
              type="number" value={val} placeholder={placeholder}
              onChange={e => set(e.target.value)}
              className="input-field !py-2 !text-sm"
            />
          </div>
        ))}
      </div>

      <div className="rounded-xl p-3 text-xs" style={{ background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.15)', color: 'var(--text-muted)' }}>
        {ar
          ? 'يمسح كل عملات USDT على فريم 5 دقائق. يدخل عند تحقق: Supertrend صاعد + EMA20 صاعدة + RSI 50–70 + حجم مرتفع.'
          : 'Scans all USDT pairs on 5m. Enters when: Supertrend bullish + EMA20 rising + RSI 50–70 + volume spike.'}
      </div>

      <button
        onClick={handleCreate}
        disabled={creating}
        className="btn-primary w-full flex items-center justify-center gap-2"
        style={{ background: `linear-gradient(135deg, ${ACCENT}, #D97706)` }}
      >
        <Zap size={14} />
        {creating ? (ar ? 'جاري التشغيل...' : 'Starting...') : (ar ? 'تشغيل السكانر' : 'Start Scanner')}
      </button>
    </div>
  );
}

export default function SupertrendPanel({ lang }: Props) {
  const ar = lang === 'ar';
  const [scanners, setScanners]     = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [loading, setLoading]       = useState(true);

  const load = useCallback(async () => {
    try { setScanners(await listSupertrendScanners()); }
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
            <Activity size={16} style={{ color: ACCENT }} />
            <span className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>
              {tr('stScannerTitle', lang)}
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
            {tr('stScannerDesc', lang)}
          </p>
        </div>
        {!showCreate && (
          <button
            onClick={() => setShowCreate(true)}
            className="btn-secondary !px-3 !min-h-[34px] !text-xs flex items-center gap-1.5"
            style={{ borderColor: `${ACCENT}40`, color: ACCENT }}
          >
            <Activity size={12} />
            {ar ? 'سكانر جديد' : 'New Scanner'}
          </button>
        )}
      </div>

      {showCreate && (
        <CreateForm lang={lang} onCreated={() => { setShowCreate(false); load(); }} />
      )}

      {loading ? (
        <div className="flex items-center justify-center py-8">
          <RefreshCw size={18} className="spin" style={{ color: 'var(--text-muted)' }} />
        </div>
      ) : scanners.length === 0 && !showCreate ? (
        <div className="flex flex-col items-center gap-3 py-10 text-center">
          <div className="flex items-center justify-center rounded-2xl"
            style={{ width: 52, height: 52, background: `${ACCENT}10`, border: `1px solid ${ACCENT}20` }}>
            <AlertCircle size={24} style={{ color: ACCENT, opacity: 0.5 }} />
          </div>
          <div className="text-sm font-semibold" style={{ color: 'var(--text-muted)' }}>
            {tr('noStScanners', lang)}
          </div>
          <div className="text-xs max-w-xs" style={{ color: 'var(--text-muted)', opacity: 0.7 }}>
            {tr('noStScannersDesc', lang)}
          </div>
          <button onClick={() => setShowCreate(true)} className="btn-primary !px-5 !min-h-[36px] !text-xs mt-1"
            style={{ background: `linear-gradient(135deg, ${ACCENT}, #D97706)` }}>
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
