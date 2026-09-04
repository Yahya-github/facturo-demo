// Popover (click-triggered panel) and HoverCard (hover/focus preview), both on
// the shared positioner in floating.js.
//
//   const p = ui.popover.open(anchorEl, { content: nodeOrTrustedHtml, side: 'bottom', align: 'start' });
//   ui.popover.toggle(anchorEl, opts);            // second call closes it
//   ui.popover.attach(btn, () => ({ content }));  // click / Enter opens; aria-expanded kept in sync
//   ui.hoverCard.attach(container, '.client-name', target => nodeOrHtml | null);
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};
  const openFor = new WeakMap();

  function toNode(c) {
    if (c instanceof Node) return c;
    const t = document.createElement('template');
    t.innerHTML = String(c ?? '');
    return t.content;
  }

  /**
   * Open a popover next to `anchor`. Focus moves inside (first control, else the panel)
   * and returns to the anchor on Escape or close. Outside press closes it.
   * @param {Element|object} anchor element or {x,y,width,height}
   * @param {{content: Node|string, side?: string, align?: string, offset?: number,
   *   label?: string, className?: string, onClose?: Function}} o content strings are trusted HTML
   */
  function open(anchor, o) {
    if (anchor instanceof Element && openFor.has(anchor)) return openFor.get(anchor);
    ui.layer.closeAll(false);
    const el = ui.h('div', {
      class: `popover popover-panel${o.className ? ` ${o.className}` : ''}`,
      role: 'dialog', tabindex: '-1', 'aria-label': o.label || null,
    }, toNode(o.content));
    const layer = ui.layer.open(el, anchor, {
      side: o.side || 'bottom', align: o.align || 'start', offset: o.offset ?? 6, fitHeight: true,
      onClose(restore) {
        if (anchor instanceof Element) { openFor.delete(anchor); anchor.setAttribute('aria-expanded', 'false'); }
        if (o.onClose) o.onClose(restore);
      },
    });
    if (anchor instanceof Element) { openFor.set(anchor, layer); anchor.setAttribute('aria-expanded', 'true'); }
    (ui.focusable(el)[0] || el).focus({ preventScroll: true });
    return layer;
  }

  function toggle(anchor, o) {
    const existing = anchor instanceof Element && openFor.get(anchor);
    if (existing) { existing.close(true); return null; }
    return open(anchor, o);
  }

  /** Wire a trigger button; `factory()` returns the open() options each time. */
  function attach(trigger, factory) {
    trigger.setAttribute('aria-haspopup', 'dialog');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.addEventListener('click', () => toggle(trigger, factory()));
  }

  // ── HoverCard ──
  const OPEN_MS = 450, CLOSE_MS = 180;

  /**
   * Preview card for elements matching `selector` inside `container`.
   * Opens on hover (after a delay) or keyboard focus; stays open while the
   * pointer is over the card.
   */
  function hoverAttach(container, selector, contentFor, o = {}) {
    let layer = null, target = null, openT = null, closeT = null;
    const cancel = () => { clearTimeout(openT); clearTimeout(closeT); };
    const close = () => { cancel(); if (layer) { layer.close(false); layer = null; target = null; } };
    function show(el) {
      const c = contentFor(el);
      if (c === null || c === undefined) return;
      close();
      const card = ui.h('div', { class: 'popover hovercard', role: 'group' }, toNode(c));
      card.addEventListener('mouseenter', () => clearTimeout(closeT));
      card.addEventListener('mouseleave', () => { closeT = setTimeout(close, CLOSE_MS); });
      target = el;
      layer = ui.layer.open(card, el, { side: o.side || 'bottom', align: o.align || 'start', offset: 8, restoreFocus: false, onClose() { layer = null; } });
    }
    const hit = e => (e.target instanceof Element ? e.target.closest(selector) : null);
    container.addEventListener('mouseover', e => {
      const el = hit(e);
      if (!el || el === target || el.contains(e.relatedTarget)) { if (el === target) clearTimeout(closeT); return; }
      cancel();
      openT = setTimeout(() => show(el), OPEN_MS);
    });
    container.addEventListener('mouseout', e => {
      const el = hit(e);
      if (!el || el.contains(e.relatedTarget)) return;
      clearTimeout(openT);
      closeT = setTimeout(close, CLOSE_MS);
    });
    container.addEventListener('focusin', e => { const el = hit(e); if (el) { cancel(); show(el); } });
    container.addEventListener('focusout', e => { if (hit(e)) closeT = setTimeout(close, CLOSE_MS); });
    return { close };
  }

  ui.popover = { open, toggle, attach };
  ui.hoverCard = { attach: hoverAttach };
})(window);
