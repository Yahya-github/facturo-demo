// ── SETTINGS: Valeurs connues ───────────────────────────
// Curation of the shop's own Chantier / Plaque vocabulary (what autocomplete
// offers and what the AI corrects towards). The list shows hidden and merged
// values too, which loadData() filters out of the suggestion lists.

// Which list the card is showing. Module-level so it survives the
// render() that follows every edit.
let kvTab = 'chantier';

function renderKnownValuesCard() {
  const rows = (state.kvAll || []).filter(v => v.kind === kvTab);
  const what = ui.i18n.t(kvTab === 'chantier' ? 'settings.known.a_worksite' : 'settings.known.a_plate');
  const t = ui.i18n.t;
  const count = kind => (state.kvAll || []).filter(v => v.kind === kind).length;
  const body = rows.length
    ? rows.map(v => `<div class="kv-row${v.hidden ? ' is-hidden' : ''}">
        <span class="kv-value">${esc(v.valeur)}</span>
        <span class="kv-meta">${v.times_used}×${v.alias_valeur ? ` → ${esc(v.alias_valeur)}` : ''}${v.hidden ? ` · ${esc(t('settings.known.hidden'))}` : ''}</span>
        <span class="kv-actions">
          <button type="button" class="kv-btn" onclick="renameKnownValue(${Number(v.id)})">${esc(t('settings.known.rename'))}</button>
          <button type="button" class="kv-btn" onclick="toggleKnownValue(${Number(v.id)}, ${v.hidden ? 'false' : 'true'})">${esc(t(v.hidden ? 'settings.known.show' : 'settings.known.hide'))}</button>
          <button type="button" class="kv-btn kv-btn-danger" onclick="deleteKnownValue(${Number(v.id)})">${esc(t('action.delete'))}</button>
        </span>
      </div>`).join('')
    : `<div class="kv-empty">${icon('tag')}<p>${esc(t('settings.known.empty'))}</p></div>`;

  return `<section class="card settings-card" aria-label="${escAttr(t('settings.known.title'))}">
    ${settingsCardHead('tag', t('settings.known.title'), esc(t('settings.known.desc')))}
    <div class="seg kv-seg" role="group" aria-label="${escAttr(t('settings.known.type_aria'))}">
      <button type="button" class="seg-btn${kvTab === 'chantier' ? ' active' : ''}" onclick="setKvTab('chantier')">${esc(t('settings.known.worksites'))} <span class="kv-count">${count('chantier')}</span></button>
      <button type="button" class="seg-btn${kvTab === 'plaque' ? ' active' : ''}" onclick="setKvTab('plaque')">${esc(t('settings.known.plates'))} <span class="kv-count">${count('plaque')}</span></button>
    </div>
    <div class="kv-list">${body}</div>
    <div class="kv-add">
      <input class="form-input" id="kv-new" placeholder="${escAttr(t('settings.known.add_ph', { what }))}" autocomplete="off" onkeydown="if(event.key==='Enter'){event.preventDefault();addKnownValue();}">
      <button type="button" class="btn btn-outline" onclick="addKnownValue()">${icons.plus} ${esc(t('action.add'))}</button>
    </div>
  </section>`;
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
    toast(ui.i18n.t('settings.known.added'));
  } catch (e) { toast(e.message, 'error'); }
}

async function renameKnownValue(id) {
  const current = (state.kvAll || []).find(v => v.id === id);
  const valeur = await ui.promptDialog({
    title: ui.i18n.t('settings.known.rename_title'), label: ui.i18n.t('settings.known.rename_label'),
    value: current ? current.valeur : '', confirmLabel: ui.i18n.t('settings.known.rename'),
    cancelLabel: ui.i18n.t('action.cancel'),
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
    title: ui.i18n.t('settings.known.delete_title'),
    description: ui.i18n.t('settings.known.delete_desc', { value: v ? v.valeur : '' }),
    confirmLabel: ui.i18n.t('action.delete'), destructive: true,
  });
  if (!ok) return;
  try {
    await api('DELETE', `/api/known-values/${id}`);
    await reloadKnownValues();
  } catch (e) { toast(e.message, 'error'); }
}

