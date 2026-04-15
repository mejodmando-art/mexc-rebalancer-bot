# AGENTS-IMPROVEMENT-SPEC.md

## Audit Summary

### What's Good ✅

**AGENTS.md**
- Covers all env vars with required/optional flags.
- `config.json` schema is accurate and complete.
- Coding conventions (type hints, logging, exception handling) are clear.
- Deployment section (Railway + Procfile) is accurate.

**UI / Design (globals.css + components)**
- Dark-first design with a coherent purple/teal palette.
- Glassmorphism cards with `backdrop-filter: blur` — consistent across all components.
- Micro-animations: `fadeUp`, `slideIn`, `ripple`, `pulseDot` — all implemented.
- Responsive: desktop sidebar + mobile bottom nav.
- RTL support (`[dir="rtl"]`) applied to sidebar, navbar, toasts, tables.
- Skeleton loaders on every data-heavy component.
- JetBrains Mono for numeric values — good for financial data readability.

---

### What's Missing ❌

**AGENTS.md**
1. **`database.py` is undocumented** — the module exists and manages SQLite (`rebalance_history`, `portfolio_snapshots`) but has no entry in Key Modules.
2. **`api/main.py` (FastAPI backend) is undocumented** — the actual entry point is now `uvicorn api.main:app`, not the CLI flags described.
3. **`grid_bot.py` is undocumented** — a Grid Bot tab exists in the UI; the module is not mentioned.
4. **`PAPER_TRADING` env var is missing** — documented in README but absent from the AGENTS.md env var table.
5. **`DISCORD_WEBHOOK_URL` env var is missing** — used in `main.py` docstring and README but not in AGENTS.md.
6. **`PORT` env var is missing** — read in `main.py` (`os.environ.get("PORT", 8000)`).
7. **Web stack is undocumented** — Next.js 14 + Tailwind + Recharts + lucide-react; build step (`npm run build`) is not mentioned.
8. **No automated tests** — acknowledged but no plan to add them.
9. **`nixpacks.toml` and `railway.json`** — deployment config files exist but are not mentioned.

**UI / Design**
1. **No 3D depth on cards** — cards use flat `box-shadow` only; no `perspective`, `transform: rotateX/Y`, or layered depth illusion.
2. **No ambient particle / mesh background** — the grid overlay (`::before`) is very subtle; no animated depth layer.
3. **Donut chart has no 3D extrusion** — pure SVG flat arcs; no depth ring or shadow layer.
4. **Stat cards lack a "floating" feel** — hover only lifts `translateY(-2px)`; no perspective tilt on hover.
5. **No gradient mesh on hero/header area** — the radial gradients on `body` are static; no animated gradient shift.
6. **Light mode is incomplete** — CSS variables for `.light` are defined in `tailwind.config.js` but `globals.css` only defines `:root` (dark) and `.dark`; light mode variables are never applied.
7. **Color inconsistency** — `tailwind.config.js` defines `accent: #00D4AA` but `globals.css` uses `--accent-purple: #7B5CF5` as the dominant color; the two systems diverge.
8. **No loading shimmer on charts** — `PortfolioPieChart` and `PerformanceChart` have skeleton divs but no animated gradient shimmer matching the card style.
9. **Mobile bottom nav icons lack 3D badge** — active state uses `translateY(-2px) scale(1.06)` but no layered shadow depth.

---

### What's Wrong ⚠️

**AGENTS.md**
1. **Entry point is wrong** — AGENTS.md says `python main.py --telegram` starts Telegram mode; actual `main.py` only runs `uvicorn api.main:app`. The `--telegram`, `--rebalance-now`, `--status`, `--setup` CLI flags no longer exist.
2. **`telegram_bot.py` description is stale** — says "runs rebalancer loop in background thread"; the actual architecture runs everything through FastAPI with the Telegram bot started from `api/main.py`.
3. **`smart_portfolio.py` `run` function** — described as the main loop but the actual entry is now the FastAPI lifespan/startup event.

**UI / Design**
1. **`tailwind.config.js` colors are unused** — `base`, `card`, `input`, `border`, `primary`, `secondary` Tailwind color tokens are defined but all components use inline `style={{}}` with hardcoded hex values or CSS variables. The Tailwind color system is effectively dead.
2. **`card-hover` class is referenced in `StatCard.tsx`** but never defined in `globals.css` — this is a silent no-op.
3. **`hero-card` class** is defined in `globals.css` but never used in any component.
4. **Duplicate animation definitions** — `shimmer`, `fadeUp`, `fadeIn`, `pulseDot` are defined in both `tailwind.config.js` (keyframes) and `globals.css` (raw CSS). The Tailwind versions are never used.

---

## Improvement Spec

### Part 1 — AGENTS.md Corrections

#### 1.1 Fix the entry point section

Replace the "Running the Bot" section with:

```bash
# Install Python dependencies
pip install -r requirements.txt

# Build the web UI (required for production)
cd web && npm install && npm run build && cp -r out/* ../static/ && cd ..

# Start the server (API + Telegram bot + web UI)
python main.py
# or directly:
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Remove all references to `--telegram`, `--rebalance-now`, `--status`, `--setup` flags — they no longer exist.

#### 1.2 Add missing env vars

| Variable              | Required | Purpose                                         |
|-----------------------|----------|-------------------------------------------------|
| `PAPER_TRADING`       | No       | Set `true` to skip real orders (dry-run mode)   |
| `DISCORD_WEBHOOK_URL` | No       | Discord webhook for trade notifications         |
| `PORT`                | No       | HTTP port for uvicorn (default: 8000)           |

#### 1.3 Add missing Key Modules

**`api/main.py` — FastAPI Application**
- Mounts the Next.js static build at `/`.
- REST endpoints: `GET /api/status`, `POST /api/rebalance`, `GET /api/history`, `GET /api/portfolios`, etc.
- Starts the Telegram bot (if `TELEGRAM_BOT_TOKEN` is set) in a background thread on startup.
- Starts the rebalancer loop per portfolio in background threads.

**`database.py` — SQLite Layer**
- Tables: `rebalance_history` (trade log), `portfolio_snapshots` (time-series for charts).
- Functions: `init_db`, `log_rebalance`, `get_history`, `save_snapshot`, `get_snapshots`.

**`grid_bot.py` — Grid Trading Bot**
- Implements a grid strategy: places buy/sell limit orders at fixed price intervals.
- Configurable via the Grid Bot tab in the web UI.

#### 1.4 Add Web Stack section

```
web/                   – Next.js 14 frontend (TypeScript + Tailwind CSS)
  src/app/             – App Router pages (layout.tsx, page.tsx, globals.css)
  src/components/      – React components (Dashboard, Sidebar, Navbar, etc.)
  src/lib/             – API client (api.ts) + i18n translations (i18n.ts)
static/                – Next.js build output; served by FastAPI as static files
```

Build: `cd web && npm install && npm run build && cp -r out/* ../static/`

#### 1.5 Add deployment files

- `nixpacks.toml` — Railway Nixpacks build config; installs Node.js + Python, runs the web build.
- `railway.json` — Railway service config (start command, health check path).

---

### Part 2 — UI Design: Professional 3D Upgrade

The goal is a **premium dark financial dashboard** with genuine depth — layered surfaces, perspective tilt, ambient light, and motion that feels physical rather than flat.

#### 2.1 Color System — Unify and Extend

**Problem:** `tailwind.config.js` tokens and `globals.css` CSS variables are two separate systems that diverge. Components use hardcoded hex values.

**Fix:** Make CSS variables the single source of truth. Update `tailwind.config.js` to reference them:

```js
// tailwind.config.js — use CSS vars
colors: {
  base:    'var(--bg-base)',
  card:    'var(--bg-card)',
  accent:  'var(--accent)',
  profit:  'var(--profit)',
  loss:    'var(--loss)',
  // ...
}
```

**New palette — "Deep Space Finance":**

```css
:root {
  /* Backgrounds — layered depth */
  --bg-base:       #060412;          /* deepest layer */
  --bg-mid:        #0C0820;          /* mid layer */
  --bg-card:       rgba(14,9,38,0.88);
  --bg-card-hover: rgba(18,12,48,0.95);
  --bg-input:      rgba(18,12,50,0.75);
  --bg-nav:        rgba(6,3,16,0.94);
  --bg-sidebar:    rgba(8,4,20,0.98);

  /* Borders */
  --border:        rgba(120,80,255,0.16);
  --border-hover:  rgba(120,80,255,0.38);
  --border-active: rgba(120,80,255,0.60);

  /* Text */
  --text-main:     #EDE8FF;
  --text-muted:    #7A6FA6;
  --text-label:    #5A5080;

  /* Accent colors */
  --accent:        #00E5B8;          /* primary teal — profit, CTA */
  --accent-dark:   #00B894;
  --accent-purple: #8B5CF6;          /* secondary — nav, borders */
  --accent-blue:   #3B82F6;          /* tertiary — charts, info */
  --accent-pink:   #EC4899;          /* quaternary — alerts */
  --accent-gold:   #F59E0B;          /* grid bot, warnings */

  /* Semantic */
  --profit:        #00E5B8;
  --loss:          #FF6B6B;

  /* 3D depth shadows */
  --shadow-xs:     0 1px 3px rgba(0,0,0,0.4);
  --shadow-sm:     0 4px 12px rgba(0,0,0,0.5);
  --shadow-md:     0 8px 32px rgba(0,0,0,0.6), 0 2px 8px rgba(0,0,0,0.4);
  --shadow-lg:     0 16px 48px rgba(0,0,0,0.7), 0 4px 16px rgba(0,0,0,0.5);
  --shadow-glow:   0 0 32px rgba(139,92,246,0.3), 0 0 64px rgba(139,92,246,0.15);
  --shadow-teal:   0 0 24px rgba(0,229,184,0.3), 0 0 48px rgba(0,229,184,0.12);
}
```

#### 2.2 Background — Animated Depth Layer

**Problem:** Static radial gradients + a faint grid. No sense of depth or motion.

**Fix:** Three-layer background system:

```css
body {
  background-color: var(--bg-base);
  background-image:
    /* Layer 1: animated aurora blobs */
    radial-gradient(ellipse 90% 70% at 15% 5%,  rgba(139,92,246,0.22) 0%, transparent 55%),
    radial-gradient(ellipse 70% 60% at 85% 85%, rgba(236,72,153,0.14) 0%, transparent 50%),
    radial-gradient(ellipse 60% 50% at 50% 50%, rgba(0,229,184,0.08) 0%, transparent 55%);
}

/* Animated aurora — slow drift */
@keyframes auroraShift {
  0%   { background-position: 0% 0%, 100% 100%, 50% 50%; }
  33%  { background-position: 5% 10%, 95% 90%, 55% 45%; }
  66%  { background-position: -5% 5%, 105% 95%, 45% 55%; }
  100% { background-position: 0% 0%, 100% 100%, 50% 50%; }
}

/* Layer 2: perspective grid (replaces flat ::before grid) */
body::before {
  content: '';
  position: fixed; inset: 0;
  background-image:
    linear-gradient(rgba(139,92,246,0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(139,92,246,0.05) 1px, transparent 1px);
  background-size: 48px 48px;
  transform: perspective(800px) rotateX(8deg) scaleY(1.15);
  transform-origin: center bottom;
  pointer-events: none; z-index: 0;
  mask-image: linear-gradient(to bottom, transparent 0%, black 30%, black 70%, transparent 100%);
}

/* Layer 3: vignette */
body::after {
  content: '';
  position: fixed; inset: 0;
  background: radial-gradient(ellipse 100% 100% at 50% 50%, transparent 40%, rgba(6,3,16,0.7) 100%);
  pointer-events: none; z-index: 0;
}
```

#### 2.3 Cards — True 3D Depth

**Problem:** Cards are flat glassmorphism panels. No perspective, no layered light.

**Fix:** Add perspective tilt on hover + layered inset highlights:

```css
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 20px;
  box-shadow:
    var(--shadow-md),
    inset 0 1px 0 rgba(255,255,255,0.07),   /* top highlight */
    inset 0 -1px 0 rgba(0,0,0,0.3);          /* bottom shadow */
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  transition: transform 0.3s cubic-bezier(0.34,1.56,0.64,1),
              box-shadow 0.3s ease,
              border-color 0.2s ease;
  transform-style: preserve-3d;
  will-change: transform;
}

.card-hover:hover {
  border-color: var(--border-hover);
  box-shadow:
    var(--shadow-lg),
    var(--shadow-glow),
    inset 0 1px 0 rgba(255,255,255,0.1),
    inset 0 -1px 0 rgba(0,0,0,0.4);
  transform: translateY(-3px) perspective(600px) rotateX(1.5deg);
}
```

**JavaScript tilt on mouse move** (add to `StatCard.tsx`):

```tsx
// On mouse move over card: apply subtle perspective tilt
const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
  const rect = e.currentTarget.getBoundingClientRect();
  const x = (e.clientX - rect.left) / rect.width  - 0.5;  // -0.5 to 0.5
  const y = (e.clientY - rect.top)  / rect.height - 0.5;
  e.currentTarget.style.transform =
    `perspective(600px) rotateX(${-y * 6}deg) rotateY(${x * 6}deg) translateY(-3px)`;
};
const handleMouseLeave = (e: React.MouseEvent<HTMLDivElement>) => {
  e.currentTarget.style.transform = '';
};
```

#### 2.4 Stat Cards — Layered 3D Icon Badge

**Problem:** Icon container is a flat rounded square with a subtle gradient.

**Fix:** Multi-layer icon badge with depth:

```tsx
// Icon badge — 3 layers
<div style={{
  width: 40, height: 40, borderRadius: 14,
  position: 'relative',
  background: `linear-gradient(145deg, ${color}35, ${color}12)`,
  border: `1px solid ${color}40`,
  boxShadow: `
    0 6px 20px ${color}30,
    0 2px 6px rgba(0,0,0,0.4),
    inset 0 1px 0 rgba(255,255,255,0.15),
    inset 0 -1px 0 rgba(0,0,0,0.2)
  `,
}}>
  {/* Specular highlight */}
  <div style={{
    position: 'absolute', top: 1, left: 4, right: 4, height: '40%',
    background: 'linear-gradient(180deg, rgba(255,255,255,0.18) 0%, transparent 100%)',
    borderRadius: '10px 10px 50% 50%',
    pointerEvents: 'none',
  }} />
  <Icon size={17} style={{ color, filter: `drop-shadow(0 2px 6px ${color}90)` }} />
</div>
```

#### 2.5 Donut Chart — 3D Extrusion Effect

**Problem:** Flat SVG arcs with no depth.

**Fix:** Add a shadow/extrusion layer beneath the donut using a duplicate SVG layer offset by 4px:

```tsx
// In DonutChart: render two SVG layers
// Layer 1 (shadow/extrusion): same paths, darker fill, offset down
// Layer 2 (main): actual colored arcs

<div style={{ position: 'relative' }}>
  {/* Extrusion shadow layer */}
  <svg
    width={size} height={size}
    viewBox={`0 0 ${size} ${size}`}
    style={{ position: 'absolute', top: 4, left: 0, filter: 'blur(3px)', opacity: 0.5 }}
  >
    {slices.map((s, i) => (
      <path key={i} d={s.path} fill={s.color} opacity={0.4} />
    ))}
  </svg>

  {/* Main chart layer */}
  <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
    {/* Outer ring glow */}
    <circle cx={cx} cy={cy} r={outerR + 2} fill="none"
      stroke="rgba(139,92,246,0.12)" strokeWidth={6} />
    {slices.map((s, i) => (
      <path
        key={i} d={s.path} fill={s.color}
        style={{
          filter: hovered === i ? `drop-shadow(0 0 8px ${s.color}90)` : 'none',
          transition: 'filter 0.2s, opacity 0.2s',
        }}
        opacity={hovered === null || hovered === i ? 1 : 0.45}
        onMouseEnter={() => setHovered(i)}
        onMouseLeave={() => setHovered(null)}
      />
    ))}
    {/* Center: specular highlight ring */}
    <circle cx={cx} cy={cy} r={innerR - 1} fill="none"
      stroke="rgba(255,255,255,0.06)" strokeWidth={1} />
  </svg>
</div>
```

#### 2.6 Sidebar — Depth Rail

**Problem:** Sidebar is a flat dark panel.

**Fix:** Add a right-edge light bleed and active item 3D pill:

```css
.sidebar {
  background: linear-gradient(180deg,
    rgba(10,5,28,0.99) 0%,
    rgba(8,4,20,0.99) 100%);
  border-right: 1px solid rgba(120,80,255,0.14);
  box-shadow: 4px 0 32px rgba(0,0,0,0.5), inset -1px 0 0 rgba(255,255,255,0.03);
  backdrop-filter: blur(24px);
}

/* Active sidebar item — 3D pill */
.sidebar-item.active {
  background: linear-gradient(135deg, rgba(139,92,246,0.22), rgba(139,92,246,0.08));
  border: 1px solid rgba(139,92,246,0.35);
  box-shadow:
    0 4px 16px rgba(139,92,246,0.25),
    inset 0 1px 0 rgba(255,255,255,0.1),
    inset 0 -1px 0 rgba(0,0,0,0.2);
  transform: translateX(2px);
}
```

#### 2.7 Buttons — Embossed 3D Style

**Problem:** Buttons are flat gradients with a simple `translateY(-1px)` hover.

**Fix:** Add inset highlights and a pressed state that simulates physical depth:

```css
.btn-accent {
  background: linear-gradient(160deg, #9B6FFF 0%, #7B5CF5 40%, #5B3FD5 100%);
  box-shadow:
    0 6px 24px rgba(123,92,245,0.5),
    0 2px 6px rgba(0,0,0,0.4),
    inset 0 1px 0 rgba(255,255,255,0.25),   /* top specular */
    inset 0 -2px 0 rgba(0,0,0,0.25);         /* bottom depth */
  border: 1px solid rgba(255,255,255,0.12);
}
.btn-accent:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow:
    0 10px 32px rgba(123,92,245,0.65),
    0 4px 10px rgba(0,0,0,0.4),
    inset 0 1px 0 rgba(255,255,255,0.3),
    inset 0 -2px 0 rgba(0,0,0,0.3);
}
.btn-accent:active:not(:disabled) {
  transform: translateY(1px);
  box-shadow:
    0 2px 8px rgba(123,92,245,0.4),
    inset 0 2px 4px rgba(0,0,0,0.3),         /* pressed inset */
    inset 0 1px 0 rgba(255,255,255,0.1);
}
```

#### 2.8 Fix: `card-hover` Missing Class

Add to `globals.css`:

```css
.card-hover {
  cursor: default;
  transition: transform 0.3s cubic-bezier(0.34,1.56,0.64,1),
              box-shadow 0.3s ease,
              border-color 0.2s ease;
}
.card-hover:hover {
  border-color: var(--border-hover);
  box-shadow: var(--shadow-lg), var(--shadow-glow),
              inset 0 1px 0 rgba(255,255,255,0.1);
  transform: translateY(-3px) perspective(600px) rotateX(1.5deg);
}
```

#### 2.9 Fix: Light Mode Variables

Add a proper `.light` block to `globals.css` (currently only `:root` dark + `.dark` exist):

```css
.light {
  --bg-base:       #F4F1FF;
  --bg-mid:        #EDE8FF;
  --bg-card:       rgba(255,255,255,0.92);
  --bg-card-hover: rgba(255,255,255,0.98);
  --bg-input:      rgba(240,236,255,0.9);
  --bg-nav:        rgba(255,255,255,0.94);
  --bg-sidebar:    rgba(248,245,255,0.98);
  --border:        rgba(120,80,255,0.14);
  --border-hover:  rgba(120,80,255,0.32);
  --text-main:     #1A1040;
  --text-muted:    #6B5FA0;
  --text-label:    #8B7FC0;
  --shadow-md:     0 8px 32px rgba(100,60,200,0.12), 0 2px 8px rgba(0,0,0,0.06);
  --shadow-lg:     0 16px 48px rgba(100,60,200,0.18), 0 4px 16px rgba(0,0,0,0.08);
  --shadow-glow:   0 0 32px rgba(139,92,246,0.18), 0 0 64px rgba(139,92,246,0.08);
  color-scheme: light;
}
```

#### 2.10 Remove Dead Code

- Remove `hero-card` CSS class (defined but never used in any component).
- Remove duplicate keyframe definitions from `tailwind.config.js` (they are already in `globals.css`).
- Either adopt Tailwind color tokens everywhere OR remove them from `tailwind.config.js` and keep only CSS variables. Do not maintain both.

---

### Part 3 — Implementation Priority

| Priority | Item | Effort |
|----------|------|--------|
| P0 | Fix AGENTS.md entry point (wrong CLI flags) | 15 min |
| P0 | Fix `card-hover` missing class | 5 min |
| P1 | Add missing env vars to AGENTS.md | 10 min |
| P1 | Document `api/main.py`, `database.py`, `grid_bot.py` | 30 min |
| P1 | Implement 3D card hover (perspective tilt + JS mouse handler) | 1 hr |
| P1 | Implement embossed button style | 30 min |
| P1 | Fix light mode CSS variables | 20 min |
| P2 | Animated aurora background | 45 min |
| P2 | Perspective grid overlay | 30 min |
| P2 | 3D donut chart extrusion | 1 hr |
| P2 | Sidebar depth rail + active pill | 30 min |
| P3 | Unify color system (CSS vars vs Tailwind tokens) | 2 hr |
| P3 | Remove dead CSS (`hero-card`, duplicate keyframes) | 20 min |
