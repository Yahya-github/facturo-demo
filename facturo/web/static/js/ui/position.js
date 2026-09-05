// Pure placement maths for every floating surface (tooltip, popover, menus).
// No DOM: rectangles in, coordinates out, so it is unit-tested with plain node
// (tests/js/ui-position.test.mjs). floating.js feeds it real rectangles.
(function (root, factory) {
  const mod = factory();
  if (typeof module === 'object' && module.exports) module.exports = mod;
  else { root.ui = root.ui || {}; root.ui.position = mod; }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const OPPOSITE = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' };

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(v, Math.max(lo, hi)));

  /** Free space on `side` of the anchor, after the offset and the viewport padding. */
  function space(side, a, vp, offset, padding) {
    if (side === 'bottom') return vp.height - (a.y + a.height) - offset - padding;
    if (side === 'top') return a.y - offset - padding;
    if (side === 'right') return vp.width - (a.x + a.width) - offset - padding;
    return a.x - offset - padding;
  }

  /** Cross-axis start for the requested alignment. */
  function cross(align, aStart, aSize, fSize) {
    if (align === 'center') return aStart + (aSize - fSize) / 2;
    if (align === 'end') return aStart + aSize - fSize;
    return aStart;
  }

  /**
   * Where to put a floating box next to an anchor.
   * Prefers `side`; flips to the opposite side when it does not fit and the
   * opposite does (or has more room); then shifts along the cross axis and clamps
   * both axes so the box always stays inside the viewport.
   * @param {{anchor:{x:number,y:number,width:number,height:number},
   *          floating:{width:number,height:number},
   *          viewport:{width:number,height:number},
   *          side?:'top'|'bottom'|'left'|'right', align?:'start'|'center'|'end',
   *          offset?:number, padding?:number, flip?:boolean}} o
   * @returns {{x:number,y:number,side:string,maxHeight:number}}
   */
  function computePosition(o) {
    const a = o.anchor, f = o.floating, vp = o.viewport;
    const offset = o.offset ?? 6, padding = o.padding ?? 8;
    let side = o.side || 'bottom';
    const vertical = s => s === 'top' || s === 'bottom';
    const need = s => (vertical(s) ? f.height : f.width);

    if (o.flip !== false && space(side, a, vp, offset, padding) < need(side)) {
      const opp = OPPOSITE[side];
      const sp = space(side, a, vp, offset, padding);
      const so = space(opp, a, vp, offset, padding);
      if (so >= need(opp) || so > sp) side = opp;
    }

    let x, y;
    if (side === 'bottom') { y = a.y + a.height + offset; x = cross(o.align, a.x, a.width, f.width); }
    else if (side === 'top') { y = a.y - f.height - offset; x = cross(o.align, a.x, a.width, f.width); }
    else if (side === 'right') { x = a.x + a.width + offset; y = cross(o.align, a.y, a.height, f.height); }
    else { x = a.x - f.width - offset; y = cross(o.align, a.y, a.height, f.height); }

    x = clamp(x, padding, vp.width - f.width - padding);
    y = clamp(y, padding, vp.height - f.height - padding);
    return { x: Math.round(x), y: Math.round(y), side, maxHeight: Math.max(0, Math.floor(vp.height - 2 * padding)) };
  }

  return { computePosition, space, OPPOSITE };
});
