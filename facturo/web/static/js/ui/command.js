// Command palette (Ctrl/Cmd+K, or any [data-cmd-open] button).
//
// Groups: Récents (empty query), Navigation, Actions, Recherche (invoices by
// numero/client, clients, payments once loaded). Accent-folding fuzzy matching
// (ui/fuzzy.js), arrows / Enter / Escape, ARIA combobox + listbox pattern.
//
// The shortcut needs Ctrl/Cmd, so it never fires from plain typing; it also
// works while an input has focus (the modifier makes the intent explicit).
//
//   ui.command.open() / close() / toggle()
//   ui.command.addSource(query => [{ id, group, label, hint?, icon?, kbd?, keywords?, run }])
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};

  const RECENT_KEY = 'facturo-cmd-recent';
  const MAX_RECENT = 5;
  const GROUP_ORDER = ['Récents', 'Navigation', 'Actions', 'Recherche'];
  const GROUP_LIMIT = { Recherche: 12 };
  const extraSources = [];
  let overlay = null;

  // ── data ──
  const click = sel => () => { const b = document.querySelector(sel); if (b) b.click(); };
  // state, pay and HIST_DEFAULTS are top-level const in the page scripts: visible by
  // bare name to every classic script, but not as window properties.
  const gState = () => (typeof state !== 'undefined' ? state : {});
  const gPay = () => (typeof pay !== 'undefined' ? pay : null);
  const gHistDefaults = () => (typeof HIST_DEFAULTS !== 'undefined' ? HIST_DEFAULTS : null);
  const call = (name, ...args) => () => { if (typeof root[name] === 'function') root[name](...args); };

  function navigationItems() {
    const pages = [
      ['home', 'Accueil', 'layout-dashboard', 'accueil tableau de bord'],
      ['clients', 'Clients', 'users', 'clients'],
      ['facture', 'Nouvelle facture', 'receipt', 'creer facture'],
      ['history', 'Historique', 'history', 'factures historique'],
      ['scans', 'Factures scannées', 'scan-line', 'scan documents'],
      ['payments', 'Paiements', 'banknote', 'paiements quittances'],
      ['settings', 'Paramètres', 'settings', 'reglages configuration'],
    ];
    return pages.map(([page, label, icon, keywords]) => ({
      id: `nav:${page}`, group: 'Navigation', label, icon, keywords, run: click(`.nav-btn[data-page="${page}"]`),
    }));
  }

  function actionItems() {
    const list = [
      { id: 'act:new', label: 'Nouvelle facture', icon: 'plus', keywords: 'creer ajouter', run: call('newFacture') },
      { id: 'act:theme', label: 'Basculer le thème', icon: 'moon', keywords: 'clair sombre dark light', run: () => ui.theme && ui.theme.setPreference(ui.theme.resolve(ui.theme.getPreference()) === 'dark' ? 'light' : 'dark') },
    ];
    if (ui.sidebar) list.push({ id: 'act:sidebar', label: 'Afficher / masquer le menu latéral', icon: 'panel-left', kbd: 'Ctrl+B', keywords: 'barre laterale sidebar', run: () => ui.sidebar.toggle() });
    const sync = gState().sync;
    if (sync && sync.configured) {
      list.push(
        { id: 'act:push', label: 'Envoyer les données vers GitHub', icon: 'cloud-upload', keywords: 'sync synchronisation envoyer', run: call('syncPush') },
        { id: 'act:pull', label: 'Recevoir les données de GitHub', icon: 'cloud-download', keywords: 'sync synchronisation recevoir', run: call('syncPull') });
    }
    return list.map(a => Object.assign({ group: 'Actions' }, a));
  }

  function searchItems() {
    const st = gState();
    const fmtMoney = typeof root.money === 'function' ? root.money : String;
    const fmtDate = typeof root.formatDate === 'function' ? root.formatDate : String;
    const out = [];
    (st.factures || []).forEach(f => out.push({
      id: `fac:${f.id}`, group: 'Recherche', icon: 'receipt', label: `Facture ${f.numero}`,
      hint: [f.client_nom, fmtDate(f.date), fmtMoney(Number(f.total_ttc) || 0)].filter(Boolean).join(' · '),
      keywords: `${f.numero} ${f.client_nom || ''}`,
      run() {
        if (gHistDefaults()) st.histFilters = Object.assign({}, gHistDefaults(), { q: String(f.numero) });
        if (typeof root.navigate === 'function') root.navigate('history');
      },
    }));
    (st.clients || []).forEach(c => out.push({
      id: `cli:${c.id}`, group: 'Recherche', icon: 'users', label: c.nom, hint: 'Client', keywords: `${c.ref || ''} ${c.prefix || ''}`,
      run: call('openClientModal', c.id),
    }));
    const payments = gPay() && Array.isArray(gPay().list) ? gPay().list : [];
    payments.forEach(p => out.push({
      id: `pay:${p.id}`, group: 'Recherche', icon: 'banknote', label: `Quittance ${p.reference || 'sans n°'}`,
      hint: [p.emetteur, fmtDate(p.date)].filter(Boolean).join(' · '), keywords: p.emetteur || '',
      run() { if (typeof root.openPayments === 'function') root.openPayments(); if (typeof root.openPayment === 'function') root.openPayment(p.id); },
    }));
    return out;
  }

  function allItems(query) {
    const extra = extraSources.flatMap(fn => { try { return fn(query) || []; } catch (e) { return []; } });
    return [...navigationItems(), ...actionItems(), ...searchItems(), ...extra];
  }

  function readRecent() {
    try { const v = JSON.parse(ui.store.get(RECENT_KEY, '[]')); return Array.isArray(v) ? v : []; } catch (e) { return []; }
  }
  function pushRecent(id) {
    ui.store.set(RECENT_KEY, JSON.stringify([id, ...readRecent().filter(x => x !== id)].slice(0, MAX_RECENT)));
  }

  /** The visible groups for a query: [{ name, items: [item] }]. Exported for tests via ui.command._plan. */
  function plan(query, items, recent) {
    const q = String(query || '').trim();
    const groups = [];
    if (!q) {
      const byId = new Map(items.map(i => [i.id, i]));
      const rec = recent.map(id => byId.get(id)).filter(Boolean);
      if (rec.length) groups.push({ name: 'Récents', items: rec });
      for (const g of ['Navigation', 'Actions']) groups.push({ name: g, items: items.filter(i => i.group === g) });
      return groups.filter(g => g.items.length);
    }
    const names = [...new Set([...GROUP_ORDER.slice(1), ...items.map(i => i.group)])];
    for (const name of names) {
      const ranked = ui.fuzzy.rank(items.filter(i => i.group === name), q, i => [i.label, i.keywords || '', i.hint || ''])
        .slice(0, GROUP_LIMIT[name] || 8).map(r => r.item);
      if (ranked.length) groups.push({ name, items: ranked });
    }
    return groups;
  }

  // ── view ──
  function highlight(text, query) {
    const rs = query ? ui.fuzzy.ranges(query, text) : [];
    if (!rs.length) return [text];
    const out = [];
    let at = 0;
    for (const [a, b] of rs) {
      if (a > at) out.push(text.slice(at, a));
      out.push(ui.h('mark', { text: text.slice(a, b) }));
      at = b;
    }
    if (at < text.length) out.push(text.slice(at));
    return out;
  }

  function open() {
    if (overlay && overlay.isConnected) return;
    if (ui.layer) ui.layer.closeAll(false);
    const { h } = ui;
    const listId = ui.uid('cmd-list');
    const input = h('input', {
      class: 'command-input', type: 'text', role: 'combobox', 'aria-expanded': 'true', 'aria-controls': listId,
      'aria-autocomplete': 'list', 'aria-label': 'Rechercher une page, une action, une facture…',
      placeholder: 'Rechercher une page, une action, une facture…', autocomplete: 'off', spellcheck: 'false',
    });
    const list = h('div', { class: 'command-list', id: listId, role: 'listbox', 'aria-label': 'Résultats' });
    const live = h('div', { class: 'sr-only', 'aria-live': 'polite' });
    const foot = h('div', { class: 'command-foot' },
      h('span', {}, h('kbd', { text: '↑' }), h('kbd', { text: '↓' }), ' naviguer'),
      h('span', {}, h('kbd', { text: '↵' }), ' ouvrir'),
      h('span', {}, h('kbd', { text: 'Échap' }), ' fermer'));
    const box = h('div', { class: 'modal command' },
      h('div', { class: 'command-search' }, h('span', { class: 'command-search-icon', html: ui.ico('search', { size: 'sm' }) }), input), list, live, foot);
    overlay = h('div', { class: 'modal-overlay command-overlay', 'aria-label': 'Palette de commandes' }, box);

    let visible = [];
    let active = 0;
    const items = allItems('');

    function setActive(i, scroll) {
      active = i;
      list.querySelectorAll('[role="option"]').forEach((el, n) => {
        const on = n === i;
        el.setAttribute('aria-selected', on ? 'true' : 'false');
        el.classList.toggle('is-active', on);
        if (on) { input.setAttribute('aria-activedescendant', el.id); if (scroll) el.scrollIntoView({ block: 'nearest' }); }
      });
    }

    function run(item) {
      pushRecent(item.id);
      close();
      setTimeout(() => item.run(), 0);
    }

    function render() {
      const q = input.value;
      const groups = plan(q, q.trim() ? allItems(q) : items, readRecent());
      list.textContent = '';
      visible = [];
      if (!groups.length) {
        list.append(h('div', { class: 'command-empty' }, h('span', { html: ui.ico('search-x', { size: 'lg' }) }), h('p', { text: `Aucun résultat pour « ${q.trim()} »` })));
        live.textContent = 'Aucun résultat';
        input.removeAttribute('aria-activedescendant');
        return;
      }
      groups.forEach(g => {
        const gid = ui.uid('cmd-group');
        const wrap = h('div', { class: 'command-group', role: 'group', 'aria-labelledby': gid }, h('div', { class: 'command-heading', id: gid, text: g.name }));
        g.items.forEach(item => {
          const idx = visible.length;
          visible.push(item);
          const row = h('div', { class: 'command-item', role: 'option', id: ui.uid('cmd-opt'), 'aria-selected': 'false' },
            h('span', { class: 'command-item-icon', html: item.icon ? ui.ico(item.icon, { size: 'sm' }) : '' }),
            h('span', { class: 'command-item-text' },
              h('span', { class: 'command-item-label' }, highlight(item.label, q)),
              item.hint && h('span', { class: 'command-item-hint', text: item.hint })),
            item.kbd && h('span', { class: 'command-item-kbd' }, item.kbd.split('+').map(k => h('kbd', { text: k.trim() }))));
          row.addEventListener('mousemove', () => { if (active !== idx) setActive(idx, false); });
          row.addEventListener('click', () => run(item));
          wrap.append(row);
        });
        list.append(wrap);
      });
      live.textContent = `${visible.length} résultat${visible.length > 1 ? 's' : ''}`;
      setActive(0, false);
      list.scrollTop = 0;
    }

    input.addEventListener('input', render);
    input.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (visible.length) setActive(ui.keys.nextIndex(visible.length, active, e.key), true);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (visible[active]) run(visible[active]);
      }
    });
    render();
    ui.dialog.open(overlay, { initialFocus: '.command-input' });
  }

  function close() {
    if (overlay && overlay.isConnected) ui.dialog.close(overlay);
    overlay = null;
  }
  const toggle = () => (overlay && overlay.isConnected ? close() : open());

  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      toggle();
    }
  });
  document.addEventListener('click', e => {
    const b = e.target instanceof Element && e.target.closest('[data-cmd-open]');
    if (b) { e.preventDefault(); open(); }
  });

  ui.command = { open, close, toggle, addSource: fn => extraSources.push(fn), _plan: plan };
})(window);
