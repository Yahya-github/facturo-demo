// ── FACTURE ─────────────────────────────────────────────

let billets = [emptyBillet()];

function emptyBillet() {
  // `corrections` and `remise_open` are display-only and never submitted:
  // generateFacture's payload is an explicit whitelist, so they cannot reach
  // billets_json.
  return { date_billet: '', chantier: '', plaque: '', numero_billet: '', description: '', desc_libre: false, quantite: '', taux: '', remise_pct: '', remise_montant: '', remise_open: false, scan_id: null, corrections: null };
}

// The scanned document a billet is linked to, or null (incl. dangling links
// whose scan was deleted).
function linkedScan(b) {
  if (!b || b.scan_id == null) return null;
  return state.scans.find(s => s.id === b.scan_id) || null;
}

// ── Duplicate "N° Billet" detection ─────────────────────
// Two billets on the same invoice must not share the same N° de billet.
// Blank numbers are ignored (an empty field isn't a real duplicate yet).

function dupKey(b) {
  // Free-description billets have no N° Billet field, so they never count.
  if (b.desc_libre) return '';
  return (b.numero_billet || '').trim();
}

// Returns the set of billet indices whose N° Billet appears more than once.
function duplicateBilletIndices() {
  const counts = {};
  billets.forEach(b => {
    const k = dupKey(b);
    if (k) counts[k] = (counts[k] || 0) + 1;
  });
  const dups = new Set();
  billets.forEach((b, i) => {
    const k = dupKey(b);
    if (k && counts[k] > 1) dups.add(i);
  });
  return dups;
}

// Toggle the red border + inline warning live, without a full re-render
// (so the field keeps focus while the user is typing).
function refreshDuplicateHighlights() {
  const dups = duplicateBilletIndices();
  $$('.numero-billet-input').forEach(input => {
    input.classList.toggle('input-error', dups.has(parseInt(input.dataset.idx)));
  });
  $$('.dup-warning').forEach(w => {
    w.hidden = !dups.has(parseInt(w.dataset.idx));
  });
}

// ── Split-by-chantier preview ───────────────────────────
// Mirrors the backend: when the selected client is flagged "separer_chantiers",
// generating splits into one invoice per distinct "Chantier / Client".

function currentFactureClient() {
  return state.clients.find(c => String(c.id) === String(state.facForm.clientId)) || null;
}

// Distinct chantier values among the billets, in first-seen order.
function chantierGroups() {
  const groups = [];
  billets.forEach(b => {
    const key = (b.chantier || '').trim();
    if (!groups.some(g => g.key === key)) {
      groups.push({ key, label: key || 'Sans chantier' });
    }
  });
  return groups;
}

function splitBannerHtml() {
  const c = currentFactureClient();
  if (!c || !c.separer_chantiers) return '';
  const groups = chantierGroups();
  if (groups.length < 2) return '';
  const labels = groups.map(g => `<span class="split-chip">${esc(g.label)}</span>`).join('');
  return `<div class="split-banner">
    ${micon('call_split')}
    <div class="split-banner-text">
      <strong>${groups.length} factures seront générées</strong> — une par chantier, toutes au nom de ${esc(c.nom)}.
      <div class="split-chips">${labels}</div>
    </div>
  </div>`;
}

function refreshSplitBanner() {
  const area = document.getElementById('split-banner-area');
  if (area) area.innerHTML = splitBannerHtml();
}

function downloadInvoice(filename) {
  const a = document.createElement('a');
  a.href = `/api/factures/download/${encodeURIComponent(filename)}`;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

function fmtPct(v) {
  const n = parseFloat(v) || 0;
  return `${n.toFixed(2).replace(/\.?0+$/, '')} %`;
}

function renderFacture() {
  if (state.clients.length === 0) {
    return `<div class="page">
      <div class="page-header"><div><h2>Nouvelle facture</h2></div></div>
      <div class="card"><div class="empty-state">
        ${icons.users}
        <h3>Aucun client</h3>
        <p>Ajoutez d'abord un client avant de créer une facture.</p>
        <button class="btn btn-primary" style="margin-top:16px" onclick="navigate('clients')">${icons.plus} Ajouter un client</button>
      </div></div>
    </div>`;
  }

  const f = state.facForm;
  const selectedId = f.clientId;
  const editing = state.editingId !== null;

  return `<div class="page">
    <div class="page-header">
      <div>
        <h2>${editing ? `Modifier la facture ${esc(f.numero)}` : 'Nouvelle facture'}</h2>
        <div class="subtitle">${editing ? 'Modifiez les billets puis régénérez les fichiers Excel et PDF' : 'Remplissez les informations et générez le fichier Excel'}</div>
      </div>
    </div>

    <div class="invoice-meta">
      <div class="meta-field">
        <label>Client</label>
        <select class="form-select" id="fac-client" onchange="onClientChange()" ${editing ? 'disabled' : ''}>
          <option value="">-- Choisir un client --</option>
          ${state.clients.map(c => `<option value="${escAttr(c.id)}" ${c.id == selectedId ? 'selected' : ''}>${esc(c.nom)}</option>`).join('')}
        </select>
      </div>
      <div class="meta-field">
        <label>N° de facture</label>
        <input class="form-input" id="fac-numero" value="${escAttr(f.numero)}" placeholder="Auto">
        ${editing ? '<div class="form-hint">Modifiable — le fichier sera renommé</div>' : ''}
      </div>
      <div class="meta-field">
        <label>Date</label>
        <input class="form-input" id="fac-date" type="date" value="${dateAttr(f.date)}">
      </div>
    </div>

    <h3 style="font-size:1.1rem; font-weight:700; margin-bottom:16px">Billets</h3>

    <div id="billets-container">
      ${billets.map((b, i) => renderBilletCard(b, i)).join('')}
    </div>

    <button type="button" class="btn-add-billet" onclick="addBillet()">${icons.plus} Ajouter un billet</button>
    <button type="button" class="btn-add-billet" onclick="openAiQuickAdd()">${micon('auto_awesome')} Ajouter avec l'IA</button>

    <div id="totals-area">
      ${renderInvoiceDiscount()}
      ${renderPreviewTotal()}
    </div>

    <div id="split-banner-area">${splitBannerHtml()}</div>

    <div style="margin-top:24px; display:flex; gap:12px; justify-content:flex-end">
      ${editing
        ? `<button class="btn btn-danger" style="margin-right:auto" onclick="confirmDeleteFacture(${state.editingId})">${icons.trash} Supprimer</button>
           <button class="btn btn-ghost" onclick="cancelEdit()">Annuler</button>
           <button class="btn btn-success btn-lg" id="btn-generate" onclick="generateFacture()">
             ${icons.edit} Mettre à jour la facture
           </button>`
        : `<button class="btn btn-ghost" onclick="billets=[emptyBillet()]; render()">Réinitialiser</button>
           <button class="btn btn-success btn-lg" id="btn-generate" onclick="generateFacture()">
             ${icons.download} Générer la facture Excel
           </button>`}
    </div>
  </div>`;
}

function renderBilletCard(b, i) {
  const scan = linkedScan(b);
  return `<div class="billet-card" data-idx="${i}">
    <div class="billet-header">
      <span class="billet-number">Billet ${i + 1}</span>
      ${typeof billetPaymentBadge === 'function' ? billetPaymentBadge(b, i) : ''}
      <div class="billet-header-actions">
        <button type="button" class="billet-attach ${scan ? 'is-linked' : ''}" onclick="openScanPicker(${i})"
          title="${scan ? 'Facture scannée liée : ' + esc(scan.nom_original) : 'Lier une facture scannée'}">
          ${micon('attach_file')}${scan ? `<span class="billet-attach-name">${esc(scan.nom_original)}</span>` : ''}
        </button>
        <div class="seg seg-labeled" role="group" aria-label="Type de description">
          <button type="button" class="seg-btn ${!b.desc_libre ? 'active' : ''}" onclick="setBilletDescMode(${i}, false)">Détails</button>
          <button type="button" class="seg-btn ${b.desc_libre ? 'active' : ''}" onclick="setBilletDescMode(${i}, true)">Description libre</button>
        </div>
        ${billets.length > 1 ? `<button class="billet-remove" onclick="removeBillet(${i})">${icons.x}</button>` : ''}
      </div>
    </div>
    ${b.desc_libre ? renderBilletFree(b, i) : renderBilletStructured(b, i)}
    ${renderBilletDiscount(b, i)}
  </div>`;
}

function renderBilletStructured(b, i) {
  const isDup = duplicateBilletIndices().has(i);
  return `<div class="billet-fields">
      <div class="form-group">
        <label class="form-label">Date du billet</label>
        <input class="form-input billet-input" data-idx="${i}" data-field="date_billet" type="date" value="${dateAttr(b.date_billet)}">
      </div>
      <div class="form-group">
        <label class="form-label">Chantier / Client</label>
        <input class="form-input billet-input ac-input" data-idx="${i}" data-field="chantier" data-ac="chantier" autocomplete="off" spellcheck="false" role="combobox" aria-expanded="false" placeholder="ex: Chantier Nord" value="${escAttr(b.chantier)}">
        ${aiFixHtml(b, i, 'chantier')}
      </div>
      <div class="form-group">
        <label class="form-label">Plaque</label>
        <input class="form-input billet-input ac-input" data-idx="${i}" data-field="plaque" data-ac="plaque" autocomplete="off" spellcheck="false" autocapitalize="characters" role="combobox" aria-expanded="false" placeholder="ex: A123456" value="${escAttr(b.plaque)}">
        ${aiFixHtml(b, i, 'plaque')}
      </div>
    </div>
    <div class="billet-fields-bottom">
      <div class="form-group">
        <label class="form-label">N° Billet</label>
        <input class="form-input billet-input numero-billet-input${isDup ? ' input-error' : ''}" data-idx="${i}" data-field="numero_billet" placeholder="ex: 30930" value="${escAttr(b.numero_billet)}">
        <div class="dup-warning" data-idx="${i}"${isDup ? '' : ' hidden'}>${micon('error')} N° de billet en double sur cette facture</div>
        ${aiFixHtml(b, i, 'numero_billet')}
      </div>
      <div class="form-group">
        <label class="form-label">Quantité (heures)</label>
        <input class="form-input billet-input" data-idx="${i}" data-field="quantite" type="number" step="0.25" min="0" placeholder="0.00" value="${numAttr(b.quantite)}">
      </div>
      <div class="form-group">
        <label class="form-label">Taux ($/h)</label>
        <input class="form-input billet-input" data-idx="${i}" data-field="taux" type="number" step="1" min="0" placeholder="0.00" value="${numAttr(b.taux)}">
      </div>
    </div>`;
}

function renderBilletFree(b, i) {
  return `<div class="form-group">
      <label class="form-label">Description</label>
      <textarea class="form-input billet-input billet-desc" data-idx="${i}" data-field="description" rows="2" placeholder="ex: Réparation, transport spécial, location d'équipement...">${esc(b.description)}</textarea>
    </div>
    <div class="billet-fields-2">
      <div class="form-group">
        <label class="form-label">Quantité</label>
        <input class="form-input billet-input" data-idx="${i}" data-field="quantite" type="number" step="0.25" min="0" placeholder="0.00" value="${numAttr(b.quantite)}">
      </div>
      <div class="form-group">
        <label class="form-label">Taux ($)</label>
        <input class="form-input billet-input" data-idx="${i}" data-field="taux" type="number" step="1" min="0" placeholder="0.00" value="${numAttr(b.taux)}">
      </div>
    </div>`;
}

function setBilletDescMode(i, libre) {
  syncBilletInputs();
  billets[i].desc_libre = libre;
  render();
}

// ── Lier un billet à une facture scannée ────────────────

function openScanPicker(i) {
  syncBilletInputs(); // keep typed values + the selected client current
  const clientId = parseInt(state.facForm.clientId) || null;
  const current = billets[i] ? billets[i].scan_id : null;

  let body;
  if (!clientId) {
    body = `<div class="scan-pick-empty">${micon('person_off')}<p>Choisissez d'abord un client pour cette facture.</p></div>`;
  } else {
    const scans = scansForClient(clientId);
    if (!scans.length) {
      body = `<div class="scan-pick-empty">${micon('document_scanner')}<p>Aucune facture scannée pour ce client. Importez-en dans « Factures scannées », puis revenez ici.</p></div>`;
    } else {
      body = `<div class="scan-pick-list">${scans.map(s => {
        const url = `/api/scans/file/${encodeURIComponent(s.fichier)}`;
        const thumb = isImageScan(s.fichier)
          ? `<img src="${url}" alt="" loading="lazy">`
          : `<div class="scan-pick-pdf">${micon('picture_as_pdf')}</div>`;
        const isCur = s.id === current;
        return `<div class="scan-pick ${isCur ? 'is-current' : ''}">
          <a class="scan-pick-thumb" href="${url}" target="_blank" rel="noopener" title="Ouvrir">${thumb}</a>
          <div class="scan-pick-info">
            <div class="scan-pick-name" title="${escAttr(s.nom_original)}">${esc(s.nom_original)}</div>
            <div class="scan-pick-date">${formatDateTime(s.cree_le)}</div>
          </div>
          ${isCur
            ? `<span class="scan-pick-cur">${micon('check')} Lié</span>
               <button class="btn btn-ghost btn-sm" onclick="setBilletScan(${i}, null)">Délier</button>`
            : `<button class="btn btn-primary btn-sm" onclick="setBilletScan(${i}, ${s.id})">Lier</button>`}
          ${isImageScan(s.fichier) ? `<button class="btn btn-ghost btn-sm" onclick="extractScanIntoBillet(${i}, ${s.id})">${micon('auto_awesome')} Extraire avec IA</button>` : ''}
        </div>`;
      }).join('')}</div>`;
    }
  }

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <h3>Lier une facture scannée — Billet ${i + 1}</h3>
        <button class="modal-close" onclick="closeModal(this.closest('.modal-overlay'))">${icons.x}</button>
      </div>
      <div class="modal-body">${body}</div>
      <div class="modal-footer">
        <button class="btn btn-ghost" onclick="closeModal(this.closest('.modal-overlay'))">Fermer</button>
      </div>
    </div>`;
  openModal(overlay);
}

function setBilletScan(i, scanId) {
  syncBilletInputs();
  if (billets[i]) billets[i].scan_id = scanId;
  closeAllModals();
  render();
  toast(scanId ? 'Facture scannée liée au billet' : 'Lien retiré');
}

// ── Extraction IA (Ollama local) ────────────────────────
// Always fills a row for the user to review/edit — never saves or generates
// an invoice on its own.

// Apply one extracted page onto an existing billet row, keeping whatever the
// user already typed when the model had nothing for that field.
function applyFieldsToBillet(b, fields, scanId) {
  b.date_billet = fields.date_billet || b.date_billet;
  b.chantier = fields.chantier || b.chantier;
  b.plaque = fields.plaque || b.plaque;
  b.numero_billet = fields.numero_billet || b.numero_billet;
  if (fields.quantite) b.quantite = String(fields.quantite);
  if (fields.taux) b.taux = String(fields.taux);
  if (fields.description) b.description = fields.description;
  b.corrections = fields.corrections && Object.keys(fields.corrections).length
    ? fields.corrections : null;
  if (scanId != null) b.scan_id = scanId;
}

// A scanned PDF holds one paper billet per page, so extraction returns a list:
// the first page fills the row the user clicked from, the rest are appended.
let extractingScan = false;

async function extractScanIntoBillet(billetIdx, scanId) {
  closeAllModals();
  if (extractingScan) {
    toast('Une extraction IA est déjà en cours, patientez.', 'error');
    return;
  }
  // The row is captured as an object, not an index: rows may be added or
  // removed while the model reads, and the whole invoice may be replaced.
  const list = billets;
  const editingAtStart = state.editingId;
  const clicked = list[billetIdx];
  extractingScan = true;
  toast('Extraction IA en cours… (un PDF de plusieurs pages peut prendre quelques minutes)');
  try {
    const { billets: pages } = await api('POST', '/api/ai/extract-scan', { scan_id: scanId });
    if (billets !== list || state.editingId !== editingAtStart) {
      toast("Extraction ignorée : la facture a changé pendant la lecture. Relancez l'extraction.", 'error');
      return;
    }
    syncBilletInputs();
    const ok = (pages || []).filter(p => !p.error);
    const failed = (pages || []).length - ok.length;
    if (!ok.length) { toast("L'IA n'a lu aucun billet dans ce document.", 'error'); return; }

    const target = billets.includes(clicked) ? clicked : null;
    if (target) applyFieldsToBillet(target, ok[0], scanId);
    // Paper billets almost never carry a rate, so rows added here need the
    // client's default the same way addBillet() gives it to a manual row.
    const client = currentFactureClient();
    for (const fields of ok.slice(target ? 1 : 0)) {
      const b = emptyBillet();
      if (client && client.taux_defaut > 0) b.taux = String(client.taux_defaut);
      applyFieldsToBillet(b, fields, scanId);
      billets.push(b);
    }
    render();
    toast(
      `${ok.length} billet(s) extrait(s)${failed ? `, ${failed} page(s) illisible(s)` : ''}` +
      ' — vérifiez avant de générer la facture.',
      failed ? 'error' : undefined
    );
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    extractingScan = false;
  }
}

function openAiQuickAdd() {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <h3>Ajouter un billet avec l'IA</h3>
        <button class="modal-close" onclick="closeModal(this.closest('.modal-overlay'))">${icons.x}</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label class="form-label">Photo ou PDF du billet</label>
          <input type="file" id="ai-quickadd-file" accept="image/*,.pdf" hidden>
          <button type="button" class="btn btn-ghost" id="ai-quickadd-file-btn">${micon('photo_camera')} Choisir un fichier</button>
          <span id="ai-quickadd-file-name" class="form-hint"></span>
          <div class="form-hint">Un PDF de plusieurs pages ajoute un billet par page.</div>
        </div>
        <div class="form-group">
          <label class="form-label">Ou décrivez le billet</label>
          <textarea class="form-input" id="ai-quickadd-text" rows="4"
            placeholder="ex: billet 4521, Loué à : Chantier Nord, plaque A123456, 5 heures à 95$ le 20 juillet"></textarea>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-ghost" onclick="closeModal(this.closest('.modal-overlay'))">Annuler</button>
        <button class="btn btn-primary" id="ai-quickadd-submit">${micon('auto_awesome')} Extraire</button>
      </div>
    </div>`;
  openModal(overlay);
  const fileInput = overlay.querySelector('#ai-quickadd-file');
  overlay.querySelector('#ai-quickadd-file-btn').addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {
    overlay.querySelector('#ai-quickadd-file-name').textContent = fileInput.files[0] ? fileInput.files[0].name : '';
  });
  overlay.querySelector('#ai-quickadd-submit').addEventListener('click', () => submitAiQuickAdd(overlay));
}

async function submitAiQuickAdd(overlay) {
  const file = overlay.querySelector('#ai-quickadd-file').files[0];
  const text = overlay.querySelector('#ai-quickadd-text').value.trim();
  if (!file && !text) { toast('Choisissez une photo ou entrez une description', 'error'); return; }
  const btn = overlay.querySelector('#ai-quickadd-submit');
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="loading-spinner"></span> Extraction…`;
  try {
    // A file may be a PDF holding a whole stack of billets, so the file path
    // yields a list; the free-text path always describes a single billet.
    let pages;
    if (file) {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch('/api/ai/extract-image', { method: 'POST', body: fd });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Erreur serveur' }));
        throw new Error(err.detail || 'Erreur');
      }
      pages = (await res.json()).billets || [];
    } else {
      pages = [await api('POST', '/api/ai/extract-text', { text })];
    }
    const ok = pages.filter(p => !p.error);
    const failed = pages.length - ok.length;
    if (!ok.length) throw new Error("L'IA n'a lu aucun billet dans ce document.");

    for (const fields of ok) {
      const overrides = {
        date_billet: fields.date_billet || '',
        chantier: fields.chantier || '',
        plaque: fields.plaque || '',
        numero_billet: fields.numero_billet || '',
        quantite: fields.quantite ? String(fields.quantite) : '',
      };
      if (fields.taux) overrides.taux = String(fields.taux);
      if (fields.description) overrides.description = fields.description;
      // Same as applyFieldsToBillet: this is the second, separate path AI
      // results reach a billet by, and both need the correction notes.
      if (fields.corrections && Object.keys(fields.corrections).length) {
        overrides.corrections = fields.corrections;
      }
      addBillet(overrides);
    }
    closeModal(overlay);
    toast(
      `${ok.length} billet(s) extrait(s)${failed ? `, ${failed} page(s) illisible(s)` : ''}` +
      ' — vérifiez avant de générer la facture.',
      failed ? 'error' : undefined
    );
  } catch (e) {
    toast(e.message, 'error');
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

// ── Discounts (remises) ────────────────────────────────
// Math lives in discounts.js (normalizeDiscount, billetGross, billetNet,
// invoiceTotals), the mirror of invoicing/discounts.py, so the preview always
// equals the generated invoice. A billet and the invoice each take a percent
// AND a fixed amount; the percent comes off first, the amount after.

function invoiceRemise() {
  return { remise_pct: state.facForm.remisePct, remise_montant: state.facForm.remiseMontant };
}

// A discount as an input value: blank when zero.
const formValue = n => (n ? String(n) : '');

// The % and $ inputs, side by side. `attrs(field)` returns the extra classes
// and attributes that wire each input to its billet or to the invoice.
function discountInputsHtml(who, [pct, montant], attrs) {
  return `<label class="discount-field">
      <span class="discount-field-label">Remise %</span>
      <input ${attrs('pct')} type="number" inputmode="decimal" min="0" max="100" step="any"
        placeholder="0" value="${numAttr(pct || '')}" aria-label="Remise en pourcentage — ${who}">
    </label>
    <label class="discount-field">
      <span class="discount-field-label">Remise $</span>
      <input ${attrs('montant')} type="number" inputmode="decimal" min="0" step="0.01"
        placeholder="0.00" value="${numAttr(montant || '')}" aria-label="Remise en dollars — ${who}">
    </label>`;
}

function billetNetText(b) {
  const gross = billetGross(b);
  const net = billetNet(b);
  return net < gross ? `−${money(gross - net)} → ${money(net)}` : '';
}

function renderBilletDiscount(b, i) {
  const values = normalizeDiscount(b);
  if (!b.remise_open && !values[0] && !values[1]) {
    return `<button type="button" class="discount-toggle" onclick="openBilletRemise(${i})">
      ${micon('sell')} Ajouter une remise sur ce billet
    </button>`;
  }
  const attrs = field =>
    `class="form-input discount-input billet-input billet-remise-input" data-idx="${i}" data-field="remise_${field}"`;
  return `<div class="discount-row">
    <span class="discount-tag">${micon('sell')} Remise</span>
    ${discountInputsHtml(`billet ${i + 1}`, values, attrs)}
    <span class="discount-net" data-idx="${i}" aria-live="polite">${billetNetText(b)}</span>
    <button type="button" class="discount-remove" onclick="removeBilletRemise(${i})"
      title="Retirer la remise" aria-label="Retirer la remise du billet ${i + 1}">${icons.x}</button>
  </div>`;
}

function renderInvoiceDiscount() {
  const f = state.facForm;
  const values = normalizeDiscount(invoiceRemise());
  const isSet = f.remiseOpen || values[0] || values[1];
  const grossSub = billets.reduce((s, b) => s + billetGross(b), 0);
  // Nothing to discount yet, and none requested: stay out of the way.
  if (grossSub === 0 && !isSet) return '';
  if (!isSet) {
    return `<button type="button" class="discount-toggle discount-toggle-invoice" onclick="openInvoiceRemise()">
      ${micon('sell')} Ajouter une remise sur toute la facture
    </button>`;
  }
  const attrs = field => `class="form-input discount-input" id="inv-remise-${field}"`;
  return `<div class="invoice-discount">
    <span class="discount-tag">${micon('sell')} Remise sur la facture</span>
    ${discountInputsHtml('toute la facture', values, attrs)}
    <span class="discount-hint">% du sous-total, puis $ une seule fois — avant taxes</span>
    <button type="button" class="discount-remove" onclick="removeInvoiceRemise()"
      title="Retirer la remise" aria-label="Retirer la remise sur la facture">${icons.x}</button>
  </div>`;
}

function renderPreviewTotal() {
  const grossSub = billets.reduce((s, b) => s + billetGross(b), 0);
  if (grossSub === 0) return '';

  const t = invoiceTotals(billets, invoiceRemise());
  const [pct] = normalizeDiscount(invoiceRemise());
  const remiseLine = (label, amount) => amount > 0
    ? `<div class="line remise-line"><span>${label}</span><span>−${money(amount)}</span></div>`
    : '';

  return `<div class="preview-total">
    <div class="line"><span>Sous-total</span><span>${money(t.sousTotal)}</span></div>
    ${remiseLine(`Remise (${fmtPct(pct)})`, t.remisePctAmount)}
    ${remiseLine('Remise ($)', t.remiseMontantAmount)}
    <div class="line"><span>TVQ (9.975%)</span><span>${money(t.tvq)}</span></div>
    <div class="line"><span>TPS (5%)</span><span>${money(t.tps)}</span></div>
    <div class="line grand-total"><span>Total dû</span><span>${money(t.total)}</span></div>
  </div>`;
}

// Open or clear a discount editor; `focusSel` names the input to focus after.
function setRemise(owner, fields, focusSel) {
  syncBilletInputs();
  Object.assign(owner, fields);
  render();
  if (focusSel) document.querySelector(focusSel)?.focus();
}

function openBilletRemise(i) {
  setRemise(billets[i], { remise_open: true }, `.billet-remise-input[data-idx="${i}"]`);
}

function removeBilletRemise(i) {
  setRemise(billets[i], { remise_pct: '', remise_montant: '', remise_open: false });
}

function openInvoiceRemise() {
  setRemise(state.facForm, { remiseOpen: true }, '#inv-remise-pct');
}

function removeInvoiceRemise() {
  setRemise(state.facForm, { remisePct: '', remiseMontant: '', remiseOpen: false });
}

// Called by core.js as quantity/rate change, and on every discount keystroke.
function updateBilletNet(i) {
  const span = document.querySelector(`.discount-net[data-idx="${i}"]`);
  if (span && billets[i]) span.textContent = billetNetText(billets[i]);
}

function updateTotalsArea() {
  const area = document.getElementById('totals-area');
  if (!area) return;
  area.innerHTML = renderInvoiceDiscount() + renderPreviewTotal();
  bindInvoiceDiscountEvents();
}

function updatePreviewOnly() {
  const area = document.getElementById('totals-area');
  if (!area) return;
  const existing = area.querySelector('.preview-total');
  const html = renderPreviewTotal();
  if (existing && html) existing.outerHTML = html;
  else if (existing && !html) existing.remove();
  else if (!existing && html) area.insertAdjacentHTML('beforeend', html);
}

function bindInvoiceDiscountEvents() {
  for (const [id, key] of [['inv-remise-pct', 'remisePct'], ['inv-remise-montant', 'remiseMontant']]) {
    const input = document.getElementById(id);
    if (!input) continue;
    input.addEventListener('input', () => {
      state.facForm[key] = input.value;
      state.facForm.remiseOpen = true; // keep the editor open while it's being cleared
      updatePreviewOnly();
    });
  }
}

// Called by core.js after every full render. core.js already stores each
// .billet-input value on the billet; this refreshes what the discount changes.
function bindTotalsEvents() {
  $$('.billet-remise-input').forEach(input => {
    input.addEventListener('input', () => {
      const i = parseInt(input.dataset.idx);
      if (!billets[i]) return;
      Object.assign(billets[i], { [input.dataset.field]: input.value, remise_open: true });
      updateBilletNet(i);
      updatePreviewOnly();
    });
  });
  bindInvoiceDiscountEvents();
}

function onClientChange() {
  const cid = $('#fac-client').value;
  state.facForm.clientId = cid;
  const client = state.clients.find(c => c.id == cid);
  if (client) {
    const num = `${client.prefix}${String(client.next_numero).padStart(3, '0')}`;
    $('#fac-numero').value = num;
    state.facForm.numero = num;
  }
  refreshSplitBanner();
}

function addBillet(overrides) {
  syncBilletInputs();
  const newBillet = emptyBillet();
  const client = currentFactureClient();
  if (client && client.taux_defaut > 0) newBillet.taux = String(client.taux_defaut);
  if (overrides) Object.assign(newBillet, overrides);
  billets.push(newBillet);
  render();
  const cards = $$('.billet-card');
  if (cards.length) cards[cards.length - 1].scrollIntoView({ behavior: 'smooth', block: 'center' });
  return billets.length - 1;
}

function removeBillet(idx) {
  syncBilletInputs();
  billets.splice(idx, 1);
  render();
}

function syncBilletInputs() {
  $$('.billet-input').forEach(input => {
    const i = parseInt(input.dataset.idx);
    const f = input.dataset.field;
    if (billets[i]) billets[i][f] = input.value;
  });
  const facClient = $('#fac-client');
  const facNumero = $('#fac-numero');
  const facDate = $('#fac-date');
  const invPct = $('#inv-remise-pct');
  const invMontant = $('#inv-remise-montant');
  if (facClient) state.facForm.clientId = facClient.value;
  if (facNumero) state.facForm.numero = facNumero.value;
  if (facDate) state.facForm.date = facDate.value;
  if (invPct) state.facForm.remisePct = invPct.value;
  if (invMontant) state.facForm.remiseMontant = invMontant.value;
}

let generating = false;

// A billet nobody has touched is the untouched starter row: skipped, not an error.
function isUntouchedBillet(b) {
  return ['date_billet', 'chantier', 'plaque', 'numero_billet', 'description', 'quantite', 'taux', 'remise_pct', 'remise_montant']
    .every(k => b[k] === undefined || b[k] === null || String(b[k]).trim() === '');
}

async function generateFacture() {
  if (generating) return;
  syncBilletInputs();
  const clientId = $('#fac-client')?.value;
  const numero = $('#fac-numero')?.value;
  const date = $('#fac-date')?.value;

  if (!clientId) { toast('Veuillez choisir un client', 'error'); return; }

  const touched = billets.filter(b => !isUntouchedBillet(b));
  if (touched.length === 0) { toast('Ajoutez au moins un billet avec quantité et taux', 'error'); return; }
  // Never drop a billet silently: a half-filled one would vanish from the invoice.
  const incomplete = incompleteBillets(touched);
  if (incomplete.length > 0) {
    const plural = incomplete.length > 1 ? 's' : '';
    toast(`Billet${plural} incomplet${plural} (quantité et taux requis) : ${incomplete.join(', ')}.`, 'error');
    return;
  }
  const validBillets = touched;

  // Refuse to generate while two billets share the same N° de billet.
  const dups = duplicateBilletIndices();
  if (dups.size > 0) {
    render(); // repaint so the duplicate fields show their red border + warning
    const first = document.querySelector('.numero-billet-input.input-error');
    if (first) { first.scrollIntoView({ behavior: 'smooth', block: 'center' }); first.focus(); }
    toast('N° de billet en double sur la facture. Corrigez-le avant de générer.', 'error');
    return;
  }

  generating = true;
  const btn = $('#btn-generate');
  const origHTML = btn.innerHTML;
  btn.innerHTML = '<span class="loading-spinner"></span> Génération...';
  btn.classList.add('btn-loading');
  btn.disabled = true;

  const editingId = state.editingId;

  try {
    const [remise_pct, remise_montant] = normalizeDiscount(invoiceRemise());
    const payload = {
      client_id: parseInt(clientId),
      numero: numero || null,
      date: date || null,
      billets: validBillets.map(b => {
        const [pct, montant] = normalizeDiscount(b);
        return {
          date_billet: b.date_billet,
          chantier: b.chantier,
          plaque: b.plaque,
          numero_billet: b.numero_billet,
          description: b.description || '',
          desc_libre: !!b.desc_libre,
          quantite: parseFloat(b.quantite),
          taux: parseFloat(b.taux),
          remise_pct: pct,
          remise_montant: montant,
          scan_id: b.scan_id ?? null,
        };
      }),
      remise_pct,
      remise_montant,
    };

    const result = editingId
      ? await api('PUT', `/api/factures/${editingId}`, payload)
      : await api('POST', '/api/factures/generate', payload);

    // Both generating and regenerating may split into several invoices.
    const invoices = result.invoices || [{ filename: result.filename, numero: result.numero }];

    if (editingId) {
      toast(invoices.length > 1
        ? `Facture séparée en ${invoices.length} factures !`
        : `Facture ${invoices[0].numero} mise à jour !`);
    } else {
      toast(invoices.length > 1
        ? `${invoices.length} factures générées !`
        : `Facture ${invoices[0].numero} générée !`);
    }

    // Trigger each download, spaced out so the browser allows the batch.
    for (let k = 0; k < invoices.length; k++) {
      downloadInvoice(invoices[k].filename);
      if (k < invoices.length - 1) await sleep(350);
    }

    state.editingId = null;
    billets = [emptyBillet()];
    state.facForm = blankFacForm();
    await loadData();
    if (editingId) {
      navigate('history');
    } else {
      render();
    }
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    generating = false;
    btn.innerHTML = origHTML;
    btn.classList.remove('btn-loading');
    btn.disabled = false;
  }
}

async function editFacture(id) {
  try {
    const f = await api('GET', `/api/factures/${id}`);
    // Opening a blank editor here would let "Mettre à jour" overwrite the
    // real invoice, so an unreadable one is not editable at all.
    if (f.billets_unreadable) {
      toast(`Impossible de modifier la facture ${f.numero} : ${f.billets_unreadable_reason}. `
        + "Le fichier d'origine n'a pas été modifié.", 'error');
      return;
    }
    state.editingId = id;
    // The API already returns v2 fields; normalizing again also covers any
    // legacy-only shape, so the editor always shows the effective discount.
    const [remisePct, remiseMontant] = normalizeDiscount(f).map(formValue);
    state.facForm = { clientId: String(f.client_id), numero: f.numero, date: f.date, remisePct, remiseMontant, remiseOpen: false };
    const loaded = (f.billets || []).map(b => {
      const [remise_pct, remise_montant] = normalizeDiscount(b).map(formValue);
      return {
        date_billet: b.date_billet || '',
        chantier: b.chantier || '',
        plaque: b.plaque || '',
        numero_billet: b.numero_billet || '',
        description: b.description || '',
        desc_libre: !!b.desc_libre,
        quantite: b.quantite != null ? String(b.quantite) : '',
        taux: b.taux != null ? String(b.taux) : '',
        remise_pct,
        remise_montant,
        remise_open: false,
        scan_id: b.scan_id ?? null,
      };
    });
    billets = loaded.length ? loaded : [emptyBillet()];
    navigate('facture');
  } catch (e) {
    toast(e.message, 'error');
  }
}

function cancelEdit() {
  state.editingId = null;
  billets = [emptyBillet()];
  state.facForm = blankFacForm();
  navigate('history');
}

function confirmDeleteFacture(id) {
  const numero = state.facForm.numero || '';
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal" style="max-width:440px">
      <div class="modal-header"><h3>Supprimer la facture</h3></div>
      <div class="modal-body">
        <p class="confirm-text">Voulez-vous vraiment supprimer la facture <strong>${esc(numero)}</strong> ? Le fichier Excel/PDF généré sera aussi supprimé. Cette action est irréversible.</p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-ghost" onclick="closeModal(this.closest('.modal-overlay'))">Annuler</button>
        <button class="btn btn-danger" id="confirm-del-fac">Supprimer</button>
      </div>
    </div>
  `;
  openModal(overlay);
  $('#confirm-del-fac').addEventListener('click', async () => {
    try {
      await api('DELETE', `/api/factures/${id}`);
      closeModal(overlay);
      toast('Facture supprimée');
      state.editingId = null;
      billets = [emptyBillet()];
      state.facForm = blankFacForm();
      await loadData();
      navigate('history');
    } catch (e) {
      toast(e.message, 'error');
    }
  });
}

function newFacture() {
  state.editingId = null;
  billets = [emptyBillet()];
  state.facForm = blankFacForm();
  navigate('facture');
}
