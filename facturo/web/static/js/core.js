// Shared state, API helper, navigation, formatting and data loading.

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

const state = {
  page: 'home',
  clients: [],
  factures: [],
  scans: [],
  scansClientId: null,
  sync: null,
  pageParams: null,
  pdfAvailable: true,
  hasLogo: false,
  editingId: null,
  // The shop's own vocabulary, most used first: what Chantier and Plaque
  // autocomplete from, and what a typed value settles to when you leave it.
  knownValues: { chantier: [], plaque: [] },
  // The same values unfiltered, for the curation card in Paramètres.
  kvAll: [],
  facForm: { clientId: '', numero: '', date: new Date().toISOString().split('T')[0], remisePct: '', remiseMontant: '', remiseOpen: false },
};

function blankFacForm() {
  return { clientId: '', numero: '', date: new Date().toISOString().split('T')[0], remisePct: '', remiseMontant: '', remiseOpen: false };
}

async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  let res;
  try {
    res = await fetch(path, opts);
  } catch (e) {
    throw new Error(networkErrorMessage(e));
  }
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(errorMessage(err));
  }
  return res.json();
}

// ── Modals ──────────────────────────────────────────────
// The implementation lives in js/ui/dialog.js (role=dialog, aria-modal, labelled
// by its heading, Escape closes, Tab stays inside, focus returns to the opener).
// These globals stay for the hand-built `.modal-overlay` callers.

/**
 * Attach a built overlay to the page as an accessible modal.
 * @param {HTMLElement} overlay  the .modal-overlay element (not yet in the DOM)
 * @param {{initialFocus?: string, onClose?: Function}} [opts]
 */
function openModal(overlay, opts = {}) { ui.dialog.open(overlay, opts); }

/** Close a modal opened with openModal(); restores focus to its opener. */
function closeModal(overlay, restoreFocus = true) { ui.dialog.close(overlay, restoreFocus); }

/** Close every open modal (e.g. before navigating away). */
function closeAllModals() { ui.dialog.closeAll(); }

function toast(msg, type = 'success') {
  let container = $('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => {
    el.style.animation = 'slideIn 300ms ease-out reverse forwards';
    setTimeout(() => el.remove(), 300);
  }, 3000);
}

function navigate(page, params) {
  state.page = page;
  state.pageParams = params;
  render();
  $$('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.page === page));
  syncLocationHash(page);
}

// ── Hash routing ────────────────────────────────────────
// Only History keeps state in the URL (#history?filters, see history.js).
// Other pages clear the hash so a reload never reopens a stale History view.
// replaceState: switching tabs does not stack browser-history entries.

function syncLocationHash(page) {
  const target = page === 'history' ? `#${historyHash(state.histFilters)}` : '';
  if (location.hash === target) return;
  history.replaceState(null, '', target || location.pathname + location.search);
}

/** The page to open on load: History (with its filters) when the URL asks for it. */
function initialPage() {
  const filters = parseHistoryHash(location.hash);
  if (!filters) return 'home';
  state.histFilters = withKnownClient(filters);
  return 'history';
}

// Legacy wrapper: page code still says micon('check_circle'). The old Material
// Symbol name is mapped to a Lucide icon by lucideName() (js/icons.js).
function micon(name, fill) {
  return icon(lucideName(name), { fill: !!fill });
}

const icons = {
  home: micon('dashboard', true),
  users: micon('groups'),
  file: micon('receipt_long'),
  plus: micon('add'),
  edit: micon('edit'),
  trash: micon('delete'),
  download: micon('download'),
  pdf: micon('picture_as_pdf'),
  x: micon('close'),
  history: micon('history'),
  truck: micon('local_shipping'),
  reset: micon('warning'),
  settings: micon('settings'),
  image: micon('image'),
  upload: micon('upload'),
};

function render() {
  // The suggestion panel lives on <body>, outside the region replaced below.
  // Without this it would survive the input it is anchored to — addBillet(),
  // removeBillet() and the description-mode switch all rebuild mid-typing.
  closeAutocomplete();
  const main = $('#main-content');
  if (state.loadError && LOAD_DEPENDENT_PAGES.includes(state.page)) {
    main.innerHTML = renderLoadError();
    return;
  }
  switch (state.page) {
    case 'home':    main.innerHTML = renderHome(); break;
    case 'clients': main.innerHTML = renderClients(); break;
    case 'facture': main.innerHTML = renderFacture(); break;
    case 'history': main.innerHTML = renderHistory(); break;
    case 'scans': main.innerHTML = renderScans(); break;
    case 'payments': main.innerHTML = renderPayments(); break;
    case 'settings': main.innerHTML = renderSettings(); break;
  }
  bindEvents();
}

// ── Payment status ──────────────────────────────────────

function paidChip(f) {
  const paid = !!f.paye;
  return `<button class="status-chip ${paid ? 'is-paid' : 'is-unpaid'}"
    onclick="togglePaid(${f.id}, ${paid ? 'false' : 'true'})"
    title="${paid ? 'Marquer comme non payée' : 'Marquer comme payée'}">
    ${micon(paid ? 'check_circle' : 'radio_button_unchecked', paid)} ${paid ? 'Payée' : 'Non payée'}
  </button>`;
}

async function togglePaid(id, makePaid) {
  try {
    await api('PATCH', `/api/factures/${id}/paye`, { paye: makePaid });
    const f = state.factures.find(x => x.id === id);
    if (f) f.paye = makePaid ? 1 : 0;
    toast(makePaid ? 'Facture marquée payée' : 'Facture marquée non payée');
    render();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ── Utils ───────────────────────────────────────────────

function money(n) {
  return n.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' $';
}

function formatDate(d) {
  if (!d) return '';
  const parts = d.split('-');
  if (parts.length === 3) return `${parts[2]}-${parts[1]}-${parts[0]}`;
  return d;
}

function formatDateTime(dt) {
  if (!dt) return '';
  return dt.replace('T', ' ').slice(0, 16);
}

function bindEvents() {
  $$('.billet-input').forEach(input => {
    const handler = ev => {
      const i = parseInt(input.dataset.idx);
      const f = input.dataset.field;
      if (billets[i]) billets[i][f] = input.value;
      // Quantity, rate and a per-billet discount all change line totals, the
      // subtotal, and any percentage discounts — refresh the line net + totals.
      // Not on `change`: it fires on blur, after `input` already refreshed, and
      // rebuilding #totals-area then replaces the button being clicked, which
      // swallowed the first click on "Ajouter une remise sur toute la facture".
      if (ev.type !== 'change' && (f === 'quantite' || f === 'taux' || f === 'remise_pct' || f === 'remise_montant')) {
        syncBilletInputs();
        updateBilletNet(i);
        updateTotalsArea();
      }
      // Editing a field the AI corrected retires the note — but in place, by
      // hiding the node. Calling render() here would tear out the input the
      // user is typing into.
      if (billets[i] && billets[i].corrections && billets[i].corrections[f]) {
        delete billets[i].corrections[f];
        const note = $(`.ai-fix[data-idx="${i}"][data-field="${f}"]`);
        if (note) note.hidden = true;
      }
      // Re-check duplicate N° Billet on every keystroke in that field.
      if (f === 'numero_billet') refreshDuplicateHighlights();
      // Chantier drives the split-by-chantier preview.
      if (f === 'chantier') refreshSplitBanner();
    };
    input.addEventListener('input', handler);
    input.addEventListener('change', handler);
  });
  const facNumero = $('#fac-numero');
  const facDate = $('#fac-date');
  if (facNumero) facNumero.addEventListener('input', () => { state.facForm.numero = facNumero.value; });
  if (facDate) facDate.addEventListener('change', () => { state.facForm.date = facDate.value; });
  bindTotalsEvents();
}

async function resetDatabase() {
  const ok = await ui.alertDialog({
    title: 'Réinitialiser la base de données',
    description: 'Supprimer tous les clients et toutes les factures? Cette action est irréversible.',
    confirmLabel: 'Tout supprimer', destructive: true,
  });
  if (!ok) return;
  try {
    await api('POST', '/api/reset');
    toast('Base de données réinitialisée');
    await loadData();
    navigate('home');
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function loadData() {
  try {
    const [clients, factures, scans, known] = await Promise.all([
      api('GET', '/api/clients'),
      api('GET', '/api/factures'),
      api('GET', '/api/scans'),
      api('GET', '/api/known-values'),
    ]);
    state.clients = clients;
    state.factures = factures;
    state.scans = scans;
    // The curation card needs everything, including what is hidden or merged.
    state.kvAll = known || [];
    // The suggestions do not: hiding a value is the user saying "stop
    // offering me this", and a merged spelling has been superseded.
    const usable = (known || []).filter(v => !v.hidden && !v.alias_of);
    state.knownValues = {
      chantier: usable.filter(v => v.kind === 'chantier'),
      plaque: usable.filter(v => v.kind === 'plaque'),
    };
    state.loadError = null;
  } catch (e) {
    console.error('Erreur chargement:', e);
    // Empty arrays would read as "no data": say so loudly and keep the state
    // visible until a retry succeeds.
    state.loadError = e.message || 'Erreur';
    toast(`Chargement des données échoué : ${state.loadError}`, 'error');
  }
}

/** Retry button on the load-failed state. */
async function retryLoadData() {
  await loadData();
  render();
}

/** Full-page replacement for pages whose data did not load. */
function renderLoadError() {
  return `<div class="empty-state load-error" role="alert">
    <h3>Chargement échoué</h3>
    <p>${esc(state.loadError)}</p>
    <p>Vos données n'ont pas été modifiées, elles ne sont simplement pas affichées.</p>
    <button class="btn btn-primary" onclick="retryLoadData()">${micon('refresh')} Réessayer</button>
  </div>`;
}

const LOAD_DEPENDENT_PAGES = ['home', 'clients', 'facture', 'history', 'scans'];

async function checkCapabilities() {
  try {
    const caps = await api('GET', '/api/capabilities');
    state.pdfAvailable = caps.pdf !== false;
    state.hasLogo = caps.logo === true;
  } catch {
    state.pdfAvailable = true; // assume available; the PDF call reports its own error
  }
}

async function loadSyncStatus() {
  try {
    state.sync = await api('GET', '/api/sync/status');
  } catch (e) {
    console.warn('Statut de synchronisation indisponible:', e);
    // Keep the last known status; only a first-ever failure has nothing to show.
    state.sync = state.sync || { available: false, configured: false };
  }
}
