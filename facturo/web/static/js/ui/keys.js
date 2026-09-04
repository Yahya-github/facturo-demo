// Pure keyboard-navigation helpers for menus, tabs and the command list.
// No DOM (unit-tested in tests/js/ui-keys.test.mjs).
(function (root, factory) {
  const mod = factory();
  if (typeof module === 'object' && module.exports) module.exports = mod;
  else { root.ui = root.ui || {}; root.ui.keys = mod; }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  /**
   * Next roving index for an arrow/Home/End key. `cur` may be -1 (nothing active).
   * @param {number} len item count
   * @param {number} cur current index
   * @param {string} key KeyboardEvent.key
   * @param {{orientation?: 'vertical'|'horizontal', loop?: boolean}} [o]
   * @returns {number} new index, or `cur` when the key does not move
   */
  function nextIndex(len, cur, key, o = {}) {
    if (len <= 0) return -1;
    const horizontal = o.orientation === 'horizontal';
    const loop = o.loop !== false;
    const fwd = horizontal ? 'ArrowRight' : 'ArrowDown';
    const back = horizontal ? 'ArrowLeft' : 'ArrowUp';
    if (key === 'Home') return 0;
    if (key === 'End') return len - 1;
    if (key === fwd) return cur + 1 >= len ? (loop ? 0 : len - 1) : cur + 1;
    if (key === back) return cur <= 0 ? (loop ? len - 1 : 0) : cur - 1;
    return cur;
  }

  /** Lower-case, accent-free text for prefix matching. */
  function fold(s) {
    return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  /**
   * Typeahead: the next index whose label starts with `buffer`, searching after
   * `from` first and wrapping. Repeating one letter cycles through matches.
   * @param {string[]} labels
   * @param {string} buffer characters typed so far
   * @param {number} from currently active index
   * @returns {number} -1 when nothing matches
   */
  function typeahead(labels, buffer, from) {
    const q = fold(buffer);
    if (!q) return -1;
    const folded = labels.map(fold);
    const repeated = q.length > 1 && [...q].every(c => c === q[0]);
    const needle = repeated ? q[0] : q;
    const start = repeated || q.length === 1 ? from + 1 : Math.max(from, 0);
    for (let n = 0; n < folded.length; n++) {
      const i = (start + n) % folded.length;
      if (folded[i].startsWith(needle)) return i;
    }
    return -1;
  }

  return { nextIndex, typeahead, fold };
});
