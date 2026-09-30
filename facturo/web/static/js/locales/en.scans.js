// English copy for the Factures scannées page. Same keys as the other language, in the same order.
(function (root, factory) {
  const dict = factory();
  if (typeof module === 'object' && module.exports) { module.exports = dict; return; }
  if (root.ui && root.ui.i18n) root.ui.i18n.define('en', dict);
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  return {

    // ── folders ──
    'scans.subtitle.pick': 'File your scanned invoices by client',
    'scans.subtitle': '{count} documents, sorted by client',
    'scans.subtitle.one': '{count} document, sorted by client',
    'scans.subtitle.many': '{count} documents, sorted by client',
    'scans.no_client.title': 'No clients',
    'scans.no_client.text': 'Add a client before importing scanned invoices: each client has their own folder.',
    'scans.no_client.add': 'Add a client',
    'scans.last_import': 'Last import: {date}',
    'scans.folder_empty': 'No documents yet',
    'scans.search_label': 'Search for a client',
    'scans.search_placeholder': 'Search for a client…',
    'scans.folders': '{count} folders',
    'scans.folders.one': '{count} folder',
    'scans.folders.many': '{count} folders',
    'scans.no_match': 'No client matches this search.',

    // ── client view ──
    'scans.dropzone': 'Drop zone',
    'scans.drop_more': 'Drop more scans here',
    'scans.drop_here': 'Drag your invoices here',
    'scans.drop_hint': 'PDF or photos (PNG, JPG, HEIC…), several at once',
    'scans.browse': 'Browse',
    'scans.count': '{count} scanned invoices',
    'scans.count.one': '{count} scanned invoice',
    'scans.count.many': '{count} scanned invoices',
    'scans.open_named': 'Open {name}',

    // ── upload ──
    'scans.percent': '{value}%',
    'scans.upload_failed': 'Upload failed',
    'scans.only_pdf_images': 'Only PDFs and images are accepted.',
    'scans.done': 'Done',
    'scans.failed': 'Failed',
    'scans.file_error': '{name}: {message}',
    'scans.imported': '{count} documents imported',
    'scans.imported.one': '{count} document imported',
    'scans.imported.many': '{count} documents imported',
    'scans.delete.title': 'Delete document',
    'scans.delete.desc': 'Delete this scanned invoice?',
    'scans.deleted': 'Document deleted',
  };
});
