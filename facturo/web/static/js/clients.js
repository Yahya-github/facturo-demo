// ── CLIENTS ─────────────────────────────────────────────

function renderClients() {
  return `<div class="page page-wide">
    <div class="page-header">
      <div>
        <h2>Clients</h2>
        <div class="subtitle">Gérez vos clients et leurs informations de facturation</div>
      </div>
      <button class="btn btn-primary" onclick="openClientModal()">${icons.plus} Ajouter un client</button>
    </div>
    <div class="card">
      ${state.clients.length === 0 ? `
        <div class="empty-state">
          ${icons.users}
          <h3>Aucun client</h3>
          <p>Ajoutez votre premier client pour commencer à créer des factures.</p>
        </div>
      ` : `
        <table class="data-table">
          <thead><tr><th>Nom</th><th>Réf</th><th>Préfixe</th><th>Prochain N°</th><th>Adresse</th><th></th></tr></thead>
          <tbody>
            ${state.clients.map(c => `
              <tr>
                <td style="font-weight:600">${esc(c.nom)}</td>
                <td><span class="badge badge-blue">${esc(c.ref)}</span></td>
                <td>${esc(c.prefix)}</td>
                <td>${esc(c.prefix)}${String(c.next_numero).padStart(3, '0')}</td>
                <td style="max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">${esc(c.adresse)}</td>
                <td class="actions">
                  <button class="btn btn-ghost btn-sm" onclick="openClientModal(${c.id})">${icons.edit}</button>
                  <button class="btn btn-ghost btn-sm" onclick="confirmDeleteClient(${Number(c.id)})" style="color:var(--red-500)">${icons.trash}</button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `}
    </div>
  </div>`;
}

function openClientModal(clientId) {
  const client = clientId ? state.clients.find(c => c.id === clientId) : null;
  const title = client ? 'Modifier le client' : 'Nouveau client';
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <h3>${title}</h3>
        <button class="modal-close" onclick="closeModal(this.closest('.modal-overlay'))">${icons.x}</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label class="form-label">Nom de l'entreprise</label>
          <input class="form-input" id="cm-nom" placeholder="ex: Sample Client Ltd." value="${escAttr(client?.nom)}">
        </div>
        <div class="form-row form-row-2">
          <div class="form-group">
            <label class="form-label">Référence</label>
            <input class="form-input" id="cm-ref" placeholder="ex: sample" value="${escAttr(client?.ref)}">
            <div class="form-hint">Identifiant court pour ce client</div>
          </div>
          <div class="form-group">
            <label class="form-label">Préfixe facture</label>
            <input class="form-input" id="cm-prefix" placeholder="ex: smpl" maxlength="10" value="${escAttr(client?.prefix)}">
            <div class="form-hint">Préfixe du numéro de facture</div>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">Adresse</label>
          <input class="form-input" id="cm-adresse" placeholder="ex: 123 rue Exemple, Villefictive, QC J0J 0J0" value="${escAttr(client?.adresse)}">
        </div>
        <div class="form-group">
          <label class="form-label">Taux horaire habituel ($)</label>
          <input class="form-input" id="cm-taux-defaut" type="number" step="1" min="0"
            placeholder="ex: 65.00" value="${numAttr(client?.taux_defaut || '')}">
          <div class="form-hint">Prérempli automatiquement sur les nouveaux billets de ce client (facultatif)</div>
        </div>
        <label class="switch-field" for="cm-separer">
          <input type="checkbox" id="cm-separer" ${client && client.separer_chantiers ? 'checked' : ''}>
          <span class="switch-track"></span>
          <span class="switch-text">
            <span class="switch-title">Séparer les factures par chantier</span>
            <span class="switch-desc">Génère une facture distincte pour chaque « Chantier / Client » des billets, toutes au nom de ce client.</span>
          </span>
        </label>
      </div>
      <div class="modal-footer">
        <button class="btn btn-ghost" onclick="closeModal(this.closest('.modal-overlay'))">Annuler</button>
        <button class="btn btn-primary" id="cm-save">${client ? 'Enregistrer' : 'Ajouter'}</button>
      </div>
    </div>
  `;
  openModal(overlay);

  const refInput = $('#cm-ref');
  const prefixInput = $('#cm-prefix');
  refInput.addEventListener('input', () => {
    if (!client && refInput.value.length >= 4 && !prefixInput.dataset.manual) {
      prefixInput.value = refInput.value.slice(0, 4).toLowerCase();
    }
  });
  prefixInput.addEventListener('input', () => { prefixInput.dataset.manual = '1'; });

  $('#cm-save').addEventListener('click', async () => {
    const data = {
      nom: $('#cm-nom').value.trim(),
      ref: $('#cm-ref').value.trim(),
      prefix: $('#cm-prefix').value.trim(),
      adresse: $('#cm-adresse').value.trim(),
      separer_chantiers: $('#cm-separer').checked,
      taux_defaut: parseFloat($('#cm-taux-defaut').value) || 0,
    };
    if (!data.nom || !data.ref || !data.prefix) {
      toast('Veuillez remplir le nom, la référence et le préfixe', 'error');
      return;
    }
    try {
      if (client) {
        await api('PUT', `/api/clients/${client.id}`, data);
        toast('Client modifié');
      } else {
        await api('POST', '/api/clients', data);
        toast('Client ajouté');
      }
      closeModal(overlay);
      await loadData();
      render();
    } catch (e) {
      toast(e.message, 'error');
    }
  });
}

function confirmDeleteClient(id) {
  const client = state.clients.find(c => c.id === id);
  if (!client) { toast('Client introuvable', 'error'); return; }
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal" style="max-width:420px">
      <div class="modal-header"><h3>Supprimer le client</h3></div>
      <div class="modal-body">
        <p class="confirm-text">Voulez-vous vraiment supprimer <strong>${esc(client.nom)}</strong> et toutes ses factures ?</p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-ghost" onclick="closeModal(this.closest('.modal-overlay'))">Annuler</button>
        <button class="btn btn-danger" id="confirm-del">Supprimer</button>
      </div>
    </div>
  `;
  openModal(overlay);
  $('#confirm-del').addEventListener('click', async () => {
    try {
      await api('DELETE', `/api/clients/${id}`);
      toast('Client supprimé');
      closeModal(overlay);
      await loadData();
      render();
    } catch (e) { toast(e.message, 'error'); }
  });
}
