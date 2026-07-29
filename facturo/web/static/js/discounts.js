// Discount and invoice-total math for the live preview. Pure functions, no DOM.
//
// Formula-for-formula mirror of facturo/invoicing/discounts.py so the preview
// always equals the generated invoice; tests/js/discounts.test.mjs checks both
// against the shared fixtures. Loaded as a plain <script> (attaches globals)
// and importable from Node for that parity test.

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    Object.assign(root, factory());
  }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const TPS_RATE = 0.05;
  const TVQ_RATE = 0.09975;

  // A stored or typed number; anything unusable (blank, text, NaN) is 0.
  function toNumber(value) {
    if (value === null || value === undefined || value === '') return 0;
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }

  // -> [pct, montant], both >= 0. The v2 fields win whenever either is set;
  // otherwise the legacy remise_type/remise_valeur pair is translated.
  function normalizeDiscount(obj) {
    const o = obj || {};
    const pct = Math.max(0, toNumber(o.remise_pct));
    const montant = Math.max(0, toNumber(o.remise_montant));
    if (pct || montant) return [pct, montant];

    const valeur = toNumber(o.remise_valeur);
    if (valeur <= 0) return [0, 0];
    if (o.remise_type === 'percent') return [valeur, 0];
    if (o.remise_type === 'montant') return [0, valeur];
    return [0, 0];
  }

  function billetGross(b) {
    return toNumber(b.quantite) * toNumber(b.taux);
  }

  // Line total after the billet's own discount; percent is a share of the
  // original gross, the fixed amount comes off after it, never below zero.
  function billetNet(b) {
    const gross = billetGross(b);
    const [pct, montant] = normalizeDiscount(b);
    return Math.max(0, gross - gross * pct / 100 - montant);
  }

  // Each REMISE amount is clamped to what is left when it applies, so
  // sousTotal - remisePctAmount - remiseMontantAmount === baseTaxable.
  function invoiceTotals(billets, facture) {
    const sousTotal = billets.reduce((sum, b) => sum + billetNet(b), 0);
    const [pct, montant] = normalizeDiscount(facture);
    const remisePctAmount = Math.max(0, Math.min(sousTotal * pct / 100, sousTotal));
    const afterPct = sousTotal - remisePctAmount;
    const remiseMontantAmount = Math.max(0, Math.min(montant, afterPct));
    const baseTaxable = afterPct - remiseMontantAmount;
    const tps = baseTaxable * TPS_RATE;
    const tvq = baseTaxable * TVQ_RATE;
    return {
      sousTotal,
      remise: remisePctAmount + remiseMontantAmount,
      remisePctAmount,
      remiseMontantAmount,
      baseTaxable,
      tps,
      tvq,
      total: baseTaxable + tps + tvq,
    };
  }

  return { normalizeDiscount, billetGross, billetNet, invoiceTotals, TPS_RATE, TVQ_RATE };
});
