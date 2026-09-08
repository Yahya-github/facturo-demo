// Fuzzy matcher for the command palette (facturo/web/static/js/ui/fuzzy.js).
// Run with: node tests/js/ui-fuzzy.test.mjs
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const require = createRequire(import.meta.url);
const fz = require(path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'facturo', 'web', 'static', 'js', 'ui', 'fuzzy.js'));

let failed = 0;
function test(name, fn) {
  try { fn(); console.log('ok   ' + name); } catch (e) { failed++; console.log('FAIL ' + name + '\n     ' + e.message); }
}

test('fold removes accents and case and keeps the length', () => {
  assert.equal(fz.fold('Éric Côté'), 'eric cote');
  assert.equal(fz.fold('Factures scannées').length, 'Factures scannées'.length);
  assert.equal(fz.fold('N° 12-A'), 'n  12 a');
  assert.equal(fz.fold(null), '');
});
test('near1 detects exactly one edit', () => {
  assert.ok(fz.near1('facture', 'facturs'));
  assert.ok(fz.near1('facture', 'factur'));
  assert.ok(fz.near1('client', 'clienta'));
  assert.ok(!fz.near1('facture', 'facture'));
  assert.ok(!fz.near1('facture', 'fxctuxe'));
});
test('accent-insensitive matches', () => {
  assert.ok(fz.score('parametres', 'Paramètres') > 0);
  assert.ok(fz.score('scannees', 'Factures scannées') > 0);
  assert.ok(fz.score('EDITER', 'Éditer') > 0);
});
test('ranking: exact > prefix > word start > substring > subsequence', () => {
  const s = q => fz.score(q, 'x');
  const exact = fz.score('clients', 'Clients');
  const prefix = fz.score('cli', 'Clients');
  const word = fz.score('scan', 'Factures scannées');
  const sub = fz.score('cture', 'Factures');
  const seq = fz.score('fctr', 'Factures');
  assert.ok(exact > prefix && prefix > word && word > sub && sub > seq && seq > 0, [exact, prefix, word, sub, seq].join(' '));
  assert.equal(s('zzz'), -1);
});
test('every token must match', () => {
  assert.ok(fz.score('facture test', 'Facture 12 CLIENT TEST INC') > 0);
  assert.equal(fz.score('facture zzz', 'Facture 12 CLIENT TEST INC'), -1);
});
test('one-letter typo is forgiven on words of 4+ letters', () => {
  assert.ok(fz.score('histrique', 'Historique') > 0);
  assert.ok(fz.score('paiments', 'Paiements') > 0);
  assert.equal(fz.score('abc', 'xyz'), -1);
});
test('empty query keeps everything with score 0, in order', () => {
  const r = fz.rank(['b', 'a', 'c'], '  ', x => x);
  assert.deepEqual(r.map(x => x.item), ['b', 'a', 'c']);
  assert.equal(r[0].score, 0);
});
test('rank sorts best first and drops non-matches; multi-text uses the best', () => {
  const items = [
    { l: 'Paramètres', k: 'settings' },
    { l: 'Paiements', k: 'payments' },
    { l: 'Historique', k: 'history' },
  ];
  const r = fz.rank(items, 'pa', i => [i.l, i.k]);
  assert.deepEqual(r.map(x => x.item.l).sort(), ['Paiements', 'Paramètres']); // shorter label ranks first on a tie
  assert.equal(r[0].item.l, 'Paiements');
  const byKeyword = fz.rank(items, 'histo', i => [i.l, i.k]);
  assert.equal(byKeyword[0].item.l, 'Historique');
});
test('ranges cover the matched text of the original string', () => {
  assert.deepEqual(fz.ranges('scan', 'Factures scannées'), [[9, 13]]);
  assert.deepEqual(fz.ranges('fac cli', 'Facture Client'), [[0, 3], [8, 11]]);
  assert.deepEqual(fz.ranges('zzz', 'Facture'), []);
});

if (failed) { console.log(`\n${failed} test(s) failed`); process.exit(1); }
console.log('\nall ui-fuzzy tests passed');
