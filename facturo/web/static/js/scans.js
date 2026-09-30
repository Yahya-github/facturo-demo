// ── SCANNED INVOICES ────────────────────────────────────

state.scansQuery = '';

const SCAN_ACCEPT_RE = /\.(pdf|png|jpe?g|webp|gif|heic)$/i;

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

// ── Folder view ─────────────────────────────────────────

function renderScansHead(subtitle, actions) {
  return `<div class="page-head">
    <div><h2>${esc(ui.i18n.t('nav.scans'))}</h2><p>${subtitle}</p></div>
    ${actions ? `<div class="page-head-actions">${actions}</div>` : ''}
  </div>`;
}

function renderScansNoClient() {
  return `<div class="page page-wide scans">
    ${renderScansHead(esc(ui.i18n.t('scans.subtitle.pick')))}
    <div class="card"><div class="empty-state clients-empty">
      <span class="empty-orb" aria-hidden="true">${icon('folder')}</span>
      <h3>${esc(ui.i18n.t('scans.no_client.title'))}</h3>
      <p>${esc(ui.i18n.t('scans.no_client.text'))}</p>
      <button type="button" class="btn btn-primary" onclick="navigate('clients')">${icons.plus} ${esc(ui.i18n.t('scans.no_client.add'))}</button>
    </div></div>
  </div>`;
}

function renderScanFolder(client, q) {
  const scans = scansForClient(client.id);
  const n = scans.length;
  const key = foldKey(client.nom);
  const hidden = q && !key.includes(q) ? ' hidden' : '';
  const latest = scans.reduce((m, s) => ((s.cree_le || '') > m ? s.cree_le : m), '');
  const meta = esc(n ? ui.i18n.t('scans.last_import', { date: formatDate((latest || '').slice(0, 10)) }) : ui.i18n.t('scans.folder_empty'));
  return `<button type="button" class="scan-folder${n ? '' : ' is-empty'}" data-fold="${escAttr(key)}" onclick="openScanClient(${Number(client.id)})"${hidden}>
    <span class="scan-folder-top">
      <span class="scan-folder-icon">${icon('folder', { fill: n > 0 })}</span>
      <span class="scan-folder-count">${n}</span>
    </span>
    <span class="scan-folder-name">${esc(client.nom)}</span>
    <span class="scan-folder-meta">${meta}</span>
  </button>`;
}

function renderScans() {
  if (state.scansClientId != null) return renderScansForClient(state.scansClientId);
  if (state.clients.length === 0) return renderScansNoClient();
  const total = state.scans.length;
  const q = foldKey(state.scansQuery);
  const anyMatch = !q || state.clients.some(c => foldKey(c.nom).includes(q));
  return `<div class="page page-wide scans">
    ${renderScansHead(esc(ui.i18n.tn('scans.subtitle', total)))}
    <div class="scan-toolbar" role="search" aria-label="${escAttr(ui.i18n.t('scans.search_label'))}">
      <label class="sr-only" for="scans-search">${esc(ui.i18n.t('col.client'))}</label>
      <div class="scan-search">
        ${icon('search')}
        <input id="scans-search" type="search" class="form-input" value="${escAttr(state.scansQuery)}"
          placeholder="${escAttr(ui.i18n.t('scans.search_placeholder'))}" autocomplete="off" spellcheck="false" oninput="scansOnSearchInput(this.value)">
      </div>
      <span class="scan-toolbar-hint">${esc(ui.i18n.tn('scans.folders', state.clients.length))}</span>
    </div>
    <div class="scan-folder-grid">${state.clients.map(c => renderScanFolder(c, q)).join('')}</div>
    <p class="flt-empty flt-empty-compact" id="scans-no-match"${anyMatch ? ' hidden' : ''}>${esc(ui.i18n.t('scans.no_match'))}</p>
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

// ── Client view ─────────────────────────────────────────

function renderDropzone(clientId, compact) {
  return `<div class="dropzone${compact ? ' is-compact' : ''}" id="scan-dropzone" role="group" aria-label="${escAttr(ui.i18n.t('scans.dropzone'))}"
      ondragenter="scanDragOver(event)" ondragover="scanDragOver(event)" ondragleave="scanDragLeave(event)" ondrop="scanDrop(event, ${Number(clientId)})">
    <span class="dropzone-icon" aria-hidden="true">${icon('upload')}</span>
    <div class="dropzone-text">
      <strong>${esc(ui.i18n.t(compact ? 'scans.drop_more' : 'scans.drop_here'))}</strong>
      <span>${esc(ui.i18n.t('scans.drop_hint'))}</span>
    </div>
    <button type="button" class="btn ${compact ? 'btn-outline' : 'btn-primary'}" onclick="document.getElementById('scan-input').click()">${icons.upload} ${esc(ui.i18n.t('scans.browse'))}</button>
    <ul class="dropzone-progress" id="scan-progress" aria-live="polite"></ul>
  </div>`;
}

function renderScansForClient(clientId) {
  const client = state.clients.find(c => c.id === clientId);
  if (!client) { state.scansClientId = null; return renderScans(); }
  const scans = scansForClient(clientId);
  const head = `<div class="page-head">
    <div class="page-back">
      <button type="button" class="btn btn-quiet btn-sm" onclick="closeScanClient()">${icon('arrow-left', { size: 'sm' })} ${esc(ui.i18n.t('filter.all_clients'))}</button>
      <div class="scan-client-title">${ui.avatar(client.nom, { size: 'lg' })}<div><h2>${esc(client.nom)}</h2><p>${esc(ui.i18n.tn('scans.count', scans.length))}</p></div></div>
    </div>
  </div>`;
  return `<div class="page page-wide scans">
    ${head}
    <input type="file" id="scan-input" accept="application/pdf,image/*" multiple hidden onchange="uploadScans(this, ${Number(clientId)})">
    ${renderDropzone(clientId, scans.length > 0)}
    ${scans.length === 0 ? '' : `<div class="scan-grid">${scans.map(renderScanCard).join('')}</div>`}
  </div>`;
}

function renderScanCard(s) {
  const url = `/api/scans/file/${encodeURIComponent(s.fichier)}`;
  const isImg = isImageScan(s.fichier);
  const thumb = isImg
    ? `<img src="${url}" alt="${escAttr(s.nom_original)}" loading="lazy" onload="this.parentElement.classList.add('is-loaded')">`
    : `<div class="scan-thumb-pdf">${icon('file-text', { size: 'xl' })}<span>PDF</span></div>`;
  return `<article class="scan-card">
    <div class="scan-thumb${isImg ? '' : ' is-loaded'}">
      ${thumb}
      <span class="scan-kind">${isImg ? 'Image' : 'PDF'}</span>
      <div class="scan-overlay">
        <a class="btn btn-secondary btn-icon btn-sm" href="${url}" target="_blank" rel="noopener" aria-label="${escAttr(ui.i18n.t('scans.open_named', { name: s.nom_original }))}" title="${escAttr(ui.i18n.t('action.open'))}">${icon('eye')}</a>
        <a class="btn btn-secondary btn-icon btn-sm" href="${url}" download="${escAttr(s.nom_original)}" aria-label="${escAttr(ui.i18n.t('action.download'))}" title="${escAttr(ui.i18n.t('action.download'))}">${icon('download')}</a>
        <button type="button" class="btn btn-secondary btn-icon btn-sm scan-del" onclick="deleteScan(${Number(s.id)})" aria-label="${escAttr(ui.i18n.t('action.delete'))}" title="${escAttr(ui.i18n.t('action.delete'))}">${icon('trash-2')}</button>
      </div>
    </div>
    <div class="scan-card-body">
      <div class="scan-name" title="${escAttr(s.nom_original)}">${esc(s.nom_original)}</div>
      <div class="scan-date">${esc(formatDateTime(s.cree_le))}</div>
    </div>
  </article>`;
}

function openScanClient(clientId) { state.scansClientId = clientId; render(); }
function closeScanClient() { state.scansClientId = null; render(); }

// ── Upload ──────────────────────────────────────────────

function scanDragOver(e) {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
  e.currentTarget.classList.add('is-dragover');
}

function scanDragLeave(e) {
  // dragleave also fires when crossing into a child: only clear when leaving the zone itself.
  if (e.relatedTarget && e.currentTarget.contains(e.relatedTarget)) return;
  e.currentTarget.classList.remove('is-dragover');
}

function scanDrop(e, clientId) {
  e.preventDefault();
  e.currentTarget.classList.remove('is-dragover');
  uploadScanFiles([...(e.dataTransfer ? e.dataTransfer.files : [])], clientId);
}

function uploadScans(input, clientId) {
  const files = [...(input.files || [])];
  input.value = '';
  return uploadScanFiles(files, clientId);
}

/** POST one file, reporting progress (0..1) — fetch has no upload progress, XHR does. */
function postScan(file, clientId, onProgress) {
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append('client_id', clientId);
    fd.append('file', file);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/scans');
    xhr.upload.onprogress = ev => { if (ev.lengthComputable) onProgress(ev.loaded / ev.total); };
    xhr.onerror = () => reject(new Error(ui.i18n.t('scans.upload_failed')));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) { resolve(); return; }
      let detail = ui.i18n.t('error.server');
      try { detail = JSON.parse(xhr.responseText).detail || detail; } catch { /* not JSON */ }
      reject(new Error(detail));
    };
    xhr.send(fd);
  });
}

function progressRow(file) {
  const li = ui.h('li', { class: 'dz-item' },
    ui.h('span', { class: 'dz-name', text: file.name }),
    ui.h('span', { class: 'dz-bar' }, ui.h('span', { class: 'dz-fill' })),
    ui.h('span', { class: 'dz-state', text: ui.i18n.t('scans.percent', { value: 0 }) }));
  return {
    li,
    set(ratio, label) {
      li.querySelector('.dz-fill').style.width = `${Math.round(ratio * 100)}%`;
      li.querySelector('.dz-state').textContent = label || ui.i18n.t('scans.percent', { value: Math.round(ratio * 100) });
    },
  };
}

async function uploadScanFiles(all, clientId) {
  const files = all.filter(f => SCAN_ACCEPT_RE.test(f.name) || /^(image\/|application\/pdf)/.test(f.type));
  if (all.length > files.length) toast(ui.i18n.t('scans.only_pdf_images'), 'error');
  if (!files.length) return;
  const zone = document.getElementById('scan-dropzone');
  const list = document.getElementById('scan-progress');
  if (zone) zone.classList.add('is-uploading');
  let ok = 0;
  for (const file of files) {
    const row = progressRow(file);
    if (list) list.append(row.li);
    try {
      await postScan(file, clientId, r => row.set(r));
      row.set(1, ui.i18n.t('scans.done'));
      row.li.classList.add('is-done');
      ok++;
    } catch (e) {
      row.li.classList.add('is-error');
      row.set(1, ui.i18n.t('scans.failed'));
      toast(ui.i18n.t('scans.file_error', { name: file.name, message: e.message }), 'error');
    }
  }
  if (ok) {
    toast(ui.i18n.tn('scans.imported', ok));
    await loadData();
    render();
  } else if (zone) {
    zone.classList.remove('is-uploading');
  }
}

async function deleteScan(id) {
  const ok = await ui.alertDialog({
    title: ui.i18n.t('scans.delete.title'),
    description: ui.i18n.t('scans.delete.desc'),
    confirmLabel: ui.i18n.t('action.delete'), destructive: true,
  });
  if (!ok) return;
  try {
    await api('DELETE', `/api/scans/${id}`);
    toast(ui.i18n.t('scans.deleted'));
    await loadData();
    render();
  } catch (e) {
    toast(e.message, 'error');
  }
}
