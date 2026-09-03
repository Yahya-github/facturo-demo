// Floating layers. `attach` keeps an element positioned next to an anchor
// (flip / shift / viewport clamp, follows scroll and resize). `layer.open` adds
// what popovers and menus share: appended to <body> above dialogs, closes on
// outside press, Escape (which must not also close the dialog underneath) and
// returns focus to the trigger.
//
//   const pos = ui.floating.attach(anchorEl | rect | () => rect, floatingEl, { side, align, offset });
//   pos.update(); pos.destroy();
//   const layer = ui.layer.open(el, anchor, { side, align, onClose, restoreFocus });
//   layer.close(); layer.update();
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};

  const rectOf = a => {
    if (typeof a === 'function') return rectOf(a());
    if (a instanceof Element) { const r = a.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; }
    return { x: a.x, y: a.y, width: a.width || 0, height: a.height || 0 };
  };

  /** Position `el` next to `anchor` and keep it there. */
  function attach(anchor, el, opts = {}) {
    el.style.position = 'fixed';
    el.style.left = '0px';
    el.style.top = '0px';
    function update() {
      const size = { width: el.offsetWidth, height: el.offsetHeight };
      const p = ui.position.computePosition({
        anchor: rectOf(anchor), floating: size,
        viewport: { width: document.documentElement.clientWidth, height: document.documentElement.clientHeight },
        side: opts.side, align: opts.align, offset: opts.offset, padding: opts.padding, flip: opts.flip,
      });
      el.style.left = `${p.x}px`;
      el.style.top = `${p.y}px`;
      el.dataset.side = p.side;
      if (opts.fitHeight) el.style.maxHeight = `${p.maxHeight}px`;
    }
    const on = () => update();
    window.addEventListener('resize', on);
    window.addEventListener('scroll', on, true);
    update();
    return { update, destroy() { window.removeEventListener('resize', on); window.removeEventListener('scroll', on, true); } };
  }

  const stack = [];

  function open(el, anchor, opts = {}) {
    el.setAttribute('data-ui-layer', '');
    el.style.visibility = 'hidden';
    document.body.appendChild(el);
    const pos = attach(anchor, el, opts);
    el.style.visibility = '';
    const layer = { el, anchor, opts, update: pos.update, closed: false };

    const onPointer = e => {
      if (el.contains(e.target)) return;
      if (anchor instanceof Element && anchor.contains(e.target)) return;
      if (stack[stack.length - 1] !== layer) return;
      close(false);
    };
    const onKey = e => {
      if (e.key !== 'Escape' || stack[stack.length - 1] !== layer || opts.escape === false) return;
      e.preventDefault();
      e.stopPropagation();
      close(true);
    };
    document.addEventListener('pointerdown', onPointer, true);
    document.addEventListener('keydown', onKey, true);

    function close(restore = true) {
      if (layer.closed) return;
      layer.closed = true;
      pos.destroy();
      document.removeEventListener('pointerdown', onPointer, true);
      document.removeEventListener('keydown', onKey, true);
      const i = stack.indexOf(layer);
      if (i >= 0) stack.splice(i, 1);
      const hadFocus = el.contains(document.activeElement);
      el.remove();
      const back = opts.restoreTo || (anchor instanceof Element ? anchor : null);
      if (restore && opts.restoreFocus !== false && (hadFocus || restore === 'force') && back && back.isConnected) back.focus();
      if (opts.onClose) opts.onClose(restore);
    }
    layer.close = close;
    stack.push(layer);
    return layer;
  }

  /** Close every open layer (page changes, dialogs opening). */
  function closeAll(restore = false) { [...stack].reverse().forEach(l => l.close(restore)); }

  ui.hydrate && ui.hydrate.register(() => {
    [...stack].forEach(l => { if (l.anchor instanceof Element && !l.anchor.isConnected) l.close(false); });
  });

  ui.floating = { attach, rectOf };
  ui.layer = { open, closeAll, get top() { return stack[stack.length - 1] || null; } };
})(window);
