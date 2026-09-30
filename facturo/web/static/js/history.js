// ── HISTORY ─────────────────────────────────────────────
//
// Filter toolbar over state.factures (client-side; a invoice is "payée" only when all its billets are covered, else "partielle" or "non payée").
// Filter state lives in state.histFilters (survives tab switches) and is
// mirrored in the URL hash as #history?q=..&client=..&statut=..&du=..&au=..&tri=..
// (non-default keys only) so reloads and back/forward restore the same view.

/** @typedef {{q: string, client: string, statut: string, du: string, au: string, tri: string}} HistFilters */

/** @type {Readonly<HistFilters>} */
const HIST_DEFAULTS = Object.freeze({ q: '', client: '', statut: '', du: '', au: '', tri: 'date_desc' });
const HIST_KEYS = ['q', 'client', 'statut', 'du', 'au', 'tri'];
const HIST_STATUTS = ['payee', 'non_payee', 'partielle'];
const HIST_TRIS = ['date_desc', 'date_asc', 'montant_desc'];
const HIST_QUERY_MAX = 200;
const HIST_SEARCH_DEBOUNCE_MS = 150;
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

// Shape AND calendar validity: '2026-99-99' passes the regex but a date input
// cannot display it, which would leave an invisible filter active.
function isIsoDate(s) {
  if (!ISO_DATE_RE.test(s)) return false;
  const [y, m, d] = s.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

state.histFilters = { ...HIST_DEFAULTS };
let histQueryTimer = null;

// ── Pure helpers ────────────────────────────────────────

/**
 * Payment status as the list shows it. Mirrors invoice_list.statut_paiement,
 * but reads the live `paye` flag so a chip toggle is reflected without a reload.
 * @returns {'payee'|'partielle'|'non_payee'}
 */
function factureStatut(f) {
  if (f.paye) return 'payee';
  const n = f.nb_billets || 0;
  const p = f.nb_billets_payes || 0;
  return p > 0 && p < n ? 'partielle' : 'non_payee';
}

/**
 * Coerce untrusted input (hash, controls) into a valid filter object.
 * @param {Partial<Record<keyof HistFilters, unknown>>} raw
 * @returns {HistFilters}
 */
function sanitizeHistFilters(raw) {
  const str = v => (typeof v === 'string' ? v.trim() : '');
  const client = str(raw.client);
  const statut = str(raw.statut);
  const tri = str(raw.tri);
  const du = str(raw.du);
  const au = str(raw.au);
  return {
    q: (typeof raw.q === 'string' ? raw.q : '').slice(0, HIST_QUERY_MAX),
    client: /^\d+$/.test(client) ? client : '',
    statut: HIST_STATUTS.includes(statut) ? statut : '',
    du: isIsoDate(du) ? du : '',
    au: isIsoDate(au) ? au : '',
    tri: HIST_TRIS.includes(tri) ? tri : HIST_DEFAULTS.tri,
  };
}

/** Drop a client filter that points at a client that no longer exists. */
function withKnownClient(filters) {
  if (!filters.client) return filters;
  const exists = state.clients.some(c => String(c.id) === filters.client);
  return exists ? filters : { ...filters, client: '' };
}

function sameFilters(a, b) {
  return HIST_KEYS.every(k => a[k] === b[k]);
}

function isDefaultFilters(f) {
  return sameFilters(f, HIST_DEFAULTS);
}

/** "history" or "history?q=..&tri=.." — only non-default keys, fixed order. */
function historyHash(filters) {
  const params = new URLSearchParams();
  HIST_KEYS.forEach(k => {
    if (filters[k] !== HIST_DEFAULTS[k]) params.append(k, filters[k]);
  });
  const qs = params.toString();
  return qs ? `history?${qs}` : 'history';
}

/** Filters from a location hash, or null when the hash is not a History route. */
function parseHistoryHash(hash) {
  const m = /^#history(?:\?(.*))?$/.exec(hash || '');
  if (!m) return null;
  const params = new URLSearchParams(m[1] || '');
  const raw = {};
  HIST_KEYS.forEach(k => { if (params.has(k)) raw[k] = params.get(k); });
  return sanitizeHistFilters(raw);
}

function searchBlobOf(f) {
  return typeof f.search_blob === 'string'
    ? f.search_blob
    : `${foldKey(f.numero)} ${foldKey(f.client_nom)}`;
}

/** @returns {object[]} the invoices matching every active filter (new array). */
function filterFactures(factures, filters) {
  const q = foldKey(filters.q);
  const clientId = filters.client ? Number(filters.client) : null;
  return factures.filter(f => {
    const date = f.date || '';
    return (!q || searchBlobOf(f).includes(q))
      && (clientId === null || f.client_id === clientId)
      && (!filters.statut || factureStatut(f) === filters.statut)
      && (!filters.du || date >= filters.du)
      && (!filters.au || date <= filters.au);
  });
}

const byDateDesc = (a, b) => (b.date || '').localeCompare(a.date || '')
  || (b.cree_le || '').localeCompare(a.cree_le || '') || b.id - a.id;
const HIST_COMPARATORS = {
  date_desc: byDateDesc,
  date_asc: (a, b) => byDateDesc(b, a),
  montant_desc: (a, b) => (Number(b.total_ttc) || 0) - (Number(a.total_ttc) || 0) || byDateDesc(a, b),
};

/** @returns {object[]} a sorted copy; the input is left untouched. */
function sortFactures(factures, tri) {
  return [...factures].sort(HIST_COMPARATORS[tri] || byDateDesc);
}

/** Count, total and unpaid balance over the given rows, summed in cents. */
function summarizeFactures(rows) {
  const cents = f => Math.round((Number(f.total_ttc) || 0) * 100);
  const total = rows.reduce((s, f) => s + cents(f), 0);
  const unpaid = rows.reduce((s, f) => s + (factureStatut(f) === 'payee' ? 0 : cents(f)), 0);
  return { count: rows.length, total: total / 100, unpaid: unpaid / 100 };
}

function currentHistoryRows() {
  return sortFactures(filterFactures(state.factures, state.histFilters), state.histFilters.tri);
}

// ── Interaction ─────────────────────────────────────────

function readHistControls() {
  const val = id => { const el = document.getElementById(id); return el ? el.value : ''; };
  return sanitizeHistFilters({
    q: val('flt-q'), client: val('flt-client'), statut: val('flt-statut'),
    du: val('flt-du'), au: val('flt-au'), tri: val('flt-tri') || HIST_DEFAULTS.tri,
  });
}

function writeHistControls(f) {
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
  set('flt-q', f.q); set('flt-client', f.client); set('flt-statut', f.statut);
  set('flt-du', f.du); set('flt-au', f.au); set('flt-tri', f.tri);
}

/**
 * Write the filters to the URL. Discrete changes push a history entry (so Back
 * undoes them); typing replaces the current one instead of one entry per word.
 */
function commitHistoryHash(push) {
  const target = `#${historyHash(state.histFilters)}`;
  if (location.hash === target) return;
  if (push) history.pushState(null, '', target);
  else history.replaceState(null, '', target);
}

/** Re-render only the results region, so the search box keeps focus and caret. */
function refreshHistoryResults() {
  const results = document.getElementById('hist-results');
  if (results) { results.innerHTML = renderHistoryResults(); bindHistoryRows(); }
  const reset = document.getElementById('flt-reset');
  if (reset) reset.classList.toggle('is-idle', isDefaultFilters(state.histFilters));
}

function applyHistFilters(next, push) {
  if (sameFilters(next, state.histFilters)) return;
  state.histFilters = next;
  state.histPage = 1;
  commitHistoryHash(push);
  refreshHistoryResults();
}

function histOnQueryInput() {
  clearTimeout(histQueryTimer);
  histQueryTimer = setTimeout(() => applyHistFilters(readHistControls(), false), HIST_SEARCH_DEBOUNCE_MS);
}

function histOnControlChange() {
  // Settle any pending keystrokes first: the controls are read as one snapshot.
  clearTimeout(histQueryTimer);
  applyHistFilters(readHistControls(), true);
}

function histResetFilters() {
  clearTimeout(histQueryTimer);
  writeHistControls(HIST_DEFAULTS);
  applyHistFilters({ ...HIST_DEFAULTS }, true);
}

/** Back/forward or a hand-edited URL: bring the view in line with the hash. */
function histOnLocationChange() {
  const parsed = parseHistoryHash(location.hash);
  if (!parsed) return;
  const next = withKnownClient(parsed);
  if (state.page !== 'history') {
    state.histFilters = next;
    navigate('history');
    return;
  }
  if (sameFilters(next, state.histFilters)) return;
  clearTimeout(histQueryTimer);
  state.histFilters = next;
  state.histPage = 1;
  writeHistControls(next);
  refreshHistoryResults();
}

window.addEventListener('popstate', histOnLocationChange);
window.addEventListener('hashchange', histOnLocationChange);

// ── Downloads ───────────────────────────────────────────

function downloadFacture(filename) {
  const a = document.createElement('a');
  // Cache-bust: invoices are overwritten in place, so a fixed URL would let the
  // browser hand back a stale cached copy of an older version of the same file.
  a.href = `/api/factures/download/${encodeURIComponent(filename)}?t=${Date.now()}`;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function downloadFacturePdf(btn, filename) {
  const origHTML = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="loading-spinner"></span> ${esc(ui.i18n.t('history.pdf_busy'))}`;
  try {
    const res = await fetch(
      `/api/factures/download-pdf/${encodeURIComponent(filename)}?t=${Date.now()}`,
      { cache: 'no-store' },
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: ui.i18n.t('error.server') }));
      throw new Error(err.detail || ui.i18n.t('history.pdf_error'));
    }
    const blob = await res.blob();
    const pdfName = filename.replace(/\.xlsx$/i, '.pdf');
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = pdfName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast(ui.i18n.t('history.pdf_done'));
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = origHTML;
  }
}
