// ── HISTORY: view ───────────────────────────────────────
// Toolbar, summary strip, sortable table with row menus, pagination and the
// date-range presets. State, filtering and URL sync live in history.js; these
// functions only run at render time, after every <script> has loaded.

const HIST_PAGE_SIZE = 25;
const HIST_STATUT_LABELS = { payee: 'Payée', non_payee: 'Non payée', partielle: 'Partielle' };

state.histPage = 1;

/** Number of pages needed for `count` rows (at least one). */
function histPageCount(count) {
  return Math.max(1, Math.ceil(count / HIST_PAGE_SIZE));
}

/** Rows of the current page and the clamped page number. */
function histPageSlice(rows) {
  const pages = histPageCount(rows.length);
  const page = Math.min(Math.max(1, state.histPage), pages);
  state.histPage = page;
  return { page, pages, slice: rows.slice((page - 1) * HIST_PAGE_SIZE, page * HIST_PAGE_SIZE) };
}

// ── Rows ────────────────────────────────────────────────

/** Paid chip, plus "x/y billets" when the payments store reports a partial payment. */
function statutCell(f) {
  const partial = factureStatut(f) === 'partielle'
    ? `<span class="flt-partial" title="Billets payés">${Number(f.nb_billets_payes)}/${Number(f.nb_billets)} billets</span>`
    : '';
  return `<td><div class="flt-statut-cell">${paidChip(f)}${partial}</div></td>`;
}

function renderHistoryRow(f) {
  const id = Number(f.id);
  return `<tr data-facture-id="${id}">
    <td><span class="badge badge-blue">${esc(f.numero)}</span></td>
    <td><div class="cell-client">${ui.avatar(f.client_nom, { size: 'sm' })}<span class="cell-name" title="${escAttr(f.client_nom)}">${esc(f.client_nom)}</span></div></td>
    <td class="flt-date-cell" title="Créée le ${escAttr(formatDateTime(f.cree_le))}">${esc(formatDate(f.date))}</td>
    <td class="flt-amount">${money(Number(f.total_ttc) || 0)}</td>
    ${statutCell(f)}
    <td class="flt-actions">
      <button type="button" class="btn btn-quiet btn-sm flt-edit" aria-label="Modifier la facture ${escAttr(f.numero)}" onclick="editFacture(${id})">${icon('pencil', { size: 'sm' })}<span class="flt-btn-label">Modifier</span></button>
      <button type="button" class="btn btn-quiet btn-icon btn-sm" data-row-menu="${id}" aria-label="Actions de la facture ${escAttr(f.numero)}">${icon('ellipsis')}</button>
    </td>
  </tr>`;
}

/** Sortable header: a real button, aria-sort on the th, the sort itself lives in #flt-tri. */
function histSortHeader(label, desc, asc, extraClass) {
  const tri = state.histFilters.tri;
  const dir = tri === desc ? 'descending' : tri === asc ? 'ascending' : 'none';
  const glyph = dir === 'descending' ? 'chevron-down' : dir === 'ascending' ? 'chevron-up' : 'chevrons-up-down';
  // Date flips between newest and oldest first; Montant toggles back to the default order.
  const next = tri === desc ? (asc || HIST_DEFAULTS.tri) : desc;
  return `<th class="${escAttr(extraClass)}" aria-sort="${dir}">
    <button type="button" class="flt-sort${dir === 'none' ? '' : ' is-sorted'}" data-sort="${escAttr(next)}" onclick="histSortBy(this.dataset.sort)">${esc(label)}${icon(glyph, { size: 'xs' })}</button>
  </th>`;
}

function renderHistoryTable(slice) {
  return `<div class="flt-scroll"><table class="data-table flt-table">
    <thead><tr>
      <th>N° Facture</th>
      <th>Client</th>
      ${histSortHeader('Date', 'date_desc', 'date_asc', '')}
      ${histSortHeader('Montant', 'montant_desc', '', 'flt-amount')}
      <th>Statut</th>
      <th><span class="sr-only">Actions</span></th>
    </tr></thead>
    <tbody>${slice.map(renderHistoryRow).join('')}</tbody>
  </table></div>`;
}

// ── Summary, empty state, pagination ────────────────────

function renderHistorySummary(rows) {
  const s = summarizeFactures(rows);
  const owed = s.unpaid > 0;
  return `<div class="flt-summary" role="status" aria-live="polite"
      data-count="${s.count}" data-total="${s.total.toFixed(2)}" data-unpaid="${s.unpaid.toFixed(2)}">
    <span class="flt-summary-item"><span class="flt-summary-label">Factures</span><strong>${s.count}</strong></span>
    <span class="flt-summary-item"><span class="flt-summary-label">Total facturé</span><strong class="flt-num">${money(s.total)}</strong></span>
    <span class="flt-summary-item${owed ? ' is-owed' : ''}"><span class="flt-summary-label">Solde impayé</span><strong class="flt-num">${money(s.unpaid)}</strong></span>
  </div>`;
}

function renderHistoryEmpty() {
  return `<div class="flt-empty">
    ${icon('search-x')}
    <h3>Aucune facture ne correspond</h3>
    <p>Modifiez la recherche ou les filtres pour élargir les résultats.</p>
    <button type="button" class="btn btn-outline btn-sm" onclick="histResetFilters()">${icon('rotate-ccw', { size: 'sm' })} Réinitialiser les filtres</button>
  </div>`;
}

function renderHistoryPager(total, page, pages) {
  if (pages <= 1) return '';
  const from = (page - 1) * HIST_PAGE_SIZE + 1;
  const to = Math.min(total, page * HIST_PAGE_SIZE);
  const btn = (label, target, glyph, disabled) =>
    `<button type="button" class="btn btn-outline btn-sm" ${disabled ? 'disabled' : ''} onclick="histGoPage(${target})">${glyph === 'chevron-left' ? icon(glyph, { size: 'sm' }) : ''}${label}${glyph === 'chevron-right' ? icon(glyph, { size: 'sm' }) : ''}</button>`;
  return `<nav class="flt-pager" aria-label="Pagination">
    <span class="flt-pager-info">${from}–${to} sur ${total}</span>
    <span class="flt-pager-ctl">
      ${btn('Précédent', page - 1, 'chevron-left', page <= 1)}
      <span class="flt-pager-page" aria-current="page">Page ${page} / ${pages}</span>
      ${btn('Suivant', page + 1, 'chevron-right', page >= pages)}
    </span>
  </nav>`;
}

function renderHistoryResults() {
  const rows = currentHistoryRows();
  const { page, pages, slice } = histPageSlice(rows);
  const body = rows.length === 0
    ? renderHistoryEmpty()
    : `${renderHistoryTable(slice)}${renderHistoryPager(rows.length, page, pages)}`;
  return `${renderHistorySummary(rows)}<div class="card flt-card">${body}</div>`;
}

// ── Toolbar ─────────────────────────────────────────────

function renderHistoryOptions(options, selected) {
  return options.map(([value, label]) =>
    `<option value="${escAttr(value)}"${value === selected ? ' selected' : ''}>${esc(label)}</option>`).join('');
}

function renderHistoryToolbar(f) {
  const clients = [...state.clients].sort((a, b) => (a.nom || '').localeCompare(b.nom || '', 'fr'));
  const clientOptions = [['', 'Tous les clients'], ...clients.map(c => [String(c.id), c.nom])];
  const statutOptions = [['', 'Toutes'], ['payee', 'Payées'], ['non_payee', 'Non payées'], ['partielle', 'Partiellement payées']];
  const triOptions = [['date_desc', 'Date (récentes)'], ['date_asc', 'Date (anciennes)'], ['montant_desc', 'Montant (décroissant)']];
  return `<form class="flt-bar" role="search" aria-label="Filtrer les factures" onsubmit="return false">
    <div class="flt-field flt-field-search">
      <label class="flt-label" for="flt-q">Recherche</label>
      <div class="flt-search">
        ${icon('search')}
        <input id="flt-q" type="search" class="form-input" value="${escAttr(f.q)}" maxlength="${HIST_QUERY_MAX}"
          placeholder="N° facture, client, chantier, plaque, N° billet…" autocomplete="off" spellcheck="false"
          oninput="histOnQueryInput()">
        <kbd class="flt-kbd" aria-hidden="true">/</kbd>
      </div>
    </div>
    <div class="flt-field">
      <label class="flt-label" for="flt-client">Client</label>
      <select id="flt-client" class="form-select" onchange="histOnControlChange()">${renderHistoryOptions(clientOptions, f.client)}</select>
    </div>
    <div class="flt-field">
      <label class="flt-label" for="flt-statut">Statut</label>
      <select id="flt-statut" class="form-select" onchange="histOnControlChange()">${renderHistoryOptions(statutOptions, f.statut)}</select>
    </div>
    <div class="flt-field flt-field-range">
      <span class="flt-label" id="flt-range-label">Période</span>
      <div class="flt-range" role="group" aria-labelledby="flt-range-label">
        <label class="sr-only" for="flt-du">Du</label>
        <input id="flt-du" type="date" class="form-input" value="${escAttr(f.du)}" oninput="histOnControlChange()">
        <span class="flt-range-sep" aria-hidden="true">${icon('arrow-right', { size: 'xs' })}</span>
        <label class="sr-only" for="flt-au">Au</label>
        <input id="flt-au" type="date" class="form-input" value="${escAttr(f.au)}" oninput="histOnControlChange()">
        <button type="button" id="flt-presets" class="btn btn-outline btn-icon flt-presets" onclick="histOpenPresets(this)" aria-haspopup="dialog" aria-label="Périodes prédéfinies" title="Périodes prédéfinies">${icon('calendar')}</button>
      </div>
    </div>
    <div class="flt-field">
      <label class="flt-label" for="flt-tri">Trier par</label>
      <select id="flt-tri" class="form-select" onchange="histOnControlChange()">${renderHistoryOptions(triOptions, f.tri)}</select>
    </div>
    <button type="button" id="flt-reset" class="btn btn-ghost btn-sm flt-reset${isDefaultFilters(f) ? ' is-idle' : ''}"
      onclick="histResetFilters()">${icon('rotate-ccw', { size: 'sm' })} Réinitialiser</button>
  </form>`;
}

// ── Page ────────────────────────────────────────────────

function renderHistory() {
  const head = `<div class="page-head">
      <div>
        <h2>Historique</h2>
        <p>Toutes les factures générées, avec recherche, filtres et actions rapides</p>
      </div>
      <div class="page-head-actions">
        <button type="button" class="btn btn-primary" onclick="newFacture()">${icons.plus} Nouvelle facture</button>
      </div>
    </div>`;
  if (state.factures.length === 0) {
    return `<div class="page page-wide history">${head}
      <div class="card"><div class="empty-state">
        ${icon('receipt')}
        <h3>Aucune facture</h3>
        <p>Les factures générées apparaîtront ici, avec leur statut de paiement.</p>
        <button type="button" class="btn btn-primary" onclick="newFacture()">${icons.plus} Créer une facture</button>
      </div></div>
    </div>`;
  }
  state.histFilters = withKnownClient(state.histFilters);
  return `<div class="page page-wide history">${head}
    ${renderHistoryToolbar(state.histFilters)}
    <div id="hist-results" class="flt-results">${renderHistoryResults()}</div>
  </div>`;
}
