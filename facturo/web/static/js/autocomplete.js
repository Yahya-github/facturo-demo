// ── Autocomplete for Chantier and Plaque ─────────────────────────────────
//
// A native <datalist> was the obvious choice and does not work here: it gives
// no reliable Tab-to-accept, no control over ordering, and no styling.
//
// The panel is created once and lives on <body>, deliberately outside
// #main-content. Everything inside that element is destroyed and rebuilt by
// render() on every change, so a panel parented there would be torn out from
// under the user mid-keystroke — and any listener bound to a billet input
// would need re-binding on every render. Both problems disappear by keeping
// one panel and delegating from a root that never gets replaced.

let acPanel = null;      // the singleton <div>, created lazily
let acInput = null;      // the input it is currently attached to
let acItems = [];        // the values currently offered
let acIndex = 0;         // which one is highlighted

// Mirror of billet_fields.fold (billet_fields.py). Kept in sync by hand: it is
// four lines, and the worst a drift can do is miss a *suggestion* — the
// authoritative correction happens server-side, where the tests are.
function foldKey(s) {
  return (s || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]/g, '');
}

// Edit distance of exactly 1 — mirror of billet_fields._near1.
function near1(a, b) {
  if (Math.abs(a.length - b.length) > 1) return false;
  if (a.length === b.length) {
    let diff = 0;
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) diff++;
    return diff === 1;
  }
  if (a.length > b.length) [a, b] = [b, a];
  let i = 0, j = 0, skipped = false;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++; }
    else if (skipped) return false;
    else { skipped = true; j++; }
  }
  return true;
}

function acCandidates(kind, query) {
  const rows = state.knownValues[kind] || [];
  const key = foldKey(query);
  if (!key) return rows.slice(0, 8);
  // Prefix matches first, then anything containing the query. Within each
  // group the server's frequency order is preserved, so the truck used every
  // day sits above the one used once.
  const starts = rows.filter(r => foldKey(r.valeur).startsWith(key));
  const contains = rows.filter(r => !foldKey(r.valeur).startsWith(key)
    && foldKey(r.valeur).includes(key));
  return [...starts, ...contains].slice(0, 8);
}

function ensureAcPanel() {
  if (acPanel) return acPanel;
  acPanel = document.createElement('div');
  acPanel.className = 'ac-panel';
  acPanel.hidden = true;
  // Keep focus in the input: a click that blurs first would close the panel
  // before the click ever lands on a row.
  acPanel.addEventListener('mousedown', e => e.preventDefault());
  acPanel.addEventListener('click', e => {
    const row = e.target.closest('.ac-row');
    if (row) acceptAutocomplete(parseInt(row.dataset.i, 10));
  });
  document.body.appendChild(acPanel);
  return acPanel;
}

function positionAcPanel(input) {
  const r = input.getBoundingClientRect();
  const panel = ensureAcPanel();
  panel.style.left = `${r.left}px`;
  panel.style.width = `${r.width}px`;
  // Flip above the field when there is no room below it.
  const below = window.innerHeight - r.bottom;
  if (below < 180 && r.top > below) {
    panel.style.top = 'auto';
    panel.style.bottom = `${window.innerHeight - r.top + 2}px`;
  } else {
    panel.style.bottom = 'auto';
    panel.style.top = `${r.bottom + 2}px`;
  }
}

function drawAcPanel() {
  const panel = ensureAcPanel();
  panel.textContent = '';
  acItems.forEach((item, i) => {
    const row = document.createElement('div');
    row.className = 'ac-row' + (i === acIndex ? ' is-active' : '');
    row.dataset.i = String(i);
    // textContent, never an interpolated attribute: esc() does not escape
    // quotes, and a value containing one would break out of the markup.
    const label = document.createElement('span');
    label.textContent = item.valeur;
    const count = document.createElement('span');
    count.className = 'ac-count';
    count.textContent = item.times_used ? `${item.times_used}×` : 'nouveau';
    row.append(label, count);
    if (i === acIndex) {
      const hint = document.createElement('span');
      hint.className = 'ac-hint';
      hint.textContent = 'Tab';
      row.appendChild(hint);
    }
    panel.appendChild(row);
  });
  panel.hidden = acItems.length === 0;
}

function openAutocomplete(input) {
  const kind = input.dataset.ac;
  acItems = acCandidates(kind, input.value);
  acIndex = 0;
  acInput = input;
  positionAcPanel(input);
  drawAcPanel();
  input.setAttribute('aria-expanded', acItems.length ? 'true' : 'false');
  window.addEventListener('scroll', repositionAutocomplete, true);
  window.addEventListener('resize', repositionAutocomplete);
}

function repositionAutocomplete() {
  if (acInput && acPanel && !acPanel.hidden) positionAcPanel(acInput);
}

function closeAutocomplete() {
  if (acPanel) acPanel.hidden = true;
  if (acInput) acInput.setAttribute('aria-expanded', 'false');
  acInput = null;
  acItems = [];
  window.removeEventListener('scroll', repositionAutocomplete, true);
  window.removeEventListener('resize', repositionAutocomplete);
}

function acceptAutocomplete(i) {
  if (!acInput || !acItems[i]) return;
  const input = acInput;
  input.value = acItems[i].valeur;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  closeAutocomplete();
  // Focus stays put on purpose: the user sees what was accepted, and a second
  // Tab moves on. Accepting and jumping away in one keystroke is faster and
  // gives no beat to notice a wrong pick.
  input.focus();
}

// Settle a typed value onto the spelling the shop already uses.
function canonicaliseField(input) {
  const kind = input.dataset.ac;
  const typed = input.value.trim();
  if (!typed) return;
  const rows = state.knownValues[kind] || [];
  const key = foldKey(typed);
  // Same identity, different spelling: apply it. "Chantier Nord", "chantier nord" and
  // "CHANTIER-NORD" all fold alike, and this is what makes the five spellings in
  // the history converge on one. There is no judgement call to surface.
  const exact = rows.find(r => foldKey(r.valeur) === key);
  if (exact) {
    if (input.value !== exact.valeur) {
      input.value = exact.valeur;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    return;
  }
  // One character away from something known is NOT applied: "Terra" and
  // "Terral" are two real clients one edit apart. Offer it and let the user
  // decide, because a genuinely new site must survive being typed.
  const near = rows.filter(r => near1(foldKey(r.valeur), key));
  if (near.length === 1 && key.length >= 5) suggestCanonical(input, near[0].valeur);
}

function suggestCanonical(input, suggestion) {
  const group = input.closest('.form-group');
  if (!group || group.querySelector('.ac-suggest')) return;
  const chip = document.createElement('div');
  chip.className = 'ac-suggest';
  const q = document.createElement('span');
  q.textContent = `Vouliez-vous dire « ${suggestion} » ?`;
  const yes = document.createElement('button');
  yes.type = 'button';
  yes.className = 'ac-suggest-yes';
  yes.textContent = 'Oui';
  yes.addEventListener('click', () => {
    input.value = suggestion;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    chip.remove();
  });
  const no = document.createElement('button');
  no.type = 'button';
  no.className = 'ac-suggest-no';
  no.textContent = 'Non';
  // Remember the refusal, or the same chip reappears on every blur.
  no.addEventListener('click', () => { input.dataset.acDeclined = input.value; chip.remove(); });
  chip.append(q, yes, no);
  group.appendChild(chip);
}

function bindAutocomplete() {
  const root = $('#main-content');
  if (!root || root.dataset.acBound) return;
  root.dataset.acBound = '1';

  root.addEventListener('input', e => {
    if (e.target.matches('.ac-input')) openAutocomplete(e.target);
  });
  root.addEventListener('focusin', e => {
    if (e.target.matches('.ac-input')) openAutocomplete(e.target);
  });
  root.addEventListener('focusout', e => {
    if (!e.target.matches('.ac-input')) return;
    const input = e.target;
    closeAutocomplete();
    if (input.dataset.acDeclined !== input.value) canonicaliseField(input);
  });
  root.addEventListener('keydown', e => {
    if (!e.target.matches('.ac-input')) return;
    const open = acPanel && !acPanel.hidden && acItems.length;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!open) return openAutocomplete(e.target);
      acIndex = (acIndex + 1) % acItems.length;
      drawAcPanel();
    } else if (e.key === 'ArrowUp' && open) {
      e.preventDefault();
      acIndex = (acIndex - 1 + acItems.length) % acItems.length;
      drawAcPanel();
    } else if ((e.key === 'Tab' || e.key === 'Enter') && open && !e.shiftKey) {
      e.preventDefault();
      acceptAutocomplete(acIndex);
    } else if (e.key === 'Escape' && open) {
      e.preventDefault();
      closeAutocomplete();
    }
  });
}

// Put back what the AI actually read, when history corrected it wrongly.
function revertAiFix(i, field) {
  const b = billets[i];
  const fix = b && b.corrections && b.corrections[field];
  if (!fix) return;
  b[field] = fix.lu;
  delete b.corrections[field];
  render();
}

// The note under a field the AI got corrected on. Showing what was read is the
// whole point: history snapping is right almost every time, and the once it is
// wrong the only thing between it and a real invoice is the user noticing.
function aiFixHtml(b, i, field) {
  const fix = b.corrections && b.corrections[field];
  if (!fix) return '';
  const message = fix.raison === 'format'
    ? `Numéro de projet ignoré — l'IA avait lu « ${esc(fix.lu)} ».`
    : `Corrigé d'après l'historique — l'IA avait lu « ${esc(fix.lu)} ».`;
  return `<div class="ai-fix" data-idx="${i}" data-field="${field}">
      ${micon('auto_fix_high')} ${message}
      <button type="button" class="ai-fix-undo" onclick="revertAiFix(${i}, '${field}')">Rétablir</button>
    </div>`;
}
