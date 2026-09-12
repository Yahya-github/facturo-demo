// SVG charts drawn with the --chart-1..5 tokens: monthly bars, a paid/unpaid
// donut and horizontal bars (top clients). Each has a hover tooltip, a draw-in
// animation (off under prefers-reduced-motion, via motion.css), an aria-label
// and a visually-hidden data table for screen readers.
//
//   ui.chart.bar(el,   ui.chartData.groupByMonth(state.factures), { title: 'Facturé par mois' })
//   ui.chart.donut(el, ui.chartData.paidSplit(state.factures))
//   ui.chart.hbar(el,  ui.chartData.topClients(state.factures, 5))
// `el` is any container; its contents are replaced. Data shaping lives in chart-data.js.
(function (root) {
  'use strict';
  const ui = root.ui = root.ui || {};
  const NS = 'http://www.w3.org/2000/svg';

  const money = n => (typeof root.money === 'function' ? root.money(n) : n.toFixed(2));

  function svg(tag, attrs, ...kids) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) el.setAttribute(k, String(v));
    kids.forEach(k => k && el.append(k));
    return el;
  }

  function text(x, y, str, cls, anchor) {
    const t = svg('text', { x, y, class: cls, 'text-anchor': anchor || 'start' });
    t.textContent = str;
    return t;
  }

  /** figure > svg + tooltip + sr-only table; returns helpers to wire hover. */
  function frame(el, o) {
    const { h } = ui;
    const tip = h('div', { class: 'chart-tip', role: 'presentation', hidden: true });
    const table = h('table', { class: 'sr-only' },
      h('caption', { text: o.title }),
      h('thead', {}, h('tr', {}, o.columns.map(c => h('th', { scope: 'col', text: c })))),
      h('tbody', {}, o.rows.map(r => h('tr', {}, r.map(c => h('td', { text: c }))))));
    const figure = h('figure', { class: `chart chart-${o.kind}` }, o.svg, tip, table);
    o.svg.setAttribute('role', 'img');
    o.svg.setAttribute('aria-label', o.label);
    el.textContent = '';
    el.append(figure);

    function showTip(target, html) {
      tip.textContent = '';
      tip.append(...html);
      tip.hidden = false;
      const f = figure.getBoundingClientRect();
      const r = target.getBoundingClientRect();
      const w = tip.offsetWidth;
      const x = Math.min(Math.max(r.left - f.left + r.width / 2 - w / 2, 0), Math.max(0, f.width - w));
      tip.style.left = `${x}px`;
      tip.style.top = `${Math.max(0, r.top - f.top - tip.offsetHeight - 8)}px`;
    }
    const hideTip = () => { tip.hidden = true; };
    function hover(node, content, anchor) {
      node.classList.add('chart-hit');
      node.addEventListener('pointerenter', () => showTip(anchor || node, content()));
      node.addEventListener('pointerleave', hideTip);
    }
    return { hover, figure };
  }

  const tipLines = (title, value, sub) => [
    ui.h('strong', { text: title }),
    ui.h('span', { text: value }),
    sub ? ui.h('span', { class: 'chart-tip-sub', text: sub }) : null,
  ].filter(Boolean);

  // ── vertical bars ──
  const DEFAULT_W = 640, DEFAULT_H = 260, MIN_W = 300, PAD = { l: 52, r: 12, t: 12, b: 32 };

  /**
   * Monthly bar chart. `data` = groupByMonth() rows ({label, short, total, count}).
   * @param {{title?: string}} [o]
   */
  function bar(el, data, o = {}) {
    const title = o.title || 'Facturé par mois';
    const W = Math.max(MIN_W, Math.round(o.width || DEFAULT_W)), H = o.height || DEFAULT_H;
    const max = Math.max(0, ...data.map(d => d.total));
    const sc = ui.chartData.niceScale(max, 4);
    const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
    const slot = iw / Math.max(1, data.length);
    const bw = Math.min(56, slot * 0.6);
    const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart-svg', preserveAspectRatio: 'xMidYMid meet' });
    for (let i = 0; i <= sc.ticks; i++) {
      const y = PAD.t + ih - (i / sc.ticks) * ih;
      s.append(svg('line', { x1: PAD.l, x2: W - PAD.r, y1: y, y2: y, class: 'chart-grid' }));
      s.append(text(PAD.l - 8, y + 4, ui.chartData.compact(i * sc.step), 'chart-axis', 'end'));
    }
    const f = frame(el, {
      kind: 'bar', svg: s, title, label: `${title} : ${data.map(d => `${d.label} ${money(d.total)}`).join(', ')}`,
      columns: ['Mois', 'Total', 'Factures'], rows: data.map(d => [d.label, money(d.total), String(d.count)]),
    });
    data.forEach((d, i) => {
      const cx = PAD.l + slot * i + slot / 2;
      const hgt = sc.max ? (d.total / sc.max) * ih : 0;
      const rect = svg('rect', {
        x: cx - bw / 2, y: PAD.t + ih - hgt, width: bw, height: Math.max(hgt, d.total > 0 ? 2 : 0), rx: 4,
        class: 'chart-bar-rect', style: `--i:${i}`, fill: 'var(--chart-1)',
      });
      s.append(rect, text(cx, H - 10, d.short, 'chart-axis', 'middle'));
      // A wider invisible target keeps thin bars easy to hover.
      const hit = svg('rect', { x: cx - slot / 2, y: PAD.t, width: slot, height: ih, fill: 'transparent' });
      hit.addEventListener('pointerenter', () => rect.classList.add('is-hover'));
      hit.addEventListener('pointerleave', () => rect.classList.remove('is-hover'));
      f.hover(hit, () => tipLines(d.label, money(d.total), `${d.count} facture${d.count > 1 ? 's' : ''}`), rect);
      s.append(hit);
    });
    return { el };
  }

  // ── donut ──
  /**
   * Paid vs unpaid donut. `data` = paidSplit() result.
   * @param {{title?: string}} [o]
   */
  function donut(el, data, o = {}) {
    const title = o.title || 'Payées et impayées';
    const R = 70, C = 2 * Math.PI * R, SW = 26, size = 200;
    const s = svg('svg', { viewBox: `0 0 ${size} ${size}`, class: 'chart-svg chart-donut-svg' });
    const parts = [
      { key: 'paid', label: 'Payées', color: 'var(--chart-1)', v: data.paid },
      { key: 'unpaid', label: 'Impayées', color: 'var(--chart-2)', v: data.unpaid },
    ];
    s.append(svg('circle', { cx: 100, cy: 100, r: R, fill: 'none', 'stroke-width': SW, class: 'chart-donut-track' }));
    const pct = Math.round(data.paidPct * 100);
    const f = frame(el, {
      kind: 'donut', svg: s, title,
      label: `${title} : ${parts.map(p => `${p.label} ${money(p.v.total)} (${p.v.count})`).join(', ')}`,
      columns: ['Statut', 'Total', 'Factures'], rows: parts.map(p => [p.label, money(p.v.total), String(p.v.count)]),
    });
    let offset = 0;
    if (data.total > 0) {
      parts.forEach((p, i) => {
        const len = (p.v.total / data.total) * C;
        if (len <= 0) return;
        const seg = svg('circle', {
          cx: 100, cy: 100, r: R, fill: 'none', stroke: p.color, 'stroke-width': SW, class: 'chart-donut-seg',
          'stroke-dasharray': `${Math.max(0, len - 2)} ${C}`, 'stroke-dashoffset': -offset,
          transform: 'rotate(-90 100 100)', style: `--i:${i};--len:${len}`,
        });
        offset += len;
        f.hover(seg, () => tipLines(p.label, money(p.v.total), `${p.v.count} facture${p.v.count > 1 ? 's' : ''}`));
        s.append(seg);
      });
    }
    s.append(text(100, 98, data.total > 0 ? `${pct} %` : '—', 'chart-donut-value', 'middle'), text(100, 118, 'payé', 'chart-axis', 'middle'));
    const legend = ui.h('ul', { class: 'chart-legend' }, parts.map(p => ui.h('li', {},
      ui.h('span', { class: 'chart-swatch', style: `background:${p.color}` }),
      ui.h('span', { class: 'chart-legend-label', text: p.label }),
      ui.h('span', { class: 'chart-legend-value', text: money(p.v.total) }))));
    f.figure.append(legend);
    return { el };
  }

  // ── horizontal bars ──
  const ROW = 38, LABEL_W = 170, VALUE_W = 96;

  /**
   * Horizontal bars (top clients). `data` = topClients() rows ({name, total, count}).
   * @param {{title?: string}} [o]
   */
  function hbar(el, data, o = {}) {
    const title = o.title || 'Meilleurs clients';
    const W = Math.max(MIN_W, Math.round(o.width || DEFAULT_W));
    const labelW = Math.min(LABEL_W, Math.round(W * 0.36)), valueW = Math.min(VALUE_W, Math.round(W * 0.3));
    const maxChars = Math.max(8, Math.floor(labelW / 7.4));
    const max = Math.max(0, ...data.map(d => d.total));
    const h = Math.max(ROW, data.length * ROW) + 8;
    const s = svg('svg', { viewBox: `0 0 ${W} ${h}`, class: 'chart-svg chart-hbar-svg' });
    const f = frame(el, {
      kind: 'hbar', svg: s, title, label: `${title} : ${data.map(d => `${d.name} ${money(d.total)}`).join(', ')}`,
      columns: ['Client', 'Total', 'Factures'], rows: data.map(d => [d.name, money(d.total), String(d.count)]),
    });
    const track = W - labelW - valueW - 8;
    data.forEach((d, i) => {
      const y = 4 + i * ROW;
      const w = max ? Math.max(3, (d.total / max) * track) : 0;
      const name = d.name.length > maxChars ? `${d.name.slice(0, maxChars - 1)}…` : d.name;
      const g = svg('g', { class: 'chart-hbar-row' });
      g.append(
        text(0, y + ROW / 2 + 4, name, 'chart-label'),
        svg('rect', { x: labelW, y: y + 8, width: track, height: ROW - 16, rx: 4, class: 'chart-track' }),
        svg('rect', { x: labelW, y: y + 8, width: w, height: ROW - 16, rx: 4, fill: 'var(--chart-1)', class: 'chart-hbar-rect', style: `--i:${i}` }),
        text(W, y + ROW / 2 + 4, money(d.total), 'chart-value', 'end'),
        svg('rect', { x: 0, y, width: W, height: ROW, fill: 'transparent' }));
      f.hover(g, () => tipLines(d.name, money(d.total), `${d.count} facture${d.count > 1 ? 's' : ''}`));
      s.append(g);
    });
    if (!data.length) s.append(text(W / 2, 30, 'Aucune donnée', 'chart-axis', 'middle'));
    return { el };
  }

  ui.chart = { bar, donut, hbar };
})(window);
