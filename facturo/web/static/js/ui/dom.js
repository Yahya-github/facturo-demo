// Tiny DOM helpers shared by every ui/ primitive. Everything hangs off the one
// global `ui` namespace; nothing else is added to window.
//
//   ui.h('button', { class: 'btn', onclick: fn, 'aria-label': 'Fermer' }, 'Texte', node)
//   ui.uid('menu')            -> 'menu-3'
//   ui.focusable(root)        -> visible, enabled tab stops inside root
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};
  let seq = 0;

  const FOCUSABLE = 'button, select, input, textarea, a[href], [tabindex]:not([tabindex="-1"])';

  /** Unique DOM id with a readable prefix. */
  function uid(prefix) { return `${prefix || 'ui'}-${++seq}`; }

  /**
   * Build an element. Props: `class`, `text` (textContent), `html` (TRUSTED markup
   * only, e.g. an icon), `on<event>` handlers, `hidden`/`disabled` booleans, and
   * anything else as an attribute (null/false skips it). Children may be nodes,
   * strings (always text, never markup) or arrays of these.
   */
  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k === 'html') el.innerHTML = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else if (k === 'hidden' || k === 'disabled') el[k] = !!v;
      else el.setAttribute(k, v === true ? '' : String(v));
    }
    append(el, kids);
    return el;
  }

  function append(el, kids) {
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }

  /** Visible, enabled tab stops inside `root`. */
  function focusable(rootEl) {
    return [...rootEl.querySelectorAll(FOCUSABLE)].filter(el => !el.disabled && el.offsetParent !== null);
  }

  /** Icon markup from icons.js, or '' when the registry is missing. */
  function ico(name, opts) {
    return typeof root.icon === 'function' ? root.icon(name, opts) : '';
  }

  /** True when the user asked for less motion. */
  function reducedMotion() {
    return !!(root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  /** localStorage that never throws. */
  const store = {
    get(key, fallback = null) { try { const v = root.localStorage.getItem(key); return v === null ? fallback : v; } catch (e) { return fallback; } },
    set(key, value) { try { root.localStorage.setItem(key, value); return true; } catch (e) { return false; } },
  };

  Object.assign(ui, { uid, h, append, focusable, ico, reducedMotion, store, FOCUSABLE });
})(window);
