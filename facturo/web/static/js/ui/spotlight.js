// Pointer-tracked glow for `.spotlight` cards (styles in motion.css). One
// delegated listener writes --mx / --my (px, relative to the card) on the card
// under the pointer; without pointer movement the glow rests top-left.
// Disabled under prefers-reduced-motion.
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};
  let frame = 0, pending = null;

  function apply() {
    frame = 0;
    if (!pending) return;
    const { card, x, y } = pending;
    pending = null;
    const r = card.getBoundingClientRect();
    card.style.setProperty('--mx', `${Math.round(x - r.left)}px`);
    card.style.setProperty('--my', `${Math.round(y - r.top)}px`);
  }

  document.addEventListener('pointermove', e => {
    if (ui.reducedMotion() || e.pointerType === 'touch' || !(e.target instanceof Element)) return;
    const card = e.target.closest('.spotlight');
    if (!card) return;
    pending = { card, x: e.clientX, y: e.clientY };
    if (!frame) frame = requestAnimationFrame(apply);
  }, { passive: true });

  ui.spotlight = { apply };
})(window);
