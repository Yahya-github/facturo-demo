// Tests for the pure helpers in facturo/web/static/js/util.js, plus a
// grep-style guard against unescaped interpolation in the page templates.
// Run with: node tests/js/util.test.mjs
import { createRequire } from 'node:module';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const jsDir = path.join(__dirname, '..', '..', 'facturo', 'web', 'static', 'js');
const require = createRequire(import.meta.url);
const u = require(path.join(jsDir, 'util.js'));

let failed = 0;
function test(name, fn) {
  try { fn(); console.log('ok   ' + name); }
  catch (e) { failed++; console.log('FAIL ' + name + '\n     ' + e.message); }
}

function scanTemplates(pattern, allowed) {
  const offenders = [];
  for (const f of readdirSync(jsDir).filter(n => n.endsWith('.js') && n !== 'util.js')) {
    readFileSync(path.join(jsDir, f), 'utf8').split('\n').forEach((line, i) => {
      if (pattern.test(line) && !(allowed && allowed.test(line))) offenders.push(`${f}:${i + 1}: ${line.trim()}`);
    });
  }
  return offenders;
}

test('esc escapes & < > " \'', () => {
  assert.equal(u.esc(`<a href="x" onclick='y'>&</a>`),
    '&lt;a href=&quot;x&quot; onclick=&#39;y&#39;&gt;&amp;&lt;/a&gt;');
});
test('esc keeps numeric 0 as "0" and empties null/undefined/""', () => {
  assert.equal(u.esc(0), '0');
  assert.equal(u.esc(null), '');
  assert.equal(u.esc(undefined), '');
  assert.equal(u.esc(''), '');
});
test('escAttr breaks out of double-quoted attributes safely', () => {
  assert.equal(u.escAttr('a" onfocus="x'), 'a&quot; onfocus=&quot;x');
  assert.equal(u.escAttr(0), '0');
  assert.equal(u.escAttr(null), '');
});
test('numAttr keeps finite numbers and blanks everything else', () => {
  assert.equal(u.numAttr(12.5), '12.5');
  assert.equal(u.numAttr('12.5'), '12.5');
  assert.equal(u.numAttr(0), '0');
  assert.equal(u.numAttr(''), '');
  assert.equal(u.numAttr(null), '');
  assert.equal(u.numAttr('" onfocus="x'), '');
  assert.equal(u.numAttr(NaN), '');
});
test('dateAttr only accepts YYYY-MM-DD', () => {
  assert.equal(u.dateAttr('2026-09-28'), '2026-09-28');
  assert.equal(u.dateAttr('2026-09-28" x="'), '');
  assert.equal(u.dateAttr(null), '');
});
test('errorMessage joins FastAPI 422 array detail msg fields', () => {
  const detail = [{ loc: ['body', 'nom'], msg: 'Field required' }, { msg: 'Bad value' }];
  assert.equal(u.errorMessage({ detail }), 'Field required ; Bad value');
});
test('errorMessage passes string detail and falls back', () => {
  assert.equal(u.errorMessage({ detail: 'Client introuvable' }), 'Client introuvable');
  assert.equal(u.errorMessage({}), 'Erreur serveur');
  assert.equal(u.errorMessage(null), 'Erreur serveur');
  assert.equal(u.errorMessage({ detail: [] }), 'Erreur serveur');
});
test('networkErrorMessage maps fetch TypeError to French', () => {
  assert.equal(u.networkErrorMessage(new TypeError('Failed to fetch')), 'Connexion au serveur impossible');
  assert.equal(u.networkErrorMessage(new Error('x')), 'x');
});
test('incompleteBillets names blank quantite/taux billets, accepts 0', () => {
  const bs = [
    { numero_billet: 'A1', quantite: '2', taux: '0' },
    { numero_billet: 'B2', quantite: '', taux: '65' },
    { numero_billet: '', quantite: '1', taux: '  ' },
  ];
  assert.deepEqual(u.incompleteBillets(bs), ['B2', '3']);
  assert.deepEqual(u.incompleteBillets([{ quantite: 0, taux: 0 }]), []);
});
test('no unescaped value="${...}" interpolation in templates', () => {
  assert.deepEqual(
    scanTemplates(/value="\$\{/, /value="\$\{\s*(escAttr|numAttr|dateAttr)\(/), []);
});
test('no esc() inside a double-quoted attribute (must be escAttr)', () => {
  assert.deepEqual(
    scanTemplates(/\b(title|alt|download|aria-label|placeholder|value|data-[\w-]+)="[^"]*\$\{esc\(/), []);
});

if (failed) { console.log(`\n${failed} test(s) failed`); process.exit(1); }
console.log('\nall util tests passed');
