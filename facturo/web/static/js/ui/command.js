// Command palette (Ctrl/Cmd+K, or any [data-cmd-open] button).
//
// Groups: recent (empty query), navigation, actions, search (invoices by
// numero/client, clients, payments once loaded); their titles follow the language. Accent-folding fuzzy matching
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
  // Group ids are stable; the visible title comes from cmd.group.<id> (an
  // extra source may pass its own already-translated title as the group).
  const GROUP_ORDER = ['recent', 'navigation', 'actions', 'search'];
  const GROUP_LIMIT = { search: 12 };
  const tr = (key, params) => ui.i18n.t(key, params);
  const groupLabel = id => (ui.i18n.has(`cmd.group.${id}`) ? tr(`cmd.group.${id}`) : id);
  const extraSources = [];
  let overlay = null;
  let refresh = null;

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
      ['home', 'layout-dashboard'], ['clients', 'users'], ['facture', 'receipt'], ['history', 'history'],
      ['scans', 'scan-line'], ['payments', 'banknote'], ['settings', 'settings'],
    ];
    return pages.map(([page, icon]) => ({
      id: `nav:${page}`, group: 'navigation', label: tr(`nav.${page}`), icon,
      keywords: tr(`cmd.kw.${page}`), run: click(`.nav-btn[data-page="${page}"]`),
    }));
  }

  function actionItems() {
    const list = [
      { id: 'act:new', label: tr('nav.facture'), icon: 'plus', keywords: tr('cmd.kw.new'), run: call('newFacture') },
      { id: 'act:theme', label: tr('cmd.act.theme'), icon: 'moon', keywords: tr('cmd.kw.theme'), run: () => ui.theme && ui.theme.setPreference(ui.theme.resolve(ui.theme.getPreference()) === 'dark' ? 'light' : 'dark') },
      // One setLang for the palette and both switchers: three controls, one
      // code path, so none of them can end up out of step with the others.
      { id: 'act:lang', label: tr('lang.action'), icon: 'code', keywords: tr('cmd.kw.lang'), run: () => ui.i18n && ui.i18n.setLang(ui.i18n.lang() === 'fr' ? 'en' : 'fr') },
    ];
    if (ui.sidebar) list.push({ id: 'act:sidebar', label: tr('cmd.act.sidebar'), icon: 'panel-left', kbd: 'Ctrl+B', keywords: tr('cmd.kw.sidebar'), run: () => ui.sidebar.toggle() });
    const sync = gState().sync;
    if (sync && sync.configured) {
      list.push(
        { id: 'act:push', label: tr('cmd.act.push'), icon: 'cloud-upload', keywords: tr('cmd.kw.push'), run: call('syncPush') },
        { id: 'act:pull', label: tr('cmd.act.pull'), icon: 'cloud-download', keywords: tr('cmd.kw.pull'), run: call('syncPull') });
    }
    return list.map(a => Object.assign({ group: 'actions' }, a));
  }

  function searchItems() {
    const st = gState();
    const fmtMoney = ui.i18n.fmtMoney;
    const fmtDate = ui.i18n.fmtDate;
    const out = [];
    (st.factures || []).forEach(f => out.push({
      id: `fac:${f.id}`, group: 'search', icon: 'receipt', label: tr('cmd.invoice', { number: f.numero }),
      hint: [f.client_nom, fmtDate(f.date), fmtMoney(Number(f.total_ttc) || 0)].filter(Boolean).join(' · '),
      keywords: `${f.numero} ${f.client_nom || ''}`,
      run() {
        if (gHistDefaults()) st.histFilters = Object.assign({}, gHistDefaults(), { q: String(f.numero) });
        if (typeof root.navigate === 'function') root.navigate('history');
      },
    }));
    (st.clients || []).forEach(c => out.push({
      id: `cli:${c.id}`, group: 'search', icon: 'users', label: c.nom, hint: tr('cmd.client'), keywords: `${c.ref || ''} ${c.prefix || ''}`,
      run: call('openClientModal', c.id),
    }));
    const payments = gPay() && Array.isArray(gPay().list) ? gPay().list : [];
    payments.forEach(p => out.push({
      id: `pay:${p.id}`, group: 'search', icon: 'banknote', label: tr('cmd.receipt', { ref: p.reference || tr('cmd.no_ref') }),
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
      if (rec.length) groups.push({ name: 'recent', items: rec });
      for (const g of ['navigation', 'actions']) groups.push({ name: g, items: items.filter(i => i.group === g) });
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
      'aria-autocomplete': 'list', 'aria-label': tr('cmd.placeholder'),
      placeholder: tr('cmd.placeholder'), autocomplete: 'off', spellcheck: 'false',
    });
    const list = h('div', { class: 'command-list', id: listId, role: 'listbox', 'aria-label': tr('cmd.results') });
    const live = h('div', { class: 'sr-only', 'aria-live': 'polite' });
    const footKids = () => [
      h('span', {}, h('kbd', { text: '↑' }), h('kbd', { text: '↓' }), ` ${tr('cmd.hint.navigate')}`),
      h('span', {}, h('kbd', { text: '↵' }), ` ${tr('cmd.hint.open')}`),
      h('span', {}, h('kbd', { text: tr('cmd.key.escape') }), ` ${tr('cmd.hint.close')}`),
    ];
    const foot = h('div', { class: 'command-foot' }, ...footKids());
    const box = h('div', { class: 'modal command' },
      h('div', { class: 'command-search' }, h('span', { class: 'command-search-icon', html: ui.ico('search', { size: 'sm' }) }), input), list, live, foot);
    overlay = h('div', { class: 'modal-overlay command-overlay', 'aria-label': tr('a11y.command_palette') }, box);

    let visible = [];
    let active = 0;
    let items = allItems('');

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
        list.append(h('div', { class: 'command-empty' }, h('span', { html: ui.ico('search-x', { size: 'lg' }) }), h('p', { text: tr('cmd.empty', { query: q.trim() }) })));
        live.textContent = tr('empty.results');
        input.removeAttribute('aria-activedescendant');
        return;
      }
      groups.forEach(g => {
        const gid = ui.uid('cmd-group');
        const wrap = h('div', { class: 'command-group', role: 'group', 'aria-labelledby': gid }, h('div', { class: 'command-heading', id: gid, text: groupLabel(g.name) }));
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
      live.textContent = ui.i18n.tn('cmd.count', visible.length);
      setActive(0, false);
      list.scrollTop = 0;
    }

    // A language switch while the palette is open: rebuild items, texts and list in place.
    refresh = () => {
      items = allItems('');
      const text = tr('cmd.placeholder');
      input.setAttribute('aria-label', text);
      input.setAttribute('placeholder', text);
      list.setAttribute('aria-label', tr('cmd.results'));
      overlay.setAttribute('aria-label', tr('a11y.command_palette'));
      foot.replaceChildren(...footKids());
      render();
    };
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
    refresh = null;
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

  ui.i18n.onLangChange(() => { if (overlay && overlay.isConnected && refresh) refresh(); });

  ui.command = { open, close, toggle, addSource: fn => extraSources.push(fn), _plan: plan };
})(window);
