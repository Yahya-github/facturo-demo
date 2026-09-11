// Pure data shaping for the Accueil charts, computed client-side from the
// /api/factures summaries (id, date 'YYYY-MM-DD', client_id, client_nom,
// total_ttc, paye 0|1). No DOM: unit-tested with node
// (tests/js/ui-chart.test.mjs).
(function (root, factory) {
  const mod = factory();
  if (typeof module === 'object' && module.exports) module.exports = mod;
  else { root.ui = root.ui || {}; root.ui.chartData = mod; }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const MONTHS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
  const cents = n => Math.round((Number(n) || 0) * 100);
  const fromCents = c => c / 100;

  /** 'YYYY-MM' of an ISO date, or null when the date is missing/invalid. */
  function monthKey(date) {
    return typeof date === 'string' && /^\d{4}-\d{2}/.test(date) ? date.slice(0, 7) : null;
  }

  function shiftMonth(key, delta) {
    const [y, m] = key.split('-').map(Number);
    const idx = y * 12 + (m - 1) + delta;
    return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, '0')}`;
  }

  /** 'sept. 2026' for '2026-09'. */
  function monthLabel(key, withYear = true) {
    const [y, m] = key.split('-').map(Number);
    return withYear ? `${MONTHS[m - 1]} ${y}` : MONTHS[m - 1];
  }

  /**
   * Invoiced total per calendar month over a continuous window (empty months are 0).
   * @param {Array} factures
   * @param {{months?: number, anchor?: 'latest'|'now', now?: Date}} [o]
   *   anchor 'latest' (default) ends the window at the newest invoice month.
   * @returns {{key:string,label:string,short:string,total:number,count:number,paid:number,unpaid:number}[]}
   */
  function groupByMonth(factures, o = {}) {
    const n = Math.max(1, o.months || 6);
    const acc = new Map();
    for (const f of factures || []) {
      const k = monthKey(f.date);
      if (!k) continue;
      const row = acc.get(k) || { total: 0, paid: 0, count: 0 };
      const c = cents(f.total_ttc);
      row.total += c;
      row.count += 1;
      if (f.paye) row.paid += c;
      acc.set(k, row);
    }
    const now = o.now || new Date();
    const nowKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const latest = [...acc.keys()].sort().pop();
    const end = o.anchor === 'now' || !latest ? nowKey : latest;
    const out = [];
    for (let i = n - 1; i >= 0; i--) {
      const key = shiftMonth(end, -i);
      const r = acc.get(key) || { total: 0, paid: 0, count: 0 };
      out.push({
        key, label: monthLabel(key), short: monthLabel(key, false),
        total: fromCents(r.total), count: r.count, paid: fromCents(r.paid), unpaid: fromCents(r.total - r.paid),
      });
    }
    return out;
  }

  /**
   * Clients ranked by invoiced total (ties: more invoices, then name).
   * @returns {{id:*,name:string,total:number,count:number}[]}
   */
  function topClients(factures, n = 5) {
    const acc = new Map();
    for (const f of factures || []) {
      const id = f.client_id !== undefined && f.client_id !== null ? f.client_id : f.client_nom;
      const row = acc.get(id) || { id, name: f.client_nom || 'Client inconnu', total: 0, count: 0 };
      row.total += cents(f.total_ttc);
      row.count += 1;
      acc.set(id, row);
    }
    return [...acc.values()]
      .sort((a, b) => b.total - a.total || b.count - a.count || a.name.localeCompare(b.name, 'fr'))
      .slice(0, Math.max(0, n))
      .map(r => ({ ...r, total: fromCents(r.total) }));
  }

  /** Paid vs unpaid totals and counts, plus the paid share of the amount (0..1). */
  function paidSplit(factures) {
    const s = { paid: { total: 0, count: 0 }, unpaid: { total: 0, count: 0 } };
    for (const f of factures || []) {
      const b = f.paye ? s.paid : s.unpaid;
      b.total += cents(f.total_ttc);
      b.count += 1;
    }
    const all = s.paid.total + s.unpaid.total;
    return {
      paid: { total: fromCents(s.paid.total), count: s.paid.count },
      unpaid: { total: fromCents(s.unpaid.total), count: s.unpaid.count },
      total: fromCents(all),
      count: s.paid.count + s.unpaid.count,
      paidPct: all ? s.paid.total / all : 0,
    };
  }

  /** A round axis maximum and step so `ticks` gridlines land on tidy numbers. */
  function niceScale(max, ticks = 4) {
    if (!(max > 0)) return { max: 1, step: 1 / ticks, ticks };
    const raw = max / ticks;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
    return { max: step * ticks, step, ticks };
  }

  /** Short French axis label: 850, 1,2 k, 3 M. */
  function compact(n) {
    const a = Math.abs(n);
    const fmt = (v, u) => `${(Math.round(v * 10) / 10).toString().replace('.', ',')}${u}`;
    if (a >= 1e6) return fmt(n / 1e6, ' M');
    if (a >= 1e3) return fmt(n / 1e3, ' k');
    return fmt(n, '');
  }

  return { groupByMonth, topClients, paidSplit, niceScale, compact, monthKey, monthLabel, shiftMonth };
});
