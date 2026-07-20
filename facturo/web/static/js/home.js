// ── HOME ────────────────────────────────────────────────
// Row rendering reuses factureStatut, statutCell, factureActions and
// renderHistoryOptions from history.js; they are only called at render time,
// after every <script> has loaded.

function renderHome() {
  const nc = state.clients.length;
  const nf = state.factures.length;
  if (state.homeFilters.client && !state.clients.some(c => String(c.id) === state.homeFilters.client)) {
    state.homeFilters = { ...state.homeFilters, client: '' };
  }
  return `<div class="page">
    <div class="quick-action">
      <h3>Nouvelle facture</h3>
      <p>Sélectionnez un client, ajoutez les billets et générez le fichier Excel en un clic.</p>
      <button class="btn btn-lg" onclick="newFacture()">${icons.plus} Créer une facture</button>
    </div>
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon stat-icon-blue">${icons.users}</div>
        <div class="stat-label">Clients</div>
        <div class="stat-value">${nc}</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon stat-icon-green">${icons.file}</div>
        <div class="stat-label">Factures générées</div>
        <div class="stat-value">${nf}</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon stat-icon-amber">${icons.truck}</div>
        <div class="stat-label">Entreprise</div>
        <div class="stat-value">${esc(companyName())}</div>
      </div>
    </div>
    <div style="text-align:right; margin-top:8px">
      <button class="btn btn-ghost btn-sm" style="color:var(--red-600)" onclick="resetDatabase()">${icons.reset} Réinitialiser la base de données</button>
    </div>
    ${nf > 0 ? `
    <div class="card">
      <div class="home-recent-head">
        <h3>Dernières factures</h3>
        <div class="home-flt" role="group" aria-label="Filtrer les dernières factures">
          ${renderHomeFilterSelect('home-flt-statut', 'Statut', HOME_STATUT_OPTIONS, state.homeFilters.statut)}
          ${renderHomeFilterSelect('home-flt-client', 'Client', homeClientOptions(), state.homeFilters.client)}
          <button class="btn btn-ghost btn-sm" onclick="navigate('history')">Voir tout</button>
        </div>
      </div>
      <div id="home-recent">${renderHomeRecent()}</div>
    </div>` : ''}
  </div>`;
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
const HOME_STATUT_OPTIONS = [['', 'Toutes'], ['non_payee', 'Non payées']];

state.homeFilters = { statut: '', client: '' };

function homeClientOptions() {
  const clients = [...state.clients].sort((a, b) => (a.nom || '').localeCompare(b.nom || '', 'fr'));
  return [['', 'Tous les clients'], ...clients.map(c => [String(c.id), c.nom])];
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
      <p>Aucune facture pour ces filtres.</p>
    </div>`;
  }
  return `<table class="data-table">
    <thead><tr><th>N°</th><th>Client</th><th>Date</th><th>Statut</th><th><span class="sr-only">Actions</span></th></tr></thead>
    <tbody>
      ${rows.map(f => `
        <tr data-facture-id="${Number(f.id)}">
          <td><span class="badge badge-blue">${esc(f.numero)}</span></td>
          <td>${esc(f.client_nom)}</td>
          <td class="flt-date-cell">${esc(formatDate(f.date))}</td>
          ${statutCell(f)}
          ${factureActions(f)}
        </tr>
      `).join('')}
    </tbody>
  </table>`;
}

function homeOnFilterChange() {
  const val = id => { const el = document.getElementById(id); return el ? el.value : ''; };
  const client = val('home-flt-client');
  state.homeFilters = {
    statut: val('home-flt-statut') === 'non_payee' ? 'non_payee' : '',
    client: /^\d+$/.test(client) ? client : '',
  };
  const region = document.getElementById('home-recent');
  if (region) region.innerHTML = renderHomeRecent();
}
