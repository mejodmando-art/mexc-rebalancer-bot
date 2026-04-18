'use client';

import { useState } from 'react';
import {
  CheckCircle2, Circle, ChevronDown, ChevronUp,
  Target, Brain, Crosshair, TrendingUp, AlertTriangle,
  Zap, Shield, Clock, BarChart2,
} from 'lucide-react';
import { Lang, tr } from '../lib/i18n';
import SupertrendPanel from './SupertrendPanel';

interface Props { lang: Lang; }

/* ─── Reusable sub-components ─────────────────────────────────────── */

function StepBadge({ n, color }: { n: number; color: string }) {
  return (
    <span
      className="flex items-center justify-center shrink-0 font-black text-sm rounded-xl"
      style={{
        width: 36, height: 36,
        background: `linear-gradient(145deg, ${color}30, ${color}10)`,
        border: `1px solid ${color}40`,
        boxShadow: `0 4px 14px ${color}30, inset 0 1px 0 rgba(255,255,255,0.12)`,
        color,
      }}
    >
      {n}
    </span>
  );
}

function ConditionCard({
  icon: Icon, title, desc, color, lang,
}: {
  icon: React.ElementType; title: string; desc: string; color: string; lang: Lang;
}) {
  const [open, setOpen] = useState(false);
  const ar = lang === 'ar';
  return (
    <div
      className="rounded-2xl overflow-hidden transition-all duration-200"
      style={{
        background: 'var(--bg-input)',
        border: `1px solid ${open ? color + '40' : 'var(--border)'}`,
        boxShadow: open ? `0 4px 20px ${color}18` : 'none',
      }}
    >
      <button
        className="w-full flex items-center gap-3 p-4 text-start"
        onClick={() => setOpen(v => !v)}
      >
        <span
          className="flex items-center justify-center shrink-0 rounded-xl"
          style={{
            width: 36, height: 36,
            background: `${color}18`,
            border: `1px solid ${color}30`,
          }}
        >
          <Icon size={17} style={{ color }} />
        </span>
        <span className="flex-1 text-sm font-semibold" style={{ color: 'var(--text-main)' }}>
          {title}
        </span>
        {open
          ? <ChevronUp size={15} style={{ color: 'var(--text-muted)' }} />
          : <ChevronDown size={15} style={{ color: 'var(--text-muted)' }} />}
      </button>
      {open && (
        <div
          className="px-4 pb-4 text-sm leading-relaxed"
          style={{
            color: 'var(--text-muted)',
            borderTop: `1px solid ${color}20`,
            paddingTop: 12,
            direction: ar ? 'rtl' : 'ltr',
          }}
        >
          {desc}
        </div>
      )}
    </div>
  );
}

function StepSection({
  stepNum, icon: Icon, color, title, desc, children,
}: {
  stepNum: number; icon: React.ElementType; color: string;
  title: string; desc: string; children: React.ReactNode;
}) {
  return (
    <div
      className="card p-5 sm:p-6 flex flex-col gap-4"
      style={{ borderColor: `${color}25` }}
    >
      {/* Header */}
      <div className="flex items-center gap-3">
        <StepBadge n={stepNum} color={color} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Icon size={16} style={{ color }} />
            <span className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>{title}</span>
          </div>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{desc}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

function EntryRow({
  num, title, desc, color,
}: {
  num: string; title: string; desc: string; color: string;
}) {
  return (
    <div
      className="flex gap-3 p-3 rounded-xl"
      style={{ background: `${color}08`, border: `1px solid ${color}20` }}
    >
      <span
        className="shrink-0 font-black text-xs flex items-center justify-center rounded-lg"
        style={{
          width: 28, height: 28,
          background: `${color}20`,
          color,
          border: `1px solid ${color}30`,
        }}
      >
        {num}
      </span>
      <div>
        <div className="text-sm font-semibold" style={{ color: 'var(--text-main)' }}>{title}</div>
        <div className="text-xs mt-0.5 leading-relaxed" style={{ color: 'var(--text-muted)' }}>{desc}</div>
      </div>
    </div>
  );
}

function ExitCard({
  title, desc, pct, color,
}: {
  title: string; desc: string; pct: string; color: string;
}) {
  return (
    <div
      className="flex-1 min-w-[140px] p-4 rounded-2xl flex flex-col gap-2"
      style={{
        background: `${color}08`,
        border: `1px solid ${color}25`,
        boxShadow: `0 2px 12px ${color}10`,
      }}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-bold" style={{ color }}>{title}</span>
        <span
          className="text-xs font-black px-2 py-0.5 rounded-full"
          style={{ background: `${color}20`, color }}
        >
          {pct}
        </span>
      </div>
      <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>{desc}</p>
    </div>
  );
}

/* ─── Checklist ────────────────────────────────────────────────────── */

const CHECKLIST_KEYS = [
  'checkFresh', 'checkFFG', 'checkBOS', 'checkSweep',
  'checkTrend', 'checkNoInducement', 'checkSession',
  'checkLTFConfirm', 'checkFib',
] as const;

function Checklist({ lang }: { lang: Lang }) {
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const toggle = (k: string) => setChecked(p => ({ ...p, [k]: !p[k] }));
  const count = Object.values(checked).filter(Boolean).length;
  const total = CHECKLIST_KEYS.length;
  const pct = Math.round((count / total) * 100);
  const ready = count === total;

  return (
    <div className="flex flex-col gap-3">
      {/* Progress bar */}
      <div className="flex items-center gap-3">
        <div
          className="flex-1 h-2 rounded-full overflow-hidden"
          style={{ background: 'var(--bg-input)' }}
        >
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${pct}%`,
              background: ready
                ? 'linear-gradient(90deg, #00D4AA, #00B894)'
                : 'linear-gradient(90deg, #7B5CF5, #3B82F6)',
              boxShadow: ready ? '0 0 8px rgba(0,212,170,0.5)' : 'none',
            }}
          />
        </div>
        <span
          className="text-xs font-bold shrink-0"
          style={{ color: ready ? '#00D4AA' : 'var(--text-muted)' }}
        >
          {count}/{total}
        </span>
      </div>

      {/* Items */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {CHECKLIST_KEYS.map(k => {
          const done = !!checked[k];
          return (
            <button
              key={k}
              onClick={() => toggle(k)}
              className="flex items-center gap-2.5 p-3 rounded-xl text-start transition-all duration-150 active:scale-95"
              style={{
                background: done ? 'rgba(0,212,170,0.08)' : 'var(--bg-input)',
                border: `1px solid ${done ? 'rgba(0,212,170,0.3)' : 'var(--border)'}`,
              }}
            >
              {done
                ? <CheckCircle2 size={16} style={{ color: '#00D4AA', flexShrink: 0 }} />
                : <Circle size={16} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />}
              <span
                className="text-xs"
                style={{
                  color: done ? '#00D4AA' : 'var(--text-muted)',
                  textDecoration: done ? 'line-through' : 'none',
                  fontWeight: done ? 600 : 400,
                }}
              >
                {tr(k, lang)}
              </span>
            </button>
          );
        })}
      </div>

      {/* Ready badge */}
      {ready && (
        <div
          className="flex items-center gap-2 p-3 rounded-xl"
          style={{
            background: 'rgba(0,212,170,0.1)',
            border: '1px solid rgba(0,212,170,0.35)',
            boxShadow: '0 0 16px rgba(0,212,170,0.15)',
          }}
        >
          <Zap size={15} style={{ color: '#00D4AA' }} />
          <span className="text-sm font-bold" style={{ color: '#00D4AA' }}>
            {lang === 'ar' ? '✅ جاهز للدخول — كل الشروط مكتملة' : '✅ Ready to Enter — All conditions met'}
          </span>
        </div>
      )}
    </div>
  );
}

/* ─── Main component ───────────────────────────────────────────────── */

export default function OrderBlockStrategy({ lang }: Props) {
  const ar = lang === 'ar';

  return (
    <div className="flex flex-col gap-6 animate-fade-up" dir={ar ? 'rtl' : 'ltr'}>

      {/* Supertrend Scanner panel */}
      <div className="card p-5 sm:p-6" style={{ borderColor: 'rgba(245,158,11,0.25)' }}>
        <SupertrendPanel lang={lang} />
      </div>



      {/* Hero header */}
      <div
        className="hero-card p-6 sm:p-8 relative overflow-hidden"
        style={{ borderColor: 'rgba(123,92,245,0.3)' }}
      >
        {/* Background glow */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'radial-gradient(ellipse 70% 60% at 50% 0%, rgba(123,92,245,0.15) 0%, transparent 70%)',
          }}
        />
        <div className="relative flex flex-col sm:flex-row sm:items-center gap-4">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center shrink-0"
            style={{
              background: 'linear-gradient(145deg, rgba(123,92,245,0.3), rgba(59,130,246,0.2))',
              border: '1px solid rgba(123,92,245,0.4)',
              boxShadow: '0 8px 24px rgba(123,92,245,0.3)',
            }}
          >
            <Target size={26} style={{ color: '#A78BFA' }} />
          </div>
          <div>
            <h1 className="text-xl sm:text-2xl font-black" style={{ color: 'var(--text-main)' }}>
              {tr('strategyTitle', lang)}
            </h1>
            <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
              {tr('strategySubtitle', lang)}
            </p>
          </div>
        </div>

        {/* Quick stats row */}
        <div className="relative grid grid-cols-3 gap-3 mt-6">
          {[
            { label: ar ? '٤ خطوات' : '4 Steps', sub: ar ? 'منهجية منظمة' : 'Structured method', color: '#A78BFA' },
            { label: ar ? '٩ شروط' : '9 Conditions', sub: ar ? 'قائمة تحقق' : 'Checklist', color: '#60A5FA' },
            { label: ar ? 'بدون ستوب' : 'No Stop Loss', sub: ar ? 'إدارة الحجم' : 'Size management', color: '#00D4AA' },
          ].map(({ label, sub, color }) => (
            <div
              key={label}
              className="p-3 rounded-xl text-center"
              style={{ background: `${color}10`, border: `1px solid ${color}25` }}
            >
              <div className="text-sm font-black" style={{ color }}>{label}</div>
              <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>{sub}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Step 1 — Technical filtering */}
      <StepSection
        stepNum={1}
        icon={BarChart2}
        color="#60A5FA"
        title={tr('step1Title', lang)}
        desc={tr('step1Desc', lang)}
      >
        <div className="flex flex-col gap-2">
          <ConditionCard icon={Zap}        title={tr('condMomentum', lang)} desc={tr('condMomentumDesc', lang)} color="#F0B90B" lang={lang} />
          <ConditionCard icon={TrendingUp} title={tr('condBOS', lang)}      desc={tr('condBOSDesc', lang)}      color="#60A5FA" lang={lang} />
          <ConditionCard icon={Shield}     title={tr('condFresh', lang)}    desc={tr('condFreshDesc', lang)}    color="#00D4AA" lang={lang} />
          <ConditionCard icon={Target}     title={tr('condSweep', lang)}    desc={tr('condSweepDesc', lang)}    color="#A78BFA" lang={lang} />
        </div>
      </StepSection>

      {/* Step 2 — Psychology & trend */}
      <StepSection
        stepNum={2}
        icon={Brain}
        color="#A78BFA"
        title={tr('step2Title', lang)}
        desc={tr('step2Desc', lang)}
      >
        <div className="flex flex-col gap-2">
          <ConditionCard icon={TrendingUp}    title={tr('condTrend', lang)}       desc={tr('condTrendDesc', lang)}       color="#00D4AA" lang={lang} />
          <ConditionCard icon={AlertTriangle} title={tr('condInducement', lang)}  desc={tr('condInducementDesc', lang)}  color="#FF7B72" lang={lang} />
          <ConditionCard icon={Clock}         title={tr('condTime', lang)}        desc={tr('condTimeDesc', lang)}        color="#F0B90B" lang={lang} />
        </div>
      </StepSection>

      {/* Step 3 — Execution entry */}
      <StepSection
        stepNum={3}
        icon={Crosshair}
        color="#00D4AA"
        title={tr('step3Title', lang)}
        desc={tr('step3Desc', lang)}
      >
        <div className="flex flex-col gap-2">
          <EntryRow num="١" title={tr('entryStep1', lang)} desc={tr('entryStep1Desc', lang)} color="#60A5FA" />
          <EntryRow num="٢" title={tr('entryStep2', lang)} desc={tr('entryStep2Desc', lang)} color="#A78BFA" />
          <EntryRow num="٣" title={tr('entryStep3', lang)} desc={tr('entryStep3Desc', lang)} color="#F0B90B" />
          <EntryRow num="٤" title={tr('entryStep4', lang)} desc={tr('entryStep4Desc', lang)} color="#00D4AA" />
        </div>

        {/* Fibonacci visual */}
        <div
          className="rounded-2xl p-4 mt-1"
          style={{ background: 'var(--bg-input)', border: '1px solid rgba(240,185,11,0.2)' }}
        >
          <div className="text-xs font-bold mb-3" style={{ color: '#F0B90B' }}>
            {ar ? 'مستويات فيبوناتشي الرئيسية' : 'Key Fibonacci Levels'}
          </div>
          <div className="flex flex-col gap-1.5">
            {[
              { level: '0.236', label: ar ? 'ضعيف' : 'Weak',         color: '#7B6FA8', w: '24%' },
              { level: '0.382', label: ar ? 'متوسط' : 'Moderate',    color: '#60A5FA', w: '38%' },
              { level: '0.500', label: ar ? 'مهم' : 'Important',     color: '#A78BFA', w: '50%' },
              { level: '0.618', label: ar ? 'ذهبي ⭐' : 'Golden ⭐', color: '#F0B90B', w: '62%' },
              { level: '0.786', label: ar ? 'ذهبي ⭐' : 'Golden ⭐', color: '#F0B90B', w: '79%' },
              { level: '1.000', label: ar ? 'نهاية الحركة' : 'End',  color: '#FF7B72', w: '100%' },
            ].map(({ level, label, color, w }) => (
              <div key={level} className="flex items-center gap-2">
                <span className="text-[10px] font-mono w-10 shrink-0" style={{ color: 'var(--text-muted)' }}>{level}</span>
                <div className="flex-1 h-1.5 rounded-full" style={{ background: 'rgba(123,92,245,0.1)' }}>
                  <div
                    className="h-full rounded-full"
                    style={{ width: w, background: color, boxShadow: color === '#F0B90B' ? `0 0 6px ${color}80` : 'none' }}
                  />
                </div>
                <span className="text-[10px] shrink-0" style={{ color }}>{label}</span>
              </div>
            ))}
          </div>
        </div>
      </StepSection>

      {/* Step 4 — Exit plan */}
      <StepSection
        stepNum={4}
        icon={TrendingUp}
        color="#F0B90B"
        title={tr('step4Title', lang)}
        desc={tr('step4Desc', lang)}
      >
        {/* No-SL explanation */}
        <div
          className="p-4 rounded-2xl"
          style={{
            background: 'rgba(240,185,11,0.06)',
            border: '1px solid rgba(240,185,11,0.2)',
          }}
        >
          <div className="flex items-center gap-2 mb-2">
            <Shield size={15} style={{ color: '#F0B90B' }} />
            <span className="text-sm font-bold" style={{ color: '#F0B90B' }}>{tr('exitNoSL', lang)}</span>
          </div>
          <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            {tr('exitNoSLDesc', lang)}
          </p>
        </div>

        {/* TP cards */}
        <div className="flex flex-wrap gap-3">
          <ExitCard title={tr('exitTP1', lang)} desc={tr('exitTP1Desc', lang)} pct="50%" color="#00D4AA" />
          <ExitCard title={tr('exitTP2', lang)} desc={tr('exitTP2Desc', lang)} pct="30%" color="#60A5FA" />
          <ExitCard title={tr('exitTP3', lang)} desc={tr('exitTP3Desc', lang)} pct="20%" color="#A78BFA" />
        </div>

        {/* Visual position split */}
        <div
          className="rounded-xl overflow-hidden"
          style={{ border: '1px solid var(--border)' }}
        >
          <div className="flex h-8">
            {[
              { pct: 50, color: '#00D4AA', label: 'TP1 50%' },
              { pct: 30, color: '#60A5FA', label: 'TP2 30%' },
              { pct: 20, color: '#A78BFA', label: 'TP3 20%' },
            ].map(({ pct, color, label }) => (
              <div
                key={label}
                className="flex items-center justify-center text-[10px] font-bold transition-all"
                style={{ width: `${pct}%`, background: `${color}25`, color, borderRight: '1px solid var(--bg-base)' }}
              >
                {label}
              </div>
            ))}
          </div>
        </div>
      </StepSection>

      {/* Pre-entry checklist */}
      <div className="card p-5 sm:p-6 flex flex-col gap-4" style={{ borderColor: 'rgba(0,212,170,0.25)' }}>
        <div className="flex items-center gap-3">
          <span
            className="flex items-center justify-center rounded-xl shrink-0"
            style={{
              width: 36, height: 36,
              background: 'rgba(0,212,170,0.15)',
              border: '1px solid rgba(0,212,170,0.3)',
            }}
          >
            <CheckCircle2 size={17} style={{ color: '#00D4AA' }} />
          </span>
          <div>
            <div className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>
              {tr('checklistTitle', lang)}
            </div>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              {ar ? 'اضغط على كل شرط للتأكيد قبل الدخول' : 'Tap each condition to confirm before entering'}
            </p>
          </div>
        </div>
        <Checklist lang={lang} />
      </div>

      {/* Risk note */}
      <div
        className="flex gap-3 p-4 rounded-2xl"
        style={{
          background: 'rgba(255,123,114,0.06)',
          border: '1px solid rgba(255,123,114,0.25)',
        }}
      >
        <AlertTriangle size={18} style={{ color: '#FF7B72', flexShrink: 0, marginTop: 1 }} />
        <div>
          <div className="text-sm font-bold mb-1" style={{ color: '#FF7B72' }}>
            {tr('riskNote', lang)}
          </div>
          <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            {tr('riskNoteDesc', lang)}
          </p>
        </div>
      </div>

    </div>
  );
}
