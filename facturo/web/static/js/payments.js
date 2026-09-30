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

// Labels are looked up at render time (pay.status.* / pay.ligne.*) so a language switch shows up.
const PAY_STATUTS = {
  complet: { icon: 'task_alt' },
  partiel: { icon: 'timelapse' },
  a_verifier: { icon: 'error' },
};
const payStatutLabel = key => ui.i18n.t(`pay.status.${key in PAY_STATUTS ? key : 'partiel'}`);

const LIGNE_STATUTS = {
  lie: { cls: 'status-lie', labelKey: 'pay.ligne.lie', icon: 'link' },
  non_lie: { cls: 'status-a-verifier', labelKey: 'pay.status.a_verifier', icon: 'help' },
  doublon: { cls: 'status-doublon', labelKey: 'pay.ligne.doublon', icon: 'content_copy' },
};

const payMethod = key => (['numero', 'date_plaque', 'manuel'].includes(key) ? ui.i18n.t(`pay.method.${key}`) : '');

function payMoney(n) {
  return n == null ? '—' : money(Number(n));
}

function payQty(n) {
  return n == null ? '—' : ui.i18n.fmtNumber(Number(n));
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
        <h2>${esc(ui.i18n.t('nav.payments'))}</h2>
        <p>${esc(ui.i18n.t('pay.subtitle'))}</p>
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
        <strong>${esc(ui.i18n.t('pay.importing', { current: done + 1, total }))}</strong>
        <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="${escAttr(ui.i18n.t('pay.importing_label'))}"><span style="width:${Math.max(pct, 6)}%"></span></div>
      </div>
      <button class="btn btn-primary btn-loading" id="btn-import-payment" disabled>${esc(ui.i18n.t('pay.importing_btn'))}</button>
    </div>`;
  }
  return `<div class="upzone pay-zone" id="pay-dropzone">
    <span class="upzone-icon">${icon('cloud-upload')}</span>
    <div class="pay-zone-text">
      <strong>${esc(ui.i18n.t('pay.drop_title'))}</strong>
      <span>${esc(ui.i18n.t('pay.drop_text'))}</span>
    </div>
    <button class="btn btn-primary" id="btn-import-payment"
      onclick="document.getElementById('payment-file-input').click()">${icons.upload} ${esc(ui.i18n.t('pay.import_btn'))}</button>
  </div>`;
}

function importButton() {
  return `<button class="btn btn-primary" id="btn-import-payment"
    onclick="document.getElementById('payment-file-input').click()">${icons.upload} ${esc(ui.i18n.t('pay.import_btn'))}</button>`;
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
    if (!files.length) { toast(ui.i18n.t('pay.drop_pdf'), 'error'); return; }
    importPaymentFiles(files);
  });
}

function payLoadError() {
  return `<div class="card"><div class="empty-state" role="alert" id="payments-load-error">
    ${micon('error')}
    <h3>${esc(ui.i18n.t('pay.load_failed'))}</h3>
    <p>${esc(pay.listError)}</p>
    <p>${esc(ui.i18n.t('pay.load_failed_note'))}</p>
    <button class="btn btn-primary" style="margin-top:16px" onclick="retryLoadPayments()">${micon('refresh')} ${esc(ui.i18n.t('toast.retry'))}</button>
  </div></div>`;
}

function payListSkeleton() {
  const row = `<div class="pay-skel-row"><span class="skeleton" style="width:5rem;height:.9rem"></span><span class="skeleton" style="width:38%;height:.9rem"></span><span class="skeleton" style="width:14%;height:.9rem"></span><span class="skeleton" style="width:8rem;height:.5rem"></span><span class="skeleton" style="width:5rem;height:.9rem;margin-left:auto"></span></div>`;
  return `<div class="card pay-skel" aria-busy="true" aria-label="${escAttr(ui.i18n.t('a11y.loading'))}">${row.repeat(5)}</div>`;
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
      <h3>${esc(ui.i18n.t('pay.empty.title'))}</h3>
      <p>${esc(ui.i18n.t('pay.empty.text'))}</p>
    </div></div>`;
  }
  const counts = { '': pay.list.length };
  pay.list.forEach(p => { counts[p.statut_global] = (counts[p.statut_global] || 0) + 1; });
  const filters = [['', 'pay.filter.all'], ['a_verifier', 'pay.status.a_verifier'], ['partiel', 'pay.filter.partiel'], ['complet', 'pay.filter.complet']];
  return `<div class="pay-toolbar">
      <label class="pay-search">${micon('search')}
        <input type="search" id="payments-search" class="form-input" placeholder="${escAttr(ui.i18n.t('pay.search_placeholder'))}"
          value="${escAttr(pay.search)}" oninput="filterPayments(this.value)" aria-label="${escAttr(ui.i18n.t('pay.search_label'))}">
      </label>
      <div class="seg pay-status-seg" role="group" aria-label="${escAttr(ui.i18n.t('pay.filter.label'))}">
        ${filters.map(([key, labelKey]) => `<button type="button"
          class="seg-btn pay-status-btn${pay.statut === key ? ' active' : ''}" data-statut="${key}"
          aria-pressed="${pay.statut === key}" onclick="setPaymentStatut('${key}')">${esc(ui.i18n.t(labelKey))}
          <span class="pay-count">${counts[key] || 0}</span></button>`).join('')}
      </div>
    </div>
    <div class="card card-table">
      <table class="data-table pay-table" id="payments-list">
        <thead><tr><th>${esc(ui.i18n.t('col.date'))}</th><th>${esc(ui.i18n.t('pay.col.issuer'))}</th><th>${esc(ui.i18n.t('pay.col.receipt'))}</th><th>${esc(ui.i18n.t('pay.col.linked'))}</th>
          <th class="num">${esc(ui.i18n.t('pay.col.total'))}</th><th>${esc(ui.i18n.t('pay.col.state'))}</th></tr></thead>
        <tbody>${pay.list.map(renderPaymentRow).join('')}</tbody>
      </table>
      <p class="pay-no-match" id="payments-no-match" hidden>${esc(ui.i18n.t('pay.no_match'))}</p>
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
    <td class="pay-emetteur">${esc(p.emetteur) || `<span class="pay-muted">${esc(ui.i18n.t('pay.unknown_issuer'))}</span>`}</td>
    <td><button type="button" class="pay-ref" onclick="event.stopPropagation(); openPayment(${p.id})"
      aria-label="${escAttr(ui.i18n.t('pay.open_receipt', { ref: p.reference }))}">${esc(p.reference) || esc(ui.i18n.t('pay.no_ref'))}</button></td>
    <td><div class="pay-mini-meter pay-${p.statut_global}" data-tip="${escAttr(ui.i18n.t('pay.linked_of', { linked: p.nb_lignes_liees, total: p.nb_lignes }))}">
      <span class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="${escAttr(ui.i18n.t('pay.col.linked'))}"><span style="width:${pct}%"></span></span>
      <span class="pay-mini-count">${p.nb_lignes_liees}/${p.nb_lignes}</span></div></td>
    <td class="num">${payMoney(p.total)}</td>
    <td><span class="pay-state pay-state-${p.statut_global}">${micon(st.icon)} ${esc(payStatutLabel(p.statut_global))}</span></td>
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
      const res = await fetch('/api/paiements', { method: 'POST', body: fd, headers: { 'X-Lang': ui.i18n.lang() } });
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(errorMessage(body));
      imported.push(body);
    } catch (e) {
      toast(ui.i18n.t('pay.file_error', { name: file.name, message: networkErrorMessage(e) }), 'error');
    }
  }
  pay.importing = null;
  if (imported.length) {
    toast(ui.i18n.tn('pay.imported', imported.length));
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
