// Collapsible sidebar.
//   Desktop (>= 768px): icon-only rail. <html data-sidebar="collapsed"> drives the CSS,
//     labels move into tooltips, the choice is saved in localStorage ('facturo-sidebar').
//   Mobile (< 768px): the sidebar is hidden; a slim top bar opens the very same <aside>
//     inside a left Sheet (moved, not cloned, so ids and .nav-btn[data-page] stay unique).
// Ctrl/Cmd+B toggles either mode; any [data-sidebar-toggle] button does too.
//
//   ui.sidebar.toggle() / collapse() / expand() / isCollapsed()
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};

  const KEY = 'facturo-sidebar';
  const mobileQuery = root.matchMedia('(max-width: 767.98px)');
  const html = document.documentElement;
  let sheet = null;
  let placeholder = null;

  const aside = () => document.getElementById('sidebar');
  const isCollapsed = () => html.getAttribute('data-sidebar') === 'collapsed';
  const isMobile = () => mobileQuery.matches;

  /** Labels become tooltips while the rail is collapsed (and only then). */
  function syncTips() {
    const rail = isCollapsed() && !isMobile();
    document.querySelectorAll('#sidebar .nav-btn, #sidebar .sidebar-search').forEach(btn => {
      const label = btn.querySelector('.nav-label');
      const text = label ? label.textContent.trim().replace(/…$/, '') : '';
      if (rail && text) {
        btn.setAttribute('data-tip', text);
        btn.setAttribute('data-tip-side', 'right');
        if (btn.classList.contains('sidebar-search')) btn.setAttribute('data-kbd', 'Ctrl+K');
        if (!btn.hasAttribute('aria-label')) { btn.setAttribute('aria-label', text); btn.dataset.tipLabel = '1'; }
      } else {
        btn.removeAttribute('data-tip');
        btn.removeAttribute('data-tip-side');
        if (btn.classList.contains('sidebar-search')) btn.removeAttribute('data-kbd');
        if (btn.dataset.tipLabel) { btn.removeAttribute('aria-label'); delete btn.dataset.tipLabel; }
      }
    });
    const t = document.getElementById('sidebar-toggle');
    if (t) {
      const label = ui.i18n.t(isCollapsed() ? 'sidebar.expand' : 'sidebar.collapse');
      t.setAttribute('data-tip', label);
      t.setAttribute('aria-label', label);
      t.setAttribute('aria-expanded', isCollapsed() ? 'false' : 'true');
    }
  }

  function setCollapsed(value, persist = true) {
    if (value) html.setAttribute('data-sidebar', 'collapsed'); else html.removeAttribute('data-sidebar');
    if (persist) ui.store.set(KEY, value ? 'collapsed' : 'expanded');
    syncTips();
    if (ui.tooltip) ui.tooltip.hide();
  }

  // ── mobile sheet ──
  function openSheet() {
    const el = aside();
    if (sheet || !el) return;
    const opener = document.getElementById('sidebar-open');
    placeholder = document.createComment('sidebar');
    el.replaceWith(placeholder);
    const modal = ui.h('div', { class: 'modal sheet sheet-nav' }, el);
    const overlay = ui.h('div', { class: 'modal-overlay sheet-overlay sheet-left', 'aria-label': 'Menu' }, modal);
    sheet = overlay;
    overlay.addEventListener('click', e => { if (e.target.closest('.nav-btn')) closeSheet(); });
    ui.dialog.open(overlay, {
      initialFocus: '.nav-btn.active',
      onClose() {
        if (placeholder && placeholder.parentNode) placeholder.replaceWith(el);
        placeholder = null;
        sheet = null;
        syncTips();
        if (opener && opener.isConnected && isMobile()) opener.focus();
      },
    });
    if (opener) opener.setAttribute('aria-expanded', 'true');
  }

  function closeSheet() {
    if (sheet) ui.dialog.close(sheet);
    const opener = document.getElementById('sidebar-open');
    if (opener) opener.setAttribute('aria-expanded', 'false');
  }

  function toggle() {
    if (isMobile()) { if (sheet) closeSheet(); else openSheet(); return; }
    setCollapsed(!isCollapsed());
  }

  document.addEventListener('click', e => {
    const b = e.target instanceof Element && e.target.closest('[data-sidebar-toggle]');
    if (b) toggle();
  });
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.key === 'b' || e.key === 'B')) {
      e.preventDefault();
      toggle();
    }
  });
  mobileQuery.addEventListener('change', () => { if (!isMobile() && sheet) closeSheet(); syncTips(); });

  const opener = document.getElementById('sidebar-open');
  if (opener) opener.setAttribute('aria-expanded', 'false');
  setCollapsed(ui.store.get(KEY) === 'collapsed', false);

  // index.html hydrates this button with the "collapse" text on every pass; run
  // after that pass (DOMContentLoaded order) so the collapsed rail keeps "expand".
  document.addEventListener('DOMContentLoaded', () => ui.hydrate.register(syncTips));

  ui.sidebar = { toggle, collapse: () => setCollapsed(true), expand: () => setCollapsed(false), isCollapsed, openSheet, closeSheet };
})(window);
