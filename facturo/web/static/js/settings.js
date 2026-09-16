// ── SETTINGS ────────────────────────────────────────────
// Tabs (ui/tabs.js): Général (logo, company, version and updates), Synchronisation,
// Intelligence artificielle, Valeurs connues and the danger zone. The update
// card sits in the first tab so it is on screen as soon as the page opens
// (the "database newer" banner and the sidebar dot both point there).
// Sync lives in settings-sync.js, updates in settings-updates.js.

const SETTINGS_TABS = [
  ['general', 'Général', 'settings'],
  ['sync', 'Synchronisation', 'refresh-cw'],
  ['ai', 'Intelligence artificielle', 'sparkles'],
  ['known', 'Valeurs connues', 'tag'],
  ['danger', 'Zone de danger', 'triangle-alert'],
];

/** The tab that stays selected across the re-renders every action triggers. */
let settingsTab = 'general';

/** Icon tile + title + description used by every settings card. */
function settingsCardHead(iconName, title, desc, tone) {
  return `<header class="settings-head">
    <span class="settings-ico${tone ? ` is-${escAttr(tone)}` : ''}" aria-hidden="true">${icon(iconName)}</span>
    <div><h3>${esc(title)}</h3>${desc ? `<p>${desc}</p>` : ''}</div>
  </header>`;
}

function renderLogoCard() {
  const body = state.hasLogo
    ? `<div class="logo-preview"><img src="/api/logo?t=${Date.now()}" alt="Logo de l'entreprise"></div>
       <div class="settings-actions">
         <button type="button" class="btn btn-outline" onclick="document.getElementById('logo-input').click()">${icons.upload} Remplacer</button>
         <button type="button" class="btn btn-outline btn-danger-outline" onclick="removeLogo()">${icons.trash} Retirer</button>
       </div>`
    : `<div class="logo-empty">
         <span class="empty-orb" aria-hidden="true">${icon('image')}</span>
         <p>Aucun logo pour le moment. Ajoutez celui de votre entreprise pour qu'il apparaisse en haut à droite de chaque facture (Excel et PDF).</p>
         <button type="button" class="btn btn-primary" onclick="document.getElementById('logo-input').click()">${icons.upload} Téléverser un logo</button>
       </div>`;
  return `<section class="card settings-card" aria-label="Logo de l'entreprise">
    ${settingsCardHead('image', "Logo de l'entreprise", "Format PNG ou JPG, en haut à droite de la facture.")}
    ${body}
    <input type="file" id="logo-input" accept="image/png,image/jpeg" hidden onchange="uploadLogo(this)">
  </section>`;
}

function renderCompanyCard() {
  const v = state.version || {};
  const row = (label, value) => `<div class="settings-row"><dt>${esc(label)}</dt><dd>${value}</dd></div>`;
  const yes = text => `<span class="badge badge-success">${esc(text)}</span>`;
  const no = text => `<span class="badge badge-secondary">${esc(text)}</span>`;
  return `<section class="card settings-card" aria-label="Entreprise">
    ${settingsCardHead('truck', 'Entreprise', "Le nom vient de l'installation et apparaît dans l'en-tête.")}
    <dl class="settings-list">
      ${row('Nom affiché', `<strong>${esc(companyName()) || '—'}</strong>`)}
      ${row('Version', `<span class="mono">${esc(v.version || '—')}</span>`)}
      ${row('Export PDF', state.pdfAvailable ? yes('Disponible') : no('LibreOffice requis'))}
      ${row('Logo', state.hasLogo ? yes('Ajouté') : no('Aucun'))}
    </dl>
  </section>`;
}

function renderGeneralPanel() {
  return `<div class="settings-split">
    <div class="settings-col">${renderLogoCard()}${renderCompanyCard()}</div>
    <div class="settings-col">${renderUpdateCard()}</div>
  </div>`;
}

function renderDangerPanel() {
  return `<section class="card settings-card settings-danger" aria-label="Zone de danger">
    ${settingsCardHead('triangle-alert', 'Zone de danger', 'Actions irréversibles : réfléchissez avant de confirmer.', 'danger')}
    <div class="danger-row">
      <div>
        <strong>Réinitialiser la base de données</strong>
        <p>Supprime tous les clients et toutes les factures de cet appareil. Les fichiers déjà générés et l'historique de synchronisation ne sont pas touchés.</p>
      </div>
      <button type="button" class="btn btn-danger" id="reset-db-btn" onclick="resetDatabase()">${icons.reset} Réinitialiser la base de données</button>
    </div>
  </section>`;
}

// ── Intelligence artificielle ───────────────────────────
// Read-only status of the local vision model. Fetched when the tab is first
// opened (the request can take a moment when the service is down), never on
// every render.

async function loadAiStatus() {
  state.aiStatus = { loading: true };
  paintAiPanel();
  try {
    state.aiStatus = await api('GET', '/api/ai/status');
  } catch (e) {
    state.aiStatus = { error: e.message, ready: false, installed_models: [] };
  }
  paintAiPanel();
}

function paintAiPanel() {
  const el = document.getElementById('ai-panel-body');
  if (el) el.innerHTML = renderAiBody();
}

function renderAiBody() {
  const s = state.aiStatus;
  if (!s || s.loading) {
    return `<div class="ai-loading" aria-busy="true"><span class="skeleton" style="width:38%;height:1.1rem"></span><span class="skeleton" style="width:70%;height:0.85rem;margin-top:0.8rem"></span><span class="skeleton" style="width:55%;height:0.85rem;margin-top:0.6rem"></span></div>`;
  }
  const models = (s.installed_models || []).length
    ? s.installed_models.map(m => `<li class="badge badge-outline">${esc(m)}</li>`).join('')
    : '<li class="settings-muted">Aucun modèle installé</li>';
  const row = (label, value) => `<div class="settings-row"><dt>${esc(label)}</dt><dd>${value}</dd></div>`;
  return `<div class="ai-status ${s.ready ? 'is-ready' : 'is-down'}" role="status">
      <span class="ai-dot" aria-hidden="true"></span>
      <strong>${s.ready ? 'Modèle de vision disponible' : 'Service IA non disponible'}</strong>
    </div>
    ${s.error ? `<div class="sync-warning">${icon('info')}<div>${esc(s.error)}</div></div>` : ''}
    <dl class="settings-list">
      ${row('Serveur', `<span class="mono">${esc(s.host || '—')}</span>`)}
      ${row('Modèle configuré', s.configured_model ? `<span class="mono">${esc(s.configured_model)}</span>` : '<span class="settings-muted">Automatique</span>')}
      ${row('Clé cloud', s.cloud ? '<span class="badge badge-success">Configurée</span>' : '<span class="badge badge-secondary">Aucune (local)</span>')}
      ${row('Modèles installés', `<ul class="ai-models">${models}</ul>`)}
    </dl>
    <div class="settings-actions"><button type="button" class="btn btn-outline" onclick="loadAiStatus()">${icon('refresh-cw', { size: 'sm' })} Actualiser</button></div>`;
}

function renderAiPanel() {
  return `<section class="card settings-card" aria-label="Intelligence artificielle">
    ${settingsCardHead('sparkles', 'Intelligence artificielle', "Lecture des billets par un modèle de vision, sur cet ordinateur. L'IA propose, vous validez : elle ne choisit jamais le client.")}
    <div id="ai-panel-body">${renderAiBody()}</div>
  </section>`;
}

// ── Page ────────────────────────────────────────────────

function renderSettings() {
  const panel = {
    general: renderGeneralPanel, sync: renderSyncCard, ai: renderAiPanel,
    known: renderKnownValuesCard, danger: renderDangerPanel,
  };
  const triggers = SETTINGS_TABS.map(([id, label, ico]) =>
    `<button type="button" class="tabs-trigger${id === 'danger' ? ' is-danger' : ''}" data-tab="${escAttr(id)}">${icon(ico, { size: 'sm' })}<span>${esc(label)}</span></button>`).join('');
  const panels = SETTINGS_TABS.map(([id]) =>
    `<div data-tab-panel="${escAttr(id)}" class="settings-panel"${id === settingsTab ? '' : ' hidden'}>${panel[id]()}</div>`).join('');
  return `<div class="page settings">
    <div class="page-head">
      <div>
        <h2>Paramètres</h2>
        <p>Logo, mises à jour, synchronisation, intelligence artificielle et valeurs connues</p>
      </div>
    </div>
    <div data-tabs data-tabs-value="${escAttr(settingsTab)}" class="settings-tabs" id="settings-tabs">
      <div class="tabs-list tabs-line" role="tablist" aria-label="Sections des paramètres">${triggers}</div>
      ${panels}
    </div>
  </div>`;
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


// Remember the selected tab across re-renders, and load the AI status lazily.
ui.hydrate.register(scope => {
  const host = scope.querySelector('#settings-tabs');
  if (!host || host.dataset.tabsBound) return;
  host.dataset.tabsBound = '1';
  host.addEventListener('tabschange', e => {
    settingsTab = e.detail.value;
    if (settingsTab === 'ai' && !state.aiStatus) loadAiStatus();
  });
  if (settingsTab === 'ai' && !state.aiStatus) loadAiStatus();
});
