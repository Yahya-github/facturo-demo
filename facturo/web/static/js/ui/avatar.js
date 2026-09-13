// Initials avatar with a stable tint per name, so a client keeps the same
// colour in every table.
//
//   ui.avatar('Demo Transport Inc.')              -> '<span class="avatar avatar-sm tone-2" aria-hidden="true">DT</span>'
//   ui.avatar(name, { size: 'lg' })               -> 'sm' | 'md' | 'lg'
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};
  const TONES = 5;

  /** Small stable hash of a string, 0 <= n < TONES. */
  function toneOf(name) {
    let n = 7;
    for (const ch of String(name || '')) n = (n * 31 + ch.codePointAt(0)) % 9973;
    return n % TONES;
  }

  /** @returns {string} trusted markup (initials are escaped). */
  function avatar(name, opts = {}) {
    const size = ['sm', 'lg'].includes(opts.size) ? ` avatar-${opts.size}` : '';
    const initials = ui.shell ? ui.shell.initials(name) : String(name || '?').slice(0, 2).toUpperCase();
    return `<span class="avatar${size} tone-${toneOf(name)}" aria-hidden="true">${root.esc(initials)}</span>`;
  }

  ui.avatar = avatar;
  ui.avatar.toneOf = toneOf;
})(window);
