// ── PAIEMENTS: detail, link picker, invoice badge ────────

// ── Detail ──────────────────────────────────────────────

function renderPaymentDetail(p) {
  const pdfUrl = p.fichier ? `/api/paiements/file/${encodeURIComponent(p.fichier)}` : '';
  const st = PAY_STATUTS[p.statut_global] || PAY_STATUTS.partiel;
  return `<div id="payment-detail" data-id="${p.id}">
    <header class="page-head">
      <div class="page-back">
        <button class="btn btn-ghost btn-sm" onclick="closePayment()">${micon('arrow_back')} ${esc(ui.i18n.t('pay.back'))}</button>
        <h2 class="pay-title">${esc(ui.i18n.t('pay.title'))} <span class="pay-title-ref">${esc(p.reference) || esc(ui.i18n.t('pay.no_ref_lower'))}</span></h2>
        <p>${esc(p.emetteur) || esc(ui.i18n.t('pay.unknown_issuer'))}${p.date ? ` — ${esc(formatDate(p.date))}` : ''}</p>
      </div>
      <div class="pay-head-actions">
        <span class="pay-state pay-state-${p.statut_global}">${micon(st.icon)} ${esc(payStatutLabel(p.statut_global))}</span>
        ${pdfUrl ? `<a class="btn btn-outline" href="${pdfUrl}" target="_blank" rel="noopener">${icons.pdf} ${esc(ui.i18n.t('pay.view_pdf'))}</a>` : ''}
        ${importButton()}
      </div>
    </header>
    <div class="pay-detail-grid">
      <div class="pay-detail-main">
        ${renderLignesCard(p)}
      </div>
      <aside class="pay-detail-aside" aria-label="${escAttr(ui.i18n.t('pay.summary'))}">
        ${renderPaymentLedger(p)}
        ${renderPaymentHeaderCard(p)}
        ${renderDeleteZone(p)}
      </aside>
    </div>
  </div>`;
}

function renderPaymentHeaderCard(p) {
  const field = (key, label, value, type = 'text') => `<div class="form-group">
    <label class="form-label" for="pay-${key}">${esc(label)}</label>
    <input class="form-input" id="pay-${key}" type="${type}" value="${escAttr(value)}"
      onchange="savePaymentField('${key}', this.value)">
  </div>`;
  return `<section class="card pay-header-card" aria-label="${escAttr(ui.i18n.t('pay.info.label'))}"><div class="card-body"><h3 class="pay-card-title">${esc(ui.i18n.t('pay.info.title'))}</h3>
    <div class="form-row pay-fields">
      ${field('emetteur', ui.i18n.t('pay.field.issuer'), p.emetteur)}
      ${field('reference', ui.i18n.t('pay.field.reference'), p.reference)}
    </div>
    <div class="form-row pay-fields">
      ${field('date', ui.i18n.t('pay.field.date'), p.date, 'date')}
      <div class="form-group"><span class="form-label">${esc(ui.i18n.t('pay.field.file'))}</span>
        <div class="pay-file" title="${escAttr(p.nom_original)}">${micon('picture_as_pdf')} ${esc(p.nom_original) || '—'}</div></div>
    </div>
    <div class="form-group pay-notes">
      <label class="form-label" for="pay-notes">${esc(ui.i18n.t('pay.field.notes'))}</label>
      <textarea class="form-input" id="pay-notes" rows="2" placeholder="${escAttr(ui.i18n.t('pay.notes_placeholder'))}"
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
  const t = ui.i18n.t;
  const pctText = pct != null ? ui.i18n.fmtNumber(pct) : '';
  const line = (label, value, cls = '') => `<div class="line ${cls}"><dt>${esc(label)}</dt><dd>${value}</dd></div>`;
  return `<section class="fac-summary pay-ledger" aria-label="${escAttr(t('pay.ledger.label'))}"><dl class="fac-lines">
    ${p.escompte ? line(t('pay.ledger.before'), payMoney(p.sous_total + p.escompte)) : ''}
    ${p.escompte ? line(pct != null ? t('pay.ledger.discount_pct', { pct: pctText }) : t('pay.ledger.discount'), `− ${payMoney(p.escompte)}`, 'line-remise') : ''}
    ${p.sous_total != null ? line(t('pay.ledger.subtotal'), payMoney(p.sous_total)) : ''}
    ${p.tps != null ? line(t('pay.ledger.gst'), payMoney(p.tps)) : ''}
    ${p.tvq != null ? line(t('pay.ledger.qst'), payMoney(p.tvq)) : ''}
    </dl>
    <div class="fac-total"><span>${esc(t('pay.ledger.total'))}</span><strong>${payMoney(p.total)}</strong></div>
    ${pct != null ? `<p class="pay-short">${esc(t('pay.ledger.short', { pct: pctText }))}</p>` : ''}
  </section>`;
}

function renderCoverage(lignes) {
  const n = lignes.length;
  const lies = lignes.filter(l => l.statut === 'lie').length;
  const pct = n ? Math.round((100 * lies) / n) : 0;
  const verdict = n === 0 ? ui.i18n.t('pay.coverage.none')
    : lies === n ? ui.i18n.t('pay.coverage.all')
    : ui.i18n.tn('pay.coverage.review', n - lies);
  return `<div class="pay-coverage">
    <div class="pay-coverage-text"><strong>${lies} / ${n}</strong> ${esc(ui.i18n.t('pay.coverage.linked'))} <span>${esc(verdict)}</span></div>
    <div class="progress pay-coverage-bar${lies === n && n ? ' is-complete' : ''}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="${escAttr(ui.i18n.t('pay.col.linked'))}"><span style="width:${pct}%"></span></div>
  </div>`;
}

function renderLignesCard(p) {
  return `<section class="card pay-lignes" aria-label="${escAttr(ui.i18n.t('pay.lignes.label'))}">
    ${renderCoverage(p.lignes)}
    ${p.lignes.length ? `<table class="data-table">
      <thead><tr><th>${esc(ui.i18n.t('pay.col.ticket_no'))}</th><th>${esc(ui.i18n.t('col.date'))}</th><th>${esc(ui.i18n.t('pay.col.plate'))}</th><th class="num">${esc(ui.i18n.t('pay.col.qty'))}</th>
        <th class="num">${esc(ui.i18n.t('col.amount'))}</th><th>${esc(ui.i18n.t('pay.col.state'))}</th><th><span class="sr-only">${esc(ui.i18n.t('col.actions'))}</span></th></tr></thead>
      <tbody>${p.lignes.map(renderLigneRow).join('')}</tbody>
    </table>` : ''}
    <form class="pay-add-ligne" onsubmit="event.preventDefault(); addLigne(${p.id})">
      <label for="ligne-add-numero">${esc(ui.i18n.t('pay.add_ligne'))}</label>
      <input class="form-input" id="ligne-add-numero" placeholder="${escAttr(ui.i18n.t('pay.add_placeholder'))}" maxlength="40" autocomplete="off">
      <button type="submit" class="btn btn-ghost btn-sm" id="btn-add-ligne">${icons.plus} ${esc(ui.i18n.t('action.add'))}</button>
    </form>
  </section>`;
}

function ligneDetailText(l) {
  const t = ui.i18n.t;
  if (l.statut === 'lie') {
    return `${esc(t('pay.line.invoice'))} <button type="button" class="pay-inline-link" onclick="editFacture(${l.facture_id})">${esc(l.facture_numero)}</button>
      ${l.client_nom ? `— ${esc(l.client_nom)}` : ''} <span class="pay-muted">${esc(t('pay.line.linked', { method: payMethod(l.methode) }))}</span>`;
  }
  if (l.statut === 'doublon') {
    return `${esc(t('pay.line.dup_prefix'))} <button type="button" class="pay-inline-link" onclick="openPayment(${l.doublon_paiement_id})">${esc(t('pay.line.dup_link'))}</button>`;
  }
  const hint = l.candidats.length ? ui.i18n.tn('pay.line.candidates', l.candidats.length) : t('pay.line.none');
  return `<span class="pay-muted">${esc(hint)}</span>`;
}

function renderLigneRow(l) {
  const st = LIGNE_STATUTS[l.statut] || LIGNE_STATUTS.non_lie;
  const linkBtn = l.statut === 'lie'
    ? `<button type="button" class="btn btn-ghost btn-sm" onclick="unlinkLigne(${l.id})">${micon('link_off')} ${esc(ui.i18n.t('pay.unlink'))}</button>`
    : `<button type="button" class="btn btn-outline btn-sm btn-link-ligne" data-ligne-id="${l.id}" onclick="openLinkPicker(${l.id})">${micon('add_link')} ${esc(ui.i18n.t('pay.link'))}</button>`;
  const more = `<button type="button" class="btn btn-ghost btn-icon btn-sm pay-more btn-remove-ligne" data-ligne-id="${l.id}"
      data-tip="${escAttr(ui.i18n.t('pay.more_actions'))}" aria-label="${escAttr(ui.i18n.t('pay.ticket_actions', { number: l.numero_billet }))}" aria-haspopup="menu">${icon('ellipsis')}</button>`;
  return `<tr class="ligne-row ligne-${l.statut}" data-ligne-id="${l.id}">
    <td class="pay-mono">${esc(l.numero_billet) || '—'}</td>
    <td>${esc(formatDate(l.date_billet)) || '—'}</td>
    <td class="pay-mono">${esc(l.plaque) || '—'}</td>
    <td class="num">${payQty(l.quantite)}</td>
    <td class="num">${payMoney(l.montant)}</td>
    <td><span class="ligne-status ${st.cls}">${micon(st.icon)} ${esc(ui.i18n.t(st.labelKey))}</span>
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
      { label: ui.i18n.t('pay.remove_menu'), icon: 'trash-2', destructive: true, onSelect: () => askRemoveLigne(id) },
    ]);
  });
}

function renderDeleteZone(p) {
  return `<div class="pay-delete-zone">
    <button class="btn btn-danger-ghost btn-sm pay-delete-btn" onclick="askDeletePayment(${p.id})">${icons.trash} ${esc(ui.i18n.t('pay.delete_btn'))}</button>
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
    toast(ui.i18n.t('pay.updated'));
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
  if (!numero) { toast(ui.i18n.t('pay.enter_ticket'), 'error'); return; }
  try {
    const ligne = await api('POST', `/api/paiements/${paiementId}/lignes`, { numero_billet: numero });
    toast(ui.i18n.t(ligne.statut === 'lie' ? 'pay.ticket_added_linked' : 'pay.ticket_added_review', { number: numero }));
    await refreshAfterLinkChange();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function unlinkLigne(ligneId) {
  try {
    await api('PUT', `/api/paiements/lignes/${ligneId}`, { facture_id: null });
    toast(ui.i18n.t('pay.unlinked'));
    await refreshAfterLinkChange();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function askRemoveLigne(ligneId) {
  const ok = await ui.alertDialog({
    title: ui.i18n.t('pay.remove.title'),
    description: ui.i18n.t('pay.remove.desc'),
    confirmLabel: ui.i18n.t('pay.remove.confirm'), destructive: true,
  });
  if (ok) removeLigne(ligneId);
}

async function removeLigne(ligneId) {
  try {
    await api('DELETE', `/api/paiements/lignes/${ligneId}`);
    toast(ui.i18n.t('pay.removed'));
    await refreshAfterLinkChange();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function askDeletePayment(id) {
  const ok = await ui.alertDialog({
    title: ui.i18n.t('pay.delete_btn'),
    description: ui.i18n.t('pay.delete.desc'),
    confirmLabel: ui.i18n.t('pay.delete.confirm'), destructive: true,
  });
  if (ok) deletePayment(id);
}

async function deletePayment(id) {
  try {
    await api('DELETE', `/api/paiements/${id}`);
    toast(ui.i18n.t('pay.deleted'));
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
  const t = ui.i18n.t;
  const parts = [t('pay.picker.ticket', { n: i + 1 }), b.numero_billet ? t('pay.picker.no', { number: b.numero_billet }) : '',
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
    <div class="modal-header"><h3 id="ligne-link-title">${esc(ui.i18n.t('pay.picker.title', { number: ligne.numero_billet }))}</h3>
      <button class="modal-close" onclick="closeLinkPicker()" aria-label="${escAttr(ui.i18n.t('action.close'))}">${icons.x}</button></div>
    <div class="modal-body">
      <p class="pay-picker-ligne">${esc(ui.i18n.t('pay.picker.on_payment', { date: formatDate(ligne.date_billet) || ui.i18n.t('pay.picker.unknown_date'), plate: ligne.plaque || ui.i18n.t('pay.picker.unknown_plate'), qty: payQty(ligne.quantite), amount: payMoney(ligne.montant) }))}</p>
      ${ligne.candidats.length ? `<div class="pay-suggestions"><span class="form-label">${esc(ui.i18n.t('pay.picker.close'))}</span>
        ${ligne.candidats.map(c => `<button type="button" class="pay-suggestion" onclick="pickCandidate(${c.facture_id}, ${c.billet_index})">
          <strong>${esc(c.facture_numero)}</strong> ${esc(c.client_nom)}
          <span>${c.numero_billet ? `${esc(ui.i18n.t('pay.picker.no', { number: c.numero_billet }))} — ` : ''}${esc(formatDate(c.date_billet))} — ${esc(c.plaque)}</span>
        </button>`).join('')}</div>` : ''}
      <div class="form-group"><label class="form-label" for="ligne-link-facture-select">${esc(ui.i18n.t('pay.picker.invoice'))}</label>
        <select class="form-select" id="ligne-link-facture-select" onchange="fillPickerBillets()">
          <option value="">${esc(ui.i18n.t('pay.picker.choose_invoice'))}</option>
          ${suggested.size ? `<optgroup label="${escAttr(ui.i18n.t('pay.picker.suggested'))}">${pay.pickerFactures.filter(f => suggested.has(f.id)).map(option).join('')}</optgroup>` : ''}
          <optgroup label="${escAttr(ui.i18n.t('pay.picker.all_invoices'))}">${pay.pickerFactures.filter(f => !suggested.has(f.id)).map(option).join('')}</optgroup>
        </select></div>
      <div class="form-group"><label class="form-label" for="ligne-link-billet-select">${esc(ui.i18n.t('pay.picker.ticket_label'))}</label>
        <select class="form-select" id="ligne-link-billet-select" disabled><option value="">${esc(ui.i18n.t('pay.picker.invoice_first'))}</option></select></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeLinkPicker()">${esc(ui.i18n.t('action.cancel'))}</button>
      <button class="btn btn-primary" id="ligne-link-confirm" onclick="confirmLink(${ligne.id})">${micon('link')} ${esc(ui.i18n.t('pay.picker.confirm'))}</button>
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
    : `<option value="">${esc(ui.i18n.t(facture ? 'pay.picker.no_ticket' : 'pay.picker.invoice_first'))}</option>`;
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
  if (!factureId || billetIndex === '') { toast(ui.i18n.t('pay.picker.choose_both'), 'error'); return; }
  try {
    await api('PUT', `/api/paiements/lignes/${ligneId}`, { facture_id: factureId, billet_index: Number(billetIndex) });
    closeLinkPicker(false);
    toast(ui.i18n.t('pay.picker.linked'));
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
      toast(ui.i18n.t('pay.badge_load_failed', { error: e.message }), 'error');
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
    title="${escAttr(ui.i18n.t('pay.badge.open'))}">${micon('check_circle', true)} ${esc(ui.i18n.t('pay.badge.paid', { ref: info.reference }))}</button>`;
}

ui.hydrate.register(() => { if (document.querySelector('.pay-more')) bindLigneMenus(); });
