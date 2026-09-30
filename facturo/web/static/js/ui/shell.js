// App shell wiring: workspace switcher (initials tile + dropdown menu), the
// header breadcrumb built from state.page / state.editingId, the theme button
// and the update bell that mirrors #update-dot.
//
//   updateShell()   global, called by render() in core.js on every page render
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};

  // The breadcrumb and the workspace menu are the only copy this file owns, and
  // both read through the active language rather than carrying their own.
  const tr = key => (ui.i18n ? ui.i18n.t(key) : key);

  const PAGE_KEYS = {
    home: 'nav.home', clients: 'nav.clients', facture: 'nav.facture', history: 'nav.history',
    scans: 'nav.scans', payments: 'nav.payments', settings: 'nav.settings',
  };

  const esc = s => (typeof root.esc === 'function' ? root.esc(s) : String(s));

  function company() {
    const meta = document.querySelector('meta[name="company-name"]');
    return meta ? (meta.getAttribute('content') || '').trim() : '';
  }

  /** 'Demo Transport Inc.' -> 'DT' (first letters of the first two significant words). */
  function initials(name) {
    const words = String(name || '').split(/[\s\-_.]+/).filter(w => /[\p{L}\p{N}]/u.test(w));
    const stop = /^(inc|ltée|ltee|ltd|llc|sarl|sa|cie|enr|&)$/i;
    const main = words.filter(w => !stop.test(w));
    const pick = (main.length ? main : words).slice(0, 2);
    return pick.map(w => [...w][0].toUpperCase()).join('') || 'F';
  }

  /** [{label, page?}] trail for the current state; the last item is the current page. */
  function trail() {
    // `state` is a top-level const in core.js (not a window property).
    const st = typeof state !== 'undefined' ? state : null;
    const page = st ? st.page : 'home';
    const items = [{ label: tr(PAGE_KEYS.home), page: 'home' }];
    if (page === 'home') return items;
    if (page === 'facture' && st.editingId != null) {
      const f = (st.factures || []).find(x => x.id === st.editingId);
      items.push({ label: tr(PAGE_KEYS.history), page: 'history' });
      items.push({ label: f && f.numero ? `Facture ${f.numero}` : tr('nav.facture') });
      return items;
    }
    items.push({ label: tr(PAGE_KEYS[page] || '') || page });
    return items;
  }

  function renderBreadcrumb() {
    const nav = document.getElementById('breadcrumb');
    if (!nav) return;
    const items = trail();
    const title = document.getElementById('page-title');
    if (title) title.textContent = items[items.length - 1].label;
    const sep = `<span class="breadcrumb-sep" aria-hidden="true">${ui.ico('chevron-right', { size: 'xs' })}</span>`;
    nav.innerHTML = items.map((it, i) => {
      const last = i === items.length - 1;
      if (last) return `<span aria-current="page" title="${escAttr(it.label)}">${esc(it.label)}</span>`;
      return `<button type="button" class="breadcrumb-link" data-crumb="${escAttr(it.page)}">${esc(it.label)}</button>${sep}`;
    }).join('');
  }

  function themeIcon() {
    const btn = document.getElementById('theme-cycle');
    if (!btn) return;
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    btn.innerHTML = ui.ico(dark ? 'sun' : 'moon');
  }

  function syncBell() {
    const dot = document.getElementById('update-dot');
    const bell = document.getElementById('topbar-bell');
    if (!bell) return;
    const on = !!dot && !dot.hidden;
    if (bell.hidden === on) bell.hidden = !on;
    if (on && dot.title) bell.setAttribute('data-tip', dot.title);
  }

  function wireWorkspace() {
    const btn = document.getElementById('ws-switch');
    if (!btn || !ui.menu) return;
    const name = company();
    const avatar = document.getElementById('ws-avatar');
    if (avatar) avatar.textContent = initials(name);
    ui.menu.attach(btn, () => [
      { heading: name || tr('ws.workspace') },
      { label: tr('nav.settings'), icon: 'settings', onSelect: () => root.navigate('settings') },
      { label: tr('theme.toggle'), icon: 'sun', onSelect: () => ui.theme.cycle() },
    ]);
  }

  function updateShell() {
    renderBreadcrumb();
    syncBell();
  }

  document.addEventListener('click', e => {
    const t = e.target instanceof Element ? e.target : null;
    if (!t) return;
    const crumb = t.closest('[data-crumb]');
    if (crumb) { root.navigate(crumb.getAttribute('data-crumb')); return; }
    if (t.closest('#topbar-bell')) { root.navigate('settings'); return; }
    if (t.closest('#skip-link')) {
      // A plain #anchor would rewrite the hash the router reads; move focus instead.
      e.preventDefault();
      const main = document.getElementById('main-content');
      if (main) main.focus();
      return;
    }
    if (t.closest('#theme-cycle')) { ui.theme.cycle(); themeIcon(); }
  });

  new MutationObserver(themeIcon).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  if (ui.hydrate) ui.hydrate.register(syncBell);
  // The breadcrumb is built once per render, not per language, so a switch
  // would otherwise leave it in the previous language until the next render.
  if (ui.i18n) ui.i18n.onLangChange(renderBreadcrumb);

  wireWorkspace();
  themeIcon();
  renderBreadcrumb();

  root.updateShell = updateShell;
  ui.shell = { initials, trail, updateShell };
})(window);
