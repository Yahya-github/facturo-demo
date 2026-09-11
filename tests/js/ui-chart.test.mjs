// Pure data shaping for the charts (facturo/web/static/js/ui/chart-data.js)
// and the count-up easing (ui/countup.js). Run with: node tests/js/ui-chart.test.mjs
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const require = createRequire(import.meta.url);
const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'facturo', 'web', 'static', 'js', 'ui');
const cd = require(path.join(dir, 'chart-data.js'));
const cu = require(path.join(dir, 'countup.js'));

let failed = 0;
function test(name, fn) {
  try { fn(); console.log('ok   ' + name); } catch (e) { failed++; console.log('FAIL ' + name + '\n     ' + e.message); }
}

const F = [
  { id: 1, date: '2026-07-10', client_id: 1, client_nom: 'ALPHA', total_ttc: 100.1, paye: 1 },
  { id: 2, date: '2026-07-20', client_id: 2, client_nom: 'BETA', total_ttc: 200.2, paye: 0 },
  { id: 3, date: '2026-09-01', client_id: 1, client_nom: 'ALPHA', total_ttc: 50, paye: 0 },
  { id: 4, date: null, client_id: 3, client_nom: 'GAMMA', total_ttc: '75.5', paye: 1 },
];

test('groupByMonth builds a continuous window ending at the latest month', () => {
  const m = cd.groupByMonth(F, { months: 4 });
  assert.deepEqual(m.map(x => x.key), ['2026-06', '2026-07', '2026-08', '2026-09']);
  assert.deepEqual(m.map(x => x.total), [0, 300.3, 0, 50]);
  assert.equal(m[1].count, 2);
  assert.equal(m[1].paid, 100.1);
  assert.equal(m[1].unpaid, 200.2);
  assert.equal(m[3].label, 'sept. 2026');
  assert.equal(m[3].short, 'sept.');
});
test('groupByMonth crosses year boundaries and ignores undated invoices', () => {
  const m = cd.groupByMonth([{ date: '2026-01-15', total_ttc: 10 }, { total_ttc: 99 }], { months: 3 });
  assert.deepEqual(m.map(x => x.key), ['2025-11', '2025-12', '2026-01']);
  assert.equal(m[2].total, 10);
});
test('groupByMonth with no data ends at now, all zero', () => {
  const m = cd.groupByMonth([], { months: 2, now: new Date(2026, 4, 3) });
  assert.deepEqual(m.map(x => [x.key, x.total]), [['2026-04', 0], ['2026-05', 0]]);
});
test('groupByMonth is float-safe (0.1 + 0.2)', () => {
  const m = cd.groupByMonth([{ date: '2026-03-01', total_ttc: 0.1 }, { date: '2026-03-02', total_ttc: 0.2 }], { months: 1 });
  assert.equal(m[0].total, 0.3);
});
test('topClients ranks by total, merges invoices, honours n', () => {
  const t = cd.topClients(F, 2);
  assert.deepEqual(t.map(x => [x.name, x.total, x.count]), [['BETA', 200.2, 1], ['ALPHA', 150.1, 2]]);
  assert.deepEqual(cd.topClients([], 5), []);
  assert.equal(cd.topClients(F, 0).length, 0);
});
test('paidSplit totals and share', () => {
  const s = cd.paidSplit(F);
  assert.equal(s.paid.count, 2);
  assert.equal(s.unpaid.count, 2);
  assert.equal(s.paid.total, 175.6);
  assert.equal(s.total, 425.8);
  assert.ok(Math.abs(s.paidPct - 175.6 / 425.8) < 1e-9);
  assert.equal(cd.paidSplit([]).paidPct, 0);
});
test('niceScale picks round steps', () => {
  assert.deepEqual(cd.niceScale(0), { max: 1, step: 0.25, ticks: 4 });
  assert.equal(cd.niceScale(870).max, 1000);
  assert.equal(cd.niceScale(300.3).step, 100);
  assert.equal(cd.niceScale(12).step, 5);
  assert.equal(cd.niceScale(1234).max, 2000);
});
test('compact axis labels use French decimals', () => {
  assert.equal(cd.compact(850), '850');
  assert.equal(cd.compact(1200), '1,2 k');
  assert.equal(cd.compact(3000000), '3 M');
});

test('easeOutCubic is 0 at start, 1 at end, monotonic and front-loaded', () => {
  assert.equal(cu.easeOutCubic(0), 0);
  assert.equal(cu.easeOutCubic(1), 1);
  assert.ok(cu.easeOutCubic(0.5) > 0.5);
  let prev = -1;
  for (let i = 0; i <= 20; i++) { const v = cu.easeOutCubic(i / 20); assert.ok(v >= prev); prev = v; }
  assert.equal(cu.easeOutCubic(-1), 0);
  assert.equal(cu.easeOutCubic(2), 1);
});
test('valueAt interpolates between from and to and lands exactly on to', () => {
  assert.equal(cu.valueAt(0, 100, 0, 1000), 0);
  assert.equal(cu.valueAt(0, 100, 1000, 1000), 100);
  assert.equal(cu.valueAt(0, 100, 5000, 1000), 100);
  assert.equal(cu.valueAt(100, 0, 1000, 1000), 0);
  const mid = cu.valueAt(0, 100, 500, 1000);
  assert.ok(mid > 50 && mid < 100);
  assert.equal(cu.valueAt(5, 9, 0, 0), 9);
});
test('roundTo keeps the requested decimals', () => {
  assert.equal(cu.roundTo(12.3456, 2), 12.35);
  assert.equal(cu.roundTo(12.3456, 0), 12);
});

if (failed) { console.log(`\n${failed} test(s) failed`); process.exit(1); }
console.log('\nall ui-chart tests passed');
