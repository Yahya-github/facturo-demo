// How much French is still hardcoded in the page scripts?
//
//   node tests/js/i18n-lint.mjs          human-readable tally
//   node tests/js/i18n-lint.mjs --json   machine-readable, for diffing a PR
//   node tests/js/i18n-lint.mjs --top 8  more rows
//
// This reports; it never fails. The number is a migration budget, not a gate:
// the count can only fall, and a hardcoded string is a bug the moment the
// locale engine is what serves it. Wired into nothing, on purpose — an
// over-strict lint that blocks unrelated work gets deleted, and then nobody
// knows how much is left.
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const jsDir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'facturo', 'web', 'static', 'js');

const argv = process.argv.slice(2);
const asJson = argv.includes('--json');
const topIdx = argv.indexOf('--top');
const top = topIdx >= 0 ? Number(argv[topIdx + 1]) || 5 : 5;

// A French literal needs a French-looking word: an accented vowel, the cedilla,
// the œ ligature, or a plain French function word. That keeps "Modifier",
// "Aucun résultat" and "Réinitialiser" while ignoring the identifiers, class
// names and icon keys that make up most of the file.
const FRENCH_WORD = /(?:[àâäæçéèêëîïôöùûüÿœ]|(?:^|[\s'"/(])(?:le|la|les|des|une|du|et|ou|pour|avec|sans|sur|par|au|aux|en|dans|aucun|aucune|rechercher|voir|fermer|ouvrir|modifier|ajouter|supprimer|annuler|enregistrer|paramètres|recherche|résumé|sélectionner|obligatoire|facultatif))/i;

// Only string and template literals, so a French word in a comment does not
// count.
const LITERAL = /'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`/g;

function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, m => m.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, lead) => lead);
}

function countFile(rel) {
  const src = stripComments(readFileSync(path.join(jsDir, rel), 'utf8'));
  const hits = [];
  LITERAL.lastIndex = 0;
  let m;
  while ((m = LITERAL.exec(src)) !== null) {
    const text = m[1] !== undefined ? m[1] : (m[2] !== undefined ? m[2] : m[3]);
    if (!text) continue;
    const word = FRENCH_WORD.exec(text);
    if (!word) continue;
    // Show the phrase, not the whole literal: a page template is one literal
    // holding a dozen strings, and the reader wants the dozen.
    const from = Math.max(0, word.index - 12);
    const snippet = text.slice(from, word.index + 24).replace(/\s+/g, ' ').trim();
    hits.push({ line: src.slice(0, m.index).split('\n').length, text: snippet });
  }
  return { file: rel, count: hits.length, hits };
}

// The dictionaries are the destination, not the problem, and the engine's own
// comments are in English.
const files = readdirSync(jsDir, { recursive: true })
  .filter(n => n.endsWith('.js') && !n.replace(/\\/g, '/').startsWith('locales/') && n !== 'i18n.js')
  .sort();
const results = files.map(countFile).filter(r => r.count > 0).sort((a, b) => b.count - a.count);
const total = results.reduce((n, r) => n + r.count, 0);

if (asJson) {
  console.log(JSON.stringify({ total, files: results.length, results }, null, 2));
  process.exit(0);
}

console.log('Hardcoded French literals in facturo/web/static/js/');
console.log(`${total} in ${results.length} file(s) — move each to locales/ and read it with ui.i18n.t()`);
console.log('');
for (const r of results.slice(0, top)) console.log(`  ${String(r.count).padStart(4)}  ${r.file}`);
if (results.length > top) console.log(`  ${''.padStart(4)}  … and ${results.length - top} more`);
console.log('');
console.log('per file:');
for (const r of results) {
  console.log(`  ${r.file.padEnd(26)} ${String(r.count).padStart(4)}`);
  for (const h of r.hits.slice(0, 3)) console.log(`      ${String(h.line).padStart(4)}  ${h.text}`);
  if (r.hits.length > 3) console.log(`           … ${r.hits.length - 3} more`);
}
