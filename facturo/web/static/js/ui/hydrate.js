// One MutationObserver for the whole app. Pages rebuild #main-content with
// innerHTML on every render, so anything that has to look at freshly inserted
// markup (title -> data-tip, [data-tabs], open layers whose anchor vanished)
// registers a callback here instead of running its own observer.
//
//   ui.hydrate.register(root => { ... })   // called with the document (or a subtree)
//   ui.hydrate.run(root?)                  // force a pass (tests, manual renders)
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};
  const hooks = [];
  let queued = false;

  function run(scope) {
    for (const fn of hooks) {
      try { fn(scope || document); } catch (e) { console.error('[ui.hydrate]', e); }
    }
  }

  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; run(document); });
  }

  function register(fn) {
    hooks.push(fn);
    if (document.readyState !== 'loading') { try { fn(document); } catch (e) { console.error('[ui.hydrate]', e); } }
  }

  function start() {
    run(document);
    new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();

  ui.hydrate = { register, run };
})(window);
