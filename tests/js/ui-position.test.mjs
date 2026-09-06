// Positioner maths (facturo/web/static/js/ui/position.js) and roving-key helpers
// (ui/keys.js). Plain node, no framework: node tests/js/ui-position.test.mjs
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'facturo', 'web', 'static', 'js', 'ui');
const require = createRequire(import.meta.url);
const { computePosition } = require(path.join(dir, 'position.js'));
const keys = require(path.join(dir, 'keys.js'));

let failed = 0;
function test(name, fn) {
  try { fn(); console.log('ok   ' + name); } catch (e) { failed++; console.log('FAIL ' + name + '\n     ' + e.message); }
}
const vp = { width: 1000, height: 800 };
const box = { width: 200, height: 100 };

test('places below and left-aligned by default', () => {
  const p = computePosition({ anchor: { x: 100, y: 100, width: 80, height: 30 }, floating: box, viewport: vp });
  assert.deepEqual([p.x, p.y, p.side], [100, 136, 'bottom']);
});
test('flips above when there is no room below', () => {
  const p = computePosition({ anchor: { x: 100, y: 740, width: 80, height: 30 }, floating: box, viewport: vp });
  assert.equal(p.side, 'top');
  assert.equal(p.y, 740 - 100 - 6);
});
test('does not flip when both sides are too small but the preferred has more room', () => {
  const p = computePosition({ anchor: { x: 0, y: 100, width: 10, height: 10 }, floating: { width: 50, height: 2000 }, viewport: vp });
  assert.equal(p.side, 'bottom');
  assert.equal(p.y, 8);
});
test('shifts horizontally to stay inside the viewport', () => {
  const p = computePosition({ anchor: { x: 950, y: 100, width: 40, height: 30 }, floating: box, viewport: vp });
  assert.equal(p.x, 1000 - 200 - 8);
  const q = computePosition({ anchor: { x: -30, y: 100, width: 40, height: 30 }, floating: box, viewport: vp });
  assert.equal(q.x, 8);
});
test('center and end alignment', () => {
  const a = { x: 400, y: 100, width: 100, height: 30 };
  assert.equal(computePosition({ anchor: a, floating: box, viewport: vp, align: 'center' }).x, 350);
  assert.equal(computePosition({ anchor: a, floating: box, viewport: vp, align: 'end' }).x, 300);
});
test('right side flips to left near the right edge', () => {
  const p = computePosition({ anchor: { x: 900, y: 300, width: 50, height: 30 }, floating: box, viewport: vp, side: 'right' });
  assert.equal(p.side, 'left');
  assert.equal(p.x, 900 - 200 - 6);
});
test('a zero-size pointer anchor works (context menu)', () => {
  const p = computePosition({ anchor: { x: 500, y: 400, width: 0, height: 0 }, floating: box, viewport: vp, offset: 0 });
  assert.deepEqual([p.x, p.y], [500, 400]);
});
test('flip:false keeps the requested side and clamps', () => {
  const p = computePosition({ anchor: { x: 100, y: 780, width: 40, height: 30 }, floating: box, viewport: vp, flip: false });
  assert.equal(p.side, 'bottom');
  assert.equal(p.y, 800 - 100 - 8);
});

test('nextIndex wraps and jumps', () => {
  assert.equal(keys.nextIndex(3, 2, 'ArrowDown'), 0);
  assert.equal(keys.nextIndex(3, 0, 'ArrowUp'), 2);
  assert.equal(keys.nextIndex(3, 1, 'Home'), 0);
  assert.equal(keys.nextIndex(3, 1, 'End'), 2);
  assert.equal(keys.nextIndex(3, -1, 'ArrowDown'), 0);
  assert.equal(keys.nextIndex(3, 2, 'ArrowDown', { loop: false }), 2);
  assert.equal(keys.nextIndex(3, 0, 'ArrowRight', { orientation: 'horizontal' }), 1);
  assert.equal(keys.nextIndex(3, 0, 'ArrowDown', { orientation: 'horizontal' }), 0);
  assert.equal(keys.nextIndex(0, 0, 'ArrowDown'), -1);
});
test('typeahead folds accents and cycles on a repeated letter', () => {
  const labels = ['Accueil', 'Clients', 'Historique', 'Éditer', 'Paramètres'];
  assert.equal(keys.typeahead(labels, 'e', 0), 3);
  assert.equal(keys.typeahead(labels, 'ed', 0), 3);
  assert.equal(keys.typeahead(labels, 'h', 0), 2);
  assert.equal(keys.typeahead(labels, 'zzz', 0), -1);
  assert.equal(keys.typeahead(['aa', 'ab', 'ac'], 'aa', 0), 1);
});

if (failed) { console.log(`\n${failed} test(s) failed`); process.exit(1); }
console.log('\nall ui-position tests passed');
