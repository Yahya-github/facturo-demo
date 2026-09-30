// ── HOME ────────────────────────────────────────────────
// Row rendering reuses factureStatut, statutCell, factureActions and
// renderHistoryOptions from history.js; they are only called at render time,
// after every <script> has loaded.

function renderHome() {
  if (!state.loaded) return renderHomeSkeleton();
  const nf = state.factures.length;
  if (state.homeFilters.client && !state.clients.some(c => String(c.id) === state.homeFilters.client)) {
    state.homeFilters = { ...state.homeFilters, client: '' };
  }
  const stats = homeStats(state.factures, state.clients);
  return `<div class="page home">
    <div class="page-head">
      <div>
        <h2>${esc(ui.i18n.t('nav.home'))}</h2>
        <p>${esc(ui.i18n.t('home.subtitle', { company: companyName() }))}</p>
      </div>
    </div>
    <div class="bento">
      ${renderHomeHero()}
      ${renderHomeStats(stats)}
      ${nf === 0 ? renderHomeEmpty() : `
        ${renderChartCard('bento-bar', 'home-chart-bar', ui.i18n.t('home.chart.monthly.title'), ui.i18n.t('home.chart.monthly.desc'))}
        ${renderChartCard('bento-donut', 'home-chart-donut', ui.i18n.t('home.chart.split.title'), ui.i18n.t('home.chart.split.desc'))}
        ${renderChartCard('bento-top', 'home-chart-top', ui.i18n.t('home.chart.top.title'), ui.i18n.t('home.chart.top.desc'))}
        <section class="bento-card bento-wide" aria-labelledby="home-recent-title">
          <header class="bento-head home-recent-head">
            <div><h3 id="home-recent-title">${esc(ui.i18n.t('home.recent.title'))}</h3><p>${esc(ui.i18n.t('home.recent.desc'))}</p></div>
            <div class="home-flt" role="group" aria-label="${escAttr(ui.i18n.t('home.recent.filter'))}">
              ${renderHomeFilterSelect('home-flt-statut', ui.i18n.t('col.status'), homeStatutOptions(), state.homeFilters.statut)}
              ${renderHomeFilterSelect('home-flt-client', ui.i18n.t('col.client'), homeClientOptions(), state.homeFilters.client)}
              <button class="btn btn-outline btn-sm" onclick="navigate('history')">${esc(ui.i18n.t('home.view_all'))} ${icon('arrow-right', { size: 'xs' })}</button>
            </div>
          </header>
          <div id="home-recent">${renderHomeRecent()}</div>
        </section>`}
    </div>
  </div>`;
}

/** Called by render() right after the page markup is in the DOM. */
function mountHome() {
  if (!state.loaded || state.factures.length === 0) return;
  mountHomeCharts();
  bindHomeRows();
  bindHomeContextMenu();
}

// ── Home quick filters ──────────────────────────────────
// Filter the whole list first, then keep the latest few — so "Client X" shows
// that client's latest invoices, not whichever of the global top 5 are theirs.

/** Company name set server-side (facturo.brand) in the page's company-name meta tag. */
function companyName() {
  const meta = document.querySelector('meta[name="company-name"]');
  return meta ? meta.getAttribute('content') : '';
}

const HOME_RECENT_LIMIT = 5;
// "Non payées" here means "still owes money": partially paid invoices included.
const homeStatutOptions = () => [['', ui.i18n.t('filter.all')], ['non_payee', ui.i18n.t('filter.unpaid')]];

state.homeFilters = { statut: '', client: '' };

function homeClientOptions() {
  const clients = [...state.clients].sort((a, b) => (a.nom || '').localeCompare(b.nom || '', ui.i18n.lang()));
  return [['', ui.i18n.t('filter.all_clients')], ...clients.map(c => [String(c.id), c.nom])];
}

function renderHomeFilterSelect(id, label, options, selected) {
  return `<label class="home-flt-field" for="${id}">
    <span class="home-flt-label">${esc(label)}</span>
    <select id="${id}" class="form-select" onchange="homeOnFilterChange()">${renderHistoryOptions(options, selected)}</select>
  </label>`;
}

/** @returns {object[]} the latest invoices matching the home quick filters (new array). */
function homeRecentFactures(factures, filters) {
  const clientId = filters.client ? Number(filters.client) : null;
  return factures
    .filter(f => (clientId === null || f.client_id === clientId)
      && (filters.statut !== 'non_payee' || factureStatut(f) !== 'payee'))
    .slice(0, HOME_RECENT_LIMIT);
}

function renderHomeRecent() {
  const rows = homeRecentFactures(state.factures, state.homeFilters);
  if (rows.length === 0) {
    return `<div class="flt-empty flt-empty-compact">
      ${micon('search_off')}
      <p>${esc(ui.i18n.t('home.recent.empty'))}</p>
    </div>`;
  }
  return `<div class="table-scroll"><table class="data-table home-table">
    <thead><tr><th>${esc(ui.i18n.t('col.number'))}</th><th>${esc(ui.i18n.t('col.client'))}</th><th class="hide-sm hide-md">${esc(ui.i18n.t('col.date'))}</th><th class="num">${esc(ui.i18n.t('col.amount'))}</th><th>${esc(ui.i18n.t('col.status'))}</th><th><span class="sr-only">${esc(ui.i18n.t('col.actions'))}</span></th></tr></thead>
    <tbody>
      ${rows.map(f => `
        <tr data-facture-id="${Number(f.id)}">
          <td><span class="badge badge-blue">${esc(f.numero)}</span></td>
          <td><div class="cell-client"><span class="avatar avatar-sm" aria-hidden="true">${esc(ui.shell.initials(f.client_nom))}</span><span class="cell-name" title="${escAttr(f.client_nom)}">${esc(f.client_nom)}</span></div></td>
          <td class="flt-date-cell hide-sm hide-md">${esc(formatDate(f.date))}</td>
          <td class="num">${money(Number(f.total_ttc) || 0)}</td>
          ${statutCell(f)}
          <td class="row-menu-cell"><button type="button" class="btn btn-ghost btn-icon btn-sm" data-row-menu="${Number(f.id)}" aria-label="${escAttr(ui.i18n.t('invoice.actions', { number: f.numero }))}">${icon('ellipsis')}</button></td>
        </tr>
      `).join('')}
    </tbody>
  </table></div>`;
}

/** Row actions shared by the "..." button and the right-click menu. */
function homeRowItems(f) {
  return [
    { label: ui.i18n.t('action.edit'), icon: 'pencil', onSelect: () => editFacture(f.id) },
    { label: ui.i18n.t('action.download_excel'), icon: 'download', onSelect: () => downloadFacture(f.fichier) },
    { label: ui.i18n.t('action.download_pdf'), icon: 'file-text', onSelect: () => downloadFacturePdf(document.createElement('button'), f.fichier) },
    { separator: true },
    { label: ui.i18n.t(f.paye ? 'action.mark_unpaid' : 'action.mark_paid'), icon: 'circle-check', onSelect: () => togglePaid(f.id, !f.paye) },
  ];
}

const homeFactureById = id => state.factures.find(f => f.id === Number(id));

/** (Re)attach the "..." menus; called after every rebuild of #home-recent. */
function bindHomeRows() {
  $$('#home-recent [data-row-menu]').forEach(btn => {
    ui.menu.attach(btn, () => {
      const f = homeFactureById(btn.dataset.rowMenu);
      return f ? homeRowItems(f) : [];
    });
  });
}

function bindHomeContextMenu() {
  const region = $('#home-recent');
  if (!region) return;
  ui.contextMenu.attach(region, 'tr[data-facture-id]', row => {
    const f = homeFactureById(row.dataset.factureId);
    return f ? homeRowItems(f) : null;
  });
}

function homeOnFilterChange() {
  const val = id => { const el = document.getElementById(id); return el ? el.value : ''; };
  const client = val('home-flt-client');
  state.homeFilters = {
    statut: val('home-flt-statut') === 'non_payee' ? 'non_payee' : '',
    client: /^\d+$/.test(client) ? client : '',
  };
  const region = document.getElementById('home-recent');
  if (region) { region.innerHTML = renderHomeRecent(); bindHomeRows(); }
}
