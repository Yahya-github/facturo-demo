// ── FACTURE: remises (collapsible panels) and the live summary ───────────
// Math lives in discounts.js (normalizeDiscount, billetGross, billetNet,
// invoiceTotals), the mirror of invoicing/discounts.py, so the preview always
// equals the generated invoice. A billet and the invoice each take a percent
// AND a fixed amount; the percent comes off first, the amount after.

function invoiceRemise() {
  return { remise_pct: state.facForm.remisePct, remise_montant: state.facForm.remiseMontant };
}

// A discount as an input value: blank when zero.
const formValue = n => (n ? String(n) : '');

const hasDiscount = ([pct, montant]) => pct > 0 || montant > 0;

// The % and $ inputs, side by side, each an Input Group with its adornment.
// `attrs(field)` returns the extra classes and attributes that wire each input
// to its billet or to the invoice.
function discountInputsHtml(who, [pct, montant], attrs) {
  const pctLabel = tFac('facture.discount.pct_aria', { who });
  const amountLabel = tFac('facture.discount.amount_aria', { who });
  return `<div class="field discount-field">
      <span class="form-label">${esc(tFac('facture.discount.pct'))}</span>
      <div class="input-group">
        <input ${attrs('pct')} type="number" inputmode="decimal" min="0" max="100" step="any"
          placeholder="0" value="${numAttr(pct || '')}" aria-label="${escAttr(pctLabel)}">
        <span class="input-group-addon" aria-hidden="true">%</span>
      </div>
    </div>
    <div class="field discount-field">
      <span class="form-label">${esc(tFac('facture.discount.amount'))}</span>
      <div class="input-group">
        <span class="input-group-addon" aria-hidden="true">$</span>
        <input ${attrs('montant')} type="number" inputmode="decimal" min="0" step="0.01"
          placeholder="0.00" value="${numAttr(montant || '')}" aria-label="${escAttr(amountLabel)}">
      </div>
    </div>`;
}

function discountToggleHtml(extraClass, boxId, open, closedLabel, openLabel, onclick) {
  return `<button type="button" class="discount-toggle ${extraClass}" aria-expanded="${open}" aria-controls="${boxId}" onclick="${onclick}">
      ${icon('tag', { size: 'sm' })}
      <span class="lbl-closed">${esc(closedLabel)}</span><span class="lbl-open">${esc(openLabel)}</span>
      ${icon('chevron-down', { size: 'xs', className: 'chev' })}
    </button>`;
}

function billetNetText(b) {
  const gross = billetGross(b);
  const net = billetNet(b);
  return net < gross ? `−${money(gross - net)} → ${money(net)}` : '';
}

function renderBilletDiscount(b, i) {
  const values = normalizeDiscount(b);
  const open = !!b.remise_open || hasDiscount(values);
  const attrs = field =>
    `class="form-input discount-input billet-input billet-remise-input num-input" data-idx="${i}" data-field="remise_${field}"`;
  return `<footer class="billet-foot">
      ${discountToggleHtml('', `b${i}-remise`, open, tFac('facture.discount.add_billet'), tFac('facture.discount.billet'), `toggleBilletRemise(${i})`)}
      <div class="billet-total"><span>${esc(tFac('facture.discount.billet_total'))}</span><strong data-billet-total data-idx="${i}">${money(billetNet(b))}</strong></div>
    </footer>
    <div class="collapsible discount-box${open ? ' is-open' : ''}" id="b${i}-remise" data-idx="${i}"${open ? '' : ' inert'}>
      <div class="collapsible-inner">
        <div class="discount-row">
          ${discountInputsHtml(tFac('facture.discount.who_billet', { n: i + 1 }), values, attrs)}
          <span class="discount-net" data-idx="${i}" aria-live="polite">${billetNetText(b)}</span>
          <button type="button" class="discount-remove" onclick="removeBilletRemise(${i})"
            data-tip="${escAttr(tFac('facture.discount.remove'))}" aria-label="${escAttr(tFac('facture.discount.remove_billet', { n: i + 1 }))}">${icons.x}</button>
        </div>
      </div>
    </div>`;
}

function invoiceGrossSub() {
  return billets.reduce((s, b) => s + billetGross(b), 0);
}

function invoiceDiscountOpen() {
  const f = state.facForm;
  return !!f.remiseOpen || hasDiscount(normalizeDiscount(invoiceRemise()));
}

// 'none' hides the whole panel while there is nothing to discount yet.
function invoiceDiscountMode() {
  return invoiceGrossSub() === 0 && !invoiceDiscountOpen() ? 'none' : 'on';
}

function renderInvoiceDiscount() {
  if (invoiceDiscountMode() === 'none') return '';
  const open = invoiceDiscountOpen();
  const values = normalizeDiscount(invoiceRemise());
  const attrs = field => `class="form-input discount-input num-input" id="inv-remise-${field}"`;
  return `<section class="card fac-card fac-discount" aria-label="${escAttr(tFac('facture.discount.invoice_aria'))}">
    ${discountToggleHtml('discount-toggle-invoice', 'inv-remise-box', open,
      tFac('facture.discount.add_invoice'), tFac('facture.discount.invoice'), 'toggleInvoiceRemise()')}
    <div class="collapsible discount-box invoice-discount${open ? ' is-open' : ''}" id="inv-remise-box"${open ? '' : ' inert'}>
      <div class="collapsible-inner">
        <div class="discount-row">
          ${discountInputsHtml(tFac('facture.discount.who_invoice'), values, attrs)}
          <button type="button" class="discount-remove" onclick="removeInvoiceRemise()"
            data-tip="${escAttr(tFac('facture.discount.remove'))}" aria-label="${escAttr(tFac('facture.discount.remove_invoice'))}">${icons.x}</button>
        </div>
        <p class="discount-hint">${esc(tFac('facture.discount.hint'))}</p>
      </div>
    </div>
  </section>`;
}

// ── Collapsible open / close (animated in CSS, no re-render) ─────────────

function setCollapsible(box, open) {
  if (!box) return;
  box.classList.toggle('is-open', open);
  box.inert = !open;
  const trigger = document.querySelector(`[aria-controls="${box.id}"]`);
  if (trigger) trigger.setAttribute('aria-expanded', String(open));
}

function toggleBilletRemise(i) {
  const box = document.getElementById(`b${i}-remise`);
  if (!box || !billets[i]) return;
  syncBilletInputs();
  const open = box.classList.contains('is-open');
  // A live discount cannot be hidden by accident: the x button removes it.
  if (open && hasDiscount(normalizeDiscount(billets[i]))) {
    box.querySelector('.billet-remise-input')?.focus();
    return;
  }
  billets[i].remise_open = !open;
  setCollapsible(box, !open);
  if (!open) box.querySelector('.billet-remise-input')?.focus();
}

function removeBilletRemise(i) {
  const box = document.getElementById(`b${i}-remise`);
  if (!box || !billets[i]) return;
  box.querySelectorAll('.billet-remise-input').forEach(input => { input.value = ''; });
  Object.assign(billets[i], { remise_pct: '', remise_montant: '', remise_open: false });
  setCollapsible(box, false);
  updateBilletNet(i);
  updateTotalsArea();
}

function toggleInvoiceRemise() {
  const box = document.getElementById('inv-remise-box');
  if (!box) return;
  syncBilletInputs();
  const open = box.classList.contains('is-open');
  if (open && hasDiscount(normalizeDiscount(invoiceRemise()))) {
    document.getElementById('inv-remise-pct')?.focus();
    return;
  }
  state.facForm.remiseOpen = !open;
  setCollapsible(box, !open);
  if (!open) document.getElementById('inv-remise-pct')?.focus();
}

function removeInvoiceRemise() {
  const box = document.getElementById('inv-remise-box');
  ['inv-remise-pct', 'inv-remise-montant'].forEach(id => {
    const input = document.getElementById(id);
    if (input) input.value = '';
  });
  Object.assign(state.facForm, { remisePct: '', remiseMontant: '', remiseOpen: false });
  setCollapsible(box, false);
  updateTotalsArea();
}

// Called by core.js as quantity/rate change, and on every discount keystroke.
function updateBilletNet(i) {
  const b = billets[i];
  if (!b) return;
  const span = document.querySelector(`.discount-net[data-idx="${i}"]`);
  if (span) span.textContent = billetNetText(b);
  const total = document.querySelector(`[data-billet-total][data-idx="${i}"]`);
  if (total) total.textContent = money(billetNet(b));
}

function updateTotalsArea() {
  const area = document.getElementById('totals-area');
  if (!area) return;
  const mode = invoiceDiscountMode();
  // Only rebuild the panel when it appears or disappears, so its open/close
  // animation and the focus inside it survive every keystroke.
  if (area.dataset.mode !== mode) {
    area.dataset.mode = mode;
    area.innerHTML = renderInvoiceDiscount();
    bindInvoiceDiscountEvents();
  }
  refreshSummary();
}

function bindInvoiceDiscountEvents() {
  for (const [id, key] of [['inv-remise-pct', 'remisePct'], ['inv-remise-montant', 'remiseMontant']]) {
    const input = document.getElementById(id);
    if (!input) continue;
    input.addEventListener('input', () => {
      state.facForm[key] = input.value;
      state.facForm.remiseOpen = true; // keep the editor open while it's being cleared
      refreshSummary();
    });
  }
}

// Called by core.js after every full render. core.js already stores each
// .billet-input value on the billet; this refreshes what the discount changes.
function bindTotalsEvents() {
  $$('.billet-remise-input').forEach(input => {
    input.addEventListener('input', () => {
      const i = parseInt(input.dataset.idx);
      if (!billets[i]) return;
      Object.assign(billets[i], { [input.dataset.field]: input.value, remise_open: true });
      updateBilletNet(i);
      refreshSummary();
    });
  });
  bindInvoiceDiscountEvents();
}

// ── Live summary card ───────────────────────────────────

const facSummary = { last: 0, anim: null };

function summaryModel() {
  const t = invoiceTotals(billets, invoiceRemise());
  const [pct] = normalizeDiscount(invoiceRemise());
  const lines = [];
  billets.forEach((b, i) => {
    if (billetGross(b) > 0) lines.push({ label: tFac('facture.billet.n', { n: i + 1 }), ref: dupKey(b), net: billetNet(b) });
  });
  const touched = billets.filter(b => !isUntouchedBillet(b));
  const dups = duplicateBilletIndices().size;
  const checks = [
    { ok: !!state.facForm.clientId, label: tFac('facture.check.client') },
    { ok: touched.length > 0 && incompleteBillets(touched).length === 0, label: tFac('facture.check.billets') },
    { ok: dups === 0, label: tFac(dups ? 'facture.check.dup' : 'facture.check.no_dup') },
  ];
  return { t, total: t.total, pct, lines, checks, count: billets.length };
}

function summaryLine(label, value, cls = '') {
  return `<div class="line ${cls}"><dt>${label}</dt><dd>${value}</dd></div>`;
}

function renderSummary(m = summaryModel()) {
  const t = m.t;
  const client = currentFactureClient();
  const name = client ? client.nom : tFac('facture.summary.no_client');
  const avatar = client ? ui.avatar(client.nom, { size: 'lg' }) : '<span class="avatar avatar-lg" aria-hidden="true">?</span>';
  const rows = m.lines.map(l => summaryLine(
    `${esc(l.label)}${l.ref ? ` <em>${esc(tFac('facture.summary.ref', { ref: l.ref }))}</em>` : ''}`, money(l.net), 'line-billet')).join('');
  const remise = (label, amount) => amount > 0 ? summaryLine(label, `−${money(amount)}`, 'line-remise') : '';
  return `<div class="fac-summary-head">
      ${avatar}
      <div class="fac-summary-who">
        <strong>${esc(name)}</strong>
        <span>${esc(ui.i18n.tn('facture.summary.count', m.count))}${state.facForm.numero ? ` · ${esc(state.facForm.numero)}` : ''}</span>
      </div>
    </div>
    <dl class="fac-lines">
      ${rows || `<div class="line line-empty"><dt>${esc(tFac('facture.summary.empty'))}</dt></div>`}
      ${summaryLine(esc(tFac('facture.subtotal')), money(t.sousTotal), 'line-sub')}
      ${remise(esc(tFac('facture.discount.line_pct', { pct: fmtPct(m.pct) })), t.remisePctAmount)}
      ${remise(esc(tFac('facture.discount.line_amount')), t.remiseMontantAmount)}
      ${summaryLine(esc(tFac('facture.tax.tps')), money(t.tps))}
      ${summaryLine(esc(tFac('facture.tax.tvq')), money(t.tvq))}
    </dl>
    <div class="fac-total"><span>${esc(tFac('facture.total_due'))}</span><strong data-fac-total>${money(m.total)}</strong></div>
    <ul class="fac-checks" aria-label="${escAttr(tFac('facture.check.aria'))}">
      ${m.checks.map(c => `<li class="${c.ok ? 'is-ok' : 'is-todo'}">${icon(c.ok ? 'circle-check' : 'circle', { size: 'xs' })} ${esc(c.label)}</li>`).join('')}
    </ul>`;
}

// Re-render the card in place and roll the total from its previous value.
function refreshSummary() {
  const el = document.getElementById('fac-summary');
  if (!el) return;
  const m = summaryModel();
  if (facSummary.anim) facSummary.anim.cancel();
  el.innerHTML = renderSummary(m);
  const total = el.querySelector('[data-fac-total]');
  if (total && facSummary.last !== m.total && ui.countup) {
    facSummary.anim = ui.countup.run(total, m.total, { from: facSummary.last, duration: 450, format: 'money' });
  }
  facSummary.last = m.total;
  const mini = document.querySelector('[data-fac-total-mini]');
  if (mini) mini.textContent = money(m.total);
}
