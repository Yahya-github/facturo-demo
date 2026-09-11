// Number count-up with requestAnimationFrame. Honours prefers-reduced-motion
// (jumps straight to the final value) and formats with the app's money() /
// French locale.
//
//   ui.countup.run(el, 1234.5, { format: 'money' })      // 'money' | 'int' | (n) => string
//   <span data-countup="1234.5" data-countup-format="money"></span>   // hydrated automatically
//
// easeOutCubic / valueAt / roundTo are pure and unit-tested (tests/js/ui-chart.test.mjs).
(function (root, factory) {
  const mod = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = mod;
  else { root.ui = root.ui || {}; root.ui.countup = mod; }
})(typeof window !== 'undefined' ? window : globalThis, function (root) {
  const easeOutCubic = t => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3);

  /** Value of the tween `elapsed` ms into a `duration` ms animation. */
  function valueAt(from, to, elapsed, duration) {
    if (!(duration > 0) || elapsed >= duration) return to;
    return from + (to - from) * easeOutCubic(elapsed / duration);
  }

  const roundTo = (n, decimals) => {
    const k = Math.pow(10, decimals);
    return Math.round(n * k) / k;
  };

  function formatter(spec, decimals) {
    if (typeof spec === 'function') return spec;
    if (spec === 'money' && typeof root.money === 'function') return n => root.money(n);
    return n => roundTo(n, decimals).toLocaleString('fr-CA', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  }

  /**
   * Animate `el.textContent` from `from` to `to`. Returns { cancel }.
   * @param {{from?: number, duration?: number, decimals?: number, format?: 'money'|'int'|Function}} [o]
   */
  function run(el, to, o = {}) {
    const target = Number(to) || 0;
    const decimals = o.decimals ?? (o.format === 'int' ? 0 : 2);
    const fmt = formatter(o.format, decimals);
    const reduced = root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const duration = o.duration ?? 900;
    const from = o.from ?? 0;
    el.setAttribute('data-countup-value', String(target));
    if (reduced || !root.requestAnimationFrame || from === target) { el.textContent = fmt(target); return { cancel() {} }; }
    let raf = 0, t0 = 0, dead = false;
    el.textContent = fmt(from);
    const step = now => {
      if (dead) return;
      t0 = t0 || now;
      const v = valueAt(from, target, now - t0, duration);
      el.textContent = fmt(now - t0 >= duration ? target : roundTo(v, decimals));
      if (now - t0 < duration) raf = root.requestAnimationFrame(step);
    };
    raf = root.requestAnimationFrame(step);
    return { cancel() { dead = true; root.cancelAnimationFrame(raf); el.textContent = fmt(target); } };
  }

  if (root.ui && root.ui.hydrate) {
    root.ui.hydrate.register(scope => {
      scope.querySelectorAll('[data-countup]:not([data-countup-done])').forEach(el => {
        el.setAttribute('data-countup-done', '');
        run(el, el.getAttribute('data-countup'), { format: el.getAttribute('data-countup-format') || 'money' });
      });
    });
  }

  return { run, easeOutCubic, valueAt, roundTo };
});
