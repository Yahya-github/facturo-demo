// ── PAIEMENTS: detail, link picker, invoice badge ────────

// ── Detail ──────────────────────────────────────────────

function renderPaymentDetail(p) {
  const pdfUrl = p.fichier ? `/api/paiements/file/${encodeURIComponent(p.fichier)}` : '';
  const st = PAY_STATUTS[p.statut_global] || PAY_STATUTS.partiel;
  return `<div id="payment-detail" data-id="${p.id}">
    <header class="page-head">
      <div class="page-back">
        <button class="btn btn-ghost btn-sm" onclick="closePayment()">${micon('arrow_back')} Tous les paiements</button>
        <h2 class="pay-title">Quittance <span class="pay-title-ref">${esc(p.reference) || 'sans n°'}</span></h2>
        <p>${esc(p.emetteur) || 'Émetteur inconnu'}${p.date ? ` — ${esc(formatDate(p.date))}` : ''}</p>
      </div>
      <div class="pay-head-actions">
        <span class="pay-state pay-state-${p.statut_global}">${micon(st.icon)} ${st.label}</span>
        ${pdfUrl ? `<a class="btn btn-outline" href="${pdfUrl}" target="_blank" rel="noopener">${icons.pdf} Voir le PDF</a>` : ''}
        ${importButton()}
      </div>
    </header>
    <div class="pay-detail-grid">
      <div class="pay-detail-main">
        ${renderLignesCard(p)}
      </div>
      <aside class="pay-detail-aside" aria-label="Résumé du paiement">
        ${renderPaymentLedger(p)}
        ${renderPaymentHeaderCard(p)}
        ${renderDeleteZone(p)}
      </aside>
    </div>
  </div>`;
}

function renderPaymentHeaderCard(p) {
  const field = (key, label, value, type = 'text') => `<div class="form-group">
    <label class="form-label" for="pay-${key}">${label}</label>
    <input class="form-input" id="pay-${key}" type="${type}" value="${escAttr(value)}"
      onchange="savePaymentField('${key}', this.value)">
  </div>`;
  return `<section class="card pay-header-card" aria-label="Informations du paiement"><div class="card-body"><h3 class="pay-card-title">Informations</h3>
    <div class="form-row pay-fields">
      ${field('emetteur', 'Émetteur', p.emetteur)}
      ${field('reference', 'N° de quittance', p.reference)}
    </div>
    <div class="form-row pay-fields">
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
  const line = (label, value, cls = '') => `<div class="line ${cls}"><dt>${label}</dt><dd>${value}</dd></div>`;
  return `<section class="fac-summary pay-ledger" aria-label="Montants"><dl class="fac-lines">
    ${p.escompte ? line('Avant escompte', payMoney(p.sous_total + p.escompte)) : ''}
    ${p.escompte ? line(`Escompte${pct != null ? ` −${String(pct).replace('.', ',')} %` : ''}`, `− ${payMoney(p.escompte)}`, 'line-remise') : ''}
    ${p.sous_total != null ? line('Sous-total', payMoney(p.sous_total)) : ''}
    ${p.tps != null ? line('TPS', payMoney(p.tps)) : ''}
    ${p.tvq != null ? line('TVQ', payMoney(p.tvq)) : ''}
    </dl>
    <div class="fac-total"><span>Total payé</span><strong>${payMoney(p.total)}</strong></div>
    ${pct != null ? `<p class="pay-short">Payé ${String(pct).replace('.', ',')} % sous le montant facturé (escompte pour paiement rapide).</p>` : ''}
  </section>`;
}

function renderCoverage(lignes) {
  const n = lignes.length;
  const lies = lignes.filter(l => l.statut === 'lie').length;
  const pct = n ? Math.round((100 * lies) / n) : 0;
  const verdict = n === 0 ? 'Aucun billet sur ce paiement.'
    : lies === n ? 'Tous les billets sont liés à une facture.'
    : `${n - lies} billet${n - lies > 1 ? 's' : ''} à vérifier.`;
  return `<div class="pay-coverage">
    <div class="pay-coverage-text"><strong>${lies} / ${n}</strong> billets liés <span>${verdict}</span></div>
    <div class="progress pay-coverage-bar${lies === n && n ? ' is-complete' : ''}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="Billets liés"><span style="width:${pct}%"></span></div>
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
  const linkBtn = l.statut === 'lie'
    ? `<button type="button" class="btn btn-ghost btn-sm" onclick="unlinkLigne(${l.id})">${micon('link_off')} Délier</button>`
    : `<button type="button" class="btn btn-outline btn-sm btn-link-ligne" data-ligne-id="${l.id}" onclick="openLinkPicker(${l.id})">${micon('add_link')} Lier…</button>`;
  const more = `<button type="button" class="btn btn-ghost btn-icon btn-sm pay-more btn-remove-ligne" data-ligne-id="${l.id}"
      data-tip="Plus d'actions" aria-label="Actions du billet ${escAttr(l.numero_billet)}" aria-haspopup="menu">${icon('ellipsis')}</button>`;
  return `<tr class="ligne-row ligne-${l.statut}" data-ligne-id="${l.id}">
    <td class="pay-mono">${esc(l.numero_billet) || '—'}</td>
    <td>${esc(formatDate(l.date_billet)) || '—'}</td>
    <td class="pay-mono">${esc(l.plaque) || '—'}</td>
    <td class="num">${payQty(l.quantite)}</td>
    <td class="num">${payMoney(l.montant)}</td>
    <td><span class="ligne-status ${st.cls}">${micon(st.icon)} ${st.label}</span>
      <div class="ligne-detail">${ligneDetailText(l)}</div></td>
    <td><div class="actions">${linkBtn}${more}</div></td>
  </tr>`;
}

// The "..." menu of each ligne row (delegated: rows are rebuilt on every render).
function bindLigneMenus() {
  $$('.pay-more').forEach(btn => {
    if (btn.dataset.menu) return;
    btn.dataset.menu = '1';
    const id = Number(btn.dataset.ligneId);
    ui.menu.attach(btn, () => [
      { label: 'Retirer ce billet du paiement', icon: 'trash-2', destructive: true, onSelect: () => askRemoveLigne(id) },
    ]);
  });
}

function renderDeleteZone(p) {
  return `<div class="pay-delete-zone">
    <button class="btn btn-danger-ghost btn-sm pay-delete-btn" onclick="askDeletePayment(${p.id})">${icons.trash} Supprimer ce paiement</button>
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

async function askRemoveLigne(ligneId) {
  const ok = await ui.alertDialog({
    title: 'Retirer ce billet',
    description: 'Le billet est retiré de ce paiement. Si une facture était payée grâce à lui, elle repasse à « Non payée ».',
    confirmLabel: 'Retirer', destructive: true,
  });
  if (ok) removeLigne(ligneId);
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

async function askDeletePayment(id) {
  const ok = await ui.alertDialog({
    title: 'Supprimer ce paiement',
    description: 'Supprimer ce paiement et son PDF ? Les factures payées automatiquement grâce à lui repasseront à « Non payée ».',
    confirmLabel: 'Supprimer définitivement', destructive: true,
  });
  if (ok) deletePayment(id);
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

ui.hydrate.register(() => { if (document.querySelector('.pay-more')) bindLigneMenus(); });
