// ── HOME: bento blocks ──────────────────────────────────
// Hero, stat cards, chart cards, skeleton and empty state for Accueil. Pure
// template functions plus mountHomeCharts(); the page itself (filters, recent
// invoices, row menus) is in home.js. Functions are only called at render
// time, after every <script> has loaded.

function homeGreeting() {
  const h = new Date().getHours();
  return ui.i18n.t(h < 5 || h >= 18 ? 'home.greet.evening' : 'home.greet.morning');
}

function homeDateLabel() {
  // The engine has no weekday format, so ask Intl for the active locale directly.
  const locale = ui.i18n.LOCALES[ui.i18n.lang()];
  const d = new Date().toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' });
  return d.charAt(0).toUpperCase() + d.slice(1);
}

/** Numbers behind the four stat cards, computed client-side from state. */
function homeStats(factures, clients) {
  const months = ui.chartData.groupByMonth(factures, { months: 2 });
  const sum = summarizeFactures(factures);
  return {
    clients: clients.length,
    active: new Set(factures.map(f => f.client_id)).size,
    count: factures.length,
    total: sum.total,
    unpaid: sum.unpaid,
    unpaidCount: factures.filter(f => factureStatut(f) !== 'payee').length,
    prev: months[0],
    cur: months[1],
  };
}

/** {cls, icon, text} for a month-over-month change, or null when there is nothing to compare. */
function homeTrend(cur, prev, unit) {
  if (!(prev.total > 0) && !(prev.count > 0)) return null;
  const diff = unit === 'money' ? cur.total - prev.total : cur.count - prev.count;
  const base = unit === 'money' ? prev.total : prev.count;
  const t = ui.i18n.t;
  if (diff === 0) return { cls: 'trend-flat', icon: 'trending-up', text: t('home.trend.stable', { month: prev.short }) };
  const sign = diff > 0 ? '+' : '−';
  const label = unit === 'money' ? t('home.trend.pct', { sign, value: Math.round(Math.abs(diff) / base * 100) }) : `${sign}${Math.abs(diff)}`;
  return { cls: diff > 0 ? 'trend-up' : 'trend-down', icon: diff > 0 ? 'trending-up' : 'trending-down', text: t('home.trend.vs', { change: label, month: prev.short }) };
}

function renderTrend(t, fallback) {
  if (!t) return `<span class="trend trend-flat">${esc(fallback)}</span>`;
  return `<span class="trend ${t.cls}">${icon(t.icon, { size: 'xs' })}${esc(t.text)}</span>`;
}

function renderStatCard(o) {
  const shown = o.format === 'money' ? money(o.value) : String(o.value);
  return `<article class="stat spotlight">
    <div class="stat-top">
      <span class="stat-label">${esc(o.label)}</span>
      <span class="stat-ico stat-ico-${escAttr(o.tone)}" aria-hidden="true">${icon(o.icon)}</span>
    </div>
    <div class="stat-value" data-countup="${numAttr(o.value)}" data-countup-format="${escAttr(o.format)}">${esc(shown)}</div>
    <div class="stat-hint">${o.hint}</div>
  </article>`;
}

function renderHomeStats(s) {
  const { t, tn } = ui.i18n;
  return [
    renderStatCard({
      label: t('home.stat.clients'), icon: 'users', tone: 'green', format: 'int', value: s.clients,
      hint: renderTrend(null, s.clients ? t('home.hint.clients_active', { count: s.active }) : t('home.hint.no_clients')),
    }),
    renderStatCard({
      label: t('home.stat.invoices'), icon: 'receipt', tone: 'gold', format: 'int', value: s.count,
      hint: renderTrend(homeTrend(s.cur, s.prev, 'count'), s.cur.count ? tn('home.hint.invoices_in', s.cur.count, { month: s.cur.short }) : t('home.hint.no_invoices')),
    }),
    renderStatCard({
      label: t('summary.total'), icon: 'trending-up', tone: 'green', format: 'money', value: s.total,
      hint: renderTrend(homeTrend(s.cur, s.prev, 'money'), t('home.hint.all_invoices')),
    }),
    renderStatCard({
      label: t('summary.unpaid'), icon: 'clock', tone: 'gold', format: 'money', value: s.unpaid,
      hint: s.unpaidCount > 0
        ? `<span class="trend trend-warn">${icon('circle-alert', { size: 'xs' })}${esc(tn('home.hint.pending', s.unpaidCount))}</span>`
        : `<span class="trend trend-up">${icon('circle-check', { size: 'xs' })}${esc(t('home.hint.all_settled'))}</span>`,
    }),
  ].join('');
}

function renderHomeHero() {
  return `<section class="hero" aria-labelledby="home-hero-title">
    <span class="hero-tick" aria-hidden="true"></span>
    <svg class="hero-art" viewBox="0 0 260 220" aria-hidden="true" focusable="false">
      <defs>
        <pattern id="hero-dots" width="14" height="14" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1.1" fill="currentColor"/></pattern>
      </defs>
      <rect x="0" y="0" width="260" height="220" fill="url(#hero-dots)" class="hero-dots"/>
      <g transform="rotate(-7 130 112)">
        <path d="M60 34H150L188 72V190H60Z" fill="#f3f5f2"/>
        <path d="M150 34L188 72H150Z" fill="#d4a853"/>
        <g fill="#1a4d2e" opacity="0.8"><rect x="76" y="58" width="52" height="7" rx="3"/><rect x="76" y="82" width="96" height="5" rx="2.5" opacity="0.35"/><rect x="76" y="98" width="82" height="5" rx="2.5" opacity="0.35"/><rect x="76" y="114" width="90" height="5" rx="2.5" opacity="0.35"/></g>
        <rect x="76" y="146" width="96" height="26" rx="6" fill="#1a4d2e"/>
        <rect x="84" y="156" width="34" height="6" rx="3" fill="#e8c97a"/>
      </g>
      <path d="M8 200C60 208 96 180 150 190S236 196 254 170" fill="none" stroke="#e8c97a" stroke-width="2" stroke-linecap="round" stroke-dasharray="1 8" opacity="0.8"/>
    </svg>
    <div class="hero-body">
      <span class="hero-eyebrow">${esc(ui.i18n.t('home.greeting', { greeting: homeGreeting(), date: homeDateLabel() }))}</span>
      <h3 id="home-hero-title">${esc(ui.i18n.t('home.hero.title'))}</h3>
      <p>${esc(ui.i18n.t('home.hero.text'))}</p>
      <div class="hero-actions">
        <button type="button" class="btn btn-lg hero-cta" onclick="newFacture()">${icons.plus} ${esc(ui.i18n.t('action.create_invoice'))}</button>
        <button type="button" class="btn hero-link" onclick="navigate('history')">${esc(ui.i18n.t('nav.history'))} ${icon('arrow-right', { size: 'sm' })}</button>
      </div>
    </div>
  </section>`;
}

function renderChartCard(cls, id, title, desc) {
  return `<section class="bento-card ${escAttr(cls)}" aria-labelledby="${escAttr(id)}-t">
    <header class="bento-head"><div><h3 id="${escAttr(id)}-t">${esc(title)}</h3><p>${esc(desc)}</p></div></header>
    <div class="bento-chart" id="${escAttr(id)}"></div>
  </section>`;
}

function renderHomeEmpty() {
  return `<section class="bento-card bento-wide">
    <div class="empty-state home-empty">
      ${icon('receipt')}
      <h3>${esc(ui.i18n.t('home.empty.title'))}</h3>
      <p>${esc(ui.i18n.t('home.empty.text'))}</p>
      <button type="button" class="btn btn-primary" onclick="newFacture()">${icons.plus} ${esc(ui.i18n.t('action.create_invoice'))}</button>
    </div>
  </section>`;
}

/** Shimmering placeholders shown until the first data load settles. */
function renderHomeSkeleton() {
  const stat = `<div class="stat"><span class="skeleton" style="width:40%;height:0.8rem"></span><span class="skeleton" style="width:65%;height:1.9rem;margin-top:0.9rem"></span><span class="skeleton" style="width:50%;height:0.7rem;margin-top:0.9rem"></span></div>`;
  return `<div class="page page-loading home" aria-busy="true" aria-label="${escAttr(ui.i18n.t('a11y.loading'))}">
    <div class="page-head"><div><span class="skeleton" style="width:9rem;height:2rem"></span><span class="skeleton" style="width:14rem;height:0.8rem;margin-top:0.7rem"></span></div></div>
    <div class="bento">
      <div class="hero hero-skeleton"><span class="skeleton" style="width:30%;height:0.8rem"></span><span class="skeleton" style="width:70%;height:2rem;margin-top:1rem"></span><span class="skeleton" style="width:9rem;height:2.75rem;margin-top:2rem"></span></div>
      ${stat}${stat}${stat}${stat}
      <div class="bento-card bento-bar"><span class="skeleton" style="width:100%;height:14rem"></span></div>
      <div class="bento-card bento-donut"><span class="skeleton" style="width:100%;height:9rem"></span></div>
      <div class="bento-card bento-top"><span class="skeleton" style="width:100%;height:9rem"></span></div>
    </div>
  </div>`;
}

// ── Charts ──────────────────────────────────────────────

function renderHomeCharts() {
  const bar = $('#home-chart-bar');
  const donut = $('#home-chart-donut');
  const top = $('#home-chart-top');
  if (!bar || !donut || !top) return;
  const rows = state.factures;
  ui.chart.donut(donut, ui.chartData.paidSplit(rows), { title: ui.i18n.t('home.chart.split.title') });
  ui.chart.hbar(top, ui.chartData.topClients(rows, 5), { title: ui.i18n.t('home.chart.top.title'), width: top.clientWidth });
  bar.textContent = '';
  const height = Math.min(260, Math.max(200, bar.clientHeight));
  ui.chart.bar(bar, ui.chartData.groupByMonth(rows, { months: 6 }), { title: ui.i18n.t('home.chart.monthly.title'), width: bar.clientWidth, height });
}

let homeChartWidth = 0;
let homeResizeTimer = 0;
window.addEventListener('resize', () => {
  clearTimeout(homeResizeTimer);
  homeResizeTimer = setTimeout(() => {
    const bar = $('#home-chart-bar');
    if (bar && Math.abs(bar.clientWidth - homeChartWidth) > 24) { homeChartWidth = bar.clientWidth; renderHomeCharts(); }
  }, 180);
});

function mountHomeCharts() {
  const bar = $('#home-chart-bar');
  if (bar) homeChartWidth = bar.clientWidth;
  renderHomeCharts();
}
