// ── SETTINGS ────────────────────────────────────────────
// Tabs (ui/tabs.js): Général (logo, company, version and updates), Synchronisation,
// Intelligence artificielle, Valeurs connues and the danger zone. The update
// card sits in the first tab so it is on screen as soon as the page opens
// (the "database newer" banner and the sidebar dot both point there).
// Sync lives in settings-sync.js, updates in settings-updates.js.

// A function, not a constant: the labels are read at render time so they follow
// the language instead of the one the file loaded in.
const settingsTabs = () => [
  ['general', tr('settings.tab.general'), 'settings'],
  ['sync', tr('settings.tab.sync'), 'refresh-cw'],
  ['ai', tr('settings.tab.ai'), 'sparkles'],
  ['known', tr('settings.tab.known'), 'tag'],
  ['danger', tr('settings.tab.danger'), 'triangle-alert'],
];

/** The tab that stays selected across the re-renders every action triggers. */
let settingsTab = 'general';

const tr = (key, params) => (ui.i18n ? ui.i18n.t(key, params) : key);

/**
 * Translated text with **bold** spans, as safe HTML. The whole string is
 * escaped first, so the only markup that can come out is <strong>.
 */
function settingsRich(key, params) {
  return esc(tr(key, params)).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}

/** Icon tile + title + description used by every settings card. */
function settingsCardHead(iconName, title, desc, tone) {
  return `<header class="settings-head">
    <span class="settings-ico${tone ? ` is-${escAttr(tone)}` : ''}" aria-hidden="true">${icon(iconName)}</span>
    <div><h3>${esc(title)}</h3>${desc ? `<p>${desc}</p>` : ''}</div>
  </header>`;
}

function renderLogoCard() {
  const body = state.hasLogo
    ? `<div class="logo-preview"><img src="/api/logo?t=${Date.now()}" alt="${escAttr(tr('settings.logo.alt'))}"></div>
       <div class="settings-actions">
         <button type="button" class="btn btn-outline" onclick="document.getElementById('logo-input').click()">${icons.upload} ${esc(tr('settings.logo.replace'))}</button>
         <button type="button" class="btn btn-outline btn-danger-outline" onclick="removeLogo()">${icons.trash} ${esc(tr('settings.logo.remove'))}</button>
       </div>`
    : `<div class="logo-empty">
         <span class="empty-orb" aria-hidden="true">${icon('image')}</span>
         <p>${esc(tr('settings.logo.empty'))}</p>
         <button type="button" class="btn btn-primary" onclick="document.getElementById('logo-input').click()">${icons.upload} ${esc(tr('settings.logo.upload'))}</button>
       </div>`;
  return `<section class="card settings-card" aria-label="${escAttr(tr('settings.logo.alt'))}">
    ${settingsCardHead('image', tr('settings.logo.alt'), esc(tr('settings.logo.hint')))}
    ${body}
    <input type="file" id="logo-input" accept="image/png,image/jpeg" hidden onchange="uploadLogo(this)">
  </section>`;
}

function renderCompanyCard() {
  const v = state.version || {};
  const row = (label, value) => `<div class="settings-row"><dt>${esc(label)}</dt><dd>${value}</dd></div>`;
  const yes = text => `<span class="badge badge-success">${esc(text)}</span>`;
  const no = text => `<span class="badge badge-secondary">${esc(text)}</span>`;
  return `<section class="card settings-card" aria-label="${escAttr(tr('settings.company.title'))}">
    ${settingsCardHead('truck', tr('settings.company.title'), esc(tr('settings.company.desc')))}
    <dl class="settings-list">
      ${row(tr('settings.company.name'), `<strong>${esc(companyName()) || '—'}</strong>`)}
      ${row(tr('settings.company.version'), `<span class="mono">${esc(v.version || '—')}</span>`)}
      ${row(tr('settings.company.pdf'), state.pdfAvailable ? yes(tr('settings.company.pdf_yes')) : no(tr('settings.company.pdf_no')))}
      ${row(tr('settings.company.logo'), state.hasLogo ? yes(tr('settings.company.logo_yes')) : no(tr('settings.company.logo_no')))}
    </dl>
  </section>`;
}

// Same markup contract as the header control (data-lang-group + data-lang-set),
// so ui.i18n.mountSwitchers() owns the click and paintSwitches() the state.
// A second control is worth it here: language is a preference, and preferences
// live on this page.
function renderLanguageCard() {
  const active = ui.i18n ? ui.i18n.lang() : 'en';
  const btn = (code, short) => `<button type="button" class="seg-btn" data-lang-set="${escAttr(code)}" aria-pressed="${code === active}" aria-label="${escAttr(tr('lang.' + code))}" title="${escAttr(tr('lang.' + code))}">${esc(short)}</button>`;
  return `<section class="card settings-card" aria-label="${escAttr(tr('lang.group'))}" data-i18n-attr="aria-label:lang.group">
    ${settingsCardHead('code', tr('lang.card_title'), esc(tr('lang.card_desc')))}
    <div class="seg seg-labeled" id="lang-select" role="group" aria-label="${escAttr(tr('lang.group'))}" data-lang-group data-i18n-attr="aria-label:lang.group">
      ${btn('en', 'EN')}${btn('fr', 'FR')}
    </div>
  </section>`;
}

function renderGeneralPanel() {
  return `<div class="settings-split">
    <div class="settings-col">${renderLogoCard()}${renderCompanyCard()}</div>
    <div class="settings-col">${renderLanguageCard()}${renderUpdateCard()}</div>
  </div>`;
}

function renderDangerPanel() {
  return `<section class="card settings-card settings-danger" aria-label="${escAttr(tr('settings.tab.danger'))}">
    ${settingsCardHead('triangle-alert', tr('settings.tab.danger'), esc(tr('settings.danger.desc')), 'danger')}
    <div class="danger-row">
      <div>
        <strong>${esc(tr('settings.danger.reset'))}</strong>
        <p>${esc(tr('settings.danger.reset_desc'))}</p>
      </div>
      <button type="button" class="btn btn-danger" id="reset-db-btn" onclick="resetDatabase()">${icons.reset} ${esc(tr('settings.danger.reset'))}</button>
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
    : `<li class="settings-muted">${esc(tr('settings.ai.no_models'))}</li>`;
  const row = (label, value) => `<div class="settings-row"><dt>${esc(label)}</dt><dd>${value}</dd></div>`;
  return `<div class="ai-status ${s.ready ? 'is-ready' : 'is-down'}" role="status">
      <span class="ai-dot" aria-hidden="true"></span>
      <strong>${esc(tr(s.ready ? 'settings.ai.ready' : 'settings.ai.down'))}</strong>
    </div>
    ${s.error ? `<div class="sync-warning">${icon('info')}<div>${esc(s.error)}</div></div>` : ''}
    <dl class="settings-list">
      ${row(tr('settings.ai.server'), `<span class="mono">${esc(s.host || '—')}</span>`)}
      ${row(tr('settings.ai.model'), s.configured_model ? `<span class="mono">${esc(s.configured_model)}</span>` : `<span class="settings-muted">${esc(tr('settings.ai.auto'))}</span>`)}
      ${row(tr('settings.ai.cloud'), s.cloud ? `<span class="badge badge-success">${esc(tr('settings.ai.cloud_yes'))}</span>` : `<span class="badge badge-secondary">${esc(tr('settings.ai.cloud_no'))}</span>`)}
      ${row(tr('settings.ai.installed'), `<ul class="ai-models">${models}</ul>`)}
    </dl>
    <div class="settings-actions"><button type="button" class="btn btn-outline" onclick="loadAiStatus()">${icon('refresh-cw', { size: 'sm' })} ${esc(tr('settings.ai.refresh'))}</button></div>`;
}

function renderAiPanel() {
  return `<section class="card settings-card" aria-label="${escAttr(tr('settings.tab.ai'))}">
    ${settingsCardHead('sparkles', tr('settings.tab.ai'), esc(tr('settings.ai.desc')))}
    <div id="ai-panel-body">${renderAiBody()}</div>
  </section>`;
}

// ── Page ────────────────────────────────────────────────

function renderSettings() {
  const panel = {
    general: renderGeneralPanel, sync: renderSyncCard, ai: renderAiPanel,
    known: renderKnownValuesCard, danger: renderDangerPanel,
  };
  const tabs = settingsTabs();
  const triggers = tabs.map(([id, label, ico]) =>
    `<button type="button" class="tabs-trigger${id === 'danger' ? ' is-danger' : ''}" data-tab="${escAttr(id)}">${icon(ico, { size: 'sm' })}<span>${esc(label)}</span></button>`).join('');
  const panels = tabs.map(([id]) =>
    `<div data-tab-panel="${escAttr(id)}" class="settings-panel"${id === settingsTab ? '' : ' hidden'}>${panel[id]()}</div>`).join('');
  return `<div class="page settings">
    <div class="page-head">
      <div>
        <h2>${esc(tr('nav.settings'))}</h2>
        <p>${esc(tr('settings.lead'))}</p>
      </div>
    </div>
    <div data-tabs data-tabs-value="${escAttr(settingsTab)}" class="settings-tabs" id="settings-tabs">
      <div class="tabs-list tabs-line" role="tablist" aria-label="${escAttr(tr('settings.tabs_aria'))}">${triggers}</div>
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
      const err = await res.json().catch(() => ({ detail: tr('settings.server_error') }));
      throw new Error(err.detail || tr('settings.logo.upload_failed'));
    }
    state.hasLogo = true;
    toast(tr('settings.logo.saved'));
    render();
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    input.value = '';
  }
}

async function removeLogo() {
  const ok = await ui.alertDialog({
    title: tr('settings.logo.remove_title'),
    description: tr('settings.logo.remove_desc'),
    confirmLabel: tr('settings.logo.remove'), destructive: true,
  });
  if (!ok) return;
  try {
    await api('DELETE', '/api/logo');
    state.hasLogo = false;
    toast(tr('settings.logo.removed'));
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
