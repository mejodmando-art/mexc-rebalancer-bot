'use client';

import { useState } from 'react';
import { Grid3x3, TrendingUp, BarChart2, BookOpen, Zap, Info, ChevronDown, ChevronUp } from 'lucide-react';
import { Lang } from '../lib/i18n';

interface Props { lang: Lang; }

type GridTab = 'summary' | 'guide' | 'params';

// ── Accordion item ────────────────────────────────────────────────────────────
function AccordionItem({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      className="rounded-2xl border transition-all duration-200"
      style={{ borderColor: open ? 'rgba(0,212,170,0.35)' : 'var(--border)', background: 'var(--bg-card)' }}
    >
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-4 text-start"
      >
        <span className="font-bold text-base" style={{ color: 'var(--text-main)', letterSpacing: '-0.01em' }}>
          {title}
        </span>
        {open
          ? <ChevronUp size={18} style={{ color: 'var(--accent)' }} />
          : <ChevronDown size={18} style={{ color: 'var(--text-muted)' }} />}
      </button>
      {open && (
        <div className="px-5 pb-4 text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {children}
        </div>
      )}
    </div>
  );
}

// ── Wave chart SVG ────────────────────────────────────────────────────────────
function WaveChart() {
  return (
    <div className="relative w-full h-40 rounded-2xl overflow-hidden" style={{ background: 'var(--bg-input)' }}>
      <svg viewBox="0 0 360 120" className="w-full h-full" preserveAspectRatio="none">
        <defs>
          <linearGradient id="waveGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#00D4AA" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#00D4AA" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Grid lines */}
        <line x1="0" y1="30"  x2="360" y2="30"  stroke="#1E2D45" strokeWidth="1" strokeDasharray="4,4" />
        <line x1="0" y1="60"  x2="360" y2="60"  stroke="#1E2D45" strokeWidth="1" strokeDasharray="4,4" />
        <line x1="0" y1="90"  x2="360" y2="90"  stroke="#1E2D45" strokeWidth="1" strokeDasharray="4,4" />
        {/* S2 / B2 labels */}
        <text x="8" y="28"  fontSize="9" fill="#FF7B72" fontWeight="700">S2</text>
        <text x="8" y="92"  fontSize="9" fill="#00D4AA" fontWeight="700">B2</text>
        {/* Wave path */}
        <path
          d="M0,90 C40,90 60,20 90,20 C120,20 140,100 180,100 C220,100 240,30 270,30 C300,30 330,80 360,60"
          fill="none" stroke="#00D4AA" strokeWidth="2.5" strokeLinecap="round"
        />
        <path
          d="M0,90 C40,90 60,20 90,20 C120,20 140,100 180,100 C220,100 240,30 270,30 C300,30 330,80 360,60 L360,120 L0,120 Z"
          fill="url(#waveGrad)"
        />
        {/* Dots */}
        <circle cx="90"  cy="20"  r="5" fill="#FF7B72" stroke="#0F1520" strokeWidth="2" />
        <circle cx="180" cy="100" r="5" fill="#00D4AA" stroke="#0F1520" strokeWidth="2" />
        <circle cx="270" cy="30"  r="5" fill="#FF7B72" stroke="#0F1520" strokeWidth="2" />
        {/* BUY ORDER label */}
        <rect x="185" y="55" width="80" height="22" rx="6" fill="var(--bg-card)" stroke="var(--border)" />
        <text x="225" y="64" fontSize="7" fill="var(--text-muted)" textAnchor="middle" fontWeight="600">BUY ORDER</text>
        <text x="225" y="73" fontSize="7" fill="var(--text-main)" textAnchor="middle" fontWeight="700">Price: 2,200</text>
        <line x1="225" y1="77" x2="225" y2="98" stroke="var(--border)" strokeWidth="1" strokeDasharray="2,2" />
        {/* +1500U badge */}
        <rect x="270" y="8" width="52" height="18" rx="9" fill="rgba(0,212,170,0.15)" />
        <text x="296" y="20" fontSize="8" fill="#00D4AA" textAnchor="middle" fontWeight="800">+1,500U</text>
      </svg>
    </div>
  );
}

// ── Investment slider ─────────────────────────────────────────────────────────
function InvestmentInput({ lang }: { lang: Lang }) {
  const [amount, setAmount] = useState('');
  const steps = [0, 25, 50, 75, 100];
  const [step, setStep] = useState(0);

  return (
    <div
      className="rounded-2xl p-4 space-y-3"
      style={{ background: 'rgba(0,212,170,0.06)', border: '1px solid rgba(0,212,170,0.2)' }}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
          Investment
        </span>
        <span className="text-xs font-bold px-2 py-0.5 rounded-full" style={{ background: 'rgba(0,212,170,0.15)', color: 'var(--accent)' }}>
          USDT+BTC ▾
        </span>
      </div>
      <input
        type="number"
        value={amount}
        onChange={e => setAmount(e.target.value)}
        placeholder={lang === 'ar' ? 'أدخل المبلغ' : 'Enter'}
        className="input text-lg font-bold"
        style={{ background: 'var(--bg-input)', textAlign: lang === 'ar' ? 'right' : 'left' }}
      />
      {/* Step dots */}
      <div className="flex items-center gap-1">
        {steps.map((s, i) => (
          <button
            key={s}
            onClick={() => setStep(i)}
            className="flex-1 h-2 rounded-full transition-all"
            style={{ background: i <= step ? 'var(--accent)' : 'var(--border)' }}
          />
        ))}
      </div>
      <div className="flex justify-between text-[10px]" style={{ color: 'var(--text-muted)' }}>
        {steps.map(s => <span key={s}>{s}%</span>)}
      </div>
    </div>
  );
}

// ── Summary tab ───────────────────────────────────────────────────────────────
function SummaryTab({ lang }: { lang: Lang }) {
  const ar = lang === 'ar';
  const features = [
    { label: ar ? 'إدارة التقلبات' : 'Volatility Management', color: '#00D4AA' },
    { label: ar ? 'مراجحة الشبكة' : 'Grid Arbitrage', color: '#60A5FA' },
    { label: ar ? 'التعديلات التلقائية' : 'Auto Adjustments', color: '#A78BFA' },
  ];

  return (
    <div className="space-y-5">
      {/* Wave chart */}
      <WaveChart />

      {/* Feature tags */}
      <div className="flex flex-wrap gap-2">
        {features.map(f => (
          <span
            key={f.label}
            className="px-3 py-1 rounded-full text-xs font-bold"
            style={{ background: `${f.color}18`, color: f.color, border: `1px solid ${f.color}33` }}
          >
            {f.label}
          </span>
        ))}
      </div>

      {/* What is grid bot */}
      <div className="space-y-3">
        <h3 className="font-bold text-base" style={{ color: 'var(--text-main)' }}>
          {ar ? 'ما هو بوت الشبكات الديناميكي؟' : 'What is the Dynamic Grid Bot?'}
        </h3>
        <p className="text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {ar
            ? 'يقوم بوت الشبكات الديناميكي بتعديل عدد الشبكات وفتراتها تلقائياً وبشكل فوري، بناءً على عوامل مثل تقلبات السوق وتغيرات الأسعار. يسمح ذلك للشبكة بالتحرك ديناميكياً مع السعر، مما يضمن فرص الربح المستمر من تحركات السوق.'
            : 'The Dynamic Grid Bot automatically adjusts the number of grids and their intervals in real time, based on market volatility and price changes. This allows the grid to move dynamically with the price, ensuring continuous profit opportunities from market movements.'}
        </p>
        <p className="text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {ar
            ? 'تعمل مراجحة الشبكة بشكل أفضل عندما يبقى السعر ضمن نطاق محدد. لا يمكن لبوتات الشبكة التقليدية وضع الأوامر إلا ضمن نطاق محدد — وبمجرد أن يتجاوز السعر هذا النطاق أو يقل عنه، تتوقف المراجحة. ومع ذلك، لا يخضع بوت الشبكة الديناميكي للذكاء الاصطناعي لهذا القيد.'
            : 'Grid arbitrage works best when the price stays within a set range. Traditional grid bots can only place orders within a fixed range — once the price exceeds or falls below this range, arbitrage stops. However, the AI Dynamic Grid Bot is not subject to this limitation.'}
        </p>
      </div>

      {/* How it works */}
      <div className="space-y-3">
        <h3 className="font-bold text-base" style={{ color: 'var(--text-main)' }}>
          {ar ? 'كيف يعمل؟' : 'How does it work?'}
        </h3>
        <div className="space-y-3">
          {[
            {
              title: ar ? 'مجموعات التقلب' : 'Volatility Groups',
              desc: ar
                ? 'مناسبة للاتجاهات الصعودية المتقلبة، والشراء بسعر منخفض تلقائياً والبيع بسعر مرتفع.'
                : 'Suitable for volatile uptrends, automatically buying low and selling high.',
              color: '#00D4AA',
            },
            {
              title: ar ? 'التداول الشبكي الآلي' : 'Automated Grid Trading',
              desc: ar
                ? 'يضبط الفواصل الزمنية للشبكة تلقائياً، مما يضمن مراجحة متسقة دون تعديلات يدوية.'
                : 'Automatically adjusts grid intervals, ensuring consistent arbitrage without manual adjustments.',
              color: '#60A5FA',
            },
          ].map(item => (
            <div
              key={item.title}
              className="rounded-2xl p-4"
              style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2 h-2 rounded-full" style={{ background: item.color }} />
                <span className="font-bold text-sm" style={{ color: 'var(--text-main)' }}>{item.title}</span>
              </div>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>{item.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Guide tab ─────────────────────────────────────────────────────────────────
function GuideTab({ lang }: { lang: Lang }) {
  const ar = lang === 'ar';
  return (
    <div className="space-y-4">
      <div
        className="rounded-2xl p-4 space-y-3"
        style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}
      >
        <h3 className="font-bold text-base" style={{ color: 'var(--text-main)' }}>
          {ar ? 'مبلغ الاستثمار' : 'Investment Amount'}
        </h3>
        <p className="text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {ar
            ? 'إجمالي مبلغ الأموال التي تنوي استخدامها. بمجرد تنشيط البوت، سوف تُحوّل أموال التداول تلقائياً من حساب التداول الخاص بك إلى حساب بوت التداول.'
            : 'Total amount of funds you intend to use. Once the bot is activated, trading funds will be automatically transferred from your trading account to the bot trading account.'}
        </p>
        <InvestmentInput lang={lang} />
        <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {ar
            ? 'اضغط على تشغيل لإنشاء الاستراتيجية وبدء تشغيلها. نظراً لأن هذه الاستراتيجية ذكاء اصطناعي، فلا حاجة إلى معلمات. سيقوم البوت بتنفيذ الصفقات تلقائياً بناءً على إشارات التداول.'
            : 'Press run to create the strategy and start running it. Since this is an AI strategy, no parameters are needed. The bot will execute trades automatically based on trading signals.'}
        </p>
      </div>

      <button
        className="w-full py-4 rounded-2xl font-bold text-base transition-all"
        style={{
          background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
          color: '#fff',
          border: '1px solid rgba(255,255,255,0.1)',
          boxShadow: '0 4px 20px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.08)',
          letterSpacing: '0.02em',
        }}
      >
        {ar ? 'إنشاء' : 'Create'}
      </button>
    </div>
  );
}

// ── Params tab ────────────────────────────────────────────────────────────────
function ParamsTab({ lang }: { lang: Lang }) {
  const ar = lang === 'ar';
  const params = [
    { key: ar ? 'نطاق السعر المبدئي' : 'Initial Price Range' },
    { key: ar ? 'رقم الشبكة الأولي' : 'Initial Grid Number' },
    { key: ar ? 'إجمالي الاستثمار' : 'Total Investment' },
    { key: ar ? 'ربح الشبكة' : 'Grid Profit' },
    { key: ar ? 'الأرباح والخسائر غير المحققة' : 'Unrealized P&L' },
    { key: ar ? 'إجمالي الربح' : 'Total Profit' },
    { key: ar ? 'نسبة العائد السنوي' : 'Annual Return Rate' },
    { key: ar ? 'نسبة العائد السنوي للتداول الشبكي' : 'Grid Trading Annual Return' },
  ];

  return (
    <div className="space-y-2">
      <p className="text-sm leading-relaxed mb-4" style={{ color: 'var(--text-muted)' }}>
        {ar
          ? 'سيقوم البوت تلقائياً بضبط النطاق السعري وعدد الشبكات بناءً على تقلبات الأسعار وظروف السوق. لتجنب التقلبات الكبيرة في الأسعار على المدى القصير، لن تُوضع جميع أوامر الشراء والبيع في وقت واحد.'
          : 'The bot will automatically adjust the price range and number of grids based on price fluctuations and market conditions. To avoid large short-term price swings, not all buy and sell orders will be placed at once.'}
      </p>
      {params.map(p => (
        <AccordionItem key={p.key} title={p.key}>
          <span style={{ color: 'var(--text-muted)' }}>
            {ar ? 'يتم ضبط هذه المعلمة تلقائياً بواسطة الذكاء الاصطناعي بناءً على ظروف السوق الحالية.' : 'This parameter is automatically adjusted by AI based on current market conditions.'}
          </span>
        </AccordionItem>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function GridBot({ lang }: Props) {
  const [activeTab, setActiveTab] = useState<GridTab>('summary');
  const ar = lang === 'ar';

  const tabs: { key: GridTab; label: string; icon: React.ElementType }[] = [
    { key: 'summary', label: ar ? 'ملخص' : 'Summary',    icon: BarChart2 },
    { key: 'guide',   label: ar ? 'دليل المبتدئين' : 'Beginner Guide', icon: BookOpen },
    { key: 'params',  label: ar ? 'المعلمات الشائعة' : 'Common Params', icon: Grid3x3 },
  ];

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <div
            className="w-11 h-11 rounded-2xl flex items-center justify-center shrink-0"
            style={{
              background: 'linear-gradient(145deg, rgba(0,212,170,0.25), rgba(0,212,170,0.08))',
              border: '1px solid rgba(0,212,170,0.35)',
              boxShadow: '0 4px 16px rgba(0,212,170,0.2), inset 0 1px 0 rgba(255,255,255,0.1)',
            }}
          >
            <Grid3x3 size={22} style={{ color: 'var(--accent)', filter: 'drop-shadow(0 0 6px rgba(0,212,170,0.5))' }} />
          </div>
          <div>
            <h1 className="text-xl font-bold" style={{ color: 'var(--text-main)', letterSpacing: '-0.02em' }}>
              {ar ? 'بوت الشبكات الديناميكي' : 'Dynamic Grid Bot'}
            </h1>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {ar ? 'شبكة الذكاء الاصطناعي الديناميكية' : 'AI-Powered Dynamic Grid'}
            </p>
          </div>
        </div>

        {/* Info banner */}
        <div
          className="flex items-start gap-2 rounded-2xl p-3 mt-3"
          style={{ background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.2)' }}
        >
          <Info size={14} className="shrink-0 mt-0.5" style={{ color: '#60A5FA' }} />
          <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            {ar
              ? 'هذا القسم تجريبي — بوت الشبكات قيد التطوير ولا ينفذ صفقات حقيقية حالياً.'
              : 'This section is experimental — the Grid Bot is under development and does not execute real trades yet.'}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div
        className="flex rounded-2xl overflow-hidden"
        style={{ background: 'var(--bg-input)', border: '1px solid var(--border)' }}
      >
        {tabs.map(({ key, label, icon: Icon }, i) => {
          const isActive = activeTab === key;
          return (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className="flex-1 flex flex-col items-center justify-center gap-1 py-3 transition-all duration-200 relative"
              style={{
                color: isActive ? 'var(--accent)' : 'var(--text-muted)',
                background: isActive ? 'rgba(0,212,170,0.1)' : 'transparent',
                borderRight: i < tabs.length - 1 ? '1px solid var(--border)' : 'none',
              }}
            >
              {isActive && (
                <span
                  className="absolute bottom-0 left-1/2 -translate-x-1/2 w-8 h-0.5 rounded-full"
                  style={{ background: 'var(--accent)' }}
                />
              )}
              <Icon
                size={16}
                strokeWidth={isActive ? 2.5 : 1.8}
                style={{ filter: isActive ? 'drop-shadow(0 0 4px rgba(0,212,170,0.5))' : 'none' }}
              />
              <span className="text-[10px] font-bold leading-none" style={{ fontWeight: isActive ? 800 : 600 }}>
                {label}
              </span>
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div key={activeTab} className="animate-fade-up">
        {activeTab === 'summary' && <SummaryTab lang={lang} />}
        {activeTab === 'guide'   && <GuideTab   lang={lang} />}
        {activeTab === 'params'  && <ParamsTab  lang={lang} />}
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 gap-3">
        {[
          { label: ar ? 'إجمالي الربح' : 'Total Profit',   value: '—',   color: '#00D4AA', icon: TrendingUp },
          { label: ar ? 'عدد الشبكات' : 'Grid Count',      value: '—',   color: '#60A5FA', icon: Grid3x3 },
          { label: ar ? 'ربح الشبكة' : 'Grid Profit',      value: '—',   color: '#A78BFA', icon: Zap },
          { label: ar ? 'العائد السنوي' : 'Annual Return',  value: '—',   color: '#FB923C', icon: BarChart2 },
        ].map(({ label, value, color, icon: Icon }) => (
          <div
            key={label}
            className="rounded-2xl p-4 flex flex-col gap-2"
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              boxShadow: 'var(--shadow-card)',
            }}
          >
            <div className="flex items-center gap-2">
              <span
                className="w-7 h-7 rounded-xl flex items-center justify-center"
                style={{ background: `${color}18`, border: `1px solid ${color}33` }}
              >
                <Icon size={13} style={{ color }} />
              </span>
              <span className="text-[11px] font-bold uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
                {label}
              </span>
            </div>
            <span className="num font-bold text-xl" style={{ color: 'var(--text-main)' }}>{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
