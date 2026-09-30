// Locale fragments of batch B (clients, facture, settings): same keys and
// placeholders in English and French, no empty values, no key claimed twice.
// Plain node: node --test tests/js/locales-b.test.mjs
import { createRequire } from 'node:module';
import { readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import assert from 'node:assert/strict';

const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'facturo', 'web', 'static', 'js', 'locales');
const require = createRequire(import.meta.url);
const load = (lang, area) => require(path.join(dir, `${lang}.${area}.js`));
const placeholders = text => [...String(text).matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort();
const AREAS = ['clients', 'facture', 'settings'];

for (const area of AREAS) {
  const en = load('en', area);
  const fr = load('fr', area);

  test(`${area}: English and French define the same keys`, () => {
    assert.ok(Object.keys(en).length > 0);
    assert.deepEqual(Object.keys(fr).sort(), Object.keys(en).sort());
  });

  test(`${area}: every key carries the same placeholders in both languages`, () => {
    for (const key of Object.keys(en)) {
      assert.deepEqual(placeholders(fr[key]), placeholders(en[key]), key);
    }
  });

  test(`${area}: no empty value and keys stay inside the area prefix`, () => {
    for (const lang of [en, fr]) {
      for (const [key, value] of Object.entries(lang)) {
        assert.equal(typeof value, 'string', key);
        assert.ok(value.trim().length > 0, `${key} is empty`);
        assert.ok(key.startsWith(`${area}.`), `${key} is outside ${area}.`);
        assert.match(key, /^[a-z]+(\.[a-z0-9_]+)+$/, key);
      }
    }
  });
}

test('no key is claimed by two fragments', () => {
  const owner = new Map();
  const files = readdirSync(dir).filter(f => /^(en|fr)\.\w+\.js$/.test(f));
  for (const file of files) {
    for (const key of Object.keys(require(path.join(dir, file)))) {
      const id = `${file.slice(0, 2)}:${key}`;
      assert.ok(!owner.has(id), `${id} is defined in ${owner.get(id)} and ${file}`);
      owner.set(id, file);
    }
  }
});
