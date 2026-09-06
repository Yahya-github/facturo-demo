// Tooltip for every element carrying data-tip. One shared bubble, delegated
// listeners (works for markup rendered later), shown on hover after 300ms and on
// keyboard focus at once, hidden on leave / blur / Escape / press / scroll.
//
//   <button data-tip="Copier" data-kbd="Ctrl+C" data-tip-side="right" aria-label="Copier">
//
// A hydrate pass also turns native `title="..."` into data-tip (the browser's
// own tooltip is slow and unstyled) and keeps an accessible name for
// icon-only controls via aria-label.
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};

  const HOVER_MS = 300;
  const WARM_MS = 500;      // after one tooltip closes, the next opens instantly
  const NAMELESS_ROLE_SKIP = /^(BUTTON|A|INPUT|SELECT|TEXTAREA|SUMMARY)$/;

  let bubble = null, current = null, timer = null, pos = null, lastHide = 0, pointerInput = false;

  function ensureBubble() {
    if (!bubble) {
      bubble = ui.h('div', { class: 'tooltip', role: 'tooltip', id: 'ui-tooltip', hidden: true });
      document.body.appendChild(bubble);
    }
    return bubble;
  }

  function fill(el) {
    const b = ensureBubble();
    b.textContent = '';
    b.append(ui.h('span', { text: el.getAttribute('data-tip') }));
    const kbd = el.getAttribute('data-kbd');
    if (kbd) b.append(ui.h('span', { class: 'tooltip-kbd' }, kbd.split('+').map(k => ui.h('kbd', { text: k.trim() }))));
  }

  function show(el) {
    if (!el.isConnected || !el.getAttribute('data-tip')) return;
    current = el;
    fill(el);
    const b = ensureBubble();
    b.hidden = false;
    el.setAttribute('aria-describedby', 'ui-tooltip');
    if (pos) pos.destroy();
    pos = ui.floating.attach(el, b, { side: el.getAttribute('data-tip-side') || 'top', align: 'center', offset: 8 });
  }

  function hide() {
    clearTimeout(timer);
    timer = null;
    if (!current) return;
    current.removeAttribute('aria-describedby');
    if (bubble) bubble.hidden = true;
    if (pos) { pos.destroy(); pos = null; }
    current = null;
    lastHide = Date.now();
  }

  function schedule(el, delay) {
    if (el === current) return;
    hide();
    const wait = Date.now() - lastHide < WARM_MS ? 0 : delay;
    if (wait === 0) show(el);
    else timer = setTimeout(() => show(el), wait);
  }

  const tipOf = t => (t instanceof Element ? t.closest('[data-tip]') : null);

  document.addEventListener('mouseover', e => {
    const el = tipOf(e.target);
    if (el && !el.contains(e.relatedTarget)) schedule(el, HOVER_MS);
  });
  document.addEventListener('mouseout', e => {
    const el = tipOf(e.target);
    if (el && !el.contains(e.relatedTarget)) hide();
  });
  document.addEventListener('focusin', e => {
    const el = tipOf(e.target);
    if (el && !pointerInput) schedule(el, 0);
  });
  document.addEventListener('focusout', e => { if (tipOf(e.target)) hide(); });
  document.addEventListener('pointerdown', () => { pointerInput = true; hide(); }, true);
  document.addEventListener('keydown', e => {
    pointerInput = false;
    if (e.key === 'Escape' && current) hide();
  }, true);
  window.addEventListener('scroll', () => { if (current && !current.isConnected) hide(); }, true);

  // title -> data-tip (+ aria-label for icon-only controls).
  function hydrateTitles(scope) {
    scope.querySelectorAll('[title]').forEach(el => {
      if (el.tagName === 'IFRAME' || el.tagName === 'ABBR' || el instanceof SVGElement) return;
      const text = el.getAttribute('title');
      el.removeAttribute('title');
      if (!text) return;
      el.setAttribute('data-tip', text);
      const iconOnly = !el.textContent.trim();
      if (iconOnly && !el.hasAttribute('aria-label') && !el.hasAttribute('aria-labelledby')) {
        el.setAttribute('aria-label', text);
        if (!el.hasAttribute('role') && !NAMELESS_ROLE_SKIP.test(el.tagName)) el.setAttribute('role', 'img');
      }
    });
    // A tooltip whose anchor was re-rendered must not linger.
    if (current && !current.isConnected) hide();
  }
  ui.hydrate.register(hydrateTitles);

  ui.tooltip = { show, hide, hydrateTitles };
})(window);
