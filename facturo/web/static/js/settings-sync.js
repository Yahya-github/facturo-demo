// ── Synchronisation GitHub ──────────────────────────────

function renderSyncCard() {
  const s = state.sync || {};

  if (!s.configured) {
    return `<section class="card settings-card" aria-label="${escAttr(tr('settings.tab.sync'))}">
      ${settingsCardHead('refresh-cw', tr('settings.sync.title_multi'), settingsRich('settings.sync.desc_multi'))}
      <div class="sync-warning">${icon('lock')} <div>${settingsRich('settings.sync.private_warn')}</div></div>
      <div class="field" style="margin-top:1.1rem">
        <label class="field-label" for="sync-url">${esc(tr('settings.sync.url'))}</label>
        <input class="form-input" id="sync-url" placeholder="${escAttr(tr('settings.sync.url_ph'))}" autocomplete="off">
      </div>
      <div class="field-row">
        <div class="field">
          <label class="field-label" for="sync-token">${esc(tr('settings.sync.token'))}</label>
          <input class="form-input" id="sync-token" type="password" placeholder="ghp_…" autocomplete="off">
          <span class="field-hint">${esc(tr('settings.sync.token_hint'))}</span>
        </div>
        <div class="field">
          <label class="field-label" for="sync-branch">${esc(tr('settings.sync.branch'))}</label>
          <input class="form-input" id="sync-branch" value="main">
        </div>
      </div>
      <div class="settings-actions"><button type="button" class="btn btn-primary" id="sync-connect-btn" onclick="configureSync()">${icon('link')} ${esc(tr('settings.sync.connect'))}</button></div>
    </section>`;
  }

  const last = s.last_synced ? formatDateTime(s.last_synced) : tr('settings.sync.never');
  const action = s.last_action === 'push' ? tr('settings.sync.action_push') : s.last_action === 'pull' ? tr('settings.sync.action_pull') : '—';
  return `<section class="card settings-card" aria-label="${escAttr(tr('settings.tab.sync'))}">
    ${settingsCardHead('refresh-cw', tr('settings.tab.sync'), esc(tr('settings.sync.desc')))}
    <dl class="settings-list">
      <div class="settings-row"><dt>${esc(tr('settings.sync.repo'))}</dt><dd class="sync-repo">${esc(s.remote_url)}</dd></div>
      <div class="settings-row"><dt>${esc(tr('settings.sync.branch'))}</dt><dd>${esc(s.branch)}</dd></div>
      <div class="settings-row"><dt>${esc(tr('settings.sync.last'))}</dt><dd>${esc(last)}${s.last_action ? ` (${esc(action)})` : ''}</dd></div>
    </dl>
    <div class="sync-warning" style="margin-top:1rem">${icon('info')} <div>${settingsRich('settings.sync.one_device')}</div></div>
    <div class="sync-actions">
      <button type="button" class="btn btn-outline" id="sync-pull-btn" onclick="syncPull()">${icon('cloud-download')} ${esc(tr('settings.sync.receive'))}</button>
      <button type="button" class="btn btn-primary" id="sync-push-btn" onclick="syncPush()">${icon('cloud-upload')} ${esc(tr('settings.sync.send'))}</button>
    </div>
    <button type="button" class="btn btn-quiet btn-sm settings-disconnect" onclick="disconnectSync()">${icon('unlink', { size: 'sm' })} ${esc(tr('settings.sync.disconnect'))}</button>
  </section>`;
}

async function configureSync() {
  const url = $('#sync-url').value.trim();
  const token = $('#sync-token').value.trim();
  const branch = $('#sync-branch').value.trim() || 'main';
  if (!url || !token) { toast(tr('settings.sync.need_fields'), 'error'); return; }
  const btn = $('#sync-connect-btn');
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="loading-spinner"></span> ${esc(tr('settings.sync.connecting'))}`;
  try {
    state.sync = await api('POST', '/api/sync/configure', { url, token, branch });
    toast(tr('settings.sync.connected'));
    render();
  } catch (e) {
    toast(e.message, 'error');
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

async function syncPush() {
  await runSync('sync-push-btn', tr('settings.sync.sending'), '/api/sync/push', tr('settings.sync.sent'));
}

async function syncPull() {
  const ok = await ui.alertDialog({
    title: tr('settings.sync.pull_title'),
    description: tr('settings.sync.pull_desc'),
    confirmLabel: tr('settings.sync.receive'),
  });
  if (!ok) return;
  await runSync('sync-pull-btn', tr('settings.sync.receiving'), '/api/sync/pull', tr('settings.sync.received'));
}

async function runSync(btnId, label, endpoint, okMsg) {
  const btn = document.getElementById(btnId);
  const both = ['sync-push-btn', 'sync-pull-btn'].map(id => document.getElementById(id)).filter(Boolean);
  const orig = btn ? btn.innerHTML : '';
  both.forEach(b => b.disabled = true);
  if (btn) btn.innerHTML = `<span class="loading-spinner"></span> ${esc(label)}`;
  try {
    await api('POST', endpoint);
    toast(okMsg);
    // A pull can bring in a database newer than this app (banner) and new
    // payments, so re-read the version and drop the cached Paiements state.
    if (typeof pay !== 'undefined') { pay.list = null; pay.detail = null; pay.detailId = null; }
    await Promise.all([loadData(), loadSyncStatus(), loadVersionInfo()]);
    render();
  } catch (e) {
    toast(e.message, 'error');
    both.forEach(b => b.disabled = false);
    if (btn) btn.innerHTML = orig;
  }
}

async function disconnectSync() {
  const ok = await ui.alertDialog({
    title: tr('settings.sync.disconnect_title'),
    description: tr('settings.sync.disconnect_desc'),
    confirmLabel: tr('settings.sync.disconnect_btn'), destructive: true,
  });
  if (!ok) return;
  try {
    await api('POST', '/api/sync/disconnect');
    await loadSyncStatus();
    toast(tr('settings.sync.disconnected'));
    render();
  } catch (e) {
    toast(e.message, 'error');
  }
}

