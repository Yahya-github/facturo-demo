// Accent-folding fuzzy matcher behind the command palette. Pure (no DOM) so it
// is unit-tested with node (tests/js/ui-fuzzy.test.mjs).
//
// Same idea as foldKey/near1 in autocomplete.js (fold accents and case, forgive a
// one-letter typo) but it keeps character positions, so matches can be highlighted
// in the original text.
(function (root, factory) {
  const mod = factory();
  if (typeof module === 'object' && module.exports) module.exports = mod;
  else { root.ui = root.ui || {}; root.ui.fuzzy = mod; }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  /** One folded character per input character: lower-case, accent-free, non-alphanumerics -> ' '. */
  function fold(s) {
    let out = '';
    for (const ch of String(s === null || s === undefined ? '' : s)) {
      const base = ch.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
      const c = base ? base[0] : ' ';
      out += /[a-z0-9]/.test(c) ? c : ' ';
      if (ch.length === 2) out += ' '; // astral char: keep UTF-16 indices aligned
    }
    return out;
  }

  /** Edit distance of exactly 1 (one substitution, insertion or deletion). */
  function near1(a, b) {
    if (Math.abs(a.length - b.length) > 1) return false;
    if (a.length === b.length) {
      let diff = 0;
      for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) diff++;
      return diff === 1;
    }
    if (a.length > b.length) [a, b] = [b, a];
    let i = 0, j = 0, skipped = false;
    while (i < a.length && j < b.length) {
      if (a[i] === b[j]) { i++; j++; }
      else if (skipped) return false;
      else { skipped = true; j++; }
    }
    return true;
  }

  function words(t) {
    const out = [];
    const re = /[a-z0-9]+/g;
    let m;
    while ((m = re.exec(t))) out.push({ w: m[0], at: m.index });
    return out;
  }

  /** Score one query token against folded text; -1 = no match. */
  function tokenScore(tok, t, ws) {
    if (t.trim() === tok) return 100;
    if (t.startsWith(tok)) return 90;
    const wi = ws.findIndex(x => x.w.startsWith(tok));
    if (wi >= 0) return 80 - Math.min(wi * 3, 20);
    const at = t.indexOf(tok);
    if (at >= 0) return 60 - Math.min(at, 20);
    if (tok.length >= 4 && ws.some(x => near1(tok, x.w) || near1(tok, x.w.slice(0, tok.length)))) return 35;
    // Subsequence ("fctr" -> "facture"), penalised by the span it stretches over.
    let pos = 0, first = -1;
    for (const c of tok) {
      const k = t.indexOf(c, pos);
      if (k < 0) return -1;
      if (first < 0) first = k;
      pos = k + 1;
    }
    const span = pos - first;
    return tok.length >= 3 ? Math.max(5, 25 - (span - tok.length)) : -1;
  }

  /**
   * Relevance of `text` for `query`: every whitespace-separated token must match.
   * Higher is better; -1 means no match; an empty query scores 0.
   */
  function score(query, text) {
    const toks = fold(query).split(' ').filter(Boolean);
    if (!toks.length) return 0;
    const t = fold(text);
    const ws = words(t);
    let total = 0;
    for (const tok of toks) {
      const s = tokenScore(tok, t, ws);
      if (s < 0) return -1;
      total += s;
    }
    return total / toks.length - Math.min(t.length, 80) * 0.05;
  }

  /**
   * Filter and rank `items` for `query`. `textOf(item)` returns the string(s) to
   * match (an array is allowed: the best one wins). Stable for equal scores.
   * @returns {{item: *, score: number}[]}
   */
  function rank(items, query, textOf) {
    const out = [];
    items.forEach((item, i) => {
      const texts = [].concat(textOf(item));
      let best = -1;
      for (const x of texts) best = Math.max(best, score(query, x));
      if (best >= 0) out.push({ item, score: best, i });
    });
    if (fold(query).trim()) out.sort((a, b) => b.score - a.score || a.i - b.i);
    return out.map(({ item, score: s }) => ({ item, score: s }));
  }

  /** [start, end) ranges of `text` covered by literal (folded) matches of the query tokens. */
  function ranges(query, text) {
    const t = fold(text);
    const marks = [];
    for (const tok of fold(query).split(' ').filter(Boolean)) {
      const wi = words(t).find(x => x.w.startsWith(tok));
      const at = wi ? wi.at : t.indexOf(tok);
      if (at >= 0) marks.push([at, at + tok.length]);
    }
    marks.sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const m of marks) {
      const last = merged[merged.length - 1];
      if (last && m[0] <= last[1]) last[1] = Math.max(last[1], m[1]); else merged.push(m.slice());
    }
    return merged;
  }

  return { fold, near1, score, rank, ranges };
});
