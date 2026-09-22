// ── FACTURE: scanned documents and AI extraction ───────────────────────
// The scan picker is a Sheet, the AI quick-add a Dialog with a upzone and an
// indeterminate Progress bar. Extraction always fills a row for the user to
// review — it never saves or generates an invoice on its own.

function scanPickRow(s, i, current) {
  const url = `/api/scans/file/${encodeURIComponent(s.fichier)}`;
  const thumb = isImageScan(s.fichier)
    ? `<img src="${url}" alt="" loading="lazy">`
    : `<div class="scan-pick-pdf">${icon('file-text')}</div>`;
  const isCur = s.id === current;
  return `<div class="scan-pick ${isCur ? 'is-current' : ''}">
    <a class="scan-pick-thumb" href="${url}" target="_blank" rel="noopener" data-tip="Ouvrir le document" aria-label="Ouvrir ${escAttr(s.nom_original)}">${thumb}</a>
    <div class="scan-pick-info">
      <div class="scan-pick-name" data-tip="${escAttr(s.nom_original)}">${esc(s.nom_original)}</div>
      <div class="scan-pick-date">${formatDateTime(s.cree_le)}</div>
      ${isCur ? `<span class="badge badge-warning scan-pick-cur">${icon('check', { size: 'xs' })} Lié à ce billet</span>` : ''}
    </div>
    <div class="scan-pick-actions">
      ${isCur
        ? `<button class="btn btn-ghost btn-sm" onclick="setBilletScan(${i}, null)">Délier</button>`
        : `<button class="btn btn-outline btn-sm" onclick="setBilletScan(${i}, ${s.id})">${icon('link', { size: 'xs' })} Lier</button>`}
      ${isImageScan(s.fichier) ? `<button class="btn btn-ghost btn-sm" onclick="extractScanIntoBillet(${i}, ${s.id})" data-tip="Lire ce document avec l'IA">${icon('sparkles', { size: 'xs' })} Extraire</button>` : ''}
    </div>
  </div>`;
}

function scanPickEmpty(iconName, text) {
  return `<div class="scan-pick-empty">${icon(iconName, { size: 'xl' })}<p>${text}</p></div>`;
}

function openScanPicker(i) {
  syncBilletInputs(); // keep typed values + the selected client current
  const clientId = parseInt(state.facForm.clientId) || null;
  const current = billets[i] ? billets[i].scan_id : null;

  let body;
  if (!clientId) {
    body = scanPickEmpty('user-x', "Choisissez d'abord un client pour cette facture.");
  } else {
    const scans = scansForClient(clientId);
    body = scans.length
      ? `<div class="scan-pick-list">${scans.map(s => scanPickRow(s, i, current)).join('')}</div>`
      : scanPickEmpty('scan-line', "Aucune facture scannée pour ce client. Importez-en dans « Factures scannées », puis revenez ici.");
  }
  const ctl = ui.sheet({
    title: `Lier une facture scannée — Billet ${i + 1}`,
    description: "Le document reste attaché au billet et s'ouvre depuis la facture.",
    body,
    footer: '<button type="button" class="btn btn-ghost" data-dialog-cancel>Fermer</button>',
    className: 'scan-sheet',
  });
  ctl.modal.querySelector('[data-dialog-cancel]').addEventListener('click', () => ctl.close());
}

function setBilletScan(i, scanId) {
  syncBilletInputs();
  if (billets[i]) billets[i].scan_id = scanId;
  closeAllModals();
  render();
  toast(scanId ? 'Facture scannée liée au billet' : 'Lien retiré');
}

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

// ── AI quick add ────────────────────────────────────────

function aiQuickAddBody() {
  return `<div class="field">
      <span class="form-label" id="ai-file-label">Photo ou PDF du billet</span>
      <input type="file" id="ai-quickadd-file" accept="image/*,.pdf" hidden>
      <button type="button" class="upzone" id="ai-quickadd-file-btn" aria-labelledby="ai-file-label ai-quickadd-file-name">
        <span class="upzone-icon">${icon('cloud-upload')}</span>
        <span class="upzone-title" id="ai-quickadd-file-name">Glissez un fichier ici ou <u>parcourez</u></span>
        <span class="upzone-hint">Photo ou PDF · un PDF de plusieurs pages ajoute un billet par page</span>
      </button>
    </div>
    <div class="or-rule"><span>ou</span></div>
    <div class="field">
      <label class="form-label" for="ai-quickadd-text">Décrivez le billet</label>
      <textarea class="form-input" id="ai-quickadd-text" rows="3"
        placeholder="ex: billet 4521, Loué à : Chantier Nord, plaque A123456, 5 heures à 95$ le 20 juillet"></textarea>
    </div>
    <div class="ai-progress" id="ai-quickadd-progress" hidden aria-live="polite">
      <div class="progress is-indeterminate" role="progressbar" aria-label="Extraction en cours"><span></span></div>
      <p>L'IA locale lit le billet… un PDF de plusieurs pages peut prendre quelques minutes.</p>
    </div>`;
}

function bindAiDropzone(zone, fileInput) {
  const label = zone.querySelector('.upzone-title');
  const idle = label.innerHTML;
  const showName = () => {
    const file = fileInput.files[0];
    zone.classList.toggle('has-file', !!file);
    if (file) label.textContent = file.name; else label.innerHTML = idle;
  };
  zone.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', showName);
  zone.addEventListener('dragenter', e => { e.preventDefault(); zone.classList.add('is-dragover'); });
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('is-dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('is-dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('is-dragover');
    if (e.dataTransfer && e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      showName();
    }
  });
}

function openAiQuickAdd() {
  const ctl = ui.dialog.show({
    title: "Ajouter un billet avec l'IA",
    description: 'Une photo, un PDF ou quelques mots suffisent. Vous relisez tout avant de générer.',
    body: aiQuickAddBody(),
    footer: `<div class="dialog-actions">
        <button type="button" class="btn btn-ghost" data-dialog-cancel>Annuler</button>
        <button type="button" class="btn btn-primary" id="ai-quickadd-submit">${icon('sparkles', { size: 'sm' })} Extraire</button>
      </div>`,
    className: 'ai-dialog',
  });
  const modal = ctl.modal;
  bindAiDropzone(modal.querySelector('#ai-quickadd-file-btn'), modal.querySelector('#ai-quickadd-file'));
  modal.querySelector('[data-dialog-cancel]').addEventListener('click', () => ctl.close());
  modal.querySelector('#ai-quickadd-submit').addEventListener('click', () => submitAiQuickAdd(ctl));
}

async function fetchAiPages(file, text) {
  // A file may be a PDF holding a whole stack of billets, so the file path
  // yields a list; the free-text path always describes a single billet.
  if (!file) return [await api('POST', '/api/ai/extract-text', { text })];
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/ai/extract-image', { method: 'POST', body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Erreur serveur' }));
    throw new Error(err.detail || 'Erreur');
  }
  return (await res.json()).billets || [];
}

function billetOverridesFromAi(fields) {
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
  return overrides;
}

function setAiBusy(modal, busy) {
  modal.querySelector('#ai-quickadd-progress').hidden = !busy;
  modal.querySelectorAll('textarea, .upzone').forEach(el => { el.disabled = busy; });
  const btn = modal.querySelector('#ai-quickadd-submit');
  btn.disabled = busy;
  btn.classList.toggle('btn-loading', busy);
}

async function submitAiQuickAdd(ctl) {
  const modal = ctl.modal;
  const file = modal.querySelector('#ai-quickadd-file').files[0];
  const text = modal.querySelector('#ai-quickadd-text').value.trim();
  if (!file && !text) { toast('Choisissez une photo ou entrez une description', 'error'); return; }
  setAiBusy(modal, true);
  try {
    const pages = await fetchAiPages(file, text);
    const ok = pages.filter(p => !p.error);
    const failed = pages.length - ok.length;
    if (!ok.length) throw new Error("L'IA n'a lu aucun billet dans ce document.");
    for (const fields of ok) addBillet(billetOverridesFromAi(fields));
    ctl.close();
    toast(
      `${ok.length} billet(s) extrait(s)${failed ? `, ${failed} page(s) illisible(s)` : ''}` +
      ' — vérifiez avant de générer la facture.',
      failed ? 'error' : undefined
    );
  } catch (e) {
    toast(e.message, 'error');
    setAiBusy(modal, false);
  }
}
