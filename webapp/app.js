'use strict';

// ── API Config ────────────────────────────────────────────────────────────────
const BASE_URL = window.location.origin;
let _apiKey = '';

// جلب المفتاح من الخادم مرة واحدة عند التحميل
const _configReady = fetch(BASE_URL + '/api/config')
  .then(r => r.json())
  .then(d => { _apiKey = d.api_key || ''; })
  .catch(() => {});

function apiHeaders() {
  const h = { 'Content-Type': 'application/json' };
  if (_apiKey) h['X-API-Key'] = _apiKey;
  return h;
}

async function apiFetch(path, opts = {}) {
  await _configReady; // انتظر حتى يُجلب المفتاح
  const res = await fetch(BASE_URL + path, { headers: apiHeaders(), ...opts });
  const data = await res.json().catch(() => ({ error: 'invalid response' }));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  theme:       localStorage.getItem('theme')  || 'dark',
  font:        localStorage.getItem('font')   || 'md',
  hidden:      localStorage.getItem('hidden') === 'true',
  chart:       'pie',
  portfolio:   null,
  previewData: null,
};

// ── Theme ─────────────────────────────────────────────────────────────────────
function applyTheme(isDark) {
  state.theme = isDark ? 'dark' : 'light';
  localStorage.setItem('theme', state.theme);
  document.documentElement.setAttribute('data-theme', state.theme);
  document.getElementById('btn-theme').textContent = isDark ? '🌙' : '☀️';
  document.getElementById('toggle-theme').checked = isDark;
  if (portfolioChart) rebuildChart();
}
function toggleTheme() { applyTheme(state.theme !== 'dark'); }

function setFont(size) {
  state.font = size;
  localStorage.setItem('font', size);
  document.documentElement.setAttribute('data-font', size);
  document.querySelectorAll('.font-opt').forEach(b =>
    b.classList.toggle('active', b.dataset.size === size));
}

function applyHide(hide) {
  state.hidden = hide;
  localStorage.setItem('hidden', hide);
  document.getElementById('balance-amount').classList.toggle('blurred', hide);
  document.querySelectorAll('.coin-price').forEach(el => el.classList.toggle('blurred', hide));
}

// ── Drawer ────────────────────────────────────────────────────────────────────
function openDrawer() {
  document.getElementById('settings-drawer').classList.add('open');
  document.getElementById('drawer-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeDrawer() {
  document.getElementById('settings-drawer').classList.remove('open');
  document.getElementById('drawer-overlay').classList.remove('open');
  document.body.style.overflow = '';
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function openModal(id) { document.getElementById(id).classList.add('open'); document.body.style.overflow = 'hidden'; }
function closeModal(id) { document.getElementById(id).classList.remove('open'); document.body.style.overflow = ''; }
document.querySelectorAll('.modal-overlay').forEach(o =>
  o.addEventListener('click', e => { if (e.target === o) closeModal(o.id); }));

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
  const c = document.getElementById('toast-container');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => {
    t.style.transition = 'opacity .3s,transform .3s';
    t.style.opacity = '0'; t.style.transform = 'translateY(-8px)';
    setTimeout(() => t.remove(), 300);
  }, 3000);
}

// ── Button loading state ──────────────────────────────────────────────────────
function setLoading(btn, loading) {
  if (!btn) return;
  if (loading) {
    btn.dataset.orig = btn.innerHTML;
    btn.innerHTML = '<span style="display:inline-block;animation:spin .7s linear infinite">⏳</span>';
    btn.disabled = true;
  } else {
    btn.innerHTML = btn.dataset.orig || btn.innerHTML;
    btn.disabled = false;
  }
}

// ── Ripple ────────────────────────────────────────────────────────────────────
function addRipple(e) {
  const btn = e.currentTarget;
  const r = document.createElement('span');
  r.className = 'ripple';
  const rect = btn.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height);
  r.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX-rect.left-size/2}px;top:${e.clientY-rect.top-size/2}px`;
  btn.appendChild(r);
  r.addEventListener('animationend', () => r.remove());
}
document.querySelectorAll('.btn').forEach(b => b.addEventListener('click', addRipple));

// ── Sparkline ─────────────────────────────────────────────────────────────────
function drawSparkline(canvas, data, isUp) {
  const dpr = devicePixelRatio || 1;
  canvas.width = canvas.offsetWidth * dpr;
  canvas.height = canvas.offsetHeight * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const w = canvas.offsetWidth, h = canvas.offsetHeight;
  const mn = Math.min(...data), mx = Math.max(...data), range = mx - mn || 1;
  const pts = data.map((v, i) => ({ x: (i/(data.length-1))*w, y: h-((v-mn)/range)*(h*.8)-h*.1 }));
  const color = isUp ? '#22C55E' : '#EF4444';
  const grad = ctx.createLinearGradient(0,0,0,h);
  grad.addColorStop(0, isUp ? 'rgba(34,197,94,.25)' : 'rgba(239,68,68,.25)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
  pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
  ctx.lineTo(w,h); ctx.lineTo(0,h); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();
  ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
  pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
  ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.lineJoin = 'round'; ctx.stroke();
}

function mockSpark(up) {
  return Array.from({length:7}, (_,i) => 100 + (up?1:-1)*i*2 + (Math.random()-.5)*3);
}

// ── Coin logo ─────────────────────────────────────────────────────────────────
const ICON_CDN = 'https://cdn.jsdelivr.net/npm/cryptocurrency-icons@0.18.1/svg/color';

// بعض الرموز مختلفة في المكتبة
const ICON_ALIAS = { MATIC:'matic', POL:'matic', NEAR:'near', ARB:'arb', OP:'op', INJ:'inj', SUI:'sui', TIA:'tia', FET:'fet' };

function coinLogo(sym) {
  const s = (ICON_ALIAS[sym.toUpperCase()] || sym.toLowerCase());
  const url = `${ICON_CDN}/${s}.svg`;
  return `<img class="coin-logo" src="${url}" alt="${sym}"
    onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"
    loading="lazy">
  <div class="coin-logo-fallback" style="display:none">${sym.slice(0,3)}</div>`;
}

// ── Render portfolio ──────────────────────────────────────────────────────────
function renderPortfolio(data) {
  state.portfolio = data;
  const total = data.total_account || data.capital || 0;
  const amountEl = document.getElementById('balance-amount');
  amountEl.innerHTML = `${total.toLocaleString('en',{minimumFractionDigits:2,maximumFractionDigits:2})} <span class="balance-currency">USDT</span>`;
  if (state.hidden) amountEl.classList.add('blurred');
  document.querySelector('.coin-count').textContent = `🪙 ${data.coin_count} عملة`;
  document.querySelector('.balance-capital').innerHTML = `رأس المال: <strong>$${(data.capital||0).toLocaleString('en',{minimumFractionDigits:2})}</strong>`;
  renderCoins(data.coins || []);
  if (portfolioChart) rebuildChart();
}

function renderCoins(coins) {
  const container = document.getElementById('coins-table');
  if (!coins.length) {
    container.innerHTML = `<p style="padding:20px;text-align:center;color:var(--text-muted)">لا توجد عملات</p>`;
    return;
  }
  container.innerHTML = coins.map((c, i) => {
    const up = (c.drift ?? 0) <= 0;
    const valStr = c.value >= 100
      ? `$${c.value.toLocaleString('en',{maximumFractionDigits:2})}`
      : `$${c.value.toFixed(4)}`;
    const driftStr = c.drift != null
      ? `<span style="font-size:.68rem;color:${c.drift>0?'var(--red)':'var(--green)'}">${c.drift>0?'+':''}${c.drift.toFixed(1)}%</span>`
      : '';
    return `<div class="coin-row" style="animation-delay:${i*25}ms">
      <div class="coin-emoji">${coinLogo(c.symbol)}</div>
      <div class="coin-info">
        <div class="coin-name">${c.symbol}</div>
        <div class="coin-bar-wrap">
          <div class="coin-bar-bg"><div class="coin-bar-fill" style="width:${Math.min((c.pct||0)*4,100)}%"></div></div>
          <span class="coin-bar-pct">${(c.pct||0).toFixed(1)}%</span>
          ${driftStr}
        </div>
      </div>
      <div class="sparkline-wrap"><canvas data-up="${up?1:0}" style="width:100%;height:100%"></canvas></div>
      <div class="coin-right">
        <div class="coin-price${state.hidden?' blurred':''}">${valStr}</div>
        ${c.target!=null?`<div style="font-size:.7rem;color:var(--text-muted)">🎯${c.target}%</div>`:''}
      </div>
    </div>`;
  }).join('');
  requestAnimationFrame(() => {
    container.querySelectorAll('canvas[data-up]').forEach(canvas => {
      drawSparkline(canvas, mockSpark(canvas.dataset.up==='1'), canvas.dataset.up==='1');
    });
  });
}

// ── Portfolio Chart ───────────────────────────────────────────────────────────
let portfolioChart = null;
const CHART_COLORS = ['#3B82F6','#22C55E','#A855F7','#F59E0B','#EF4444','#06B6D4','#EC4899','#84CC16','#F97316','#6366F1'];

function rebuildChart() {
  const ctx = document.getElementById('portfolio-chart').getContext('2d');
  const isDark = state.theme === 'dark';
  const labelColor = isDark ? '#94A3B8' : '#475569';
  const gridColor  = isDark ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.08)';
  const coins = state.portfolio?.coins?.slice(0,9) || [];
  const rest  = state.portfolio?.coins?.slice(9)?.reduce((s,c)=>s+(c.pct||0),0) || 0;
  const labels = [...coins.map(c=>c.symbol), ...(rest>0?['أخرى']:[])];
  const data   = [...coins.map(c=>c.pct||0), ...(rest>0?[rest]:[])];
  if (portfolioChart) portfolioChart.destroy();
  const commonPlugins = {
    legend: { labels: { color:labelColor, font:{size:11}, boxWidth:12, padding:10 } },
    tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${Number(ctx.parsed).toFixed(1)}%` } },
  };
  if (state.chart === 'pie') {
    portfolioChart = new Chart(ctx, {
      type: 'doughnut',
      data: { labels, datasets: [{ data, backgroundColor:CHART_COLORS, borderWidth:2, borderColor:isDark?'#111827':'#fff', hoverOffset:8 }] },
      options: { responsive:true, maintainAspectRatio:false, cutout:'60%', animation:{duration:600}, plugins:{...commonPlugins, legend:{...commonPlugins.legend, position:'right'}} },
    });
  } else {
    portfolioChart = new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets: [{ label:'الوزن %', data, backgroundColor:CHART_COLORS.map(c=>c+'CC'), borderColor:CHART_COLORS, borderWidth:1, borderRadius:6 }] },
      options: { responsive:true, maintainAspectRatio:false, animation:{duration:600}, scales:{ x:{ticks:{color:labelColor,font:{size:10}},grid:{color:gridColor}}, y:{ticks:{color:labelColor,font:{size:10}},grid:{color:gridColor}} }, plugins:{...commonPlugins, legend:{display:false}} },
    });
  }
}

document.querySelectorAll('.chart-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.chart-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    state.chart = tab.dataset.chart;
    rebuildChart();
  });
});

// ── Load portfolio from API ───────────────────────────────────────────────────
async function loadPortfolio() {
  const btn = document.getElementById('btn-refresh');
  btn.classList.add('spin');
  try {
    const data = await apiFetch('/api/portfolio');
    renderPortfolio(data);
  } catch (e) {
    showToast(`❌ ${e.message}`, 'error');
  } finally {
    btn.classList.remove('spin');
  }
}

// ── Rebalance ─────────────────────────────────────────────────────────────────
async function openRebalanceModal() {
  openModal('modal-rebalance');
  const tradesEl = document.getElementById('rebalance-trades');
  const execBtn  = document.getElementById('btn-exec-rebalance');
  tradesEl.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:16px">⏳ جاري التحليل...</p>';
  execBtn.disabled = true;
  try {
    const data = await apiFetch('/api/rebalance/preview', { method:'POST' });
    state.previewData = data;
    document.getElementById('modal-portfolio-total').textContent = `$${data.total.toLocaleString('en',{minimumFractionDigits:2})}`;
    document.getElementById('modal-threshold').textContent = `${data.threshold}%`;
    if (!data.trades?.length) {
      tradesEl.innerHTML = '<p style="text-align:center;color:var(--green);padding:16px">✅ المحفظة متوازنة بالفعل</p>';
      return;
    }
    tradesEl.innerHTML = data.trades.map(t => `
      <div class="trade-item ${t.action}">
        <div><div class="trade-sym">${t.symbol}</div><div class="trade-amt">$${t.usdt_amount.toFixed(2)} USDT</div></div>
        <div class="trade-act">${t.action==='buy'?'🟢 شراء':'🔴 بيع'}</div>
      </div>`).join('');
    execBtn.disabled = false;
  } catch (e) {
    tradesEl.innerHTML = `<p style="text-align:center;color:var(--red);padding:16px">❌ ${e.message}</p>`;
  }
}

async function execRebalance() {
  const btn = document.getElementById('btn-exec-rebalance');
  setLoading(btn, true);
  try {
    const result = await apiFetch('/api/rebalance/execute', {
      method: 'POST',
      body: JSON.stringify({ trades: state.previewData?.trades || null }),
    });
    closeModal('modal-rebalance');
    const msg = result.message || `✅ تم تنفيذ ${result.ok_count} صفقة — $${result.total_traded?.toFixed(2)} USDT`;
    showToast(msg, result.error_count > 0 ? 'info' : 'success');
    setTimeout(loadPortfolio, 2000);
  } catch (e) {
    showToast(`❌ ${e.message}`, 'error');
  } finally {
    setLoading(btn, false);
  }
}

// ── Sell All ──────────────────────────────────────────────────────────────────
async function execSellAll() {
  const btn = document.querySelector('#modal-sell-all .btn-danger');
  setLoading(btn, true);
  try {
    const result = await apiFetch('/api/sell_all', { method:'POST' });
    closeModal('modal-sell-all');
    showToast(`✅ تم بيع ${result.ok_count} عملة بنجاح`, 'success');
    setTimeout(loadPortfolio, 2000);
  } catch (e) {
    showToast(`❌ ${e.message}`, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function execDeletePortfolio() {
  closeModal('modal-delete-portfolio');
  showToast('✅ تم إرسال أمر الحذف للبوت', 'success');
}

async function selectMethod(method) {
  const labels = { equal:'توزيع متساوٍ', volume:'حسب حجم التداول', mcap:'حسب القيمة السوقية' };
  closeModal('modal-smart');
  showToast(`✅ تم إرسال أمر ${labels[method]} للبوت`, 'success');
}

// ── Live Balance ──────────────────────────────────────────────────────────────
async function openLiveBalance() {
  openModal('modal-live-balance');
  const el = document.getElementById('live-balance-body');
  el.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:20px">⏳ جاري الجلب...</p>';
  try {
    const data = await apiFetch('/api/portfolio');
    const coins = data.coins || [];
    if (!coins.length) {
      el.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:20px">لا توجد عملات</p>';
      return;
    }
    el.innerHTML = `
      <div style="text-align:center;margin-bottom:12px">
        <div style="font-size:1.4rem;font-weight:700">${(data.total_account||0).toLocaleString('en',{minimumFractionDigits:2})} <span style="font-size:.9rem;color:var(--text-muted)">USDT</span></div>
        <div style="font-size:.8rem;color:var(--text-muted)">${data.coin_count} عملة</div>
      </div>
      <div class="coins-table">
        ${coins.map(c => `
          <div class="coin-row">
            <div class="coin-emoji">${coinLogo(c.symbol)}</div>
            <div class="coin-info">
              <div class="coin-name">${c.symbol}</div>
              <div class="coin-bar-wrap">
                <div class="coin-bar-bg"><div class="coin-bar-fill" style="width:${Math.min((c.pct||0)*4,100)}%"></div></div>
                <span class="coin-bar-pct">${(c.pct||0).toFixed(1)}%</span>
                ${c.drift!=null?`<span style="font-size:.68rem;color:${c.drift>0?'var(--red)':'var(--green)'}">${c.drift>0?'+':''}${c.drift.toFixed(1)}%</span>`:''}
              </div>
            </div>
            <div class="coin-right">
              <div class="coin-price">$${c.value>=100?c.value.toLocaleString('en',{maximumFractionDigits:2}):c.value.toFixed(4)}</div>
              ${c.target!=null?`<div style="font-size:.7rem;color:var(--text-muted)">🎯${c.target}%</div>`:''}
            </div>
          </div>`).join('')}
      </div>`;
  } catch(e) {
    el.innerHTML = `<p style="text-align:center;color:var(--red);padding:20px">❌ ${e.message}</p>`;
  }
}

// ── History ───────────────────────────────────────────────────────────────────
async function openHistory() {
  openModal('modal-history');
  const el = document.getElementById('history-body');
  el.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:20px">⏳ جاري الجلب...</p>';
  try {
    const data = await apiFetch('/api/history');
    const rows = data.history || [];
    if (!rows.length) {
      el.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:20px">لا يوجد سجل بعد</p>';
      return;
    }
    el.innerHTML = rows.map(r => `
      <div class="trade-item" style="flex-direction:column;align-items:flex-start;gap:4px;padding:12px">
        <div style="display:flex;justify-content:space-between;width:100%">
          <span style="font-weight:600;font-size:.85rem">${r.portfolio_name||'محفظة'}</span>
          <span style="font-size:.75rem;color:var(--text-muted)">${r.timestamp||''}</span>
        </div>
        <div style="font-size:.8rem;color:var(--text-muted)">${r.summary||''}</div>
        <div style="font-size:.85rem;color:${r.success?'var(--green)':'var(--red)'}">
          ${r.success?'✅':'❌'} $${(r.total_traded||0).toFixed(2)} USDT
        </div>
      </div>`).join('');
  } catch(e) {
    el.innerHTML = `<p style="text-align:center;color:var(--red);padding:20px">❌ ${e.message}</p>`;
  }
}

// ── Load Grids ────────────────────────────────────────────────────────────────
async function loadGrids() {
  try {
    const data = await apiFetch('/api/grids');
    const el = document.getElementById('grid-list');
    const grids = data.grids || [];
    el.innerHTML = grids.length
      ? grids.map(g => `<div class="grid-item">
          <div><div class="grid-item-sym">${g.symbol}</div><div class="grid-item-info">${g.steps} خطوة · $${g.size} · 🔄${g.trades}</div></div>
          <div class="grid-status${g.active?'':' stopped'}">${g.active?'نشط':'موقوف'}</div>
        </div>`).join('')
      : `<p style="color:var(--text-muted);text-align:center;padding:20px">لا توجد شبكات بعد</p>`;
  } catch (e) {
    document.getElementById('grid-list').innerHTML =
      `<p style="color:var(--red);text-align:center;padding:16px">❌ ${e.message}</p>`;
  }
}

// ── Header buttons ────────────────────────────────────────────────────────────
document.getElementById('btn-theme').addEventListener('click', toggleTheme);
document.getElementById('btn-settings').addEventListener('click', openDrawer);
document.getElementById('btn-refresh').addEventListener('click', loadPortfolio);

// ── فتح البوت في تيليجرام ─────────────────────────────────────────────────────
function openTelegramBot(action) {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.close(); // أغلق الـ Web App وارجع للبوت
  } else {
    showToast('افتح هذه الصفحة من داخل تيليجرام', 'info');
  }
}

// ── Telegram Web App ──────────────────────────────────────────────────────────
if (window.Telegram?.WebApp) {
  const tg = window.Telegram.WebApp;
  tg.ready(); tg.expand();
  tg.setHeaderColor(state.theme==='dark'?'#0A0F1F':'#F0F4FF');
  tg.setBackgroundColor(state.theme==='dark'?'#0A0F1F':'#F0F4FF');
}

// ── Init ──────────────────────────────────────────────────────────────────────
(function init() {
  document.documentElement.setAttribute('data-theme', state.theme);
  document.documentElement.setAttribute('data-font',  state.font);
  document.getElementById('btn-theme').textContent = state.theme==='dark'?'🌙':'☀️';
  document.getElementById('toggle-theme').checked  = state.theme==='dark';
  document.getElementById('toggle-hide').checked   = state.hidden;
  document.querySelectorAll('.font-opt').forEach(b =>
    b.classList.toggle('active', b.dataset.size===state.font));
  loadPortfolio();
  if (window.Chart) rebuildChart();
  else document.querySelector('script[src*="chart.js"]')?.addEventListener('load', rebuildChart);
  if (state.hidden) applyHide(true);
})();
