// Accessible Tabs, declared with data attributes and hydrated automatically
// (also after a page re-render):
//
//   <div data-tabs data-tabs-value="general">
//     <div class="tabs-list tabs-line" role="tablist" aria-label="Paramètres">
//       <button class="tabs-trigger" data-tab="general">Général</button>
//       <button class="tabs-trigger" data-tab="sync">Synchronisation</button>
//     </div>
//     <div data-tab-panel="general">...</div>
//     <div data-tab-panel="sync" hidden>...</div>
//   </div>
//
// Roving tabindex, Left/Right/Home/End (automatic activation), aria-selected /
// aria-controls / aria-labelledby, and a sliding underline moved with transform.
// Listen for the `tabschange` event (detail.value) on the [data-tabs] root.
// ui.tabs.select(root, value) switches programmatically.
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};

  function parts(host) {
    const list = host.querySelector(':scope > [role="tablist"], :scope > .tabs-list');
    const triggers = list ? [...list.querySelectorAll('[data-tab]')] : [];
    const panels = [...host.querySelectorAll(':scope > [data-tab-panel]')];
    return { list, triggers, panels };
  }

  function moveIndicator(host, animate) {
    const { list, triggers } = parts(host);
    const ind = list && list.querySelector('.tabs-indicator');
    const cur = triggers.find(t => t.getAttribute('aria-selected') === 'true');
    if (!ind || !cur) return;
    ind.classList.toggle('no-anim', !animate || ui.reducedMotion());
    const x = cur.offsetLeft;
    ind.style.transform = `translateX(${x}px) scaleX(${cur.offsetWidth})`;
  }

  function select(host, value, opts = {}) {
    const { triggers, panels } = parts(host);
    const target = triggers.find(t => t.dataset.tab === value) || triggers[0];
    if (!target) return;
    triggers.forEach(t => {
      const on = t === target;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
    });
    panels.forEach(p => { p.hidden = p.dataset.tabPanel !== target.dataset.tab; });
    host.dataset.tabsValue = target.dataset.tab;
    moveIndicator(host, opts.animate !== false);
    if (opts.focus) target.focus();
    if (opts.emit !== false) host.dispatchEvent(new CustomEvent('tabschange', { bubbles: true, detail: { value: target.dataset.tab } }));
  }

  function init(host) {
    if (host._tabsReady) return;
    const { list, triggers, panels } = parts(host);
    if (!list || !triggers.length) return;
    host._tabsReady = true;
    list.setAttribute('role', 'tablist');
    if (!list.querySelector('.tabs-indicator') && list.classList.contains('tabs-line')) {
      list.append(ui.h('span', { class: 'tabs-indicator', 'aria-hidden': 'true' }));
    }
    triggers.forEach(t => {
      const id = ui.uid('tab');
      const panel = panels.find(p => p.dataset.tabPanel === t.dataset.tab);
      t.id = t.id || id;
      t.setAttribute('role', 'tab');
      t.type = 'button';
      if (panel) {
        panel.id = panel.id || `${t.id}-panel`;
        panel.setAttribute('role', 'tabpanel');
        panel.setAttribute('aria-labelledby', t.id);
        panel.tabIndex = 0;
        t.setAttribute('aria-controls', panel.id);
      }
    });
    list.addEventListener('click', e => {
      const t = e.target.closest('[data-tab]');
      if (t && list.contains(t)) select(host, t.dataset.tab);
    });
    list.addEventListener('keydown', e => {
      const i = triggers.indexOf(document.activeElement);
      if (i < 0) return;
      const j = ui.keys.nextIndex(triggers.length, i, e.key, { orientation: 'horizontal' });
      if (j === i) return;
      e.preventDefault();
      select(host, triggers[j].dataset.tab, { focus: true });
    });
    select(host, host.dataset.tabsValue || triggers[0].dataset.tab, { emit: false, animate: false });
    // Fonts/layout may still move the triggers: re-measure once painted.
    requestAnimationFrame(() => moveIndicator(host, false));
    if (root.ResizeObserver) new ResizeObserver(() => moveIndicator(host, false)).observe(list);
  }

  ui.hydrate.register(scope => scope.querySelectorAll('[data-tabs]').forEach(init));
  ui.tabs = { init, select };
})(window);
