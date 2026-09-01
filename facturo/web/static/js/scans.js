// ── FACTURES SCANNÉES ───────────────────────────────────

state.scansQuery = '';

function openScans() {
  state.scansClientId = null;
  navigate('scans');
}

function scansForClient(clientId) {
  return state.scans.filter(s => s.client_id === clientId);
}

function isImageScan(fichier) {
  return /\.(png|jpe?g|webp|gif|heic)$/i.test(fichier || '');
}

function renderScans() {
  // Detail view: a single client's scanned invoices.
  if (state.scansClientId != null) return renderScansForClient(state.scansClientId);

  // Folder view: one card per client with its document count.
  if (state.clients.length === 0) {
    return `<div class="page">
      <div class="page-header"><div>
        <h2>Factures scannées</h2>
        <div class="subtitle">Classez vos factures numérisées par client</div>
      </div></div>
      <div class="card"><div class="empty-state">
        ${icons.users}
        <h3>Aucun client</h3>
        <p>Ajoutez un client avant d'importer des factures scannées.</p>
        <button class="btn btn-primary" style="margin-top:16px" onclick="navigate('clients')">${icons.plus} Ajouter un client</button>
      </div></div>
    </div>`;
  }

  const total = state.scans.length;
  const q = foldKey(state.scansQuery);
  const folders = state.clients.map(c => ({ client: c, key: foldKey(c.nom) }));
  const anyMatch = !q || folders.some(f => f.key.includes(q));
  return `<div class="page">
    <div class="page-header"><div>
      <h2>Factures scannées</h2>
      <div class="subtitle">${total} document${total > 1 ? 's' : ''} — classés par client</div>
    </div></div>
    <div class="flt-bar flt-bar-compact" role="search" aria-label="Rechercher un client">
      <div class="flt-field flt-field-search">
        <label class="flt-label" for="scans-search">Client</label>
        <div class="flt-search">
          ${icon('search')}
          <input id="scans-search" type="search" class="form-input" value="${escAttr(state.scansQuery)}"
            placeholder="Rechercher un client…" autocomplete="off" spellcheck="false" oninput="scansOnSearchInput(this.value)">
        </div>
      </div>
    </div>
    <div class="scan-folder-grid">
      ${folders.map(({ client: c, key }) => {
        const n = scansForClient(c.id).length;
        const hidden = q && !key.includes(q) ? ' hidden' : '';
        return `<button class="scan-folder" data-fold="${escAttr(key)}" onclick="openScanClient(${Number(c.id)})"${hidden}>
          <span class="scan-folder-icon">${micon('folder', n > 0)}</span>
          <span class="scan-folder-name">${esc(c.nom)}</span>
          <span class="scan-folder-count">${n} document${n > 1 ? 's' : ''}</span>
        </button>`;
      }).join('')}
    </div>
    <p class="flt-empty flt-empty-compact" id="scans-no-match"${anyMatch ? ' hidden' : ''}>Aucun client ne correspond à cette recherche.</p>
  </div>`;
}

/**
 * Client-name search over the folder grid. Toggles `hidden` in place rather
 * than re-rendering, so the input keeps focus and caret while typing.
 */
function scansOnSearchInput(value) {
  state.scansQuery = String(value || '').slice(0, 200);
  const q = foldKey(state.scansQuery);
  let shown = 0;
  $$('.scan-folder').forEach(btn => {
    const match = !q || (btn.dataset.fold || '').includes(q);
    btn.hidden = !match;
    if (match) shown++;
  });
  const none = document.getElementById('scans-no-match');
  if (none) none.hidden = shown > 0;
}

function renderScansForClient(clientId) {
  const client = state.clients.find(c => c.id === clientId);
  if (!client) { state.scansClientId = null; return renderScans(); }
  const scans = scansForClient(clientId);
  return `<div class="page">
    <div class="page-header">
      <div class="page-back">
        <button class="btn btn-ghost btn-sm" onclick="closeScanClient()">${micon('arrow_back')} Tous les clients</button>
        <h2>${esc(client.nom)}</h2>
        <div class="subtitle">${scans.length} facture${scans.length > 1 ? 's' : ''} scannée${scans.length > 1 ? 's' : ''}</div>
      </div>
      <button class="btn btn-primary" onclick="document.getElementById('scan-input').click()">${icons.upload} Importer des scans</button>
    </div>
    <input type="file" id="scan-input" accept="application/pdf,image/*" multiple style="display:none" onchange="uploadScans(this, ${clientId})">
    ${scans.length === 0 ? `
      <div class="card"><div class="empty-state">
        ${micon('document_scanner')}
        <h3>Aucune facture scannée</h3>
        <p>Importez des PDF ou des photos de factures pour ce client.</p>
        <button class="btn btn-primary" style="margin-top:16px" onclick="document.getElementById('scan-input').click()">${icons.upload} Importer des scans</button>
      </div></div>
    ` : `
      <div class="scan-grid">${scans.map(renderScanCard).join('')}</div>
    `}
  </div>`;
}

function renderScanCard(s) {
  const url = `/api/scans/file/${encodeURIComponent(s.fichier)}`;
  const thumb = isImageScan(s.fichier)
    ? `<img src="${url}" alt="${escAttr(s.nom_original)}" loading="lazy">`
    : `<div class="scan-thumb-pdf">${micon('picture_as_pdf')}<span>PDF</span></div>`;
  return `<div class="scan-card">
    <a class="scan-thumb" href="${url}" target="_blank" rel="noopener" title="Ouvrir">${thumb}</a>
    <div class="scan-card-body">
      <div class="scan-name" title="${escAttr(s.nom_original)}">${esc(s.nom_original)}</div>
      <div class="scan-date">${formatDateTime(s.cree_le)}</div>
    </div>
    <div class="scan-actions">
      <a class="btn btn-ghost btn-sm" href="${url}" target="_blank" rel="noopener">${micon('visibility')} Voir</a>
      <a class="btn btn-ghost btn-sm" href="${url}" download="${escAttr(s.nom_original)}" title="Télécharger">${icons.download}</a>
      <button class="btn btn-ghost btn-sm" style="color:var(--red-600)" onclick="deleteScan(${s.id})" title="Supprimer">${icons.trash}</button>
    </div>
  </div>`;
}

function openScanClient(clientId) { state.scansClientId = clientId; render(); }
function closeScanClient() { state.scansClientId = null; render(); }

async function uploadScans(input, clientId) {
  const files = [...(input.files || [])];
  if (!files.length) return;
  let ok = 0;
  for (const file of files) {
    const fd = new FormData();
    fd.append('client_id', clientId);
    fd.append('file', file);
    try {
      const res = await fetch('/api/scans', { method: 'POST', body: fd });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Erreur serveur' }));
        throw new Error(err.detail || 'Échec du téléversement');
      }
      ok++;
    } catch (e) {
      toast(`${file.name}: ${e.message}`, 'error');
    }
  }
  input.value = '';
  if (ok) {
    toast(`${ok} document${ok > 1 ? 's' : ''} importé${ok > 1 ? 's' : ''}`);
    await loadData();
    render();
  }
}

async function deleteScan(id) {
  if (!confirm('Supprimer cette facture scannée ?')) return;
  try {
    await api('DELETE', `/api/scans/${id}`);
    toast('Document supprimé');
    await loadData();
    render();
  } catch (e) {
    toast(e.message, 'error');
  }
}
