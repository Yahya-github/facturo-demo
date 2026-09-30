// Bilingual engine (facturo/web/static/js/i18n.js) and the shell dictionaries
// in locales/. Plain node: node --test tests/js/i18n.test.mjs
//
// The module reads localStorage and <html lang> at load time, so the fakes go
// in before the require — that ordering is the whole point of loading the file
// from <head>, and the tests lean on it.
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import assert from 'node:assert/strict';

const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'facturo', 'web', 'static', 'js');

// ── browser stand-ins ───────────────────────────────────

const store = new Map();
const attrs = new Map();
globalThis.localStorage = {
  getItem: k => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => { store.set(k, String(v)); },
  removeItem: k => { store.delete(k); },
};
globalThis.document = {
  // 'loading' so the module's DOMContentLoaded wiring never fires here: this
  // suite is about lookup and formatting, and the mount path needs a real DOM.
  readyState: 'loading',
  addEventListener() {},
  documentElement: {
    setAttribute: (n, v) => { attrs.set(n, v); },
    getAttribute: n => (attrs.has(n) ? attrs.get(n) : null),
  },
};

const require = createRequire(import.meta.url);
const i18n = require(path.join(dir, 'i18n.js'));
i18n.define('en', require(path.join(dir, 'locales', 'en.ui.js')));
i18n.define('fr', require(path.join(dir, 'locales', 'fr.ui.js')));

const NNBSP = '\u202f';   // narrow no-break space, thousands
const NBSP = '\u00a0';    // no-break space, before the dollar sign
const MINUS = '−';
const use = code => i18n.setLang(code);

// ── lookup ──────────────────────────────────────────────

test('English is the default and the language is a two-letter code', () => {
  use('en');
  assert.equal(i18n.lang(), 'en');
  assert.deepEqual(i18n.SUPPORTED, ['en', 'fr']);
  assert.equal(i18n.DEFAULT_LANG, 'en');
});

test('t() reads the active language', () => {
  use('en');
  assert.equal(i18n.t('nav.home'), 'Home');
  assert.equal(i18n.t('nav.payments'), 'Payments');
  use('fr');
  assert.equal(i18n.t('nav.home'), 'Accueil');
  assert.equal(i18n.t('nav.payments'), 'Paiements');
});

test('an unsupported code falls back to English', () => {
  assert.equal(i18n.setLang('de'), 'en');
  assert.equal(i18n.lang(), 'en');
  assert.equal(i18n.setLang(null), 'en');
});

test('t() returns the key itself when nothing defines it', () => {
  use('fr');
  assert.equal(i18n.t('nothing.here'), 'nothing.here');
  assert.equal(i18n.has('nothing.here'), false);
});

test('t() falls back to English for a key French is missing', () => {
  // fr.ui.js has no 'only.en' key; English is the base, so it wins.
  i18n.define('en', { 'only.en': 'English only' });
  use('fr');
  assert.equal(i18n.t('only.en'), 'English only');
  assert.equal(i18n.has('only.en'), true);
  use('en');
  assert.equal(i18n.t('only.en'), 'English only');
});

test('t() never returns undefined and never throws', () => {
  use('en');
  assert.equal(i18n.t('missing.key'), 'missing.key');
  assert.equal(i18n.t(undefined), '');
  assert.equal(i18n.t(null), '');
  // A dictionary value that is not a string must not blow up a render.
  i18n.define('en', { 'weird.value': { toString: () => 'coerced' } });
  assert.equal(i18n.t('weird.value'), 'coerced');
});

test('placeholders are filled and unknown ones are left visible', () => {
  i18n.define('en', { 'greet.hello': 'Hello {name}, you have {count}' });
  use('en');
  assert.equal(i18n.t('greet.hello', { name: 'Ana', count: 2 }), 'Hello Ana, you have 2');
  assert.equal(i18n.t('greet.hello', { name: 'Ana' }), 'Hello Ana, you have {count}');
  assert.equal(i18n.t('greet.hello'), 'Hello {name}, you have {count}');
});

// ── plurals ─────────────────────────────────────────────

test('tn() picks the CLDR category of the active language', () => {
  i18n.define('en', { 'bill.line': '{count} lines', 'bill.line.one': '{count} line' });
  i18n.define('fr', { 'bill.line': '{count} lignes', 'bill.line.one': '{count} ligne' });
  use('en');
  assert.equal(i18n.tn('bill.line', 1), '1 line');
  assert.equal(i18n.tn('bill.line', 4), '4 lines');
  use('fr');
  assert.equal(i18n.tn('bill.line', 1), '1 ligne');
  // A category French has no explicit form for falls through to the base key,
  // which is why the base is never allowed to be blank.
  assert.equal(i18n.tn('bill.line', 4), '4 lignes');
});

test('tn() prefers a suffixed form, then the base, then the key', () => {
  // A base key with only a '.one' form: the singular is explicit, and every
  // other category has to fall through to the base.
  i18n.define('en', { 'row': '{count} rows', 'row.one': '{count} row' });
  use('en');
  assert.equal(i18n.tn('row', 1), '1 row');
  assert.equal(i18n.tn('row', 7), '7 rows');
  // Neither a base nor a matching suffix: the key itself, so the UI shows the
  // hole rather than a blank.
  assert.equal(i18n.tn('absent.key', 3), 'absent.key');
});

test('tn() always offers {count} and survives a bad count', () => {
  i18n.define('en', { 'n.row': '{count} rows', 'n.row.one': '{count} row' });
  use('en');
  assert.equal(i18n.tn('n.row', 0), '0 rows');
  assert.equal(i18n.tn('n.row', 'nope'), '0 rows');
});

// ── registration ────────────────────────────────────────

test('define() rejects an unsupported language and a non-object', () => {
  assert.equal(i18n.define('de', { a: 'b' }), false);
  assert.equal(i18n.define('en', null), false);
  assert.equal(i18n.define('en', 'nope'), false);
});

test('define() keeps the first value and warns on a duplicate', () => {
  const warn = console.warn;
  const seen = [];
  console.warn = m => { seen.push(m); };
  try {
    i18n.define('en', { 'dupe.key': 'first' });
    i18n.define('en', { 'dupe.key': 'second' });
  } finally {
    console.warn = warn;
  }
  assert.equal(i18n.t('dupe.key'), 'first');
  assert.equal(seen.length, 1);
  assert.match(seen[0], /duplicate key "dupe.key" for "en"/);
});

// ── language switching ──────────────────────────────────

test('setLang() persists, updates <html lang> and returns the language', () => {
  use('fr');
  assert.equal(i18n.lang(), 'fr');
  assert.equal(store.get('facturo-lang'), 'fr');
  assert.equal(globalThis.document.documentElement.getAttribute('lang'), 'fr-CA');
  use('en');
  assert.equal(store.get('facturo-lang'), 'en');
  assert.equal(globalThis.document.documentElement.getAttribute('lang'), 'en-CA');
});

test('onLangChange() fires on a real change and returns an unsubscribe', () => {
  const seen = [];
  const off = i18n.onLangChange(code => { seen.push(code); });
  assert.equal(typeof off, 'function');
  use('en');
  use('fr');
  use('fr'); // no change, no second call
  off();
  use('en');
  assert.deepEqual(seen, ['fr']);
});

test('a throwing subscriber does not stop the others', () => {
  const err = console.error;
  console.error = () => {};
  const seen = [];
  i18n.onLangChange(() => { throw new Error('boom'); });
  const off = i18n.onLangChange(code => { seen.push(code); });
  try {
    use('fr');
  } finally {
    off();
    console.error = err;
  }
  assert.deepEqual(seen, ['fr']);
});

test('a blocked localStorage does not break setLang()', () => {
  const boom = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } };
  const real = globalThis.localStorage;
  globalThis.localStorage = boom;
  try {
    assert.equal(i18n.setLang('fr'), 'fr');
    assert.equal(i18n.t('nav.home'), 'Accueil');
  } finally {
    globalThis.localStorage = real;
    use('en');
  }
});

// ── formatting ──────────────────────────────────────────

test('fmtMoney() prints Canadian dollars with the sign after the amount', () => {
  use('en');
  assert.equal(i18n.fmtMoney(1234.56), `1,234.56${NBSP}$`);
  use('fr');
  // Narrow no-break space between thousands, decimal comma, plain no-break
  // space before the $: the two widths this app has always used.
  assert.equal(i18n.fmtMoney(1234.56), `1${NNBSP}234,56${NBSP}$`);
  assert.equal(i18n.fmtMoney(9042.78), `9${NNBSP}042,78${NBSP}$`);
  assert.equal(i18n.fmtMoney(1234567.1), `1${NNBSP}234${NNBSP}567,10${NBSP}$`);
});

test('fmtMoney() rounds, drops a negative zero and uses a real minus', () => {
  use('fr');
  assert.equal(i18n.fmtMoney(999.999), `1${NNBSP}000,00${NBSP}$`);
  assert.equal(i18n.fmtMoney(-0.001), `0,00${NBSP}$`);
  assert.equal(i18n.fmtMoney(-1234.5), `${MINUS}1${NNBSP}234,50${NBSP}$`);
  assert.equal(i18n.fmtMoney(undefined), `0,00${NBSP}$`);
});

test('fmtMoney() keeps the dollar sign last in English too', () => {
  use('en');
  // Intl puts "$1,234.56" for en-CA; the app always prints the sign last.
  assert.equal(i18n.fmtMoney(1234.56), `1,234.56${NBSP}$`);
  assert.equal(i18n.fmtMoney(-1234.5), `${MINUS}1,234.50${NBSP}$`);
});

test('fmtNumber() groups without a currency and can pin decimals', () => {
  use('en');
  assert.equal(i18n.fmtNumber(1234567.5), '1,234,567.5');
  assert.equal(i18n.fmtNumber(1234567.5, 2), '1,234,567.50');
  use('fr');
  // Plain Intl spacing here: only fmtMoney() narrows the group separator, so
  // counts and quantities keep whatever the locale gives.
  assert.equal(i18n.fmtNumber(1234567.5), `1${NBSP}234${NBSP}567,5`);
  assert.equal(i18n.fmtNumber(0.5, 0), '1');
  assert.equal(i18n.fmtNumber('x'), '0');
});

test('fmtDate() keeps the calendar day, whatever the timezone', () => {
  // new Date('2026-09-30') is UTC midnight, which is the 29th west of Greenwich.
  use('en');
  assert.equal(i18n.fmtDate('2026-09-30'), 'Sep 30, 2026');
  use('fr');
  assert.equal(i18n.fmtDate('2026-09-30'), '30 sept. 2026');
  // A month boundary and a leap day, the two places a naive parser slips.
  assert.equal(i18n.fmtDate('2026-03-01'), '1 mars 2026');
  assert.equal(i18n.fmtDate('2024-02-29'), '29 févr. 2024');
});

test('fmtDate() passes empty and unparseable input through', () => {
  use('fr');
  assert.equal(i18n.fmtDate(''), '');
  assert.equal(i18n.fmtDate(null), '');
  assert.equal(i18n.fmtDate('not-a-date'), 'not-a-date');
  // A full timestamp is read by its date part, not re-rendered.
  assert.ok(i18n.fmtDate('2026-09-30T14:05:00').includes('2026'));
});

test('fmtMonth() accepts YYYY-MM and YYYY-MM-DD', () => {
  use('en');
  assert.equal(i18n.fmtMonth('2026-09'), 'Sep 2026');
  assert.equal(i18n.fmtMonth('2026-09-30'), 'Sep 2026');
  use('fr');
  assert.equal(i18n.fmtMonth('2026-09'), 'sept. 2026');
  assert.equal(i18n.fmtMonth('2026-01'), 'janv. 2026');
  assert.equal(i18n.fmtMonth('nope'), 'nope');
  assert.equal(i18n.fmtMonth(null), '');
});

// ── data-i18n hydration ─────────────────────────────────

/** The smallest thing applyMarkup() can walk: a list of attribute-carrying nodes. */
function fakeScope(nodes) {
  const has = (n, one) => {
    const attr = /^\[([\w-]+)\]$/.exec(one);
    return attr ? Object.prototype.hasOwnProperty.call(n, attr[1]) : true;
  };
  return {
    matches: () => false,
    querySelectorAll: sel => ({ forEach: fn => nodes.filter(n => sel.split(',').some(one => has(n, one.trim()))).forEach(fn) }),
  };
}

/** A node that reports its own data-* attributes and records what gets set. */
function fakeNode(attrs) {
  const node = Object.assign({}, attrs);
  node.getAttribute = n => (n in node ? node[n] : null);
  node.setAttribute = (n, v) => { node[n] = v; };
  return node;
}

test('applyMarkup() writes text through textContent and attributes through setAttribute', () => {
  use('fr');
  const text = fakeNode({ 'data-i18n': 'nav.home', textContent: 'stale' });
  const attrsOnly = fakeNode({ 'data-i18n-attr': 'aria-label:nav.settings,data-tip:nav.home' });
  i18n.applyMarkup(fakeScope([text, attrsOnly]));
  assert.equal(text.textContent, 'Accueil');
  assert.equal(attrsOnly['aria-label'], 'Paramètres');
  assert.equal(attrsOnly['data-tip'], 'Accueil');
  // Never innerHTML: a translation can never become markup.
  assert.equal(text.innerHTML, undefined);
});

test('applyMarkup() ignores a malformed attribute list', () => {
  use('en');
  const el = fakeNode({ 'data-i18n-attr': 'no-colon,:no-key,ok:nav.home' });
  i18n.applyMarkup(fakeScope([el]));
  assert.equal(el.ok, 'Home');
  assert.equal(el['no-colon'], undefined);
});

test('paintSwitches() reflects the active language on every control', () => {
  use('fr');
  // The double counts its own writes, so the read-before-write guard is visible:
  // a second pass over the same buttons must be a genuine no-op.
  const mk = code => {
    const node = { 'data-lang-set': code, dataset: { langSet: code }, writes: 0 };
    const on = new Set();
    node.classList = { contains: c => on.has(c), toggle: (c, want) => { node.writes++; (want ? on.add : on.delete).call(on, c); } };
    node.getAttribute = n => (n in node ? node[n] : null);
    node.setAttribute = (n, v) => { node.writes++; node[n] = v; };
    return node;
  };
  const en = mk('en');
  const fr = mk('fr');
  const group = { querySelectorAll: () => ({ forEach: fn => { fn(en); fn(fr); } }) };
  const scope = { matches: () => false, querySelectorAll: () => ({ forEach: fn => fn(group) }) };
  i18n.paintSwitches(scope);
  assert.equal(fr['aria-pressed'], 'true');
  assert.equal(en['aria-pressed'], 'false');
  const after = en.writes + fr.writes;
  i18n.paintSwitches(scope);
  assert.equal(en.writes + fr.writes, after, 'a repeated pass must not write');
});

// ── the shell dictionaries ──────────────────────────────

test('both dictionaries carry the same keys, so neither can blank the UI', () => {
  const en = require(path.join(dir, 'locales', 'en.ui.js'));
  const fr = require(path.join(dir, 'locales', 'fr.ui.js'));
  assert.deepEqual(Object.keys(en).filter(k => !(k in fr)), []);
  assert.deepEqual(Object.keys(fr).filter(k => !(k in en)), []);
  assert.equal(Object.keys(en).length, Object.keys(fr).length);
  assert.ok(Object.keys(en).length >= 50, 'the shell fragment should carry the shared vocabulary');
});

test('the two dictionaries really differ where they should', () => {
  i18n.define('en', { 'probe.key': 'Home' });
  i18n.define('fr', { 'probe.key': 'Accueil' });
  use('en');
  assert.equal(i18n.t('probe.key'), 'Home');
  use('fr');
  assert.equal(i18n.t('probe.key'), 'Accueil');
  use('en');
});

test('the language picker names its options in both languages', () => {
  use('en');
  assert.equal(i18n.t('lang.en'), 'English');
  assert.equal(i18n.t('lang.fr'), 'French');
  use('fr');
  assert.equal(i18n.t('lang.en'), 'Anglais');
  assert.equal(i18n.t('lang.fr'), 'Français');
  // Deliberately identical in both files: the palette entry is a hand-off.
  assert.equal(i18n.t('lang.action'), 'Langue / Language');
});
