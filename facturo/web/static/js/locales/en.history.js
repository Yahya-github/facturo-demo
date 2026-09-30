// English copy for the Historique page. Same keys as the other language, in the same order.
(function (root, factory) {
  const dict = factory();
  if (typeof module === 'object' && module.exports) { module.exports = dict; return; }
  if (root.ui && root.ui.i18n) root.ui.i18n.define('en', dict);
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  return {

    // ── page ──
    'history.subtitle': 'All generated invoices, with search, filters and quick actions',
    'history.empty.title': 'No invoices',
    'history.empty.text': 'Generated invoices will appear here, with their payment status.',

    // ── table ──
    'history.col.invoice_no': 'Invoice no.',
    'history.created_on': 'Created on {date}',
    'history.edit_invoice': 'Edit invoice {number}',
    'history.paid_tickets': 'Paid tickets',
    'history.partial_tickets': '{paid}/{total} tickets',
    'history.no_match.title': 'No invoices match',
    'history.no_match.text': 'Change the search or filters to widen the results.',
    'history.no_match.reset': 'Reset filters',
    'history.pager.label': 'Pagination',
    'history.pager.info': '{from}–{to} of {total}',
    'history.pager.prev': 'Previous',
    'history.pager.next': 'Next',
    'history.pager.page': 'Page {page} / {pages}',

    // ── toolbar ──
    'history.filter.label': 'Filter invoices',
    'history.filter.search': 'Search',
    'history.filter.placeholder': 'Invoice no., client, site, plate, ticket no.…',
    'history.filter.period': 'Period',
    'history.filter.from': 'From',
    'history.filter.to': 'To',
    'history.filter.presets': 'Preset periods',
    'history.filter.sort': 'Sort by',
    'history.filter.reset': 'Reset',
    'history.sort.date_desc': 'Date (newest)',
    'history.sort.date_asc': 'Date (oldest)',
    'history.sort.montant_desc': 'Amount (high to low)',
    'history.preset.month': 'This month',
    'history.preset.30d': 'Last 30 days',
    'history.preset.year': 'This year',
    'history.preset.clear': 'All time',

    // ── actions ──
    'history.delete.title': 'Delete invoice',
    'history.delete.desc': 'Delete invoice {number}? The generated Excel/PDF file will be deleted too.',
    'history.deleted': 'Invoice {number} deleted',
    'history.pdf_busy': 'PDF...',
    'history.pdf_error': 'PDF conversion failed',
    'history.pdf_done': 'PDF downloaded!',
  };
});
