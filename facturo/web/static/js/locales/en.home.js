// English copy for the Accueil page and its charts. Same keys as the other language, in the same order.
(function (root, factory) {
  const dict = factory();
  if (typeof module === 'object' && module.exports) { module.exports = dict; return; }
  if (root.ui && root.ui.i18n) root.ui.i18n.define('en', dict);
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  return {

    // ── page ──
    'home.subtitle': "Overview of {company}'s invoicing",
    'home.greet.morning': 'Good morning',
    'home.greet.evening': 'Good evening',
    'home.greeting': '{greeting} · {date}',
    'home.hero.title': 'Ready to invoice your next delivery?',
    'home.hero.text': 'Pick a client, add the tickets and generate the Excel file in one click.',

    // ── stat cards ──
    'home.stat.clients': 'Clients',
    'home.stat.invoices': 'Invoices',
    'home.hint.clients_active': '{count} with invoices',
    'home.hint.no_clients': 'No clients',
    'home.hint.invoices_in': '{count} invoices in {month}',
    'home.hint.invoices_in.one': '{count} invoice in {month}',
    'home.hint.invoices_in.many': '{count} invoices in {month}',
    'home.hint.no_invoices': 'No invoices',
    'home.hint.all_invoices': 'Across all invoices',
    'home.hint.pending': '{count} invoices pending',
    'home.hint.pending.one': '{count} invoice pending',
    'home.hint.pending.many': '{count} invoices pending',
    'home.hint.all_settled': 'All settled',
    'home.trend.stable': 'Flat vs {month}',
    'home.trend.vs': '{change} vs {month}',
    'home.trend.pct': '{sign}{value}%',

    // ── charts and recent invoices ──
    'home.chart.monthly.title': 'Invoiced per month',
    'home.chart.monthly.desc': 'Last six months of invoicing',
    'home.chart.split.title': 'Paid and unpaid',
    'home.chart.split.desc': 'Breakdown of the invoiced amount',
    'home.chart.top.title': 'Top clients',
    'home.chart.top.desc': 'Ranked by invoiced amount',
    'home.chart.aria': '{title}: {items}',
    'home.chart.col_month': 'Month',
    'home.chart.col_total': 'Total',
    'home.chart.col_invoices': 'Invoices',
    'home.chart.col_status': 'Status',
    'home.chart.col_client': 'Client',
    'home.chart.paid': 'Paid',
    'home.chart.unpaid': 'Unpaid',
    'home.chart.paid_label': 'paid',
    'home.chart.no_data': 'No data',
    'home.chart.unknown_client': 'Unknown client',
    'home.chart.count': '{count} invoices',
    'home.chart.count.one': '{count} invoice',
    'home.chart.count.many': '{count} invoices',
    'home.recent.title': 'Latest invoices',
    'home.recent.desc': 'The most recent, with quick actions',
    'home.recent.filter': 'Filter the latest invoices',
    'home.recent.empty': 'No invoices match these filters.',
    'home.view_all': 'View all',
    'home.empty.title': 'No invoices yet',
    'home.empty.text': 'Create your first invoice: your stats and charts will show up here.',
  };
});
