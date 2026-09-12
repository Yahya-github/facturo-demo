// money() lives in core.js (a browser script), so its source is evaluated in isolation.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import assert from 'node:assert/strict';

const dir = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(dir, '..', '..', 'facturo', 'web', 'static', 'js', 'core.js'), 'utf8');
const fn = /function money\(n\) \{[^]*?\n\}\n/.exec(src);
const money = vm.runInNewContext(`${fn[0]}; money`);

test('formats French-Canadian with narrow thousands space and comma decimal', () => {
  assert.equal(money(9042.78), '9 042,78 $');
  assert.equal(money(1234567.1), '1 234 567,10 $');
});

test('small, zero and rounded values', () => {
  assert.equal(money(0), '0,00 $');
  assert.equal(money(999.999), '1 000,00 $');
  assert.equal(money(-0.001), '0,00 $');
});

test('negative amounts use a real minus sign', () => {
  assert.equal(money(-1234.5), '−1 234,50 $');
});

test('non-numbers fall back to zero', () => {
  assert.equal(money(undefined), '0,00 $');
});
