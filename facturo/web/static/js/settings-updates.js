// ── Mises à jour (GitHub Releases) ──────────────────────
// state.version  : GET /api/version (version, frozen, db_newer_than_app)
// state.updates  : GET /api/updates/status (never contains the token)
// state.updateCheck : last GET /api/updates/check result
// updateUi.phase : 'idle' | 'checking' | 'saving' | 'confirm' | 'installing'

const UPDATE_SESSION_KEY = 'facturo.updateCheck';
const UPDATE_POLL_MS = 2000;
const UPDATE_POLL_GIVE_UP_MS = 180000;
const updateUi = { phase: 'idle', slow: false };

function sessionGet(key) {
  try { return JSON.parse(sessionStorage.getItem(key) || 'null'); } catch { return null; }
}
function sessionSet(key, value) {
  try { sessionStorage.setItem(key, JSON.stringify(value)); } catch { /* storage disabled: re-check next time */ }
}

async function loadVersionInfo() {
  try {
    state.version = await api('GET', '/api/version');
  } catch (e) {
    // Keep the last known version (and so the 'database newer' banner as it
    // stood) rather than hiding a safety warning because one request failed.
    console.warn('Version indisponible:', e);
    return;
  }
  showDbNewerBanner(!!(state.version && state.version.db_newer_than_app));
}

async function loadUpdateStatus() {
  try {
    const s = await api('GET', '/api/updates/status');
    // The failure report is handed out once by the server: keep it here.
    if (s.update_failed_message) state.updateFailure = s.update_failed_message;
    state.updates = s;
  } catch {
    state.updates = state.updates || null;
  }
}

function showDbNewerBanner(show) {
  let el = document.getElementById('db-newer-banner');
  if (!show) { if (el) el.remove(); return; }
  if (el) return;
  el = document.createElement('div');
  el.id = 'db-newer-banner';
  el.className = 'db-guard-banner';
  el.setAttribute('role', 'alert');
  el.innerHTML = `${micon('warning', true)}
    <div><strong>Cette base de données provient d'une version plus récente — mettez à jour l'application.</strong>
    <span>L'envoi (synchronisation) est bloqué jusqu'à la mise à jour, pour ne pas écraser des données plus récentes.</span></div>
    <button class="btn btn-sm db-guard-btn" onclick="navigate('settings')">Mettre à jour</button>`;
  document.body.prepend(el);
}

function setUpdateDot(available, version) {
  const dot = document.getElementById('update-dot');
  if (!dot) return;
  dot.hidden = !available;
  dot.title = available && version ? `Mise à jour disponible : v${version}` : 'Mise à jour disponible';
}

// Once per browser session, in the background: never blocks startup, never throws.
async function backgroundUpdateCheck() {
  try {
    await loadUpdateStatus();
    if (state.updateFailure) toast(state.updateFailure, 'error');
    const cached = sessionGet(UPDATE_SESSION_KEY);
    if (cached) {
      state.updateCheck = cached;
      setUpdateDot(!!cached.available, cached.latest);
    }
    if (state.page === 'settings') render();
    if (cached) return;
    if (!state.updates || !state.updates.configured || !(state.version && state.version.frozen)) return;
    const result = await api('GET', '/api/updates/check');
    state.updateCheck = result;
    sessionSet(UPDATE_SESSION_KEY, result);
    setUpdateDot(!!result.available, result.latest);
    if (state.page === 'settings') render();
  } catch {
    // Offline or token problem: the Paramètres card shows details on demand.
  }
}

function renderUpdateCard() {
  const v = state.version || {};
  const s = state.updates || {};
  const c = state.updateCheck;
  const frozen = !!v.frozen;
  const busy = updateUi.phase !== 'idle' && updateUi.phase !== 'confirm';
  const current = v.version || s.current || '—';

  if (updateUi.phase === 'installing') {
    return `<div class="card settings-card update-card" id="update-card">
      <h3 class="update-title">${micon('system_update')} Mises à jour</h3>
      <div class="update-progress" role="status">
        <span class="loading-spinner update-spinner"></span>
        <div><strong>Mise à jour en cours… une nouvelle fenêtre va s'ouvrir.</strong>
        <div class="form-hint">Ne fermez pas cette page : elle se rechargera automatiquement sur la nouvelle version.</div>
        ${updateUi.slow ? `<div class="form-hint update-slow">La nouvelle version tarde à répondre. Si aucune fenêtre ne s'est ouverte, relancez Factures : en cas d'échec, l'ancienne version est rétablie automatiquement.</div>` : ''}
        </div>
      </div>
    </div>`;
  }

  const failure = state.updateFailure
    ? `<div class="sync-warning update-failure">${micon('error')} <div>${esc(state.updateFailure)}</div></div>` : '';
  const devNote = frozen ? '' : `<div class="sync-warning">${micon('code')} <div><strong>Mode développement</strong> — l'installation automatique n'est disponible que dans Factures.exe. La vérification fonctionne normalement.</div></div>`;

  let result = '';
  if (c && c.available) {
    const date = c.published_at ? ` · publiée le ${esc(formatDateTime(c.published_at))}` : '';
    const notes = c.notes ? `<div class="update-notes">${esc(c.notes)}</div>` : '';
    let action;
    if (!frozen) {
      action = `<button class="btn btn-primary" disabled title="Indisponible en mode développement">${micon('download')} Installer</button>`;
    } else if (updateUi.phase === 'confirm') {
      action = `<div class="update-confirm">
        <p>Factures va se fermer, installer la version <strong>${esc(c.latest)}</strong> puis redémarrer dans une nouvelle fenêtre. Une copie de sauvegarde de vos données est faite avant.</p>
        <div class="sync-actions">
          <button class="btn btn-ghost" onclick="cancelUpdateInstall()">Annuler</button>
          <button class="btn btn-success" id="update-confirm-btn" onclick="confirmUpdateInstall()">${micon('check')} Confirmer l'installation</button>
        </div>
      </div>`;
    } else {
      action = `<button class="btn btn-success" id="update-install-btn" onclick="askUpdateInstall()" ${busy ? 'disabled' : ''}>${micon('download')} Installer</button>`;
    }
    result = `<div class="update-available">
      <div class="update-available-head">${micon('new_releases', true)} <strong>Version ${esc(c.latest)} disponible</strong><span class="form-hint">${date}</span></div>
      ${notes}
      <div class="update-action">${action}</div>
    </div>`;
  } else if (c) {
    result = `<div class="update-uptodate">${micon('check_circle', true)} Vous avez la dernière version${c.latest ? ` (${esc(c.latest)})` : ''}.</div>`;
  }

  const configured = !!s.configured;
  return `<div class="card settings-card update-card" id="update-card">
    <h3 class="update-title">${micon('system_update')} Mises à jour</h3>
    <div class="sync-meta" style="margin-bottom:14px">
      <div><span class="sync-meta-label">Version installée</span> <span id="update-current">${esc(current)}</span></div>
      <div><span class="sync-meta-label">Jeton</span> ${configured ? 'configuré' : 'non configuré'}</div>
    </div>
    ${failure}
    ${devNote}
    <div class="form-group" style="margin-top:14px">
      <label class="form-label" for="update-token">Jeton GitHub (lecture seule)</label>
      <input class="form-input" id="update-token" type="password" autocomplete="new-password" spellcheck="false"
        placeholder="${configured ? 'Jeton enregistré — laissez vide pour le conserver' : 'github_pat_…'}">
      <div class="form-hint">Jeton « fine-grained » avec l'accès <strong>Contents: Read-only</strong> au seul dépôt <strong>facturo-releases</strong> (jamais au code source). Il n'est jamais réaffiché.</div>
    </div>
    <label class="switch-field" for="update-prereleases">
      <input type="checkbox" id="update-prereleases" ${s.include_prereleases ? 'checked' : ''} onchange="saveUpdateConfig(true)">
      <span class="switch-track"></span>
      <span class="switch-text">
        <span class="switch-title">Inclure les versions de test</span>
        <span class="switch-desc">Propose aussi les pré-versions (-rc). À laisser décoché sur les postes de travail.</span>
      </span>
    </label>
    <div class="sync-actions">
      <button class="btn btn-ghost" id="update-save-btn" onclick="saveUpdateConfig(false)" ${busy ? 'disabled' : ''}>${micon('key')} Enregistrer le jeton</button>
      <button class="btn btn-primary" id="update-check-btn" onclick="checkForUpdates()" ${busy ? 'disabled' : ''}>
        ${updateUi.phase === 'checking' ? '<span class="loading-spinner"></span> Vérification…' : `${micon('refresh')} Vérifier`}
      </button>
    </div>
    ${result}
  </div>`;
}

async function saveUpdateConfig(fromCheckbox) {
  const tokenInput = $('#update-token');
  const box = $('#update-prereleases');
  const token = tokenInput ? tokenInput.value.trim() : '';
  const include = box ? box.checked : false;
  if (!fromCheckbox && !token) { toast('Collez le jeton GitHub avant d\'enregistrer.', 'error'); return; }
  const body = { include_prereleases: include };
  if (token) body.token = token;
  updateUi.phase = 'saving';
  try {
    state.updates = await api('POST', '/api/updates/config', body);
    state.updateCheck = null;
    sessionSet(UPDATE_SESSION_KEY, null);
    toast(token ? 'Jeton enregistré et vérifié.' : 'Préférence enregistrée.');
  } catch (e) {
    if (box && fromCheckbox) box.checked = !include;
    toast(e.message, 'error');
  } finally {
    if (tokenInput) tokenInput.value = '';
    updateUi.phase = 'idle';
    if (state.page === 'settings') render();
  }
}

async function checkForUpdates() {
  updateUi.phase = 'checking';
  render();
  try {
    const result = await api('GET', '/api/updates/check');
    state.updateCheck = result;
    sessionSet(UPDATE_SESSION_KEY, result);
    setUpdateDot(!!result.available, result.latest);
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    updateUi.phase = 'idle';
    if (state.page === 'settings') render();
  }
}

function askUpdateInstall() { updateUi.phase = 'confirm'; render(); }
function cancelUpdateInstall() { updateUi.phase = 'idle'; render(); }

async function confirmUpdateInstall() {
  const btn = $('#update-confirm-btn');
  if (btn) btn.disabled = true;
  const port = parseInt(window.location.port, 10) || 80;
  const before = (state.version && state.version.version) || '';
  try {
    await api('POST', '/api/updates/install', { port });
  } catch (e) {
    toast(e.message, 'error');
    updateUi.phase = 'idle';
    render();
    return;
  }
  updateUi.phase = 'installing';
  updateUi.slow = false;
  sessionSet(UPDATE_SESSION_KEY, null);
  render();
  waitForNewVersion(before, Date.now());
}

// The old server exits, the helper swaps the exe and starts the new one on
// the same port: poll until a different version answers, then reload.
function waitForNewVersion(before, startedAt) {
  setTimeout(async () => {
    try {
      const res = await fetch('/api/version', { cache: 'no-store' });
      if (res.ok) {
        const info = await res.json();
        if (info.version && info.version !== before) { window.location.reload(); return; }
      }
    } catch { /* server restarting: keep polling */ }
    if (!updateUi.slow && Date.now() - startedAt > UPDATE_POLL_GIVE_UP_MS) {
      updateUi.slow = true;
      if (state.page === 'settings') render();
    }
    waitForNewVersion(before, startedAt);
  }, UPDATE_POLL_MS);
}
