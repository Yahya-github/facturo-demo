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
    return `<div class="page">${input}${pay.detail ? renderPaymentDetail(pay.detail) : payLoadingCard()}</div>`;
  }
  if (pay.list === null && !pay.loading && !pay.listError) loadPayments();
  return `<div class="page">${input}
    <div class="page-header">
      <div>
        <h2>Paiements</h2>
        <div class="subtitle">Preuves de paiement reçues de vos clients, rapprochées de vos billets</div>
      </div>
      ${importButton()}
    </div>
    ${pay.listError ? payLoadError() : pay.list === null ? payLoadingCard() : renderPaymentsList()}
  </div>`;
}

function importButton() {
  if (pay.importing) {
    return `<button class="btn btn-primary btn-loading" id="btn-import-payment" disabled aria-live="polite">
      <span class="loading-spinner"></span> Import ${pay.importing.done + 1}/${pay.importing.total}…</button>`;
  }
  return `<button class="btn btn-primary" id="btn-import-payment"
    onclick="document.getElementById('payment-file-input').click()">${icons.upload} Importer des PDF</button>`;
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

function payLoadingCard() {
  return `<div class="card"><div class="empty-state pay-loading">
    <span class="loading-spinner pay-spinner"></span><p>Chargement…</p></div></div>`;
}

// ── List ────────────────────────────────────────────────

function renderPaymentsList() {
  if (pay.list.length === 0) {
    return `<div class="card" id="payments-list"><div class="empty-state">
      ${micon('payments')}
      <h3>Aucun paiement importé</h3>
      <p>Importez la quittance PDF d'un client : chaque billet qu'elle liste est retrouvé sur vos factures, et les factures entièrement couvertes passent à « Payée ».</p>
      <button class="btn btn-primary" style="margin-top:16px"
        onclick="document.getElementById('payment-file-input').click()">${icons.upload} Importer des PDF</button>
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
    <div class="card">
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
    <td><div class="pay-mini-meter" title="${p.nb_lignes_liees} sur ${p.nb_lignes}">
      <span class="pay-mini-bar"><span style="width:${pct}%"></span></span>
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

async function importPayments(input) {
  const files = [...(input.files || [])];
  input.value = '';
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

// ── Detail ──────────────────────────────────────────────

function renderPaymentDetail(p) {
  const pdfUrl = p.fichier ? `/api/paiements/file/${encodeURIComponent(p.fichier)}` : '';
  return `<div id="payment-detail" data-id="${p.id}">
    <div class="page-header">
      <div class="page-back">
        <button class="btn btn-ghost btn-sm" onclick="closePayment()">${micon('arrow_back')} Tous les paiements</button>
        <h2 class="pay-title">Quittance <span class="pay-title-ref">${esc(p.reference) || 'sans n°'}</span></h2>
        <div class="subtitle">${esc(p.emetteur) || 'Émetteur inconnu'}${p.date ? ` — ${esc(formatDate(p.date))}` : ''}</div>
      </div>
      <div class="pay-head-actions">
        ${pdfUrl ? `<a class="btn btn-ghost" href="${pdfUrl}" target="_blank" rel="noopener">${icons.pdf} Voir le PDF</a>` : ''}
        ${importButton()}
      </div>
    </div>
    <div class="pay-detail-grid">
      ${renderPaymentHeaderCard(p)}
      ${renderPaymentLedger(p)}
    </div>
    ${renderLignesCard(p)}
    ${renderDeleteZone(p)}
  </div>`;
}

function renderPaymentHeaderCard(p) {
  const field = (key, label, value, type = 'text') => `<div class="form-group">
    <label class="form-label" for="pay-${key}">${label}</label>
    <input class="form-input" id="pay-${key}" type="${type}" value="${escAttr(value)}"
      onchange="savePaymentField('${key}', this.value)">
  </div>`;
  return `<section class="card pay-header-card" aria-label="Informations du paiement"><div class="card-body">
    <div class="form-row form-row-2">
      ${field('emetteur', 'Émetteur', p.emetteur)}
      ${field('reference', 'N° de quittance', p.reference)}
    </div>
    <div class="form-row form-row-2">
      ${field('date', 'Date', p.date, 'date')}
      <div class="form-group"><span class="form-label">Fichier</span>
        <div class="pay-file" title="${escAttr(p.nom_original)}">${micon('picture_as_pdf')} ${esc(p.nom_original) || '—'}</div></div>
    </div>
    <div class="form-group pay-notes">
      <label class="form-label" for="pay-notes">Notes</label>
      <textarea class="form-input" id="pay-notes" rows="2" placeholder="Ex. : écart de 5 % accepté, chèque déposé le…"
        onchange="savePaymentField('notes', this.value)">${esc(p.notes || '')}</textarea>
    </div>
  </div></section>`;
}

function escomptePct(p) {
  if (!p.escompte || p.sous_total == null) return null;
  const base = p.sous_total + p.escompte;
  return base > 0 ? Math.round((1000 * p.escompte) / base) / 10 : null;
}

function renderPaymentLedger(p) {
  const pct = escomptePct(p);
  const line = (label, value, cls = '') => `<div class="line ${cls}"><span>${label}</span><span>${value}</span></div>`;
  return `<section class="preview-total pay-ledger" aria-label="Montants">
    ${p.escompte ? line('Avant escompte', payMoney(p.sous_total + p.escompte)) : ''}
    ${p.escompte ? line(`Escompte${pct != null ? ` −${String(pct).replace('.', ',')} %` : ''}`, `− ${payMoney(p.escompte)}`, 'remise-line') : ''}
    ${p.sous_total != null ? line('Sous-total', payMoney(p.sous_total)) : ''}
    ${p.tps != null ? line('TPS', payMoney(p.tps)) : ''}
    ${p.tvq != null ? line('TVQ', payMoney(p.tvq)) : ''}
    ${line('Total payé', payMoney(p.total), 'grand-total')}
    ${pct != null ? `<p class="pay-short">Payé ${String(pct).replace('.', ',')} % sous le montant facturé (escompte pour paiement rapide).</p>` : ''}
  </section>`;
}

function renderCoverage(lignes) {
  const n = lignes.length;
  const lies = lignes.filter(l => l.statut === 'lie').length;
  const segs = lignes.map(l => `<span class="pay-seg-${l.statut}" title="${escAttr(l.numero_billet)} — ${LIGNE_STATUTS[l.statut].label}"></span>`).join('');
  const verdict = n === 0 ? 'Aucun billet sur ce paiement.'
    : lies === n ? 'Tous les billets sont liés à une facture.'
    : `${n - lies} billet${n - lies > 1 ? 's' : ''} à vérifier.`;
  return `<div class="pay-coverage">
    <div class="pay-coverage-text"><strong>${lies} / ${n}</strong> billets liés <span>${verdict}</span></div>
    <div class="pay-coverage-strip" aria-hidden="true">${segs}</div>
  </div>`;
}

function renderLignesCard(p) {
  return `<section class="card pay-lignes" aria-label="Billets payés">
    ${renderCoverage(p.lignes)}
    ${p.lignes.length ? `<table class="data-table">
      <thead><tr><th>N° billet</th><th>Date</th><th>Plaque</th><th class="num">Qté</th>
        <th class="num">Montant</th><th>État</th><th><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>${p.lignes.map(renderLigneRow).join('')}</tbody>
    </table>` : ''}
    <form class="pay-add-ligne" onsubmit="event.preventDefault(); addLigne(${p.id})">
      <label for="ligne-add-numero">Ajouter un billet absent du PDF</label>
      <input class="form-input" id="ligne-add-numero" placeholder="N° de billet" maxlength="40" autocomplete="off">
      <button type="submit" class="btn btn-ghost btn-sm" id="btn-add-ligne">${icons.plus} Ajouter</button>
    </form>
  </section>`;
}

function ligneDetailText(l) {
  if (l.statut === 'lie') {
    return `Facture <button type="button" class="pay-inline-link" onclick="editFacture(${l.facture_id})">${esc(l.facture_numero)}</button>
      ${l.client_nom ? `— ${esc(l.client_nom)}` : ''} <span class="pay-muted">(lié ${METHODES[l.methode] || ''})</span>`;
  }
  if (l.statut === 'doublon') {
    return `Déjà payé par <button type="button" class="pay-inline-link" onclick="openPayment(${l.doublon_paiement_id})">un autre paiement</button>`;
  }
  const hint = l.candidats.length
    ? `${l.candidats.length} billet${l.candidats.length > 1 ? 's' : ''} proche${l.candidats.length > 1 ? 's' : ''} trouvé${l.candidats.length > 1 ? 's' : ''}`
    : 'Aucun billet correspondant sur vos factures';
  return `<span class="pay-muted">${hint}</span>`;
}

function renderLigneRow(l) {
  const st = LIGNE_STATUTS[l.statut] || LIGNE_STATUTS.non_lie;
  const confirming = pay.confirmRemoveLigne === l.id;
  const linkBtn = l.statut === 'lie'
    ? `<button type="button" class="btn btn-ghost btn-sm" onclick="unlinkLigne(${l.id})">${micon('link_off')} Délier</button>`
    : `<button type="button" class="btn btn-ghost btn-sm btn-link-ligne" data-ligne-id="${l.id}" onclick="openLinkPicker(${l.id})">${micon('add_link')} Lier…</button>`;
  const removeBtn = confirming
    ? `<button type="button" class="btn btn-danger btn-sm" onclick="removeLigne(${l.id})">Retirer</button>
       <button type="button" class="btn btn-ghost btn-sm" onclick="askRemoveLigne(null)">Annuler</button>`
    : `<button type="button" class="pay-icon-btn btn-remove-ligne" data-ligne-id="${l.id}" onclick="askRemoveLigne(${l.id})"
        title="Retirer ce billet du paiement" aria-label="Retirer le billet ${escAttr(l.numero_billet)}">${icons.trash}</button>`;
  return `<tr class="ligne-row ligne-${l.statut}" data-ligne-id="${l.id}">
    <td class="pay-mono">${esc(l.numero_billet) || '—'}</td>
    <td>${esc(formatDate(l.date_billet)) || '—'}</td>
    <td class="pay-mono">${esc(l.plaque) || '—'}</td>
    <td class="num">${payQty(l.quantite)}</td>
    <td class="num">${payMoney(l.montant)}</td>
    <td><span class="ligne-status ${st.cls}">${micon(st.icon)} ${st.label}</span>
      <div class="ligne-detail">${ligneDetailText(l)}</div></td>
    <td><div class="actions">${linkBtn}${removeBtn}</div></td>
  </tr>`;
}

function renderDeleteZone(p) {
  if (pay.confirmDelete) {
    return `<div class="pay-delete-zone is-confirming" role="alert">
      <span>Supprimer ce paiement et son PDF ? Les factures payées automatiquement grâce à lui repasseront à « Non payée ».</span>
      <button class="btn btn-danger btn-sm" onclick="deletePayment(${p.id})">Supprimer définitivement</button>
      <button class="btn btn-ghost btn-sm" onclick="askDeletePayment(false)">Annuler</button>
    </div>`;
  }
  return `<div class="pay-delete-zone">
    <button class="btn btn-ghost btn-sm pay-delete-btn" onclick="askDeletePayment(true)">${icons.trash} Supprimer ce paiement</button>
  </div>`;
}

// ── Detail actions ──────────────────────────────────────

async function refreshAfterLinkChange() {
  await Promise.all([openPayment(pay.detailId), loadData()]);
}

async function savePaymentField(key, value) {
  const id = pay.detailId;
  try {
    const detail = await api('PUT', `/api/paiements/${id}`, { [key]: value });
    if (pay.detailId !== id) return; // user moved on while saving
    pay.detail = detail;
    toast('Paiement mis à jour');
    render();
  } catch (e) {
    toast(e.message, 'error');
    // The field still shows the rejected edit: put back what is stored.
    const input = $(`#pay-${key}`);
    if (input && pay.detail) input.value = pay.detail[key] == null ? '' : pay.detail[key];
  }
}

async function addLigne(paiementId) {
  const input = $('#ligne-add-numero');
  const numero = (input && input.value || '').trim();
  if (!numero) { toast('Saisissez un numéro de billet', 'error'); return; }
  try {
    const ligne = await api('POST', `/api/paiements/${paiementId}/lignes`, { numero_billet: numero });
    toast(ligne.statut === 'lie' ? `Billet ${numero} ajouté et lié` : `Billet ${numero} ajouté — à vérifier`);
    await refreshAfterLinkChange();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function unlinkLigne(ligneId) {
  try {
    await api('PUT', `/api/paiements/lignes/${ligneId}`, { facture_id: null });
    toast('Billet délié');
    await refreshAfterLinkChange();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function askRemoveLigne(ligneId) {
  pay.confirmRemoveLigne = ligneId;
  render();
}

async function removeLigne(ligneId) {
  try {
    await api('DELETE', `/api/paiements/lignes/${ligneId}`);
    toast('Billet retiré du paiement');
    await refreshAfterLinkChange();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function askDeletePayment(on) {
  pay.confirmDelete = on;
  render();
}

async function deletePayment(id) {
  try {
    await api('DELETE', `/api/paiements/${id}`);
    toast('Paiement supprimé');
    await loadData();
    closePayment();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ── Manual link picker ──────────────────────────────────

function pickerBillets(facture) {
  try {
    const billets = JSON.parse(facture.billets_json || '[]');
    return Array.isArray(billets) ? billets : [];
  } catch {
    return [];
  }
}

function billetOptionLabel(b, i) {
  const parts = [`Billet ${i + 1}`, b.numero_billet ? `n° ${b.numero_billet}` : '',
    formatDate(b.date_billet || ''), b.plaque || '', b.quantite ? `${b.quantite} h` : ''];
  return parts.filter(Boolean).join(' — ');
}

const picker = { trigger: null, ligneId: null };

async function openLinkPicker(ligneId) {
  const ligne = pay.detail.lignes.find(l => l.id === ligneId);
  if (!ligne) return;
  try {
    pay.pickerFactures = await api('GET', '/api/factures'); // fresh: invoices may be new
  } catch (e) {
    toast(e.message, 'error');
    return;
  }
  closeLinkPicker();
  picker.trigger = document.activeElement;
  picker.ligneId = ligneId;
  const suggested = new Set(ligne.candidats.map(c => c.facture_id));
  const option = f => `<option value="${escAttr(f.id)}">${esc(f.numero)} — ${esc(f.client_nom)} (${esc(formatDate(f.date))})</option>`;
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.id = 'ligne-link-picker';
  overlay.innerHTML = `<div class="modal pay-picker">
    <div class="modal-header"><h3 id="ligne-link-title">Lier le billet ${esc(ligne.numero_billet)}</h3>
      <button class="modal-close" onclick="closeLinkPicker()" aria-label="Fermer">${icons.x}</button></div>
    <div class="modal-body">
      <p class="pay-picker-ligne">Sur le paiement : ${esc(formatDate(ligne.date_billet)) || 'date inconnue'} — ${esc(ligne.plaque) || 'plaque inconnue'} — ${payQty(ligne.quantite)} h — ${payMoney(ligne.montant)}</p>
      ${ligne.candidats.length ? `<div class="pay-suggestions"><span class="form-label">Billets proches</span>
        ${ligne.candidats.map(c => `<button type="button" class="pay-suggestion" onclick="pickCandidate(${c.facture_id}, ${c.billet_index})">
          <strong>${esc(c.facture_numero)}</strong> ${esc(c.client_nom)}
          <span>${esc(c.numero_billet) ? `n° ${esc(c.numero_billet)} — ` : ''}${esc(formatDate(c.date_billet))} — ${esc(c.plaque)}</span>
        </button>`).join('')}</div>` : ''}
      <div class="form-group"><label class="form-label" for="ligne-link-facture-select">Facture</label>
        <select class="form-select" id="ligne-link-facture-select" onchange="fillPickerBillets()">
          <option value="">Choisir une facture…</option>
          ${suggested.size ? `<optgroup label="Suggérées">${pay.pickerFactures.filter(f => suggested.has(f.id)).map(option).join('')}</optgroup>` : ''}
          <optgroup label="Toutes les factures">${pay.pickerFactures.filter(f => !suggested.has(f.id)).map(option).join('')}</optgroup>
        </select></div>
      <div class="form-group"><label class="form-label" for="ligne-link-billet-select">Billet</label>
        <select class="form-select" id="ligne-link-billet-select" disabled><option value="">Choisissez d'abord une facture</option></select></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeLinkPicker()">Annuler</button>
      <button class="btn btn-primary" id="ligne-link-confirm" onclick="confirmLink(${ligne.id})">${micon('link')} Lier ce billet</button>
    </div>
  </div>`;
  openModal(overlay, {
    initialFocus: '#ligne-link-facture-select',
    onClose: restoreFocus => { if (restoreFocus) restorePickerFocus(); },
  });
}

// Focus goes back where the user was: the trigger if it still exists, else
// the same ligne's first action (a re-render replaces the row's buttons).
function restorePickerFocus() {
  const target = picker.trigger && picker.trigger.isConnected
    ? picker.trigger
    : $(`.ligne-row[data-ligne-id="${picker.ligneId}"] .actions button`);
  if (target) target.focus();
  picker.trigger = null;
}

function fillPickerBillets(selectedIndex) {
  const fid = Number($('#ligne-link-facture-select').value);
  const select = $('#ligne-link-billet-select');
  const facture = pay.pickerFactures.find(f => f.id === fid);
  const billets = facture ? pickerBillets(facture) : [];
  select.disabled = billets.length === 0;
  select.innerHTML = billets.length
    ? billets.map((b, i) => `<option value="${escAttr(i)}">${esc(billetOptionLabel(b, i))}</option>`).join('')
    : `<option value="">${facture ? 'Aucun billet sur cette facture' : "Choisissez d'abord une facture"}</option>`;
  if (selectedIndex != null) select.value = String(selectedIndex);
}

function pickCandidate(factureId, billetIndex) {
  $('#ligne-link-facture-select').value = String(factureId);
  fillPickerBillets(billetIndex);
  $('#ligne-link-confirm').focus();
}

function closeLinkPicker(restoreFocus = true) {
  closeModal($('#ligne-link-picker'), restoreFocus);
}

async function confirmLink(ligneId) {
  const factureId = Number($('#ligne-link-facture-select').value);
  const billetIndex = $('#ligne-link-billet-select').value;
  if (!factureId || billetIndex === '') { toast('Choisissez une facture et un billet', 'error'); return; }
  try {
    await api('PUT', `/api/paiements/lignes/${ligneId}`, { facture_id: factureId, billet_index: Number(billetIndex) });
    closeLinkPicker(false);
    toast('Billet lié');
    await refreshAfterLinkChange();
    restorePickerFocus();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ── Invoice form badge (called by facture.js renderBilletCard) ─────────
// editFacture is wrapped so the invoice's payment links are loaded before its
// form renders; each billet object is then bound to its payment info once, so
// the badge follows the billet if others are added or removed while editing.

// Load-order dependency: index.html must load payments.js AFTER facture.js,
// otherwise editFacture is not defined yet and the badges never get data.
const payBadges = { factureId: null, billets: [], byBillet: new WeakMap(), bound: false };

if (typeof editFacture === 'function') {
  const editFactureWithoutPayments = editFacture;
  editFacture = async function (id) {
    try {
      const data = await api('GET', `/api/factures/${id}/paiements`);
      Object.assign(payBadges, { factureId: id, billets: data.billets || [], byBillet: new WeakMap(), bound: false });
    } catch (e) {
      Object.assign(payBadges, { factureId: null, billets: [], byBillet: new WeakMap(), bound: false });
      toast(`Impossible de charger l'état de paiement des billets : ${e.message}`, 'error');
    }
    return editFactureWithoutPayments(id);
  };
}

function billetPaymentBadge(b, i) {
  if (state.editingId == null || state.editingId !== payBadges.factureId) return '';
  if (!payBadges.bound) {
    payBadges.billets.forEach((info, k) => { if (billets[k]) payBadges.byBillet.set(billets[k], info); });
    payBadges.bound = true;
  }
  const info = payBadges.byBillet.get(b);
  if (!info || !info.paye) return '';
  return `<button type="button" class="billet-payment-badge" data-paiement-id="${info.paiement_id}"
    onclick="navigate('payments', { paiementId: ${info.paiement_id} })"
    title="Ouvrir le paiement">${micon('check_circle', true)} Payé — Quittance ${esc(info.reference)}</button>`;
}
