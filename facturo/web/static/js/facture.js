// ── FACTURE ─────────────────────────────────────────────

let billets = [emptyBillet()];

function emptyBillet() {
  // `corrections` and `remise_open` are display-only and never submitted:
  // generateFacture's payload is an explicit whitelist, so they cannot reach
  // billets_json.
  return { date_billet: '', chantier: '', plaque: '', numero_billet: '', description: '', desc_libre: false, quantite: '', taux: '', remise_pct: '', remise_montant: '', remise_open: false, scan_id: null, corrections: null };
}

// The scanned document a billet is linked to, or null (incl. dangling links
// whose scan was deleted).
function linkedScan(b) {
  if (!b || b.scan_id == null) return null;
  return state.scans.find(s => s.id === b.scan_id) || null;
}

// ── Duplicate "N° Billet" detection ─────────────────────
// Two billets on the same invoice must not share the same N° de billet.
// Blank numbers are ignored (an empty field isn't a real duplicate yet).

function dupKey(b) {
  // Free-description billets have no N° Billet field, so they never count.
  if (b.desc_libre) return '';
  return (b.numero_billet || '').trim();
}

// Returns the set of billet indices whose N° Billet appears more than once.
function duplicateBilletIndices() {
  const counts = {};
  billets.forEach(b => {
    const k = dupKey(b);
    if (k) counts[k] = (counts[k] || 0) + 1;
  });
  const dups = new Set();
  billets.forEach((b, i) => {
    const k = dupKey(b);
    if (k && counts[k] > 1) dups.add(i);
  });
  return dups;
}

// Toggle the red border + inline warning live, without a full re-render
// (so the field keeps focus while the user is typing).
function refreshDuplicateHighlights() {
  const dups = duplicateBilletIndices();
  $$('.numero-billet-input').forEach(input => {
    input.classList.toggle('input-error', dups.has(parseInt(input.dataset.idx)));
  });
  $$('.dup-warning').forEach(w => {
    w.hidden = !dups.has(parseInt(w.dataset.idx));
  });
  refreshSummary();
}


// ── Split-by-chantier preview ───────────────────────────
// Mirrors the backend: when the selected client is flagged "separer_chantiers",
// generating splits into one invoice per distinct "Chantier / Client".

function currentFactureClient() {
  return state.clients.find(c => String(c.id) === String(state.facForm.clientId)) || null;
}

// Distinct chantier values among the billets, in first-seen order.
function chantierGroups() {
  const groups = [];
  billets.forEach(b => {
    const key = (b.chantier || '').trim();
    if (!groups.some(g => g.key === key)) {
      groups.push({ key, label: key || 'Sans chantier' });
    }
  });
  return groups;
}

function splitBannerHtml() {
  const c = currentFactureClient();
  if (!c || !c.separer_chantiers) return '';
  const groups = chantierGroups();
  if (groups.length < 2) return '';
  const labels = groups.map(g => `<span class="split-chip">${esc(g.label)}</span>`).join('');
  return `<div class="alert split-banner" role="status">
    ${icon('split', { size: 'sm' })}
    <div class="alert-body">
      <div class="alert-title">${groups.length} factures seront générées</div>
      <div class="alert-desc">Une par chantier, toutes au nom de ${esc(c.nom)}.</div>
      <div class="split-chips">${labels}</div>
    </div>
  </div>`;
}

function refreshSplitBanner() {
  const area = document.getElementById('split-banner-area');
  if (area) area.innerHTML = splitBannerHtml();
}

function downloadInvoice(filename) {
  const a = document.createElement('a');
  a.href = `/api/factures/download/${encodeURIComponent(filename)}`;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

function fmtPct(v) {
  const n = parseFloat(v) || 0;
  return `${n.toFixed(2).replace(/\.?0+$/, '')} %`;
}


function onClientChange() {
  const cid = $('#fac-client').value;
  state.facForm.clientId = cid;
  const client = state.clients.find(c => c.id == cid);
  if (client) {
    const num = `${client.prefix}${String(client.next_numero).padStart(3, '0')}`;
    $('#fac-numero').value = num;
    state.facForm.numero = num;
  }
  refreshSplitBanner();
  refreshClientHint();
  refreshSummary();
}

function addBillet(overrides) {
  syncBilletInputs();
  const newBillet = emptyBillet();
  const client = currentFactureClient();
  if (client && client.taux_defaut > 0) newBillet.taux = String(client.taux_defaut);
  if (overrides) Object.assign(newBillet, overrides);
  billets.push(newBillet);
  render();
  const cards = $$('.billet-card');
  if (cards.length) cards[cards.length - 1].scrollIntoView({ behavior: 'smooth', block: 'center' });
  return billets.length - 1;
}

function removeBillet(idx) {
  syncBilletInputs();
  billets.splice(idx, 1);
  render();
}

function syncBilletInputs() {
  $$('.billet-input').forEach(input => {
    const i = parseInt(input.dataset.idx);
    const f = input.dataset.field;
    if (billets[i]) billets[i][f] = input.value;
  });
  const facClient = $('#fac-client');
  const facNumero = $('#fac-numero');
  const facDate = $('#fac-date');
  const invPct = $('#inv-remise-pct');
  const invMontant = $('#inv-remise-montant');
  if (facClient) state.facForm.clientId = facClient.value;
  if (facNumero) state.facForm.numero = facNumero.value;
  if (facDate) state.facForm.date = facDate.value;
  if (invPct) state.facForm.remisePct = invPct.value;
  if (invMontant) state.facForm.remiseMontant = invMontant.value;
}
