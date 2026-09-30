// French copy for the Factures scannées page. Same keys as the other language, in the same order.
(function (root, factory) {
  const dict = factory();
  if (typeof module === 'object' && module.exports) { module.exports = dict; return; }
  if (root.ui && root.ui.i18n) root.ui.i18n.define('fr', dict);
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  return {

    // ── folders ──
    'scans.subtitle.pick': 'Classez vos factures numérisées par client',
    'scans.subtitle': '{count} documents, classés par client',
    'scans.subtitle.one': '{count} document, classés par client',
    'scans.subtitle.many': '{count} documents, classés par client',
    'scans.no_client.title': 'Aucun client',
    'scans.no_client.text': "Ajoutez un client avant d'importer des factures scannées : chaque client a son propre dossier.",
    'scans.no_client.add': 'Ajouter un client',
    'scans.last_import': 'Dernier import : {date}',
    'scans.folder_empty': 'Aucun document pour le moment',
    'scans.search_label': 'Rechercher un client',
    'scans.search_placeholder': 'Rechercher un client…',
    'scans.folders': '{count} dossiers',
    'scans.folders.one': '{count} dossier',
    'scans.folders.many': '{count} dossiers',
    'scans.no_match': 'Aucun client ne correspond à cette recherche.',

    // ── client view ──
    'scans.dropzone': 'Zone de dépôt',
    'scans.drop_more': "Déposez d'autres scans ici",
    'scans.drop_here': 'Glissez vos factures ici',
    'scans.drop_hint': 'PDF ou photos (PNG, JPG, HEIC…), plusieurs à la fois',
    'scans.browse': 'Parcourir',
    'scans.count': '{count} factures scannées',
    'scans.count.one': '{count} facture scannée',
    'scans.count.many': '{count} factures scannées',
    'scans.open_named': 'Ouvrir {name}',

    // ── upload ──
    'scans.percent': '{value} %',
    'scans.upload_failed': 'Échec du téléversement',
    'scans.only_pdf_images': 'Seuls les PDF et les images sont acceptés.',
    'scans.done': 'Terminé',
    'scans.failed': 'Échec',
    'scans.file_error': '{name} : {message}',
    'scans.imported': '{count} documents importés',
    'scans.imported.one': '{count} document importé',
    'scans.imported.many': '{count} documents importés',
    'scans.delete.title': 'Supprimer le document',
    'scans.delete.desc': 'Supprimer cette facture scannée ?',
    'scans.deleted': 'Document supprimé',
  };
});
