// Sonner-style toasts: a stack of at most three, newest at the bottom, pauses on
// hover/focus, a progress bar that mirrors the remaining time, an optional
// action button (e.g. "Annuler"), a close button, swipe-to-dismiss, and a polite
// aria-live region (errors are announced assertively via role=alert).
//
//   ui.toast('Enregistré')                       // success
//   ui.toast('Oups', 'error')                    // .toast.toast-error
//   ui.toast('Supprimé', 'info', { action: { label: 'Annuler', onClick: undo } })
//   const t = ui.toast(...); t.dismiss();
// core.js keeps the global toast(msg, type) as a thin wrapper.
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};

  const MAX_VISIBLE = 3;
  const DEFAULT_MS = 4000;
  const ERROR_MS = 6500;
  const LEAVE_MS = 220;
  const SWIPE_PX = 70;
  const TYPES = ['success', 'error', 'info'];

  const toasts = [];
  let container = null;

  function ensureContainer() {
    if (container && container.isConnected) return container;
    container = document.querySelector('.toast-container');
    if (!container) {
      container = ui.h('div', { class: 'toast-container', role: 'region', 'aria-label': 'Notifications', 'aria-live': 'polite' });
      document.body.appendChild(container);
    }
    return container;
  }

  /** Hide everything but the newest MAX_VISIBLE toasts (they keep their timers). */
  function restack() {
    const live = toasts.filter(t => !t.leaving);
    live.forEach((t, i) => { t.el.hidden = i < live.length - MAX_VISIBLE; });
  }

  function dismiss(t, dx) {
    if (t.leaving) return;
    t.leaving = true;
    clearTimeout(t.timer);
    if (typeof dx === 'number') t.el.style.setProperty('--swipe-x', `${dx > 0 ? 120 : -120}%`);
    t.el.classList.add('is-leaving');
    const i = toasts.indexOf(t);
    if (i >= 0) toasts.splice(i, 1);
    restack();
    setTimeout(() => t.el.remove(), LEAVE_MS);
  }

  function arm(t) {
    clearTimeout(t.timer);
    if (!Number.isFinite(t.remaining)) return;
    t.startedAt = Date.now();
    t.timer = setTimeout(() => dismiss(t), t.remaining);
  }

  function pause(t) {
    if (t.leaving || t.paused || !Number.isFinite(t.remaining)) return;
    t.paused = true;
    clearTimeout(t.timer);
    t.remaining = Math.max(0, t.remaining - (Date.now() - t.startedAt));
    t.el.classList.add('is-paused');
  }

  function resume(t) {
    if (t.leaving || !t.paused) return;
    t.paused = false;
    t.el.classList.remove('is-paused');
    arm(t);
  }

  function bindSwipe(t) {
    let x0 = null;
    const el = t.el;
    el.addEventListener('pointerdown', e => {
      if (e.target.closest('button')) return;
      x0 = e.clientX;
      pause(t);
      el.setPointerCapture?.(e.pointerId);
    });
    el.addEventListener('pointermove', e => {
      if (x0 === null) return;
      el.style.transform = `translateX(${e.clientX - x0}px)`;
      el.style.opacity = String(Math.max(0.3, 1 - Math.abs(e.clientX - x0) / 240));
    });
    const end = e => {
      if (x0 === null) return;
      const dx = e.clientX - x0;
      x0 = null;
      el.style.transform = '';
      el.style.opacity = '';
      if (Math.abs(dx) > SWIPE_PX) dismiss(t, dx); else resume(t);
    };
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
  }

  /**
   * Show a toast.
   * @param {string} msg  plain text (never parsed as HTML)
   * @param {'success'|'error'|'info'} [type]
   * @param {{duration?: number, action?: {label: string, onClick?: Function}}} [opts]
   *   duration in ms; 0 keeps it until dismissed.
   * @returns {{dismiss: Function, el: HTMLElement}}
   */
  function show(msg, type = 'success', opts = {}) {
    const kind = TYPES.includes(type) ? type : 'info';
    const ms = opts.duration === 0 ? Infinity : (opts.duration || (kind === 'error' ? ERROR_MS : DEFAULT_MS));
    const { h } = ui;
    const el = h('div', { class: `toast toast-${kind}`, role: kind === 'error' ? 'alert' : 'status' },
      h('span', { class: 'toast-msg', text: String(msg) }));
    const t = { el, remaining: ms, paused: false, leaving: false, timer: null, startedAt: 0 };
    if (opts.action && opts.action.label) {
      el.append(h('button', {
        type: 'button', class: 'toast-action', text: opts.action.label,
        onclick() { dismiss(t); if (opts.action.onClick) opts.action.onClick(); },
      }));
    }
    el.append(h('button', { type: 'button', class: 'toast-close', 'aria-label': ui.i18n.t('toast.close'), html: ui.ico('x', { size: 'xs' }), onclick() { dismiss(t); } }));
    if (Number.isFinite(ms)) {
      el.append(h('span', { class: 'toast-progress', 'aria-hidden': 'true', style: `--toast-ms:${ms}ms` }));
    }
    el.addEventListener('mouseenter', () => pause(t));
    el.addEventListener('mouseleave', () => resume(t));
    el.addEventListener('focusin', () => pause(t));
    el.addEventListener('focusout', () => resume(t));
    bindSwipe(t);
    ensureContainer().appendChild(el);
    toasts.push(t);
    restack();
    arm(t);
    return { el, dismiss: () => dismiss(t) };
  }

  /** Dismiss every toast (used by tests and page teardown). */
  function clear() { [...toasts].forEach(t => dismiss(t)); }

  const toast = show;
  toast.show = show;
  toast.clear = clear;
  toast.success = (m, o) => show(m, 'success', o);
  toast.error = (m, o) => show(m, 'error', o);
  toast.info = (m, o) => show(m, 'info', o);
  toast.MAX_VISIBLE = MAX_VISIBLE;
  ui.toast = toast;
})(window);
