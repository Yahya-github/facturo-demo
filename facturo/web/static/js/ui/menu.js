// DropdownMenu and ContextMenu (role=menu) with a roving tabindex.
//
//   items: [{ label, icon?, kbd?, onSelect?, disabled?, destructive?, checked?, submenu?: items },
//           { separator: true }, { heading: 'Actions' }]
//
//   ui.menu.attach(triggerBtn, items | () => items)      // click / Enter / Space / ArrowDown
//   ui.menu.open(anchor, items, { keyboard: true })
//   ui.contextMenu.attach(container, '[data-row]', target => items)  // right-click, Shift+F10, Menu key
//
// Keys: Up/Down/Home/End move (wrapping), letters jump (typeahead, accents
// ignored), Enter/Space select, Right opens a submenu, Left closes it,
// Escape closes and returns focus to the trigger, Tab closes.
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};
  const TYPE_RESET_MS = 700;

  function build(items) {
    const { h } = ui;
    const el = h('div', { class: 'popover menu', role: 'menu', 'aria-orientation': 'vertical', tabindex: '-1' });
    const rows = [];
    items.forEach(it => {
      if (it.separator) { el.append(h('div', { class: 'menu-sep', role: 'separator' })); return; }
      if (it.heading) { el.append(h('div', { class: 'menu-label', role: 'presentation', text: it.heading })); return; }
      const role = it.checked === undefined ? 'menuitem' : 'menuitemcheckbox';
      const row = h('button', {
        type: 'button', class: `menu-item${it.destructive ? ' menu-item-destructive' : ''}`, role, tabindex: '-1',
        disabled: false, 'aria-disabled': it.disabled ? 'true' : null,
        'aria-checked': it.checked === undefined ? null : String(!!it.checked),
        'aria-haspopup': it.submenu ? 'menu' : null, 'aria-expanded': it.submenu ? 'false' : null,
      },
      h('span', { class: 'menu-item-icon', html: it.icon ? ui.ico(it.icon, { size: 'sm' }) : (it.checked ? ui.ico('check', { size: 'sm' }) : '') }),
      h('span', { class: 'menu-item-label', text: it.label }),
      it.kbd && h('span', { class: 'menu-item-kbd' }, it.kbd.split('+').map(k => h('kbd', { text: k.trim() }))),
      it.submenu && h('span', { class: 'menu-item-chevron', html: ui.ico('chevron-right', { size: 'xs' }) }));
      row._item = it;
      rows.push(row);
      el.append(row);
    });
    return { el, rows };
  }

  /** Open a menu. Returns the layer ({ close }) — closing it also closes submenus. */
  function open(anchor, items, o = {}) {
    ui.layer.closeAll(false);
    return openLayer(anchor, items, o, null);
  }

  function openLayer(anchor, items, o, parent) {
    const { el, rows } = build(items);
    let active = -1, typed = '', typedT = null;
    let child = null;

    function focusRow(i) {
      active = i;
      rows.forEach((r, n) => { r.tabIndex = n === i ? 0 : -1; r.classList.toggle('is-active', n === i); });
      if (rows[i]) rows[i].focus({ preventScroll: false });
    }
    const layer = ui.layer.open(el, anchor, {
      side: parent ? 'right' : (o.side || 'bottom'), align: parent ? 'start' : (o.align || 'start'),
      offset: parent ? 2 : (o.offset ?? 4), fitHeight: true, restoreTo: o.restoreTo,
      onClose(restore) { if (child) child.close(false); if (o.onClose) o.onClose(restore); },
    });

    function choose(row) {
      const it = row._item;
      if (it.disabled) return;
      if (it.submenu) { openChild(row, true); return; }
      layer.close(true);
      if (parent) parent.close(true);
      if (it.onSelect) it.onSelect(it);
    }
    function openChild(row, keyboard) {
      if (child) child.close(false);
      row.setAttribute('aria-expanded', 'true');
      child = openLayer(row, row._item.submenu, Object.assign({}, o, { keyboard }), layer);
      child.parentRow = row;
    }

    el.addEventListener('keydown', e => {
      const k = e.key;
      if (k === 'Tab') { layer.close(false); if (parent) parent.close(false); return; }
      if (k === 'ArrowLeft' && parent) { e.preventDefault(); e.stopPropagation(); layer.close(true); return; }
      if (k === 'ArrowRight' && rows[active] && rows[active]._item.submenu) { e.preventDefault(); openChild(rows[active], true); return; }
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(k)) {
        e.preventDefault();
        focusRow(ui.keys.nextIndex(rows.length, active, k));
      } else if (k === 'Enter' || k === ' ') {
        e.preventDefault();
        if (rows[active]) choose(rows[active]);
      } else if (k.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        typed += k;
        clearTimeout(typedT);
        typedT = setTimeout(() => { typed = ''; }, TYPE_RESET_MS);
        const i = ui.keys.typeahead(rows.map(r => r._item.label), typed, active);
        if (i >= 0) focusRow(i);
      }
    });
    rows.forEach((row, i) => {
      row.addEventListener('click', () => choose(row));
      row.addEventListener('mouseenter', () => {
        focusRow(i);
        if (child && child.parentRow !== row) { child.close(false); child.parentRow.setAttribute('aria-expanded', 'false'); child = null; }
        if (row._item.submenu && !row._item.disabled) openChild(row, false);
      });
    });
    const firstEnabled = rows.findIndex(r => !r._item.disabled);
    if (o.keyboard || parent) focusRow(firstEnabled >= 0 ? firstEnabled : 0);
    else el.focus({ preventScroll: true });
    return layer;
  }

  /** Make `trigger` a dropdown button. `items` may be an array or a function returning one. */
  function attach(trigger, items, o = {}) {
    trigger.setAttribute('aria-haspopup', 'menu');
    trigger.setAttribute('aria-expanded', 'false');
    let layer = null;
    function toggle(keyboard) {
      if (layer && !layer.closed) { layer.close(true); return; }
      const list = typeof items === 'function' ? items() : items;
      trigger.setAttribute('aria-expanded', 'true');
      layer = open(trigger, list, Object.assign({}, o, {
        keyboard,
        onClose() { trigger.setAttribute('aria-expanded', 'false'); layer = null; },
      }));
    }
    trigger.addEventListener('click', e => toggle(e.detail === 0));
    trigger.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') { e.preventDefault(); if (!layer) toggle(true); }
    });
    return { toggle };
  }

  // ── Context menu ──
  /**
   * Right-click (or Shift+F10 / the Menu key on a focused target) opens `itemsFor(target)`
   * at the pointer / the element. Return null/[] from itemsFor to keep the browser menu.
   */
  function contextAttach(container, selector, itemsFor) {
    const hit = e => (e.target instanceof Element ? e.target.closest(selector) : null);
    container.addEventListener('contextmenu', e => {
      const t = hit(e);
      if (!t || !container.contains(t)) return;
      const items = itemsFor(t);
      if (!items || !items.length) return;
      e.preventDefault();
      open({ x: e.clientX, y: e.clientY, width: 0, height: 0 }, items, { side: 'bottom', align: 'start', offset: 0, keyboard: e.detail === 0 && e.button === 0, restoreTo: t.matches('[tabindex], a, button, input') ? t : null });
    });
    container.addEventListener('keydown', e => {
      const isMenuKey = e.key === 'ContextMenu' || (e.key === 'F10' && e.shiftKey);
      if (!isMenuKey) return;
      const t = hit(e);
      if (!t) return;
      const items = itemsFor(t);
      if (!items || !items.length) return;
      e.preventDefault();
      open(t, items, { side: 'bottom', align: 'start', keyboard: true, restoreTo: t });
    });
  }

  ui.menu = { open, attach };
  ui.contextMenu = { attach: contextAttach };
})(window);
