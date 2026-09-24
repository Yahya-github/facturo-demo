// ── PAIEMENTS ───────────────────────────────────────────
// Proofs of payment (quittances listing billets). Each billet line is matched
// against invoiced billets; an invoice whose billets are all linked is marked
// paid automatically. Bills addressed to the company itself are refused at import.

const pay = {
  list: null,          // summaries from GET /api/paiements, null until loaded
  loading: false,
  listError: null,     // message while the list failed to load (list stays null)
  listSeq: 0,          // request sequence: only the latest list load may apply
  detailSeq: 0,        // same guard for openPayment / closePayment
  detail: null,        // full payment from GET /api/paiements/{id}
  detailId: null,
  search: '',
  statut: '',          // '' | 'complet' | 'partiel' | 'a_verifier'
  importing: null,     // { done, total } while an import runs
  confirmDelete: false,
  confirmRemoveLigne: null,
  pickerFactures: [],
};

const PAY_STATUTS = {
  complet: { label: 'Complet', icon: 'task_alt' },
  partiel: { label: 'Partiel', icon: 'timelapse' },
  a_verifier: { label: 'À vérifier', icon: 'error' },
};

const LIGNE_STATUTS = {
  lie: { cls: 'status-lie', label: 'Lié', icon: 'link' },
  non_lie: { cls: 'status-a-verifier', label: 'À vérifier', icon: 'help' },
  doublon: { cls: 'status-doublon', label: 'Doublon', icon: 'content_copy' },
};

const METHODES = { numero: 'par n° de billet', date_plaque: 'par date, plaque et quantité', manuel: 'manuellement' };

function payMoney(n) {
  return n == null ? '—' : money(Number(n));
}

function payQty(n) {
  return n == null ? '—' : String(Number(n)).replace('.', ',');
}

// ── Navigation & loading ────────────────────────────────

function openPayments() {
  pay.detailId = null;
  pay.detail = null;
  pay.list = null;
  navigate('payments');
}

async function loadPayments() {
  const seq = ++pay.listSeq;
  pay.loading = true;
  pay.listError = null;
  try {
    const list = await api('GET', '/api/paiements');
    if (seq !== pay.listSeq) return; // a newer load (e.g. after an import) owns the result
    pay.list = list;
  } catch (e) {
    if (seq !== pay.listSeq) return;
    // Keep list === null: an empty array would read as "no payments imported".
    pay.list = null;
    pay.listError = e.message;
    toast(e.message, 'error');
  }
  pay.loading = false;
  if (state.page === 'payments') render();
}

function retryLoadPayments() {
  pay.listError = null;
  pay.list = null;
  render();
}

async function openPayment(id) {
  const seq = ++pay.detailSeq;
  pay.confirmDelete = false;
  pay.confirmRemoveLigne = null;
  try {
    const detail = await api('GET', `/api/paiements/${id}`);
    if (seq !== pay.detailSeq) return; // closed or replaced by another open meanwhile
    pay.detail = detail;
    pay.detailId = id;
  } catch (e) {
    if (seq !== pay.detailSeq) return;
    toast(e.message, 'error');
    pay.detailId = null;
  }
  if (state.page === 'payments') render();
}

function closePayment() {
  pay.detailSeq++; // invalidate any openPayment still in flight
  pay.detailId = null;
  pay.detail = null;
  pay.list = null;
  render();
}

// ── Page ────────────────────────────────────────────────

function renderPayments() {
  const wanted = state.pageParams && state.pageParams.paiementId;
  if (wanted) {
    state.pageParams = null;
    pay.detailId = wanted;
    pay.detail = null;
    openPayment(wanted);
  }
  const input = `<input type="file" id="payment-file-input" accept="application/pdf" multiple hidden
    onchange="importPayments(this)">`;
  if (pay.detailId != null) {
    return `<div class="page page-wide pay-page">${input}${pay.detail ? renderPaymentDetail(pay.detail) : payDetailSkeleton()}</div>`;
  }
  if (pay.list === null && !pay.loading && !pay.listError) loadPayments();
  return `<div class="page page-wide pay-page">${input}
    <header class="page-head">
      <div>
        <h2>Paiements</h2>
        <p>Preuves de paiement reçues de vos clients, rapprochées de vos billets.</p>
      </div>
    </header>
    ${importZone()}
    ${pay.listError ? payLoadError() : pay.list === null ? payListSkeleton() : renderPaymentsList()}
  </div>`;
}

// Import control: a dropzone that is also the button. Files dropped anywhere
// on it go through the same path as the file picker; progress shows per file.
function importZone() {
  if (pay.importing) {
    const { done, total } = pay.importing;
    const pct = Math.round((100 * done) / total);
    return `<div class="upzone pay-zone is-busy" id="pay-dropzone" aria-live="polite">
      <span class="upzone-icon"><span class="loading-spinner"></span></span>
      <div class="pay-zone-text">
        <strong>Import ${done + 1} sur ${total}…</strong>
        <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="Import en cours"><span style="width:${Math.max(pct, 6)}%"></span></div>
      </div>
      <button class="btn btn-primary btn-loading" id="btn-import-payment" disabled>Import…</button>
    </div>`;
  }
  return `<div class="upzone pay-zone" id="pay-dropzone">
    <span class="upzone-icon">${icon('cloud-upload')}</span>
    <div class="pay-zone-text">
      <strong>Glissez des quittances PDF ici</strong>
      <span>Chaque billet listé est retrouvé sur vos factures ; les factures entièrement couvertes passent à « Payée ».</span>
    </div>
    <button class="btn btn-primary" id="btn-import-payment"
      onclick="document.getElementById('payment-file-input').click()">${icons.upload} Importer des PDF</button>
  </div>`;
}

function importButton() {
  return `<button class="btn btn-primary" id="btn-import-payment"
    onclick="document.getElementById('payment-file-input').click()">${icons.upload} Importer des PDF</button>`;
}

function bindPaymentDrop() {
  const root = document.getElementById('main-content');
  if (!root || root.dataset.payDrop) return;
  root.dataset.payDrop = '1';
  const zoneOf = e => e.target.closest && e.target.closest('#pay-dropzone');
  const over = e => { const z = zoneOf(e); if (z) { e.preventDefault(); z.classList.add('is-dragover'); } };
  root.addEventListener('dragenter', over);
  root.addEventListener('dragover', over);
  root.addEventListener('dragleave', e => { const z = zoneOf(e); if (z && !z.contains(e.relatedTarget)) z.classList.remove('is-dragover'); });
  root.addEventListener('drop', e => {
    const z = zoneOf(e);
    if (!z) return;
    e.preventDefault();
    z.classList.remove('is-dragover');
    const files = [...(e.dataTransfer ? e.dataTransfer.files : [])].filter(f => /\.pdf$/i.test(f.name) || f.type === 'application/pdf');
    if (!files.length) { toast('Déposez des fichiers PDF', 'error'); return; }
    importPaymentFiles(files);
  });
}

function payLoadError() {
  return `<div class="card"><div class="empty-state" role="alert" id="payments-load-error">
    ${micon('error')}
    <h3>Chargement des paiements échoué</h3>
    <p>${esc(pay.listError)}</p>
    <p>Vos paiements ne sont pas perdus, ils ne sont simplement pas affichés.</p>
    <button class="btn btn-primary" style="margin-top:16px" onclick="retryLoadPayments()">${micon('refresh')} Réessayer</button>
  </div></div>`;
}

function payListSkeleton() {
  const row = `<div class="pay-skel-row"><span class="skeleton" style="width:5rem;height:.9rem"></span><span class="skeleton" style="width:38%;height:.9rem"></span><span class="skeleton" style="width:14%;height:.9rem"></span><span class="skeleton" style="width:8rem;height:.5rem"></span><span class="skeleton" style="width:5rem;height:.9rem;margin-left:auto"></span></div>`;
  return `<div class="card pay-skel" aria-busy="true" aria-label="Chargement">${row.repeat(5)}</div>`;
}

function payDetailSkeleton() {
  return `<div class="pay-skel-detail" aria-busy="true"><span class="skeleton" style="width:16rem;height:2rem"></span>
    <div class="pay-detail-grid"><div class="card pay-skel">${'<div class="pay-skel-row"><span class="skeleton" style="width:100%;height:.9rem"></span></div>'.repeat(5)}</div>
    <div class="card pay-skel"><div class="pay-skel-row"><span class="skeleton" style="width:100%;height:6rem"></span></div></div></div></div>`;
}

// ── List ────────────────────────────────────────────────

function renderPaymentsList() {
  if (pay.list.length === 0) {
    return `<div class="card" id="payments-list"><div class="empty-state">
      ${micon('payments')}
      <h3>Aucun paiement importé</h3>
      <p>Déposez la quittance PDF d'un client dans la zone ci-dessus pour commencer le rapprochement.</p>
    </div></div>`;
  }
  const counts = { '': pay.list.length };
  pay.list.forEach(p => { counts[p.statut_global] = (counts[p.statut_global] || 0) + 1; });
  const filters = [['', 'Tous'], ['a_verifier', 'À vérifier'], ['partiel', 'Partiels'], ['complet', 'Complets']];
  return `<div class="pay-toolbar">
      <label class="pay-search">${micon('search')}
        <input type="search" id="payments-search" class="form-input" placeholder="Émetteur, n° de quittance, fichier…"
          value="${escAttr(pay.search)}" oninput="filterPayments(this.value)" aria-label="Rechercher un paiement">
      </label>
      <div class="seg pay-status-seg" role="group" aria-label="Filtrer par état">
        ${filters.map(([key, label]) => `<button type="button"
          class="seg-btn pay-status-btn${pay.statut === key ? ' active' : ''}" data-statut="${key}"
          aria-pressed="${pay.statut === key}" onclick="setPaymentStatut('${key}')">${label}
          <span class="pay-count">${counts[key] || 0}</span></button>`).join('')}
      </div>
    </div>
    <div class="card card-table">
      <table class="data-table pay-table" id="payments-list">
        <thead><tr><th>Date</th><th>Émetteur</th><th>Quittance</th><th>Billets liés</th>
          <th class="num">Total</th><th>État</th></tr></thead>
        <tbody>${pay.list.map(renderPaymentRow).join('')}</tbody>
      </table>
      <p class="pay-no-match" id="payments-no-match" hidden>Aucun paiement ne correspond à cette recherche.</p>
    </div>`;
}

function paymentMatchesFilters(p) {
  if (pay.statut && p.statut_global !== pay.statut) return false;
  const q = pay.search.trim().toLowerCase();
  if (!q) return true;
  return [p.emetteur, p.reference, p.nom_original, p.date, formatDate(p.date)]
    .some(v => (v || '').toLowerCase().includes(q));
}

function renderPaymentRow(p) {
  const st = PAY_STATUTS[p.statut_global] || PAY_STATUTS.partiel;
  const pct = p.nb_lignes ? Math.round((100 * p.nb_lignes_liees) / p.nb_lignes) : 0;
  return `<tr class="payment-row" data-id="${p.id}" ${paymentMatchesFilters(p) ? '' : 'hidden'}
      onclick="openPayment(${p.id})">
    <td class="pay-date">${esc(formatDate(p.date)) || '—'}</td>
    <td class="pay-emetteur">${esc(p.emetteur) || '<span class="pay-muted">Émetteur inconnu</span>'}</td>
    <td><button type="button" class="pay-ref" onclick="event.stopPropagation(); openPayment(${p.id})"
      aria-label="Ouvrir la quittance ${escAttr(p.reference)}">${esc(p.reference) || 'Sans n°'}</button></td>
    <td><div class="pay-mini-meter pay-${p.statut_global}" data-tip="${p.nb_lignes_liees} sur ${p.nb_lignes} billets liés">
      <span class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="Billets liés"><span style="width:${pct}%"></span></span>
      <span class="pay-mini-count">${p.nb_lignes_liees}/${p.nb_lignes}</span></div></td>
    <td class="num">${payMoney(p.total)}</td>
    <td><span class="pay-state pay-state-${p.statut_global}">${micon(st.icon)} ${st.label}</span></td>
  </tr>`;
}

// Filters rows in place, so typing never re-renders (and never loses focus).
function filterPayments(value) {
  pay.search = value;
  let shown = 0;
  $$('.payment-row').forEach(row => {
    const p = pay.list.find(x => x.id === Number(row.dataset.id));
    const ok = p && paymentMatchesFilters(p);
    row.hidden = !ok;
    if (ok) shown++;
  });
  const none = $('#payments-no-match');
  if (none) none.hidden = shown > 0;
}

function setPaymentStatut(key) {
  pay.statut = key;
  render();
}

// ── Import ──────────────────────────────────────────────

function importPayments(input) {
  const files = [...(input.files || [])];
  input.value = '';
  return importPaymentFiles(files);
}

async function importPaymentFiles(files) {
  if (!files.length || pay.importing) return;
  pay.importing = { done: 0, total: files.length };
  render();
  const imported = [];
  for (const [i, file] of files.entries()) {
    pay.importing = { done: i, total: files.length };
    if (state.page === 'payments') render();
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch('/api/paiements', { method: 'POST', body: fd });
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(errorMessage(body));
      imported.push(body);
    } catch (e) {
      toast(`${file.name} : ${networkErrorMessage(e)}`, 'error');
    }
  }
  pay.importing = null;
  if (imported.length) {
    toast(`${imported.length} paiement${imported.length > 1 ? 's' : ''} importé${imported.length > 1 ? 's' : ''}`);
    await loadData(); // invoices may have just become paid
  }
  pay.listSeq++; // a list load still in flight predates the import: drop it
  pay.loading = false;
  pay.list = null;
  pay.listError = null;
  if (imported.length === 1) {
    pay.detailSeq++;
    pay.detail = imported[0];
    pay.detailId = imported[0].id;
  }
  if (state.page === 'payments') render();
}


bindPaymentDrop();
