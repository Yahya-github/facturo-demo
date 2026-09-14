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
  const rate = Number(c.taux_defaut) > 0 ? money(Number(c.taux_defaut)).replace(/,00(?= )/, '') + '/h' : '—';
  return `<tr data-client-id="${id}">
    <td><div class="cell-client">${ui.avatar(c.nom)}<div class="client-id-cell">
      <span class="cell-name" title="${escAttr(c.nom)}">${esc(c.nom)}</span>
      <span class="cell-sub" title="${escAttr(c.adresse)}">${esc(c.adresse) || 'Aucune adresse'}</span>
    </div></div></td>
    <td><span class="badge badge-blue">${esc(c.ref)}</span></td>
    <td class="client-next"><span class="client-next-num">${esc(next)}</span><span class="cell-sub">préfixe ${esc(c.prefix)}</span></td>
    <td class="num hide-sm">${esc(rate)}</td>
    <td class="num hide-sm">${t.count}</td>
    <td class="num">${t.count ? money(t.cents / 100) : '—'}</td>
    <td class="row-menu-cell"><button type="button" class="btn btn-quiet btn-icon btn-sm" data-client-menu="${id}" aria-label="Actions pour ${escAttr(c.nom)}">${icon('ellipsis')}</button></td>
  </tr>`;
}

function renderClientsEmpty() {
  return `<div class="card"><div class="empty-state clients-empty">
    <span class="empty-orb" aria-hidden="true">${icon('users')}</span>
    <h3>Aucun client pour le moment</h3>
    <p>Ajoutez votre premier client : il apparaîtra dans le sélecteur de facture, avec son préfixe et son taux habituel.</p>
    <button type="button" class="btn btn-primary" onclick="openClientModal()">${icons.plus} Ajouter un client</button>
  </div></div>`;
}

function renderClients() {
  const n = state.clients.length;
  const totals = clientTotals();
  const table = `<div class="card card-table"><div class="table-scroll"><table class="data-table clients-table">
      <thead><tr><th>Client</th><th>Réf</th><th>Prochain N°</th><th class="num hide-sm">Taux</th><th class="num hide-sm">Factures</th><th class="num">Facturé</th><th><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>${state.clients.map(c => renderClientRow(c, totals)).join('')}</tbody>
    </table></div></div>`;
  return `<div class="page page-wide clients">
    <div class="page-head">
      <div>
        <h2>Clients</h2>
        <p>${n ? `${n} client${n > 1 ? 's' : ''} : coordonnées, préfixe de facture et taux horaire habituel` : 'Gérez vos clients et leurs informations de facturation'}</p>
      </div>
      <div class="page-head-actions">
        <button type="button" class="btn btn-primary" onclick="openClientModal()">${icons.plus} Ajouter un client</button>
      </div>
    </div>
    ${n === 0 ? renderClientsEmpty() : table}
  </div>`;
}

// ── Row menus ───────────────────────────────────────────

const clientById = id => state.clients.find(c => c.id === Number(id));

function clientRowItems(c) {
  return [
    { label: 'Modifier', icon: 'pencil', onSelect: () => openClientModal(c.id) },
    { separator: true },
    { label: 'Supprimer', icon: 'trash-2', destructive: true, onSelect: () => confirmDeleteClient(c.id) },
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

const CLIENT_RULES = {
  'cm-nom': v => (v ? '' : "Indiquez le nom de l'entreprise"),
  'cm-ref': v => (v ? '' : 'La référence est requise'),
  'cm-prefix': v => (!v ? 'Le préfixe est requis' : /\s/.test(v) ? 'Sans espaces' : ''),
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
  const nom = clientField({ id: 'cm-nom', label: "Nom de l'entreprise", required: true,
    control: `<input class="form-input" id="cm-nom" autocomplete="off" placeholder="ex: Sample Client Ltd." value="${escAttr(client?.nom)}">` });
  const ref = clientField({ id: 'cm-ref', label: 'Référence', required: true, hint: 'Identifiant court pour ce client',
    control: `<input class="form-input" id="cm-ref" autocomplete="off" placeholder="ex: sample" value="${escAttr(client?.ref)}">` });
  const prefix = clientField({ id: 'cm-prefix', label: 'Préfixe facture', required: true,
    hint: '<span id="cm-prefix-preview">Préfixe du numéro de facture</span>',
    control: `<input class="form-input" id="cm-prefix" autocomplete="off" placeholder="ex: smpl" maxlength="10" value="${escAttr(client?.prefix)}">` });
  const adresse = clientField({ id: 'cm-adresse', label: 'Adresse',
    control: `<input class="form-input" id="cm-adresse" autocomplete="off" placeholder="ex: 123 rue Exemple, Villefictive, QC J0J 0J0" value="${escAttr(client?.adresse)}">` });
  const taux = clientField({ id: 'cm-taux-defaut', label: 'Taux horaire habituel', hint: 'Prérempli sur les nouveaux billets de ce client (facultatif)',
    control: `<div class="input-group-box"><span class="addon" aria-hidden="true">$</span>
      <input class="form-input" id="cm-taux-defaut" type="number" step="1" min="0" placeholder="65" value="${numAttr(client?.taux_defaut || '')}">
      <span class="addon" aria-hidden="true">/ h</span></div>` });
  return `${nom}<div class="field-row">${ref}${prefix}</div>${adresse}${taux}
    <label class="switch-field" for="cm-separer">
      <input type="checkbox" id="cm-separer" ${client && client.separer_chantiers ? 'checked' : ''}>
      <span class="switch-track"></span>
      <span class="switch-text">
        <span class="switch-title">Séparer les factures par chantier</span>
        <span class="switch-desc">Génère une facture distincte pour chaque « Chantier / Client » des billets, toutes au nom de ce client.</span>
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
    preview.textContent = p ? `Ex. : ${p}${n}, ${p}${String(Number(n) + 1).padStart(3, '0')}…` : 'Préfixe du numéro de facture';
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
      toast('Client modifié');
    } else {
      await api('POST', '/api/clients', readClientForm());
      toast('Client ajouté');
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
    title: client ? 'Modifier le client' : 'Nouveau client',
    description: client ? 'Les factures déjà générées ne changent pas.' : 'Ces informations apparaissent sur chaque facture de ce client.',
    body: `<form class="client-form" onsubmit="return false" novalidate>${clientDialogBody(client)}</form>`,
    footer: `<button type="button" class="btn btn-ghost" id="cm-cancel">Annuler</button>
      <button type="button" class="btn btn-primary" id="cm-save">${client ? 'Enregistrer' : 'Ajouter'}</button>`,
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
  if (!client) { toast('Client introuvable', 'error'); return; }
  const ok = await ui.alertDialog({
    title: 'Supprimer le client',
    description: `Voulez-vous vraiment supprimer ${client.nom} et toutes ses factures ? Cette action est irréversible.`,
    confirmLabel: 'Supprimer', destructive: true,
  });
  if (!ok) return;
  try {
    await api('DELETE', `/api/clients/${id}`);
    toast('Client supprimé');
    await loadData();
    render();
  } catch (e) { toast(e.message, 'error'); }
}
