// App shell wiring: workspace switcher (initials tile + dropdown menu), the
// header breadcrumb built from state.page / state.editingId, the theme button
// and the update bell that mirrors #update-dot.
//
//   updateShell()   global, called by render() in core.js on every page render
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};

  const PAGE_LABELS = {
    home: 'Accueil', clients: 'Clients', facture: 'Nouvelle facture', history: 'Historique',
    scans: 'Factures scannées', payments: 'Paiements', settings: 'Paramètres',
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
    const items = [{ label: PAGE_LABELS.home, page: 'home' }];
    if (page === 'home') return items;
    if (page === 'facture' && st.editingId != null) {
      const f = (st.factures || []).find(x => x.id === st.editingId);
      items.push({ label: PAGE_LABELS.history, page: 'history' });
      items.push({ label: f && f.numero ? `Facture ${f.numero}` : 'Facture' });
      return items;
    }
    items.push({ label: PAGE_LABELS[page] || page });
    return items;
  }

  function renderBreadcrumb() {
    const nav = document.getElementById('breadcrumb');
    if (!nav) return;
    const items = trail();
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
      { heading: name || 'Espace de travail' },
      { label: 'Paramètres', icon: 'settings', onSelect: () => root.navigate('settings') },
      { label: 'Changer de thème', icon: 'sun', onSelect: () => ui.theme.cycle() },
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
    if (t.closest('#theme-cycle')) { ui.theme.cycle(); themeIcon(); }
  });

  new MutationObserver(themeIcon).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  if (ui.hydrate) ui.hydrate.register(syncBell);

  wireWorkspace();
  themeIcon();
  renderBreadcrumb();

  root.updateShell = updateShell;
  ui.shell = { initials, trail, updateShell };
})(window);
