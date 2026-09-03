// Dialog, AlertDialog, PromptDialog and Sheet on one focus-trapping core.
//
// ui.dialog.open(overlay, opts) / close(overlay, restoreFocus) / closeAll() are the
// original openModal/closeModal (core.js keeps global wrappers), so every
// hand-built `.modal-overlay` keeps working unchanged: role=dialog, aria-modal,
// labelled by its heading, Escape closes the topmost, Tab stays inside, focus
// returns to the opener.
//
// Higher level, all returning a controller or a Promise:
//   ui.dialog.show({ title, description, body, footer, size })  -> { overlay, close, closed }
//   ui.alertDialog({ title, description, confirmLabel, destructive }) -> Promise<boolean>
//   ui.promptDialog({ title, label, value, confirmLabel })            -> Promise<string|null>
//   ui.sheet({ side: 'left'|'right'|'bottom', title, body })          -> controller
// `body` / `footer` may be a Node or a string of TRUSTED html (escape user data).
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};
  let titleSeq = 0;

  const all = () => [...document.querySelectorAll('.modal-overlay')];

  /**
   * Attach a built overlay to the page as an accessible modal.
   * @param {HTMLElement} overlay  the .modal-overlay element (not yet in the DOM)
   * @param {{initialFocus?: string, role?: string, onClose?: Function}} [opts]
   *   initialFocus: selector to focus first (default: first focusable in the modal)
   *   role: 'dialog' (default) or 'alertdialog'
   *   onClose(restoreFocus, trigger): replaces the default focus restore
   */
  function open(overlay, opts = {}) {
    const heading = overlay.querySelector('.modal-header h3, .modal-header h2');
    if (heading && !heading.id) heading.id = `modal-title-${++titleSeq}`;
    overlay.setAttribute('role', opts.role || 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    if (heading) overlay.setAttribute('aria-labelledby', heading.id);
    overlay.querySelectorAll('.modal-close').forEach(b => { if (!b.getAttribute('aria-label')) b.setAttribute('aria-label', 'Fermer'); });

    const trigger = document.activeElement;
    const onKeydown = e => {
      if (!overlay.isConnected) { document.removeEventListener('keydown', onKeydown); return; }
      // Only the topmost modal reacts.
      const list = all();
      if (list[list.length - 1] !== overlay) return;
      if (e.key === 'Escape') { if (e.defaultPrevented) return; e.preventDefault(); close(overlay); return; }
      if (e.key !== 'Tab') return;
      // A popover/menu opened from inside the dialog owns its own Tab handling.
      if (document.activeElement && document.activeElement.closest('[data-ui-layer]')) return;
      const items = ui.focusable(overlay);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (!overlay.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
      else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    overlay._modal = { trigger, onKeydown, onClose: opts.onClose };
    document.addEventListener('keydown', onKeydown);
    overlay.addEventListener('click', e => { if (e.target === overlay) close(overlay); });
    document.body.appendChild(overlay);
    const target = (opts.initialFocus && overlay.querySelector(opts.initialFocus))
      || [...overlay.querySelectorAll(ui.FOCUSABLE)].find(el => !el.disabled);
    if (target) target.focus();
  }

  /** Close a modal opened with open(); restores focus to its opener. */
  function close(overlay, restoreFocus = true) {
    if (!overlay) return;
    const m = overlay._modal;
    if (m) document.removeEventListener('keydown', m.onKeydown);
    overlay.remove();
    if (!m) return;
    overlay._modal = null;
    if (m.onClose) m.onClose(restoreFocus, m.trigger);
    else if (restoreFocus && m.trigger && m.trigger.isConnected) m.trigger.focus();
  }

  /** Close every open modal (e.g. before navigating away). */
  function closeAll() {
    all().forEach(o => close(o, false));
  }

  function content(node) {
    if (node === null || node === undefined) return null;
    if (node instanceof Node) return node;
    const t = document.createElement('template');
    t.innerHTML = String(node);
    return t.content;
  }

  /**
   * Build and open a dialog. Resolve `closed` with whatever was passed to close(value).
   * @param {{title: string, description?: string, body?: Node|string, footer?: Node|string,
   *   size?: 'sm'|'md'|'lg', side?: string, role?: string, initialFocus?: string,
   *   dismissible?: boolean, className?: string, onClose?: Function}} o
   */
  function show(o) {
    const { h } = ui;
    let settle;
    const closed = new Promise(res => { settle = res; });
    const dismissible = o.dismissible !== false;
    const header = h('div', { class: 'modal-header' },
      h('h3', { text: o.title || '' }),
      dismissible && h('button', { type: 'button', class: 'modal-close', 'aria-label': 'Fermer', html: ui.ico('x', { size: 'sm' }) }));
    const modal = h('div', { class: `modal${o.side ? ' sheet' : ''}${o.size ? ` modal-${o.size}` : ''}${o.className ? ` ${o.className}` : ''}` },
      header,
      o.description && h('p', { class: 'modal-desc', id: ui.uid('dlg-desc'), text: o.description }),
      o.body !== undefined && h('div', { class: 'modal-body' }, content(o.body)),
      o.footer !== undefined && h('div', { class: 'modal-footer' }, content(o.footer)));
    const overlay = h('div', { class: `modal-overlay${o.side ? ` sheet-overlay sheet-${o.side}` : ''}` }, modal);
    const desc = modal.querySelector('.modal-desc');
    if (desc) overlay.setAttribute('aria-describedby', desc.id);

    let value;
    const ctl = { overlay, modal, closed, close(v) { value = v; close(overlay); } };
    const closeBtn = header.querySelector('.modal-close');
    if (closeBtn) closeBtn.addEventListener('click', () => ctl.close(undefined));
    open(overlay, {
      role: o.role,
      initialFocus: o.initialFocus,
      onClose(restoreFocus, trigger) {
        if (restoreFocus && trigger && trigger.isConnected) trigger.focus();
        if (o.onClose) o.onClose(value);
        settle(value);
      },
    });
    return ctl;
  }

  /** Right/left/bottom panel on the same overlay + focus trap. */
  function sheet(o) {
    return show(Object.assign({ side: 'right' }, o));
  }

  function actionButtons(cancelLabel, confirmLabel, destructive) {
    const { h } = ui;
    const cancel = h('button', { type: 'button', class: 'btn btn-ghost', 'data-dialog-cancel': '', text: cancelLabel });
    const confirm = h('button', { type: 'button', class: `btn ${destructive ? 'btn-danger' : 'btn-primary'}`, 'data-dialog-confirm': '', text: confirmLabel });
    return { cancel, confirm };
  }

  /**
   * Confirmation dialog (role=alertdialog). Resolves true only on confirm; Escape,
   * the scrim and Annuler resolve false. Destructive dialogs focus Annuler first.
   * @returns {Promise<boolean>}
   */
  function alertDialog(o) {
    const { cancel, confirm } = actionButtons(o.cancelLabel || 'Annuler', o.confirmLabel || 'Confirmer', !!o.destructive);
    const footer = ui.h('div', { class: 'dialog-actions' }, cancel, confirm);
    const ctl = show({
      title: o.title || 'Confirmer',
      body: ui.h('p', { class: 'confirm-text', text: o.description || '' }),
      footer, role: 'alertdialog', size: 'sm', dismissible: false,
      initialFocus: o.destructive ? '[data-dialog-cancel]' : '[data-dialog-confirm]',
    });
    if (o.destructive) ctl.modal.classList.add('modal-destructive');
    cancel.addEventListener('click', () => ctl.close(false));
    confirm.addEventListener('click', () => ctl.close(true));
    ctl.overlay.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.target.closest('button')) { e.preventDefault(); ctl.close(true); }
    });
    return ctl.closed.then(v => v === true);
  }

  /**
   * Single-field prompt. Resolves the trimmed text, or null when cancelled.
   * Enter submits, Escape cancels; an empty value keeps the confirm button disabled.
   * @returns {Promise<string|null>}
   */
  function promptDialog(o) {
    const { h } = ui;
    const id = ui.uid('prompt');
    const input = h('input', { class: 'form-input', id, type: 'text', autocomplete: 'off', placeholder: o.placeholder || '' });
    input.value = o.value || '';
    const { cancel, confirm } = actionButtons(o.cancelLabel || 'Annuler', o.confirmLabel || 'Enregistrer', false);
    const sync = () => { confirm.disabled = !o.allowEmpty && !input.value.trim(); };
    sync();
    const ctl = show({
      title: o.title || 'Saisir une valeur',
      description: o.description,
      body: h('div', { class: 'form-group' }, o.label && h('label', { class: 'form-label', for: id, text: o.label }), input),
      footer: h('div', { class: 'dialog-actions' }, cancel, confirm),
      size: 'sm', initialFocus: `#${id}`,
    });
    input.select();
    input.addEventListener('input', sync);
    input.addEventListener('keydown', e => { if (e.key === 'Enter' && !confirm.disabled) { e.preventDefault(); ctl.close(input.value.trim()); } });
    cancel.addEventListener('click', () => ctl.close(null));
    confirm.addEventListener('click', () => ctl.close(input.value.trim()));
    return ctl.closed.then(v => (typeof v === 'string' ? v : null));
  }

  ui.dialog = { open, close, closeAll, show, sheet };
  ui.sheet = sheet;
  ui.alertDialog = alertDialog;
  ui.promptDialog = promptDialog;
})(window);
