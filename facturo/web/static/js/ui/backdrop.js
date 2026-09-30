// Decorative background (see css/background.css). Injects, once:
//   - into #app-backdrop (behind the floating panel): a film-grain layer + a ledger grid;
//   - into #inset (the panel, behind its content): a dotted delivery route with a pin
//     and a tiny truck that follows it via SMIL <animateMotion>.
// Everything is aria-hidden and pointer-events:none. CSS animations stop under
// prefers-reduced-motion by themselves; SMIL cannot be reached from CSS, so the
// route SVG is paused from here and re-synced when the preference changes.
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};

  const ROUTE_PATH = 'M8 152C70 152 84 70 146 96S236 138 288 58';

  const ROUTE_SVG = `<svg class="panel-route" viewBox="0 0 310 170" aria-hidden="true" focusable="false">
    <path id="route-path" class="route-line" d="${ROUTE_PATH}"/>
    <circle cx="8" cy="152" r="4" fill="none" stroke="var(--bg-route)" stroke-width="1.5"/>
    <circle class="route-pulse" cx="288" cy="58" r="7"/>
    <path class="route-pin" d="M288 28a10 10 0 0 1 10 10c0 8-10 20-10 20S278 46 278 38a10 10 0 0 1 10-10z"/>
    <circle class="route-pin-hole" cx="288" cy="38" r="3.6"/>
    <g opacity="0">
      <g transform="translate(-8 -11)" class="route-truck">
        <path d="M0 2h10v8H0zM10 5h3.5l2.5 3v2h-6"/>
        <circle cx="3.6" cy="11" r="1.5" fill="var(--background)"/>
        <circle cx="12.4" cy="11" r="1.5" fill="var(--background)"/>
      </g>
      <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.05;0.9;1" dur="80s" repeatCount="indefinite"/>
      <animateMotion dur="80s" repeatCount="indefinite" rotate="auto" calcMode="linear"
        keyPoints="0;1;1" keyTimes="0;0.9;1"><mpath href="#route-path"/></animateMotion>
    </g>
  </svg>`;

  function mount() {
    const back = document.getElementById('app-backdrop');
    if (back && !back.firstChild) {
      back.innerHTML = '<div class="bg-grain"></div><div class="bg-ledger"></div>';
    }
    const panel = document.getElementById('inset');
    if (!panel || panel.querySelector('.panel-route')) return null;
    panel.insertAdjacentHTML('afterbegin', ROUTE_SVG);
    return panel.querySelector('.panel-route');
  }

  function syncMotion(svg) {
    if (!svg || typeof svg.pauseAnimations !== 'function') return;
    if (ui.reducedMotion()) svg.pauseAnimations(); else svg.unpauseAnimations();
  }

  const svg = mount();
  syncMotion(svg);
  if (root.matchMedia) {
    const mq = root.matchMedia('(prefers-reduced-motion: reduce)');
    if (mq.addEventListener) mq.addEventListener('change', () => syncMotion(svg));
  }

  ui.backdrop = { mount };
})(window);
