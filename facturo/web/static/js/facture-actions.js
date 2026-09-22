// ── FACTURE: generate, edit, cancel, delete ─────────────────────────────

let generating = false;

// A billet nobody has touched is the untouched starter row: skipped, not an error.
function isUntouchedBillet(b) {
  return ['date_billet', 'chantier', 'plaque', 'numero_billet', 'description', 'quantite', 'taux', 'remise_pct', 'remise_montant']
    .every(k => b[k] === undefined || b[k] === null || String(b[k]).trim() === '');
}

async function generateFacture() {
  if (generating) return;
  syncBilletInputs();
  const clientId = $('#fac-client')?.value;
  const numero = $('#fac-numero')?.value;
  const date = $('#fac-date')?.value;

  if (!clientId) { toast('Veuillez choisir un client', 'error'); return; }

  const touched = billets.filter(b => !isUntouchedBillet(b));
  if (touched.length === 0) { toast('Ajoutez au moins un billet avec quantité et taux', 'error'); return; }
  // Never drop a billet silently: a half-filled one would vanish from the invoice.
  const incomplete = incompleteBillets(touched);
  if (incomplete.length > 0) {
    const plural = incomplete.length > 1 ? 's' : '';
    toast(`Billet${plural} incomplet${plural} (quantité et taux requis) : ${incomplete.join(', ')}.`, 'error');
    return;
  }
  const validBillets = touched;

  // Refuse to generate while two billets share the same N° de billet.
  const dups = duplicateBilletIndices();
  if (dups.size > 0) {
    render(); // repaint so the duplicate fields show their red border + warning
    const first = document.querySelector('.numero-billet-input.input-error');
    if (first) { first.scrollIntoView({ behavior: 'smooth', block: 'center' }); first.focus(); }
    toast('N° de billet en double sur la facture. Corrigez-le avant de générer.', 'error');
    return;
  }

  generating = true;
  const btn = $('#btn-generate');
  const origHTML = btn.innerHTML;
  btn.innerHTML = '<span class="loading-spinner"></span> Génération...';
  btn.classList.add('btn-loading');
  btn.disabled = true;

  const editingId = state.editingId;

  try {
    const [remise_pct, remise_montant] = normalizeDiscount(invoiceRemise());
    const payload = {
      client_id: parseInt(clientId),
      numero: numero || null,
      date: date || null,
      billets: validBillets.map(b => {
        const [pct, montant] = normalizeDiscount(b);
        return {
          date_billet: b.date_billet,
          chantier: b.chantier,
          plaque: b.plaque,
          numero_billet: b.numero_billet,
          description: b.description || '',
          desc_libre: !!b.desc_libre,
          quantite: parseFloat(b.quantite),
          taux: parseFloat(b.taux),
          remise_pct: pct,
          remise_montant: montant,
          scan_id: b.scan_id ?? null,
        };
      }),
      remise_pct,
      remise_montant,
    };

    const result = editingId
      ? await api('PUT', `/api/factures/${editingId}`, payload)
      : await api('POST', '/api/factures/generate', payload);

    // Both generating and regenerating may split into several invoices.
    const invoices = result.invoices || [{ filename: result.filename, numero: result.numero }];

    if (editingId) {
      toast(invoices.length > 1
        ? `Facture séparée en ${invoices.length} factures !`
        : `Facture ${invoices[0].numero} mise à jour !`);
    } else {
      toast(invoices.length > 1
        ? `${invoices.length} factures générées !`
        : `Facture ${invoices[0].numero} générée !`);
    }

    // Trigger each download, spaced out so the browser allows the batch.
    for (let k = 0; k < invoices.length; k++) {
      downloadInvoice(invoices[k].filename);
      if (k < invoices.length - 1) await sleep(350);
    }

    state.editingId = null;
    billets = [emptyBillet()];
    state.facForm = blankFacForm();
    await loadData();
    if (editingId) {
      navigate('history');
    } else {
      render();
    }
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    generating = false;
    btn.innerHTML = origHTML;
    btn.classList.remove('btn-loading');
    btn.disabled = false;
  }
}

async function editFacture(id) {
  try {
    const f = await api('GET', `/api/factures/${id}`);
    // Opening a blank editor here would let "Mettre à jour" overwrite the
    // real invoice, so an unreadable one is not editable at all.
    if (f.billets_unreadable) {
      toast(`Impossible de modifier la facture ${f.numero} : ${f.billets_unreadable_reason}. `
        + "Le fichier d'origine n'a pas été modifié.", 'error');
      return;
    }
    state.editingId = id;
    // The API already returns v2 fields; normalizing again also covers any
    // legacy-only shape, so the editor always shows the effective discount.
    const [remisePct, remiseMontant] = normalizeDiscount(f).map(formValue);
    state.facForm = { clientId: String(f.client_id), numero: f.numero, date: f.date, remisePct, remiseMontant, remiseOpen: false };
    const loaded = (f.billets || []).map(b => {
      const [remise_pct, remise_montant] = normalizeDiscount(b).map(formValue);
      return {
        date_billet: b.date_billet || '',
        chantier: b.chantier || '',
        plaque: b.plaque || '',
        numero_billet: b.numero_billet || '',
        description: b.description || '',
        desc_libre: !!b.desc_libre,
        quantite: b.quantite != null ? String(b.quantite) : '',
        taux: b.taux != null ? String(b.taux) : '',
        remise_pct,
        remise_montant,
        remise_open: false,
        scan_id: b.scan_id ?? null,
      };
    });
    billets = loaded.length ? loaded : [emptyBillet()];
    navigate('facture');
  } catch (e) {
    toast(e.message, 'error');
  }
}

function cancelEdit() {
  state.editingId = null;
  billets = [emptyBillet()];
  state.facForm = blankFacForm();
  navigate('history');
}


function resetFacture() {
  billets = [emptyBillet()];
  state.facForm = blankFacForm();
  render();
}

async function confirmDeleteFacture(id) {
  const numero = state.facForm.numero || '';
  const ok = await ui.alertDialog({
    title: 'Supprimer la facture',
    description: `Voulez-vous vraiment supprimer la facture ${numero} ? Le fichier Excel/PDF généré sera aussi supprimé. Cette action est irréversible.`,
    confirmLabel: 'Supprimer',
    destructive: true,
  });
  if (!ok) return;
  try {
    await api('DELETE', `/api/factures/${id}`);
    toast('Facture supprimée');
    state.editingId = null;
    billets = [emptyBillet()];
    state.facForm = blankFacForm();
    await loadData();
    navigate('history');
  } catch (e) {
    toast(e.message, 'error');
  }
}

function newFacture() {
  state.editingId = null;
  billets = [emptyBillet()];
  state.facForm = blankFacForm();
  navigate('facture');
}
