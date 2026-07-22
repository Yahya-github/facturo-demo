// Parity test: the discount math the browser preview runs must agree with
// facturo/invoicing/discounts.py to the cent. No test framework, no
// package.json, no node_modules -- this project ships plain <script> tags
// with no bundler, so this stays a single file runnable with a bare `node`.
//
// Run with:
//   node tests/js/discounts.test.mjs
//
// It expects facturo/web/static/js/discounts.js to export (as a UMD module,
// so the SAME file also works as a plain <script> global -- see
// changes/team-a.md for the exact contract):
//   normalizeDiscount(obj) -> [pct, montant]
//   billetNet(billet)      -> number
//   invoiceTotals(billets, facture) -> {
//     sousTotal, remise, remisePctAmount, remiseMontantAmount,
//     baseTaxable, tps, tvq, total
//   }

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const fixturesPath = path.join(__dirname, '..', 'fixtures', 'discount_cases.json');
const modulePath = path.join(__dirname, '..', '..', 'facturo', 'web', 'static', 'js', 'discounts.js');

const EPSILON = 1e-6;
const failures = [];

function approx(actual, expected, label) {
  if (typeof actual !== 'number' || Number.isNaN(actual) || Math.abs(actual - expected) > EPSILON) {
    failures.push(`${label}: expected ${expected}, got ${actual}`);
  }
}

async function main() {
  let discounts;
  try {
    const mod = await import(`file://${modulePath}`);
    discounts = mod.default ?? mod;
  } catch (err) {
    console.error('FAIL: could not load facturo/web/static/js/discounts.js');
    console.error(`  ${err.message}`);
    console.error('  This module does not exist yet, or does not export the expected functions.');
    console.error('  See changes/team-a.md for the exact interface it must expose.');
    process.exitCode = 1;
    return;
  }

  const required = ['normalizeDiscount', 'billetNet', 'invoiceTotals'];
  const missing = required.filter((name) => typeof discounts[name] !== 'function');
  if (missing.length) {
    console.error(`FAIL: discounts.js is missing exported function(s): ${missing.join(', ')}`);
    process.exitCode = 1;
    return;
  }

  const cases = JSON.parse(readFileSync(fixturesPath, 'utf8'));

  for (const c of cases) {
    const nets = c.billets.map((b) => discounts.billetNet(b));
    nets.forEach((n, i) => approx(n, c.expected.billet_nets[i], `${c.name}: billet_nets[${i}]`));

    const totals = discounts.invoiceTotals(c.billets, c.facture);
    approx(totals.sousTotal, c.expected.sous_total, `${c.name}: sousTotal`);
    approx(totals.remise, c.expected.remise, `${c.name}: remise`);
    approx(totals.remisePctAmount, c.expected.remise_pct_amount, `${c.name}: remisePctAmount`);
    approx(totals.remiseMontantAmount, c.expected.remise_montant_amount, `${c.name}: remiseMontantAmount`);
    approx(totals.baseTaxable, c.expected.base_taxable, `${c.name}: baseTaxable`);
    approx(totals.tps, c.expected.tps, `${c.name}: tps`);
    approx(totals.tvq, c.expected.tvq, `${c.name}: tvq`);
    approx(totals.total, c.expected.total, `${c.name}: total`);
  }

  // normalizeDiscount: a representative subset of the Python
  // test_normalize_discount parametrize list in tests/test_discounts.py.
  const normCases = [
    [{}, [0, 0]],
    [{ remise_pct: 10, remise_montant: 25 }, [10, 25]],
    [{ remise_type: 'percent', remise_valeur: 15 }, [15, 0]],
    [{ remise_type: 'montant', remise_valeur: 40 }, [0, 40]],
    [{ remise_type: 'percent', remise_valeur: 99, remise_pct: 10, remise_montant: 0 }, [10, 0]],
    [{ remise_pct: -10, remise_montant: -5 }, [0, 0]],
  ];
  for (const [input, [expPct, expMontant]] of normCases) {
    const result = discounts.normalizeDiscount(input);
    const [pct, montant] = Array.isArray(result) ? result : [undefined, undefined];
    approx(pct, expPct, `normalizeDiscount(${JSON.stringify(input)}): pct`);
    approx(montant, expMontant, `normalizeDiscount(${JSON.stringify(input)}): montant`);
  }

  if (failures.length) {
    failures.forEach((f) => console.error(`FAIL: ${f}`));
    console.error(
      `\n${failures.length} failure(s) out of ${cases.length} fixture cases + ${normCases.length} normalize cases.`
    );
    process.exitCode = 1;
  } else {
    console.log(
      `PASS: all ${cases.length} fixture cases + ${normCases.length} normalize cases match the Python math.`
    );
  }
}

main();
