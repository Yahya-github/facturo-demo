// ── SETTINGS ────────────────────────────────────────────

function renderSettings() {
  const preview = state.hasLogo
    ? `<div class="logo-preview">
         <img src="/api/logo?t=${Date.now()}" alt="Logo de l'entreprise">
       </div>
       <div style="display:flex; gap:12px; margin-top:16px">
         <button class="btn btn-ghost" onclick="document.getElementById('logo-input').click()">${icons.upload} Remplacer</button>
         <button class="btn btn-ghost" style="color:var(--red-600)" onclick="removeLogo()">${icons.trash} Retirer</button>
       </div>`
    : `<div class="logo-empty">
         ${icons.image}
         <p>Aucun logo. Ajoutez le logo de votre entreprise pour qu'il apparaisse en haut à droite de chaque facture (Excel et PDF).</p>
         <button class="btn btn-primary" style="margin-top:16px" onclick="document.getElementById('logo-input').click()">${icons.upload} Téléverser un logo</button>
       </div>`;

  return `<div class="page">
    <div class="page-header">
      <div>
        <h2>Paramètres</h2>
        <div class="subtitle">Logo, synchronisation et mises à jour</div>
      </div>
    </div>
    <div class="card" style="padding:24px; max-width:560px">
      <h3 style="font-size:1rem; font-weight:700; margin-bottom:4px">Logo de l'entreprise</h3>
      <div class="form-hint" style="margin-bottom:16px">Format PNG ou JPG. Coin supérieur droit de la facture.</div>
      ${preview}
      <input type="file" id="logo-input" accept="image/png,image/jpeg" style="display:none" onchange="uploadLogo(this)">
    </div>
    ${renderKnownValuesCard()}
    ${renderSyncCard()}
    ${renderUpdateCard()}
  </div>`;
}

// Which list the curation card is showing. Module-level so it survives the
// render() that follows every edit.
let kvTab = 'chantier';

function renderKnownValuesCard() {
  const rows = (state.kvAll || []).filter(v => v.kind === kvTab);
  const label = kvTab === 'chantier' ? 'un chantier' : 'une plaque';
  const body = rows.length
    ? rows.map(v => `<div class="kv-row${v.hidden ? ' is-hidden' : ''}">
        <span class="kv-value">${esc(v.valeur)}</span>
        <span class="kv-meta">${v.times_used}×${v.alias_valeur ? ` → ${esc(v.alias_valeur)}` : ''}${v.hidden ? ' · masqué' : ''}</span>
        <span class="kv-actions">
          <button class="kv-btn" onclick="renameKnownValue(${v.id})">Renommer</button>
          <button class="kv-btn" onclick="toggleKnownValue(${v.id}, ${v.hidden ? 'false' : 'true'})">${v.hidden ? 'Afficher' : 'Masquer'}</button>
          <button class="kv-btn kv-btn-danger" onclick="deleteKnownValue(${v.id})">Supprimer</button>
        </span>
      </div>`).join('')
    : `<div class="form-hint">Aucune valeur enregistrée pour l'instant.</div>`;

  return `<div class="card" style="padding:24px; max-width:560px; margin-top:20px">
    <h3 style="font-size:1rem; font-weight:700; margin-bottom:4px">Chantiers et plaques connus</h3>
    <div class="form-hint" style="margin-bottom:16px">
      Ce que les champs Chantier et Plaque proposent, et ce que l'IA utilise pour
      corriger ses lectures. Renommer une valeur ne modifie pas les factures déjà générées.
    </div>
    <div class="seg" style="margin-bottom:14px">
      <button class="seg-btn${kvTab === 'chantier' ? ' active' : ''}" onclick="setKvTab('chantier')">Chantiers</button>
      <button class="seg-btn${kvTab === 'plaque' ? ' active' : ''}" onclick="setKvTab('plaque')">Plaques</button>
    </div>
    <div class="kv-list">${body}</div>
    <div class="kv-add">
      <input class="form-input" id="kv-new" placeholder="Ajouter ${label}…">
      <button class="btn btn-ghost" onclick="addKnownValue()">Ajouter</button>
    </div>
  </div>`;
}

function setKvTab(kind) { kvTab = kind; render(); }

// The curation card shows hidden and merged rows too, which loadData filters
// out of the suggestion lists — so it keeps its own unfiltered copy.
async function reloadKnownValues() {
  state.kvAll = await api('GET', '/api/known-values');
  await loadData();
  render();
}

async function addKnownValue() {
  const input = $('#kv-new');
  const valeur = (input.value || '').trim();
  if (!valeur) return;
  try {
    await api('POST', '/api/known-values', { kind: kvTab, valeur });
    await reloadKnownValues();
    toast('Valeur ajoutée.');
  } catch (e) { toast(e.message, 'error'); }
}

async function renameKnownValue(id) {
  const current = (state.kvAll || []).find(v => v.id === id);
  const valeur = await ui.promptDialog({
    title: 'Renommer la valeur', label: 'Nouvelle orthographe',
    value: current ? current.valeur : '', confirmLabel: 'Renommer',
  });
  if (valeur === null || !valeur.trim()) return;
  try {
    await api('PUT', `/api/known-values/${id}`, { valeur: valeur.trim() });
    await reloadKnownValues();
  } catch (e) { toast(e.message, 'error'); }
}

async function toggleKnownValue(id, hidden) {
  try {
    await api('PUT', `/api/known-values/${id}`, { hidden });
    await reloadKnownValues();
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteKnownValue(id) {
  const v = (state.kvAll || []).find(x => x.id === id);
  const ok = await ui.alertDialog({
    title: 'Supprimer la valeur',
    description: `Supprimer « ${v ? v.valeur : ''} » de la liste ?\n\nLes factures déjà générées ne changent pas.`,
    confirmLabel: 'Supprimer', destructive: true,
  });
  if (!ok) return;
  try {
    await api('DELETE', `/api/known-values/${id}`);
    await reloadKnownValues();
  } catch (e) { toast(e.message, 'error'); }
}

async function uploadLogo(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch('/api/logo', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Erreur serveur' }));
      throw new Error(err.detail || 'Échec du téléversement');
    }
    state.hasLogo = true;
    toast('Logo enregistré ! Il apparaîtra sur les prochaines factures.');
    render();
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    input.value = '';
  }
}

// ── Synchronisation GitHub ──────────────────────────────

function renderSyncCard() {
  const s = state.sync || {};

  if (!s.configured) {
    return `<div class="card" style="padding:24px; max-width:560px; margin-top:20px">
      <h3 style="font-size:1rem; font-weight:700; margin-bottom:4px">${micon('sync')} Synchronisation multi-appareils</h3>
      <div class="form-hint" style="margin-bottom:14px">Sauvegardez et partagez vos données (clients, factures, scans) entre plusieurs ordinateurs via un dépôt GitHub <strong>privé</strong>.</div>
      <div class="sync-warning">${micon('lock')} <div>Le dépôt doit être <strong>privé</strong> — il contiendra vos clients et le détail de vos factures. Ne le rendez jamais public.</div></div>
      <div class="form-group" style="margin-top:14px">
        <label class="form-label">URL du dépôt GitHub</label>
        <input class="form-input" id="sync-url" placeholder="https://github.com/votre-compte/factures-data">
      </div>
      <div class="form-row form-row-2">
        <div class="form-group">
          <label class="form-label">Jeton d'accès (token)</label>
          <input class="form-input" id="sync-token" type="password" placeholder="ghp_…" autocomplete="off">
          <div class="form-hint">GitHub → Settings → Developer settings → Personal access tokens. Donnez l'accès « Contents: Read and write » à ce dépôt.</div>
        </div>
        <div class="form-group">
          <label class="form-label">Branche</label>
          <input class="form-input" id="sync-branch" value="main">
        </div>
      </div>
      <button class="btn btn-primary" id="sync-connect-btn" onclick="configureSync()" style="margin-top:8px">${micon('link')} Connecter</button>
    </div>`;
  }

  const last = s.last_synced ? formatDateTime(s.last_synced) : 'jamais';
  const action = s.last_action === 'push' ? 'Envoi' : s.last_action === 'pull' ? 'Réception' : '—';
  return `<div class="card" style="padding:24px; max-width:560px; margin-top:20px">
    <h3 style="font-size:1rem; font-weight:700; margin-bottom:4px">${micon('sync')} Synchronisation</h3>
    <div class="sync-meta">
      <div><span class="sync-meta-label">Dépôt</span> <span class="sync-repo">${esc(s.remote_url)}</span></div>
      <div><span class="sync-meta-label">Branche</span> ${esc(s.branch)}</div>
      <div><span class="sync-meta-label">Dernière synchro</span> ${last}${s.last_action ? ` (${action})` : ''}</div>
    </div>
    <div class="sync-warning" style="margin-top:14px">${micon('info')} <div>Un seul appareil à la fois. Cliquez <strong>Recevoir</strong> avant de commencer à travailler, et <strong>Envoyer</strong> quand vous avez terminé.</div></div>
    <div class="sync-actions">
      <button class="btn btn-ghost" id="sync-pull-btn" onclick="syncPull()">${micon('cloud_download')} Recevoir</button>
      <button class="btn btn-success" id="sync-push-btn" onclick="syncPush()">${micon('cloud_upload')} Envoyer</button>
    </div>
    <button class="btn btn-ghost btn-sm" style="margin-top:14px; color:var(--gray-500)" onclick="disconnectSync()">${micon('link_off')} Déconnecter cet appareil</button>
  </div>`;
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

async function removeLogo() {
  const ok = await ui.alertDialog({
    title: 'Retirer le logo',
    description: 'Retirer le logo de l\'entreprise ?',
    confirmLabel: 'Retirer', destructive: true,
  });
  if (!ok) return;
  try {
    await api('DELETE', '/api/logo');
    state.hasLogo = false;
    toast('Logo retiré');
    render();
  } catch (e) {
    toast(e.message, 'error');
  }
}

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
    return `<div class="card update-card" id="update-card">
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
  return `<div class="card update-card" id="update-card">
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
