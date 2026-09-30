// Bilingual engine for the interface: English by default, French on request.
//
// One engine for lookup, formatting and the switchers, so the header control,
// the Paramètres control and the command palette can never disagree. Keys live
// in facturo/web/static/js/locales/*.js and register themselves with define().
//
// The preference is read at load and written to <html lang> before the first
// paint, so setting localStorage before this file runs comes up in the right
// language with no flash. Stored under 'facturo-lang' the same way ui/theme.js
// stores 'facturo-theme', and every access is guarded: storage can be blocked.
//
//   ui.i18n.t('nav.home')                    // 'Home' / 'Accueil'
//   ui.i18n.t('greet', { name: 'Ana' })      // {name} placeholders, unknown ones survive
//   ui.i18n.tn('bills', 2)                   // CLDR plural of the active language
//   ui.i18n.fmtMoney(1234.5)                 // '1,234.56 $' / '1 234,56 $'
//   ui.i18n.setLang('fr') / onLangChange(fn)
//
// Markup opts in with data-i18n (text) and data-i18n-attr="placeholder:k".
// Both are re-applied on every re-render and on every language change.
(function (root, factory) {
  const mod = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = mod;
  else { root.ui = root.ui || {}; root.ui.i18n = mod; }
})(typeof window !== 'undefined' ? window : globalThis, function (root) {
  'use strict';

  const KEY = 'facturo-lang';
  const DEFAULT_LANG = 'en';
  const SUPPORTED = ['en', 'fr'];
  // Canadian locales: French groups thousands and puts "$" after the amount,
  // which is what every invoice this shop issues looks like.
  const LOCALES = { en: 'en-CA', fr: 'fr-CA' };

  // U+00A0 before the dollar sign, U+202F between thousands: the separator
  // widths this app has always printed. Intl hands back U+00A0 for fr-CA, so the
  // body is narrowed below.
  const NBSP = ' ';
  const NNBSP = ' ';
  const MINUS = '−';
  const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
  const ISO_MONTH = /^(\d{4})-(\d{2})$/;
  const PLACEHOLDER = /\{(\w+)\}/g;

  const dicts = {};
  const plurals = {};
  const formatters = new Map();
  const subscribers = [];
  let current = DEFAULT_LANG;

  // ── storage ─────────────────────────────────────────────

  function storedLang() {
    try {
      const v = root.localStorage.getItem(KEY);
      return SUPPORTED.includes(v) ? v : null;
    } catch (e) {
      return null;
    }
  }

  function remember(code) {
    try { root.localStorage.setItem(KEY, code); } catch (e) { /* blocked: lasts this session only */ }
  }

  // ── lookup ──────────────────────────────────────────────

  const owns = (dict, key) => Object.prototype.hasOwnProperty.call(dict, key);

  function lookup(key, lang) {
    const dict = dicts[lang];
    return dict && owns(dict, key) ? dict[key] : undefined;
  }

  /** {name} placeholders. An unknown name is left alone so a typo is visible. */
  function fill(template, params) {
    if (!params) return template;
    return String(template).replace(PLACEHOLDER, (match, name) =>
      (params !== null && typeof params === 'object' && owns(params, name) ? String(params[name]) : match));
  }

  /**
   * The active language, then English, then the key itself. A half-finished
   * translation degrades to English instead of blanking the interface, and this
   * never returns undefined and never throws.
   */
  function t(key, params) {
    const name = typeof key === 'string' ? key : (key === null || key === undefined ? '' : String(key));
    try {
      const own = lookup(name, current);
      const fallback = lookup(name, DEFAULT_LANG);
      const template = own !== undefined ? own : (fallback !== undefined ? fallback : name);
      return fill(String(template), params);
    } catch (e) {
      return name;
    }
  }

  /** True when either language has an entry for the key. */
  function has(key) {
    const name = typeof key === 'string' ? key : '';
    return lookup(name, current) !== undefined || lookup(name, DEFAULT_LANG) !== undefined;
  }

  function category(count, lang) {
    try { return plurals[lang].select(count); } catch (e) { return 'other'; }
  }

  /**
   * Counted copy. English carries the whole sentence on the base key (it has
   * only one/other); French selects 'key.one' / 'key.many' / 'key.other'.
   * {count} is always available to the template.
   */
  function tn(key, count, params) {
    const name = typeof key === 'string' ? key : (key === null || key === undefined ? '' : String(key));
    const n = Number(count);
    const total = Number.isFinite(n) ? n : 0;
    try {
      const suffixed = lookup(`${name}.${category(total, current)}`, current);
      const own = lookup(name, current);
      const fallback = lookup(name, DEFAULT_LANG);
      const base = own !== undefined ? own : (fallback !== undefined ? fallback : name);
      return fill(String(suffixed !== undefined ? suffixed : base), Object.assign({ count: total }, params));
    } catch (e) {
      return name;
    }
  }

  /**
   * Register (or extend) one language's dictionary.
   * @returns {boolean} false when the language or the dictionary is unusable.
   */
  function define(lang, dict) {
    if (!SUPPORTED.includes(lang) || !dict || typeof dict !== 'object') return false;
    const target = dicts[lang] || (dicts[lang] = {});
    Object.keys(dict).forEach(key => {
      // Two fragments claiming one key is a copy-paste between areas, never a
      // load-order question: warn and keep the first, so the mistake shows up
      // in dev instead of flipping when someone reorders the <script> tags.
      if (owns(target, key) && target[key] !== dict[key]) {
        console.warn(`[ui.i18n] duplicate key "${key}" for "${lang}"; keeping "${target[key]}"`);
        return;
      }
      target[key] = dict[key];
    });
    try { plurals[lang] = new Intl.PluralRules(LOCALES[lang]); } catch (e) { /* category() falls back */ }
    return true;
  }

  // ── language ────────────────────────────────────────────

  /** @returns {'en'|'fr'} the language in effect right now. */
  function lang() { return current; }

  /** @returns {'en-CA'|'fr-CA'} the BCP-47 tag handed to Intl. */
  function locale() { return LOCALES[current] || LOCALES[DEFAULT_LANG]; }

  function applyToDocument() {
    const el = root.document && root.document.documentElement;
    if (!el || !el.setAttribute) return;
    try { el.setAttribute('lang', locale()); } catch (e) { /* no DOM to update */ }
  }

  function notify(code) {
    subscribers.slice().forEach(fn => {
      try { fn(code); } catch (e) { console.error('[ui.i18n]', e); }
    });
  }

  /**
   * Persist a language, update <html lang> and notify subscribers when it
   * actually changed. An unsupported code falls back to the default.
   */
  function setLang(code) {
    const next = SUPPORTED.includes(code) ? code : DEFAULT_LANG;
    const changed = next !== current;
    current = next;
    remember(next);
    applyToDocument();
    if (changed) notify(next);
    return current;
  }

  /** @returns {Function} an unsubscribe, so a re-mounted view can let go. */
  function onLangChange(fn) {
    if (typeof fn !== 'function') return () => {};
    subscribers.push(fn);
    return () => {
      const i = subscribers.indexOf(fn);
      if (i >= 0) subscribers.splice(i, 1);
    };
  }

  // ── formatting ──────────────────────────────────────────

  /** Intl objects are cached: a table builds one call per row. */
  function cached(kind, opts) {
    const id = `${kind}:${current}:${JSON.stringify(opts)}`;
    let f = formatters.get(id);
    if (!f) {
      const Ctor = kind === 'date' ? Intl.DateTimeFormat : Intl.NumberFormat;
      try { f = new Ctor(locale(), opts); } catch (e) { f = new Ctor('en-CA', opts); }
      formatters.set(id, f);
    }
    return f;
  }

  function amount(n) {
    const v = Number(n);
    return Number.isFinite(v) ? v : 0;
  }

  /**
   * Canadian dollars, always two decimals and the sign after the amount, in
   * both languages: "1,234.56 $" / "1 234,56 $".
   */
  function fmtMoney(n) {
    const rounded = Math.round(amount(n) * 100) / 100;
    // An amount that rounds to zero prints unsigned: "-0,00 $" reads as a bug.
    const body = cached('number', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(rounded === 0 ? 0 : rounded);
    return `${body.replace(/[   ](?=\d)/g, NNBSP).replace('-', MINUS)}${NBSP}$`;
  }

  /** Grouped number, no currency. An integer `decimals` pins the fraction. */
  function fmtNumber(n, decimals) {
    const opts = Number.isInteger(decimals) ? { minimumFractionDigits: decimals, maximumFractionDigits: decimals } : {};
    return cached('number', opts).format(amount(n));
  }

  /**
   * Parse 'YYYY-MM-DD' by hand. new Date('2026-09-30') is UTC midnight, so a
   * browser west of Greenwich would print the 29th.
   */
  function parseLocal(value) {
    if (typeof value !== 'string') return null;
    const day = ISO_DATE.exec(value.slice(0, 10));
    if (day) {
      const d = new Date(Number(day[1]), Number(day[2]) - 1, Number(day[3]));
      return Number.isNaN(d.getTime()) ? null : d;
    }
    const month = ISO_MONTH.exec(value.slice(0, 7));
    if (month) return new Date(Number(month[1]), Number(month[2]) - 1, 1);
    return null;
  }

  /** 'Sep 30, 2026' / '30 sept. 2026'. Empty stays empty, odd input survives. */
  function fmtDate(iso) {
    if (!iso) return '';
    const d = parseLocal(iso);
    if (!d) return String(iso);
    try { return cached('date', { dateStyle: 'medium' }).format(d); } catch (e) { return String(iso).slice(0, 10); }
  }

  /** 'Sep 2026' / 'sept. 2026', from 'YYYY-MM' or 'YYYY-MM-DD'. */
  function fmtMonth(iso) {
    const d = parseLocal(iso);
    if (!d) return typeof iso === 'string' ? iso.slice(0, 7) : '';
    try { return cached('date', { month: 'short', year: 'numeric' }).format(d); } catch (e) { return String(iso).slice(0, 7); }
  }

  // ── data-i18n hydration ─────────────────────────────────

  function withSelf(scope, selector, fn) {
    if (scope.matches && scope.matches(selector)) fn(scope);
    scope.querySelectorAll(selector).forEach(fn);
  }

  /**
   * Apply data-i18n / data-i18n-attr to a subtree. Text goes in through
   * textContent and attributes through setAttribute, never innerHTML, so a
   * translation can never become markup.
   *
   * Both write only on a real change. ui.hydrate re-runs on a childList
   * mutation and assigning textContent always removes and re-adds the text
   * node, so an unconditional write would queue another pass, and another,
   * for as long as the page is open.
   */
  function applyMarkup(scope) {
    const target = scope && scope.querySelectorAll ? scope : root.document;
    if (!target) return;
    withSelf(target, '[data-i18n]', el => {
      const text = t(el.getAttribute('data-i18n'));
      if (el.textContent !== text) el.textContent = text;
    });
    withSelf(target, '[data-i18n-attr]', el => {
      String(el.getAttribute('data-i18n-attr') || '').split(',').forEach(pair => {
        const sep = pair.indexOf(':');
        if (sep < 0) return;
        const name = pair.slice(0, sep).trim();
        const key = pair.slice(sep + 1).trim();
        if (!name || !key) return;
        const value = t(key);
        if (el.getAttribute(name) !== value) el.setAttribute(name, value);
      });
    });
  }

  // ── switchers ───────────────────────────────────────────

  /** Reflect the active language on every control in this subtree. */
  function paintSwitches(scope) {
    const target = scope && scope.querySelectorAll ? scope : root.document;
    if (!target) return;
    withSelf(target, '[data-lang-group]', group => {
      group.querySelectorAll('[data-lang-set]').forEach(btn => {
        const on = btn.dataset.langSet === current;
        // Same reason as applyMarkup: a no-op classList.toggle still writes.
        if (btn.classList.contains('active') !== on) btn.classList.toggle('active', on);
        const pressed = on ? 'true' : 'false';
        if (btn.getAttribute('aria-pressed') !== pressed) btn.setAttribute('aria-pressed', pressed);
      });
    });
  }

  /**
   * The one wiring point for every language control. Any element carrying
   * data-lang-group holds data-lang-set buttons — the header one and the
   * Paramètres one use the same markup, so they cannot drift apart.
   */
  function mountSwitchers() {
    const doc = root.document;
    if (!doc || !doc.querySelectorAll) return;
    doc.querySelectorAll('[data-lang-group]').forEach(group => {
      if (group.dataset.langBound) return;
      group.dataset.langBound = '1';
      group.addEventListener('click', e => {
        const btn = e.target instanceof Element && e.target.closest('[data-lang-set]');
        if (btn && group.contains(btn)) setLang(btn.dataset.langSet);
      });
    });
    paintSwitches(doc);
  }

  function mount() {
    mountSwitchers();
    // #main-content is rebuilt with innerHTML on every render, so both passes
    // have to re-run: one for the translations, one for the switch state.
    if (root.ui && root.ui.hydrate && root.ui.hydrate.register) {
      root.ui.hydrate.register(applyMarkup);
      root.ui.hydrate.register(paintSwitches);
    }
    onLangChange(() => { if (root.document) applyMarkup(root.document); });
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('DOMContentLoaded', mount, { once: true });
    if (root.document.readyState !== 'loading') mount();
  }

  // Read the stored preference before anything renders: this file is loaded in
  // <head> for exactly that, next to ui/theme.js.
  current = storedLang() || DEFAULT_LANG;
  applyToDocument();

  return {
    lang, setLang, t, tn, has, onLangChange, define,
    fmtMoney, fmtDate, fmtNumber, fmtMonth,
    applyMarkup, paintSwitches, mountSwitchers,
    SUPPORTED, DEFAULT_LANG, LOCALES,
  };
});