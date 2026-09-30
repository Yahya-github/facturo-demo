// Locale fragments owned by batch A (ui, home, history, scans, payments):
// English and French must stay in lockstep. Plain node: node --test tests/js/locales-a.test.mjs
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';

const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'facturo', 'web', 'static', 'js', 'locales');
const require = createRequire(import.meta.url);
const AREAS = ['ui', 'home', 'history', 'scans', 'payments'];

const load = (lang, area) => require(path.join(dir, `${lang}.${area}.js`));
const placeholders = text => [...String(text).matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort();

// The literal keys in the source, so a duplicate inside one object (which a JS
// object literal would silently collapse) is caught too.
const sourceKeys = (lang, area) => {
  const src = readFileSync(path.join(dir, `${lang}.${area}.js`), 'utf8');
  return [...src.matchAll(/^\s+(?:'([^']+)'|"([^"]+)"):/gm)].map(m => m[1] || m[2]);
};

for (const area of AREAS) {
  test(`${area}: en and fr define the same keys`, () => {
    const en = Object.keys(load('en', area));
    const fr = Object.keys(load('fr', area));
    assert.deepEqual(fr.filter(k => !en.includes(k)), [], 'in fr but not en');
    assert.deepEqual(en.filter(k => !fr.includes(k)), [], 'in en but not fr');
  });

  test(`${area}: placeholders match per key`, () => {
    const en = load('en', area);
    const fr = load('fr', area);
    for (const key of Object.keys(en)) {
      assert.deepEqual(placeholders(fr[key]), placeholders(en[key]), key);
    }
  });

  test(`${area}: no empty values`, () => {
    for (const lang of ['en', 'fr']) {
      for (const [key, value] of Object.entries(load(lang, area))) {
        assert.equal(typeof value, 'string', `${lang}:${key}`);
        assert.ok(value.trim().length > 0, `${lang}:${key} is empty`);
      }
    }
  });

  test(`${area}: no key written twice in one file`, () => {
    for (const lang of ['en', 'fr']) {
      const keys = sourceKeys(lang, area);
      const dupes = keys.filter((k, i) => keys.indexOf(k) !== i);
      assert.deepEqual(dupes, [], `${lang}.${area}.js`);
    }
  });
}

test('no key is claimed by two fragments', () => {
  for (const lang of ['en', 'fr']) {
    const owner = new Map();
    for (const area of AREAS) {
      for (const key of Object.keys(load(lang, area))) {
        assert.ok(!owner.has(key), `${lang}: "${key}" is in both ${owner.get(key)} and ${area}`);
        owner.set(key, area);
      }
    }
  }
});

test('keys are lowercase dotted names', () => {
  for (const area of AREAS) {
    for (const key of Object.keys(load('en', area))) {
      assert.match(key, /^[a-z0-9_]+(\.[a-z0-9_]+)+$/, key);
    }
  }
});

test('plural keys always have a base key', () => {
  for (const area of AREAS) {
    const fr = load('fr', area);
    for (const key of Object.keys(fr)) {
      const m = /\.(zero|one|two|few|many|other)$/.exec(key);
      if (m) assert.ok(fr[key.slice(0, -m[0].length)] !== undefined, `${key} has no base key`);
    }
  }
});
