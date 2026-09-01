// Light / dark / system theme.
//
// Loaded as a plain <script> in <head> so <html data-theme> is set before the
// first paint (no flash). The preference lives in localStorage under
// 'facturo-theme' ('light' | 'dark' | 'system'); every access is guarded because
// storage can be blocked. The resolved value is always written to data-theme.
(function (root) {
  'use strict';

  const KEY = 'facturo-theme';
  const MODES = ['light', 'dark', 'system'];
  const doc = root.document;
  const mql = root.matchMedia ? root.matchMedia('(prefers-color-scheme: dark)') : null;

  /** @returns {'light'|'dark'|'system'} the stored preference (default 'system') */
  function getPreference() {
    try {
      const v = root.localStorage.getItem(KEY);
      return MODES.includes(v) ? v : 'system';
    } catch (e) {
      return 'system';
    }
  }

  /** @returns {'light'|'dark'} what the preference resolves to right now */
  function resolve(pref) {
    if (pref === 'light' || pref === 'dark') return pref;
    return mql && mql.matches ? 'dark' : 'light';
  }

  function apply(pref) {
    const resolved = resolve(pref);
    doc.documentElement.setAttribute('data-theme', resolved);
    doc.documentElement.setAttribute('data-theme-pref', pref);
    const btns = doc.querySelectorAll('#theme-toggle [data-theme-set]');
    btns.forEach(b => {
      const on = b.dataset.themeSet === pref;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    return resolved;
  }

  /** Persist and apply a preference. Unknown values fall back to 'system'. */
  function setPreference(pref) {
    const next = MODES.includes(pref) ? pref : 'system';
    try { root.localStorage.setItem(KEY, next); } catch (e) { /* storage blocked: still apply for this session */ }
    return apply(next);
  }

  /** Cycle light -> dark -> system (used by the command palette later). */
  function cycle() {
    const order = ['light', 'dark', 'system'];
    return setPreference(order[(order.indexOf(getPreference()) + 1) % order.length]);
  }

  apply(getPreference());
  if (mql && mql.addEventListener) {
    mql.addEventListener('change', () => { if (getPreference() === 'system') apply('system'); });
  }

  // Wire the sidebar footer toggle once the DOM exists (icons.js has run by then).
  doc.addEventListener('DOMContentLoaded', () => {
    const group = doc.getElementById('theme-toggle');
    if (!group) return;
    group.querySelectorAll('[data-theme-set]').forEach(b => {
      const name = { light: 'sun', dark: 'moon', system: 'monitor' }[b.dataset.themeSet];
      if (typeof root.icon === 'function' && !b.querySelector('svg')) b.insertAdjacentHTML('afterbegin', root.icon(name, { size: 'sm' }));
      b.addEventListener('click', () => setPreference(b.dataset.themeSet));
    });
    apply(getPreference());
  });

  root.ui = Object.assign(root.ui || {}, { theme: { getPreference, setPreference, cycle, resolve } });
})(window);
