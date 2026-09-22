// ── FACTURE: page markup ────────────────────────────────
// Nouvelle facture / Modifier la facture. Two columns on wide screens: the form
// on the left, a sticky live summary on the right, a sticky action bar below.
// Every quoted attribute goes through escAttr/numAttr/dateAttr (util.js).

function factureEmptyState() {
  return `<div class="page">
    <header class="page-head"><div><h2>Nouvelle facture</h2><p>Créez d'abord un client pour pouvoir facturer.</p></div></header>
    <div class="card"><div class="empty-state">
      ${icons.users}
      <h3>Aucun client</h3>
      <p>Ajoutez d'abord un client avant de créer une facture.</p>
      <button class="btn btn-primary" style="margin-top:16px" onclick="navigate('clients')">${icons.plus} Ajouter un client</button>
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
        <h2>${editing ? `Modifier la facture ${esc(f.numero)}` : 'Nouvelle facture'}</h2>
        <p>${editing ? 'Modifiez les billets puis régénérez les fichiers Excel et PDF.' : 'Renseignez le client et les billets, le total se calcule en direct.'}</p>
      </div>
      ${editing ? `<span class="badge badge-warning">${icon('pencil', { size: 'xs' })} Modification en cours</span>` : ''}
    </header>
    <div class="fac-layout">
      <div class="fac-main">
        ${renderFactureMeta(editing)}
        <section class="fac-billets" aria-labelledby="fac-billets-title">
          <div class="fac-section-head">
            <h3 id="fac-billets-title">Billets <span class="badge badge-secondary" id="fac-billets-count">${billets.length}</span></h3>
            <div class="fac-section-actions">
              <button type="button" class="btn btn-outline btn-sm" onclick="openAiQuickAdd()" data-tip="Lire un billet avec l'IA locale">${icon('sparkles', { size: 'sm' })} Ajouter avec l'IA</button>
              <button type="button" class="btn btn-outline btn-sm" onclick="addBillet()">${icon('plus', { size: 'sm' })} Ajouter un billet</button>
            </div>
          </div>
          <div id="billets-container">${billets.map((b, i) => renderBilletCard(b, i)).join('')}</div>
          <button type="button" class="btn-add-billet" onclick="addBillet()">${icon('plus', { size: 'sm' })} Ajouter un billet</button>
        </section>
        <div id="totals-area" data-mode="${invoiceDiscountMode()}">${renderInvoiceDiscount()}</div>
        <div id="split-banner-area">${splitBannerHtml()}</div>
      </div>
      <aside class="fac-aside" aria-label="Résumé de la facture">
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
      <h3 id="fac-info-title">Informations</h3>
      <p>Le client, le numéro et la date qui figureront sur la facture.</p>
    </header>
    <div class="fac-meta">
      <div class="field fac-field-client">
        <label class="form-label" for="fac-client">Client</label>
        <select class="form-select" id="fac-client" onchange="onClientChange()" ${editing ? 'disabled' : ''}>
          <option value="">Choisir un client…</option>${options}
        </select>
        <div class="form-hint" id="fac-client-hint">${clientHintText()}</div>
      </div>
      <div class="field">
        <label class="form-label" for="fac-numero">N° de facture</label>
        <div class="input-group">
          <span class="input-group-addon" aria-hidden="true">N°</span>
          <input class="form-input" id="fac-numero" value="${escAttr(f.numero)}" placeholder="Auto">
        </div>
        <div class="form-hint">${editing ? 'Modifiable — le fichier sera renommé.' : 'Laissez « Auto » pour suivre la numérotation du client.'}</div>
      </div>
      <div class="field">
        <label class="form-label" for="fac-date">Date</label>
        <input class="form-input" id="fac-date" type="date" value="${dateAttr(f.date)}">
        <div class="form-hint">Date de la facture.</div>
      </div>
    </div>
  </section>`;
}

function clientHintText() {
  const c = currentFactureClient();
  if (!c) return 'Sélectionnez le client à facturer.';
  const rate = c.taux_defaut > 0 ? `Taux par défaut ${money(Number(c.taux_defaut))}/h` : 'Aucun taux par défaut';
  return `${esc(rate)}${c.separer_chantiers ? ' · une facture par chantier' : ''}`;
}

function refreshClientHint() {
  const el = document.getElementById('fac-client-hint');
  if (el) el.innerHTML = clientHintText();
}

function renderActionBar(editing) {
  const total = money(summaryModel().total);
  const left = editing
    ? `<button type="button" class="btn btn-danger-ghost" id="btn-delete-facture" onclick="confirmDeleteFacture(${state.editingId})">${icons.trash} <span class="btn-label">Supprimer</span></button>`
    : `<button type="button" class="btn btn-ghost" id="btn-reset-facture" onclick="resetFacture()" data-tip="Vider le formulaire" aria-label="Réinitialiser">${icon('rotate-ccw', { size: 'sm' })} <span class="btn-label">Réinitialiser</span></button>`;
  const main = editing
    ? `<button type="button" class="btn btn-ghost" onclick="cancelEdit()">Annuler</button>
       <button type="button" class="btn btn-primary btn-lg" id="btn-generate" onclick="generateFacture()">${icons.edit} <span>Mettre à jour<span class="btn-hide-sm"> la facture</span></span></button>`
    : `<button type="button" class="btn btn-primary btn-lg" id="btn-generate" onclick="generateFacture()">${icons.download} <span>Générer<span class="btn-hide-sm"> la facture Excel</span></span></button>`;
  return `<div class="fac-actionbar" role="toolbar" aria-label="Actions de la facture">
    <div class="fac-actionbar-left">${left}</div>
    <div class="fac-actionbar-total"><span>Total dû</span><strong data-fac-total-mini>${total}</strong></div>
    <div class="fac-actionbar-main">${main}</div>
  </div>`;
}

// ── Billet card ─────────────────────────────────────────

function renderBilletCard(b, i) {
  const scan = linkedScan(b);
  const tip = scan ? `Facture scannée liée : ${scan.nom_original}` : 'Lier une facture scannée';
  return `<article class="billet-card card" data-idx="${i}" aria-label="Billet ${i + 1}">
    <header class="billet-header">
      <span class="billet-index" aria-hidden="true">${i + 1}</span>
      <div class="billet-title">
        <span class="billet-number">Billet ${i + 1}</span>
        ${typeof billetPaymentBadge === 'function' ? billetPaymentBadge(b, i) : ''}
      </div>
      <div class="billet-header-actions">
        <button type="button" class="billet-attach ${scan ? 'is-linked' : ''}" onclick="openScanPicker(${i})"
          data-tip="${escAttr(tip)}" aria-label="${escAttr(tip)}">
          ${icon('paperclip', { size: 'sm' })}${scan ? `<span class="billet-attach-name">${esc(scan.nom_original)}</span>` : ''}
        </button>
        <div class="seg seg-labeled" role="group" aria-label="Type de description">
          <button type="button" class="seg-btn ${!b.desc_libre ? 'active' : ''}" aria-pressed="${!b.desc_libre}" onclick="setBilletDescMode(${i}, false)">Détails</button>
          <button type="button" class="seg-btn ${b.desc_libre ? 'active' : ''}" aria-pressed="${!!b.desc_libre}" onclick="setBilletDescMode(${i}, true)">Description libre</button>
        </div>
        ${billets.length > 1 ? `<button type="button" class="billet-remove" onclick="removeBillet(${i})" data-tip="Retirer ce billet" aria-label="Retirer le billet ${i + 1}">${icons.x}</button>` : ''}
      </div>
    </header>
    <div class="billet-body">${b.desc_libre ? renderBilletFree(b, i) : renderBilletStructured(b, i)}</div>
    ${renderBilletDiscount(b, i)}
  </article>`;
}

function qtyRateFields(b, i, unit) {
  return `<div class="field">
      <label class="form-label" for="b${i}-quantite">Quantité${unit ? ' (heures)' : ''}</label>
      <div class="input-group">
        <input class="form-input billet-input num-input" id="b${i}-quantite" data-idx="${i}" data-field="quantite" type="number" step="0.25" min="0" inputmode="decimal" placeholder="0.00" value="${numAttr(b.quantite)}">
        ${unit ? '<span class="input-group-addon" aria-hidden="true">h</span>' : ''}
      </div>
    </div>
    <div class="field">
      <label class="form-label" for="b${i}-taux">Taux${unit ? ' horaire' : ''}</label>
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
        <label class="form-label" for="b${i}-date">Date du billet</label>
        <input class="form-input billet-input" id="b${i}-date" data-idx="${i}" data-field="date_billet" type="date" value="${dateAttr(b.date_billet)}">
      </div>
      <div class="field">
        <label class="form-label" for="b${i}-chantier">Chantier / Client</label>
        <input class="form-input billet-input ac-input" id="b${i}-chantier" data-idx="${i}" data-field="chantier" data-ac="chantier" autocomplete="off" spellcheck="false" role="combobox" aria-expanded="false" placeholder="ex: Chantier Nord" value="${escAttr(b.chantier)}">
        ${aiFixHtml(b, i, 'chantier')}
      </div>
      <div class="field">
        <label class="form-label" for="b${i}-plaque">Plaque</label>
        <input class="form-input billet-input ac-input" id="b${i}-plaque" data-idx="${i}" data-field="plaque" data-ac="plaque" autocomplete="off" spellcheck="false" autocapitalize="characters" role="combobox" aria-expanded="false" placeholder="ex: A123456" value="${escAttr(b.plaque)}">
        ${aiFixHtml(b, i, 'plaque')}
      </div>
    </div>
    <div class="fac-grid-3">
      <div class="field">
        <label class="form-label" for="b${i}-numero">N° Billet</label>
        <input class="form-input billet-input numero-billet-input${isDup ? ' input-error' : ''}" id="b${i}-numero" data-idx="${i}" data-field="numero_billet" placeholder="ex: 30930" value="${escAttr(b.numero_billet)}">
        <div class="dup-warning" data-idx="${i}" role="alert"${isDup ? '' : ' hidden'}>${icon('circle-alert', { size: 'xs' })} N° de billet en double sur cette facture</div>
        ${aiFixHtml(b, i, 'numero_billet')}
      </div>
      ${qtyRateFields(b, i, true)}
    </div>`;
}

function renderBilletFree(b, i) {
  return `<div class="field">
      <label class="form-label" for="b${i}-desc">Description</label>
      <textarea class="form-input billet-input billet-desc" id="b${i}-desc" data-idx="${i}" data-field="description" rows="2" placeholder="ex: Réparation, transport spécial, location d'équipement...">${esc(b.description)}</textarea>
    </div>
    <div class="fac-grid-2">${qtyRateFields(b, i, false)}</div>`;
}

function setBilletDescMode(i, libre) {
  syncBilletInputs();
  billets[i].desc_libre = libre;
  render();
}
