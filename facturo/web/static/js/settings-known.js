// ── SETTINGS: Valeurs connues ───────────────────────────
// Curation of the shop's own Chantier / Plaque vocabulary (what autocomplete
// offers and what the AI corrects towards). The list shows hidden and merged
// values too, which loadData() filters out of the suggestion lists.

// Which list the card is showing. Module-level so it survives the
// render() that follows every edit.
let kvTab = 'chantier';

function renderKnownValuesCard() {
  const rows = (state.kvAll || []).filter(v => v.kind === kvTab);
  const label = kvTab === 'chantier' ? 'un chantier' : 'une plaque';
  const count = kind => (state.kvAll || []).filter(v => v.kind === kind).length;
  const body = rows.length
    ? rows.map(v => `<div class="kv-row${v.hidden ? ' is-hidden' : ''}">
        <span class="kv-value">${esc(v.valeur)}</span>
        <span class="kv-meta">${v.times_used}×${v.alias_valeur ? ` → ${esc(v.alias_valeur)}` : ''}${v.hidden ? ' · masqué' : ''}</span>
        <span class="kv-actions">
          <button type="button" class="kv-btn" onclick="renameKnownValue(${Number(v.id)})">Renommer</button>
          <button type="button" class="kv-btn" onclick="toggleKnownValue(${Number(v.id)}, ${v.hidden ? 'false' : 'true'})">${v.hidden ? 'Afficher' : 'Masquer'}</button>
          <button type="button" class="kv-btn kv-btn-danger" onclick="deleteKnownValue(${Number(v.id)})">Supprimer</button>
        </span>
      </div>`).join('')
    : `<div class="kv-empty">${icon('tag')}<p>Aucune valeur enregistrée pour l'instant. Elles s'ajoutent d'elles-mêmes au fil de vos factures.</p></div>`;

  return `<section class="card settings-card" aria-label="Chantiers et plaques connus">
    ${settingsCardHead('tag', 'Chantiers et plaques connus', "Ce que les champs Chantier et Plaque proposent, et ce que l'IA utilise pour corriger ses lectures. Renommer une valeur ne modifie pas les factures déjà générées.")}
    <div class="seg kv-seg" role="group" aria-label="Type de valeur">
      <button type="button" class="seg-btn${kvTab === 'chantier' ? ' active' : ''}" onclick="setKvTab('chantier')">Chantiers <span class="kv-count">${count('chantier')}</span></button>
      <button type="button" class="seg-btn${kvTab === 'plaque' ? ' active' : ''}" onclick="setKvTab('plaque')">Plaques <span class="kv-count">${count('plaque')}</span></button>
    </div>
    <div class="kv-list">${body}</div>
    <div class="kv-add">
      <input class="form-input" id="kv-new" placeholder="Ajouter ${label}…" autocomplete="off" onkeydown="if(event.key==='Enter'){event.preventDefault();addKnownValue();}">
      <button type="button" class="btn btn-outline" onclick="addKnownValue()">${icons.plus} Ajouter</button>
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

