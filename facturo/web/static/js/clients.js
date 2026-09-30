// ── CLIENTS ─────────────────────────────────────────────

/** Invoice count and billed total per client id, from the already loaded invoices. */
function clientTotals() {
  const totals = new Map();
  state.factures.forEach(f => {
    const t = totals.get(f.client_id) || { count: 0, cents: 0 };
    t.count += 1;
    t.cents += Math.round((Number(f.total_ttc) || 0) * 100);
    totals.set(f.client_id, t);
  });
  return totals;
}

function renderClientRow(c, totals) {
  const t = totals.get(c.id) || { count: 0, cents: 0 };
  const id = Number(c.id);
  const next = `${c.prefix || ''}${String(c.next_numero).padStart(3, '0')}`;
  const rate = Number(c.taux_defaut) > 0 ? money(Number(c.taux_defaut)).replace(/[.,]00(?= )/, '') + '/h' : '—';
  return `<tr data-client-id="${id}">
    <td><div class="cell-client">${ui.avatar(c.nom)}<div class="client-id-cell">
      <span class="cell-name" title="${escAttr(c.nom)}">${esc(c.nom)}</span>
      <span class="cell-sub" title="${escAttr(c.adresse)}">${esc(c.adresse) || esc(ui.i18n.t('clients.no_address'))}</span>
    </div></div></td>
    <td><span class="badge badge-blue">${esc(c.ref)}</span></td>
    <td class="client-next"><span class="client-next-num">${esc(next)}</span><span class="cell-sub">${esc(ui.i18n.t('clients.prefix_label', { prefix: c.prefix }))}</span></td>
    <td class="num hide-sm">${esc(rate)}</td>
    <td class="num hide-sm">${t.count}</td>
    <td class="num">${t.count ? money(t.cents / 100) : '—'}</td>
    <td class="row-menu-cell"><button type="button" class="btn btn-quiet btn-icon btn-sm" data-client-menu="${id}" aria-label="${escAttr(ui.i18n.t('clients.aria_actions', { name: c.nom }))}">${icon('ellipsis')}</button></td>
  </tr>`;
}

function renderClientsEmpty() {
  return `<div class="card"><div class="empty-state clients-empty">
    <span class="empty-orb" aria-hidden="true">${icon('users')}</span>
    <h3>${esc(ui.i18n.t('clients.empty_title'))}</h3>
    <p>${esc(ui.i18n.t('clients.empty_desc'))}</p>
    <button type="button" class="btn btn-primary" onclick="openClientModal()">${icons.plus} ${esc(ui.i18n.t('clients.add'))}</button>
  </div></div>`;
}

function renderClients() {
  const t = ui.i18n.t;
  const n = state.clients.length;
  const totals = clientTotals();
  const table = `<div class="card card-table"><div class="table-scroll"><table class="data-table clients-table">
      <thead><tr><th>${esc(t('clients.col.client'))}</th><th>${esc(t('clients.col.ref'))}</th><th>${esc(t('clients.col.next'))}</th><th class="num hide-sm">${esc(t('clients.col.rate'))}</th><th class="num hide-sm">${esc(t('clients.col.invoices'))}</th><th class="num">${esc(t('clients.col.billed'))}</th><th><span class="sr-only">${esc(t('clients.col.actions'))}</span></th></tr></thead>
      <tbody>${state.clients.map(c => renderClientRow(c, totals)).join('')}</tbody>
    </table></div></div>`;
  return `<div class="page page-wide clients">
    <div class="page-head">
      <div>
        <h2>${esc(t('clients.title'))}</h2>
        <p>${esc(n ? ui.i18n.tn('clients.subtitle', n) : t('clients.subtitle_empty'))}</p>
      </div>
      <div class="page-head-actions">
        <button type="button" class="btn btn-primary" onclick="openClientModal()">${icons.plus} ${esc(t('clients.add'))}</button>
      </div>
    </div>
    ${n === 0 ? renderClientsEmpty() : table}
  </div>`;
}

// ── Row menus ───────────────────────────────────────────

const clientById = id => state.clients.find(c => c.id === Number(id));

function clientRowItems(c) {
  return [
    { label: ui.i18n.t('action.edit'), icon: 'pencil', onSelect: () => openClientModal(c.id) },
    { separator: true },
    { label: ui.i18n.t('action.delete'), icon: 'trash-2', destructive: true, onSelect: () => confirmDeleteClient(c.id) },
  ];
}

function bindClientRows() {
  document.querySelectorAll('.clients [data-client-menu]').forEach(btn => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = '1';
    ui.menu.attach(btn, () => {
      const c = clientById(btn.dataset.clientMenu);
      return c ? clientRowItems(c) : [];
    });
  });
  const table = document.querySelector('.clients-table');
  if (table && !table.dataset.ctxBound) {
    table.dataset.ctxBound = '1';
    ui.contextMenu.attach(table, 'tr[data-client-id]', row => {
      const c = clientById(row.dataset.clientId);
      return c ? clientRowItems(c) : null;
    });
  }
}

ui.hydrate.register(bindClientRows);

// ── Client dialog ───────────────────────────────────────

// Messages are read when a field is checked, not when the file loads, so they
// follow the language.
const CLIENT_RULES = {
  'cm-nom': v => (v ? '' : ui.i18n.t('clients.field.name_required')),
  'cm-ref': v => (v ? '' : ui.i18n.t('clients.field.ref_required')),
  'cm-prefix': v => (!v ? ui.i18n.t('clients.field.prefix_required') : /\s/.test(v) ? ui.i18n.t('clients.field.prefix_spaces') : ''),
};

/** Show or clear the inline message of one field; returns true when it is valid. */
function checkClientField(id) {
  const input = document.getElementById(id);
  const rule = CLIENT_RULES[id];
  if (!input || !rule) return true;
  const message = rule(input.value.trim());
  const field = input.closest('.field');
  field.classList.toggle('is-invalid', !!message);
  field.classList.toggle('is-valid', !message && !!input.value.trim());
  input.setAttribute('aria-invalid', message ? 'true' : 'false');
  const err = field.querySelector('.field-error-text');
  if (err) err.textContent = message;
  return !message;
}

function clientField(o) {
  const hint = o.hint ? `<span class="field-hint" id="${o.id}-hint">${o.hint}</span>` : '';
  const err = o.required ? `<span class="field-error">${icon('circle-alert', { size: 'xs' })}<span class="field-error-text" role="alert"></span></span>` : '';
  return `<div class="field">
    <label class="field-label" for="${o.id}">${esc(o.label)}${o.required ? '<span class="req" aria-hidden="true">*</span>' : ''}</label>
    ${o.control}${hint}${err}
  </div>`;
}

function clientDialogBody(client) {
  const t = ui.i18n.t;
  const nom = clientField({ id: 'cm-nom', label: t('clients.field.name'), required: true,
    control: `<input class="form-input" id="cm-nom" autocomplete="off" placeholder="${escAttr(t('clients.field.name_ph'))}" value="${escAttr(client?.nom)}">` });
  const ref = clientField({ id: 'cm-ref', label: t('clients.field.ref'), required: true, hint: esc(t('clients.field.ref_hint')),
    control: `<input class="form-input" id="cm-ref" autocomplete="off" placeholder="${escAttr(t('clients.field.ref_ph'))}" value="${escAttr(client?.ref)}">` });
  const prefix = clientField({ id: 'cm-prefix', label: t('clients.field.prefix'), required: true,
    hint: `<span id="cm-prefix-preview">${esc(t('clients.field.prefix_hint'))}</span>`,
    control: `<input class="form-input" id="cm-prefix" autocomplete="off" placeholder="${escAttr(t('clients.field.prefix_ph'))}" maxlength="10" value="${escAttr(client?.prefix)}">` });
  const adresse = clientField({ id: 'cm-adresse', label: t('clients.field.address'),
    control: `<input class="form-input" id="cm-adresse" autocomplete="off" placeholder="${escAttr(t('clients.field.address_ph'))}" value="${escAttr(client?.adresse)}">` });
  const taux = clientField({ id: 'cm-taux-defaut', label: t('clients.field.rate'), hint: esc(t('clients.field.rate_hint')),
    control: `<div class="input-group-box"><span class="addon" aria-hidden="true">$</span>
      <input class="form-input" id="cm-taux-defaut" type="number" step="1" min="0" placeholder="65" value="${numAttr(client?.taux_defaut || '')}">
      <span class="addon" aria-hidden="true">/ h</span></div>` });
  return `${nom}<div class="field-row">${ref}${prefix}</div>${adresse}${taux}
    <label class="switch-field" for="cm-separer">
      <input type="checkbox" id="cm-separer" ${client && client.separer_chantiers ? 'checked' : ''}>
      <span class="switch-track"></span>
      <span class="switch-text">
        <span class="switch-title">${esc(t('clients.field.split_title'))}</span>
        <span class="switch-desc">${esc(t('clients.field.split_desc'))}</span>
      </span>
    </label>`;
}

/** Live "abcd001" preview under the prefix field, and the ref -> prefix suggestion. */
function wireClientDialog(client) {
  const ref = document.getElementById('cm-ref');
  const prefix = document.getElementById('cm-prefix');
  const preview = document.getElementById('cm-prefix-preview');
  const paint = () => {
    const p = prefix.value.trim();
    const n = client ? String(client.next_numero).padStart(3, '0') : '001';
    const text = p
      ? ui.i18n.t('clients.field.prefix_preview', { a: `${p}${n}`, b: `${p}${String(Number(n) + 1).padStart(3, '0')}` })
      : ui.i18n.t('clients.field.prefix_hint');
    if (preview.textContent !== text) preview.textContent = text;
  };
  ref.addEventListener('input', () => {
    if (!client && ref.value.length >= 4 && !prefix.dataset.manual) { prefix.value = ref.value.slice(0, 4).toLowerCase(); paint(); }
  });
  prefix.addEventListener('input', () => { prefix.dataset.manual = '1'; paint(); });
  Object.keys(CLIENT_RULES).forEach(id => {
    const el = document.getElementById(id);
    el.addEventListener('blur', () => checkClientField(id));
    el.addEventListener('input', () => { if (el.closest('.field').classList.contains('is-invalid')) checkClientField(id); });
  });
  paint();
}

function readClientForm() {
  const val = id => document.getElementById(id).value.trim();
  return {
    nom: val('cm-nom'), ref: val('cm-ref'), prefix: val('cm-prefix'), adresse: val('cm-adresse'),
    separer_chantiers: document.getElementById('cm-separer').checked,
    taux_defaut: parseFloat(val('cm-taux-defaut')) || 0,
  };
}

async function saveClient(client, dialog) {
  const invalid = Object.keys(CLIENT_RULES).filter(id => !checkClientField(id));
  if (invalid.length) { document.getElementById(invalid[0]).focus(); return; }
  const save = document.getElementById('cm-save');
  save.disabled = true;
  try {
    if (client) {
      await api('PUT', `/api/clients/${client.id}`, readClientForm());
      toast(ui.i18n.t('clients.toast.updated'));
    } else {
      await api('POST', '/api/clients', readClientForm());
      toast(ui.i18n.t('clients.toast.added'));
    }
    dialog.close(true);
    await loadData();
    render();
  } catch (e) {
    save.disabled = false;
    toast(e.message, 'error');
  }
}

function openClientModal(clientId) {
  const client = clientId ? clientById(clientId) : null;
  const dialog = ui.dialog.show({
    title: ui.i18n.t(client ? 'clients.dialog.edit_title' : 'clients.dialog.new_title'),
    description: ui.i18n.t(client ? 'clients.dialog.edit_desc' : 'clients.dialog.new_desc'),
    body: `<form class="client-form" onsubmit="return false" novalidate>${clientDialogBody(client)}</form>`,
    footer: `<button type="button" class="btn btn-ghost" id="cm-cancel">${esc(ui.i18n.t('action.cancel'))}</button>
      <button type="button" class="btn btn-primary" id="cm-save">${esc(ui.i18n.t(client ? 'action.save' : 'action.add'))}</button>`,
    initialFocus: '#cm-nom',
  });
  wireClientDialog(client);
  document.getElementById('cm-cancel').addEventListener('click', () => dialog.close(false));
  document.getElementById('cm-save').addEventListener('click', () => saveClient(client, dialog));
  document.querySelector('.client-form').addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type !== 'checkbox') { e.preventDefault(); saveClient(client, dialog); }
  });
}

async function confirmDeleteClient(id) {
  const client = clientById(id);
  if (!client) { toast(ui.i18n.t('clients.not_found'), 'error'); return; }
  const ok = await ui.alertDialog({
    title: ui.i18n.t('clients.delete_title'),
    description: ui.i18n.t('clients.delete_desc', { name: client.nom }),
    confirmLabel: ui.i18n.t('action.delete'), destructive: true,
  });
  if (!ok) return;
  try {
    await api('DELETE', `/api/clients/${id}`);
    toast(ui.i18n.t('clients.toast.deleted'));
    await loadData();
    render();
  } catch (e) { toast(e.message, 'error'); }
}
