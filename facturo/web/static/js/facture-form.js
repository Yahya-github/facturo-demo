// ── FACTURE: page markup ────────────────────────────────
// Nouvelle facture / Modifier la facture. Two columns on wide screens: the form
// on the left, a sticky live summary on the right, a sticky action bar below.
// Every quoted attribute goes through escAttr/numAttr/dateAttr (util.js).

const tFac = (key, params) => ui.i18n.t(key, params);

function factureEmptyState() {
  return `<div class="page">
    <header class="page-head"><div><h2>${esc(tFac('nav.facture'))}</h2><p>${esc(tFac('facture.empty.lead'))}</p></div></header>
    <div class="card"><div class="empty-state">
      ${icons.users}
      <h3>${esc(tFac('facture.empty.title'))}</h3>
      <p>${esc(tFac('facture.empty.desc'))}</p>
      <button class="btn btn-primary" style="margin-top:16px" onclick="navigate('clients')">${icons.plus} ${esc(tFac('clients.add'))}</button>
    </div></div>
  </div>`;
}

function renderFacture() {
  if (state.clients.length === 0) return factureEmptyState();
  const editing = state.editingId !== null;
  const f = state.facForm;
  facSummary.last = summaryModel().total;
  return `<div class="page page-wide fac-page">
    <header class="page-head">
      <div>
        <h2>${esc(editing ? tFac('facture.title_edit', { numero: f.numero }) : tFac('nav.facture'))}</h2>
        <p>${esc(tFac(editing ? 'facture.lead_edit' : 'facture.lead_new'))}</p>
      </div>
      ${editing ? `<span class="badge badge-warning">${icon('pencil', { size: 'xs' })} ${esc(tFac('facture.editing_badge'))}</span>` : ''}
    </header>
    <div class="fac-layout">
      <div class="fac-main">
        ${renderFactureMeta(editing)}
        <section class="fac-billets" aria-labelledby="fac-billets-title">
          <div class="fac-section-head">
            <h3 id="fac-billets-title">${esc(tFac('facture.billets'))} <span class="badge badge-secondary" id="fac-billets-count">${billets.length}</span></h3>
            <div class="fac-section-actions">
              <button type="button" class="btn btn-outline btn-sm" onclick="openAiQuickAdd()" data-tip="${escAttr(tFac('facture.ai.tip'))}">${icon('sparkles', { size: 'sm' })} ${esc(tFac('facture.ai.add'))}</button>
              <button type="button" class="btn btn-outline btn-sm" onclick="addBillet()">${icon('plus', { size: 'sm' })} ${esc(tFac('facture.billet.add'))}</button>
            </div>
          </div>
          <div id="billets-container">${billets.map((b, i) => renderBilletCard(b, i)).join('')}</div>
          <button type="button" class="btn-add-billet" onclick="addBillet()">${icon('plus', { size: 'sm' })} ${esc(tFac('facture.billet.add'))}</button>
        </section>
        <div id="totals-area" data-mode="${invoiceDiscountMode()}">${renderInvoiceDiscount()}</div>
        <div id="split-banner-area">${splitBannerHtml()}</div>
      </div>
      <aside class="fac-aside" aria-label="${escAttr(tFac('facture.summary.aria'))}">
        <div class="fac-summary" id="fac-summary">${renderSummary()}</div>
      </aside>
    </div>
    ${renderActionBar(editing)}
  </div>`;
}

function renderFactureMeta(editing) {
  const f = state.facForm;
  const options = state.clients.map(c =>
    `<option value="${escAttr(c.id)}" ${c.id == f.clientId ? 'selected' : ''}>${esc(c.nom)}</option>`).join('');
  return `<section class="card fac-card" aria-labelledby="fac-info-title">
    <header class="fac-card-head">
      <h3 id="fac-info-title">${esc(tFac('facture.meta.title'))}</h3>
      <p>${esc(tFac('facture.meta.desc'))}</p>
    </header>
    <div class="fac-meta">
      <div class="field fac-field-client">
        <label class="form-label" for="fac-client">${esc(tFac('facture.meta.client'))}</label>
        <select class="form-select" id="fac-client" onchange="onClientChange()" ${editing ? 'disabled' : ''}>
          <option value="">${esc(tFac('facture.meta.pick_client'))}</option>${options}
        </select>
        <div class="form-hint" id="fac-client-hint">${clientHintText()}</div>
      </div>
      <div class="field">
        <label class="form-label" for="fac-numero">${esc(tFac('facture.meta.numero'))}</label>
        <div class="input-group">
          <span class="input-group-addon" aria-hidden="true">N°</span>
          <input class="form-input" id="fac-numero" value="${escAttr(f.numero)}" placeholder="${escAttr(tFac('facture.meta.numero_ph'))}">
        </div>
        <div class="form-hint">${esc(tFac(editing ? 'facture.meta.numero_hint_edit' : 'facture.meta.numero_hint'))}</div>
      </div>
      <div class="field">
        <label class="form-label" for="fac-date">${esc(tFac('facture.meta.date'))}</label>
        <input class="form-input" id="fac-date" type="date" value="${dateAttr(f.date)}">
        <div class="form-hint">${esc(tFac('facture.meta.date_hint'))}</div>
      </div>
    </div>
  </section>`;
}

function clientHintText() {
  const c = currentFactureClient();
  if (!c) return esc(tFac('facture.client.select'));
  const rate = c.taux_defaut > 0 ? tFac('facture.client.rate_default', { rate: money(Number(c.taux_defaut)) }) : tFac('facture.client.no_rate');
  return `${esc(rate)}${c.separer_chantiers ? ` · ${esc(tFac('facture.client.split_hint'))}` : ''}`;
}

function refreshClientHint() {
  const el = document.getElementById('fac-client-hint');
  if (el) el.innerHTML = clientHintText();
}

function renderActionBar(editing) {
  const total = money(summaryModel().total);
  const left = editing
    ? `<button type="button" class="btn btn-danger-ghost" id="btn-delete-facture" onclick="confirmDeleteFacture(${state.editingId})">${icons.trash} <span class="btn-label">${esc(tFac('action.delete'))}</span></button>`
    : `<button type="button" class="btn btn-ghost" id="btn-reset-facture" onclick="resetFacture()" data-tip="${escAttr(tFac('facture.reset_tip'))}" aria-label="${escAttr(tFac('facture.reset'))}">${icon('rotate-ccw', { size: 'sm' })} <span class="btn-label">${esc(tFac('facture.reset'))}</span></button>`;
  const main = editing
    ? `<button type="button" class="btn btn-ghost" onclick="cancelEdit()">${esc(tFac('action.cancel'))}</button>
       <button type="button" class="btn btn-primary btn-lg" id="btn-generate" onclick="generateFacture()">${icons.edit} <span>${esc(tFac('facture.update'))}<span class="btn-hide-sm">${esc(tFac('facture.update_rest'))}</span></span></button>`
    : `<button type="button" class="btn btn-primary btn-lg" id="btn-generate" onclick="generateFacture()">${icons.download} <span>${esc(tFac('facture.generate'))}<span class="btn-hide-sm">${esc(tFac('facture.generate_rest'))}</span></span></button>`;
  return `<div class="fac-actionbar" role="toolbar" aria-label="${escAttr(tFac('facture.actions_aria'))}">
    <div class="fac-actionbar-left">${left}</div>
    <div class="fac-actionbar-total"><span>${esc(tFac('facture.total_due'))}</span><strong data-fac-total-mini>${total}</strong></div>
    <div class="fac-actionbar-main">${main}</div>
  </div>`;
}

// ── Billet card ─────────────────────────────────────────

function renderBilletCard(b, i) {
  const scan = linkedScan(b);
  const tip = scan ? tFac('facture.scan.linked_tip', { name: scan.nom_original }) : tFac('facture.scan.link_tip');
  return `<article class="billet-card card" data-idx="${i}" aria-label="${escAttr(tFac('facture.billet.n', { n: i + 1 }))}">
    <header class="billet-header">
      <span class="billet-index" aria-hidden="true">${i + 1}</span>
      <div class="billet-title">
        <span class="billet-number">${esc(tFac('facture.billet.n', { n: i + 1 }))}</span>
        ${typeof billetPaymentBadge === 'function' ? billetPaymentBadge(b, i) : ''}
      </div>
      <div class="billet-header-actions">
        <button type="button" class="billet-attach ${scan ? 'is-linked' : ''}" onclick="openScanPicker(${i})"
          data-tip="${escAttr(tip)}" aria-label="${escAttr(tip)}">
          ${icon('paperclip', { size: 'sm' })}${scan ? `<span class="billet-attach-name">${esc(scan.nom_original)}</span>` : ''}
        </button>
        <div class="seg seg-labeled" role="group" aria-label="${escAttr(tFac('facture.billet.mode_aria'))}">
          <button type="button" class="seg-btn ${!b.desc_libre ? 'active' : ''}" aria-pressed="${!b.desc_libre}" onclick="setBilletDescMode(${i}, false)">${esc(tFac('facture.billet.mode_details'))}</button>
          <button type="button" class="seg-btn ${b.desc_libre ? 'active' : ''}" aria-pressed="${!!b.desc_libre}" onclick="setBilletDescMode(${i}, true)">${esc(tFac('facture.billet.mode_free'))}</button>
        </div>
        ${billets.length > 1 ? `<button type="button" class="billet-remove" onclick="removeBillet(${i})" data-tip="${escAttr(tFac('facture.billet.remove_tip'))}" aria-label="${escAttr(tFac('facture.billet.remove_aria', { n: i + 1 }))}">${icons.x}</button>` : ''}
      </div>
    </header>
    <div class="billet-body">${b.desc_libre ? renderBilletFree(b, i) : renderBilletStructured(b, i)}</div>
    ${renderBilletDiscount(b, i)}
  </article>`;
}

function qtyRateFields(b, i, unit) {
  return `<div class="field">
      <label class="form-label" for="b${i}-quantite">${esc(tFac(unit ? 'facture.field.quantity_hours' : 'facture.field.quantity'))}</label>
      <div class="input-group">
        <input class="form-input billet-input num-input" id="b${i}-quantite" data-idx="${i}" data-field="quantite" type="number" step="0.25" min="0" inputmode="decimal" placeholder="0.00" value="${numAttr(b.quantite)}">
        ${unit ? '<span class="input-group-addon" aria-hidden="true">h</span>' : ''}
      </div>
    </div>
    <div class="field">
      <label class="form-label" for="b${i}-taux">${esc(tFac(unit ? 'facture.field.rate_hourly' : 'facture.field.rate'))}</label>
      <div class="input-group">
        <span class="input-group-addon" aria-hidden="true">$</span>
        <input class="form-input billet-input num-input" id="b${i}-taux" data-idx="${i}" data-field="taux" type="number" step="1" min="0" inputmode="decimal" placeholder="0.00" value="${numAttr(b.taux)}">
        ${unit ? '<span class="input-group-addon" aria-hidden="true">/h</span>' : ''}
      </div>
    </div>`;
}

function renderBilletStructured(b, i) {
  const isDup = duplicateBilletIndices().has(i);
  return `<div class="fac-grid-3">
      <div class="field">
        <label class="form-label" for="b${i}-date">${esc(tFac('facture.field.date'))}</label>
        <input class="form-input billet-input" id="b${i}-date" data-idx="${i}" data-field="date_billet" type="date" value="${dateAttr(b.date_billet)}">
      </div>
      <div class="field">
        <label class="form-label" for="b${i}-chantier">${esc(tFac('facture.field.worksite'))}</label>
        <input class="form-input billet-input ac-input" id="b${i}-chantier" data-idx="${i}" data-field="chantier" data-ac="chantier" autocomplete="off" spellcheck="false" role="combobox" aria-expanded="false" placeholder="${escAttr(tFac('facture.field.worksite_ph'))}" value="${escAttr(b.chantier)}">
        ${aiFixHtml(b, i, 'chantier')}
      </div>
      <div class="field">
        <label class="form-label" for="b${i}-plaque">${esc(tFac('facture.field.plate'))}</label>
        <input class="form-input billet-input ac-input" id="b${i}-plaque" data-idx="${i}" data-field="plaque" data-ac="plaque" autocomplete="off" spellcheck="false" autocapitalize="characters" role="combobox" aria-expanded="false" placeholder="${escAttr(tFac('facture.field.plate_ph'))}" value="${escAttr(b.plaque)}">
        ${aiFixHtml(b, i, 'plaque')}
      </div>
    </div>
    <div class="fac-grid-3">
      <div class="field">
        <label class="form-label" for="b${i}-numero">${esc(tFac('facture.field.number'))}</label>
        <input class="form-input billet-input numero-billet-input${isDup ? ' input-error' : ''}" id="b${i}-numero" data-idx="${i}" data-field="numero_billet" placeholder="${escAttr(tFac('facture.field.number_ph'))}" value="${escAttr(b.numero_billet)}">
        <div class="dup-warning" data-idx="${i}" role="alert"${isDup ? '' : ' hidden'}>${icon('circle-alert', { size: 'xs' })} ${esc(tFac('facture.field.dup'))}</div>
        ${aiFixHtml(b, i, 'numero_billet')}
      </div>
      ${qtyRateFields(b, i, true)}
    </div>`;
}

function renderBilletFree(b, i) {
  return `<div class="field">
      <label class="form-label" for="b${i}-desc">${esc(tFac('facture.field.description'))}</label>
      <textarea class="form-input billet-input billet-desc" id="b${i}-desc" data-idx="${i}" data-field="description" rows="2" placeholder="${escAttr(tFac('facture.field.description_ph'))}">${esc(b.description)}</textarea>
    </div>
    <div class="fac-grid-2">${qtyRateFields(b, i, false)}</div>`;
}

function setBilletDescMode(i, libre) {
  syncBilletInputs();
  billets[i].desc_libre = libre;
  render();
}
