// ── Synchronisation GitHub ──────────────────────────────

function renderSyncCard() {
  const s = state.sync || {};

  if (!s.configured) {
    return `<section class="card settings-card" aria-label="Synchronisation">
      ${settingsCardHead('refresh-cw', 'Synchronisation multi-appareils', 'Sauvegardez et partagez vos données (clients, factures, scans) entre plusieurs ordinateurs via un dépôt GitHub <strong>privé</strong>.')}
      <div class="sync-warning">${icon('lock')} <div>Le dépôt doit être <strong>privé</strong> : il contiendra vos clients et le détail de vos factures. Ne le rendez jamais public.</div></div>
      <div class="field" style="margin-top:1.1rem">
        <label class="field-label" for="sync-url">URL du dépôt GitHub</label>
        <input class="form-input" id="sync-url" placeholder="https://github.com/votre-compte/factures-data" autocomplete="off">
      </div>
      <div class="field-row">
        <div class="field">
          <label class="field-label" for="sync-token">Jeton d'accès (token)</label>
          <input class="form-input" id="sync-token" type="password" placeholder="ghp_…" autocomplete="off">
          <span class="field-hint">GitHub → Settings → Developer settings → Personal access tokens. Donnez l'accès « Contents: Read and write » à ce dépôt.</span>
        </div>
        <div class="field">
          <label class="field-label" for="sync-branch">Branche</label>
          <input class="form-input" id="sync-branch" value="main">
        </div>
      </div>
      <div class="settings-actions"><button type="button" class="btn btn-primary" id="sync-connect-btn" onclick="configureSync()">${icon('link')} Connecter</button></div>
    </section>`;
  }

  const last = s.last_synced ? formatDateTime(s.last_synced) : 'jamais';
  const action = s.last_action === 'push' ? 'Envoi' : s.last_action === 'pull' ? 'Réception' : '—';
  return `<section class="card settings-card" aria-label="Synchronisation">
    ${settingsCardHead('refresh-cw', 'Synchronisation', 'Cet appareil est relié à un dépôt GitHub privé.')}
    <dl class="settings-list">
      <div class="settings-row"><dt>Dépôt</dt><dd class="sync-repo">${esc(s.remote_url)}</dd></div>
      <div class="settings-row"><dt>Branche</dt><dd>${esc(s.branch)}</dd></div>
      <div class="settings-row"><dt>Dernière synchro</dt><dd>${esc(last)}${s.last_action ? ` (${action})` : ''}</dd></div>
    </dl>
    <div class="sync-warning" style="margin-top:1rem">${icon('info')} <div>Un seul appareil à la fois. Cliquez <strong>Recevoir</strong> avant de commencer à travailler, et <strong>Envoyer</strong> quand vous avez terminé.</div></div>
    <div class="sync-actions">
      <button type="button" class="btn btn-outline" id="sync-pull-btn" onclick="syncPull()">${icon('cloud-download')} Recevoir</button>
      <button type="button" class="btn btn-primary" id="sync-push-btn" onclick="syncPush()">${icon('cloud-upload')} Envoyer</button>
    </div>
    <button type="button" class="btn btn-quiet btn-sm settings-disconnect" onclick="disconnectSync()">${icon('unlink', { size: 'sm' })} Déconnecter cet appareil</button>
  </section>`;
}

async function configureSync() {
  const url = $('#sync-url').value.trim();
  const token = $('#sync-token').value.trim();
  const branch = $('#sync-branch').value.trim() || 'main';
  if (!url || !token) { toast('Renseignez l\'URL du dépôt et le jeton.', 'error'); return; }
  const btn = $('#sync-connect-btn');
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="loading-spinner"></span> Connexion…';
  try {
    state.sync = await api('POST', '/api/sync/configure', { url, token, branch });
    toast('Synchronisation connectée. Choisissez Recevoir ou Envoyer.');
    render();
  } catch (e) {
    toast(e.message, 'error');
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

async function syncPush() {
  await runSync('sync-push-btn', 'Envoi…', '/api/sync/push', 'Données envoyées sur GitHub ✓');
}

async function syncPull() {
  const ok = await ui.alertDialog({
    title: 'Recevoir les données de GitHub',
    description: 'Recevoir remplacera les données de cet appareil par celles de GitHub. Une sauvegarde locale sera créée. Continuer ?',
    confirmLabel: 'Recevoir',
  });
  if (!ok) return;
  await runSync('sync-pull-btn', 'Réception…', '/api/sync/pull', 'Données reçues de GitHub ✓');
}

async function runSync(btnId, label, endpoint, okMsg) {
  const btn = document.getElementById(btnId);
  const both = ['sync-push-btn', 'sync-pull-btn'].map(id => document.getElementById(id)).filter(Boolean);
  const orig = btn ? btn.innerHTML : '';
  both.forEach(b => b.disabled = true);
  if (btn) btn.innerHTML = `<span class="loading-spinner"></span> ${label}`;
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
    title: 'Déconnecter la synchronisation',
    description: 'Déconnecter la synchronisation sur cet appareil ? Vos données et l\'historique restent intacts.',
    confirmLabel: 'Déconnecter', destructive: true,
  });
  if (!ok) return;
  try {
    await api('POST', '/api/sync/disconnect');
    await loadSyncStatus();
    toast('Synchronisation déconnectée');
    render();
  } catch (e) {
    toast(e.message, 'error');
  }
}

