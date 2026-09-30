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
  el.innerHTML = dbNewerBannerHtml();
  document.body.prepend(el);
}

function dbNewerBannerHtml() {
  return `${micon('warning', true)}
    <div><strong>${esc(tr('settings.updates.db_newer'))}</strong>
    <span>${esc(tr('settings.updates.db_newer_desc'))}</span></div>
    <button class="btn btn-sm db-guard-btn" onclick="navigate('settings')">${esc(tr('settings.updates.db_newer_btn'))}</button>`;
}

let updateDotState = { available: false, version: '' };

function setUpdateDot(available, version) {
  updateDotState = { available, version };
  const dot = document.getElementById('update-dot');
  if (!dot) return;
  dot.hidden = !available;
  const title = available && version ? tr('settings.updates.dot', { version }) : tr('update.available');
  if (dot.title !== title) dot.title = title;
}

// These two live outside the page render, so a language change has to repaint them.
ui.i18n.onLangChange(() => {
  const banner = document.getElementById('db-newer-banner');
  if (banner) banner.innerHTML = dbNewerBannerHtml();
  setUpdateDot(updateDotState.available, updateDotState.version);
});

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
      <h3 class="update-title">${micon('system_update')} ${esc(tr('settings.updates.title'))}</h3>
      <div class="update-progress" role="status">
        <span class="loading-spinner update-spinner"></span>
        <div><strong>${esc(tr('settings.updates.installing'))}</strong>
        <div class="form-hint">${esc(tr('settings.updates.installing_hint'))}</div>
        ${updateUi.slow ? `<div class="form-hint update-slow">${esc(tr('settings.updates.slow'))}</div>` : ''}
        </div>
      </div>
    </div>`;
  }

  const failure = state.updateFailure
    ? `<div class="sync-warning update-failure">${micon('error')} <div>${esc(state.updateFailure)}</div></div>` : '';
  const devNote = frozen ? '' : `<div class="sync-warning">${micon('code')} <div>${settingsRich('settings.updates.dev_note')}</div></div>`;

  let result = '';
  if (c && c.available) {
    const date = c.published_at ? ` · ${esc(tr('settings.updates.published', { date: formatDateTime(c.published_at) }))}` : '';
    const notes = c.notes ? `<div class="update-notes">${esc(c.notes)}</div>` : '';
    let action;
    if (!frozen) {
      action = `<button class="btn btn-primary" disabled title="${escAttr(tr('settings.updates.dev_tip'))}">${micon('download')} ${esc(tr('settings.updates.install'))}</button>`;
    } else if (updateUi.phase === 'confirm') {
      action = `<div class="update-confirm">
        <p>${settingsRich('settings.updates.confirm_text', { version: c.latest })}</p>
        <div class="sync-actions">
          <button class="btn btn-ghost" onclick="cancelUpdateInstall()">${esc(tr('action.cancel'))}</button>
          <button class="btn btn-success" id="update-confirm-btn" onclick="confirmUpdateInstall()">${micon('check')} ${esc(tr('settings.updates.confirm_btn'))}</button>
        </div>
      </div>`;
    } else {
      action = `<button class="btn btn-success" id="update-install-btn" onclick="askUpdateInstall()" ${busy ? 'disabled' : ''}>${micon('download')} ${esc(tr('settings.updates.install'))}</button>`;
    }
    result = `<div class="update-available">
      <div class="update-available-head">${micon('new_releases', true)} <strong>${esc(tr('settings.updates.available', { version: c.latest }))}</strong><span class="form-hint">${date}</span></div>
      ${notes}
      <div class="update-action">${action}</div>
    </div>`;
  } else if (c) {
    result = `<div class="update-uptodate">${micon('check_circle', true)} ${esc(tr('settings.updates.uptodate', { latest: c.latest ? ` (${c.latest})` : '' }))}</div>`;
  }

  const configured = !!s.configured;
  return `<div class="card settings-card update-card" id="update-card">
    <h3 class="update-title">${micon('system_update')} ${esc(tr('settings.updates.title'))}</h3>
    <div class="sync-meta" style="margin-bottom:14px">
      <div><span class="sync-meta-label">${esc(tr('settings.updates.installed'))}</span> <span id="update-current">${esc(current)}</span></div>
      <div><span class="sync-meta-label">${esc(tr('settings.updates.token'))}</span> ${esc(tr(configured ? 'settings.updates.configured' : 'settings.updates.not_configured'))}</div>
    </div>
    ${failure}
    ${devNote}
    <div class="form-group" style="margin-top:14px">
      <label class="form-label" for="update-token">${esc(tr('settings.updates.token_label'))}</label>
      <input class="form-input" id="update-token" type="password" autocomplete="new-password" spellcheck="false"
        placeholder="${escAttr(configured ? tr('settings.updates.token_saved_ph') : 'github_pat_…')}">
      <div class="form-hint">${settingsRich('settings.updates.token_hint')}</div>
    </div>
    <label class="switch-field" for="update-prereleases">
      <input type="checkbox" id="update-prereleases" ${s.include_prereleases ? 'checked' : ''} onchange="saveUpdateConfig(true)">
      <span class="switch-track"></span>
      <span class="switch-text">
        <span class="switch-title">${esc(tr('settings.updates.pre_title'))}</span>
        <span class="switch-desc">${esc(tr('settings.updates.pre_desc'))}</span>
      </span>
    </label>
    <div class="sync-actions">
      <button class="btn btn-ghost" id="update-save-btn" onclick="saveUpdateConfig(false)" ${busy ? 'disabled' : ''}>${micon('key')} ${esc(tr('settings.updates.save_token'))}</button>
      <button class="btn btn-primary" id="update-check-btn" onclick="checkForUpdates()" ${busy ? 'disabled' : ''}>
        ${updateUi.phase === 'checking' ? `<span class="loading-spinner"></span> ${esc(tr('settings.updates.checking'))}` : `${micon('refresh')} ${esc(tr('settings.updates.check'))}`}
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
  if (!fromCheckbox && !token) { toast(tr('settings.updates.need_token'), 'error'); return; }
  const body = { include_prereleases: include };
  if (token) body.token = token;
  updateUi.phase = 'saving';
  try {
    state.updates = await api('POST', '/api/updates/config', body);
    state.updateCheck = null;
    sessionSet(UPDATE_SESSION_KEY, null);
    toast(tr(token ? 'settings.updates.token_saved' : 'settings.updates.pref_saved'));
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
