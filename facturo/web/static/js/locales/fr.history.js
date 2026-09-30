// French copy for the Historique page. Same keys as the other language, in the same order.
(function (root, factory) {
  const dict = factory();
  if (typeof module === 'object' && module.exports) { module.exports = dict; return; }
  if (root.ui && root.ui.i18n) root.ui.i18n.define('fr', dict);
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  return {

    // ── page ──
    'history.subtitle': 'Toutes les factures générées, avec recherche, filtres et actions rapides',
    'history.empty.title': 'Aucune facture',
    'history.empty.text': 'Les factures générées apparaîtront ici, avec leur statut de paiement.',

    // ── table ──
    'history.col.invoice_no': 'N° Facture',
    'history.created_on': 'Créée le {date}',
    'history.edit_invoice': 'Modifier la facture {number}',
    'history.paid_tickets': 'Billets payés',
    'history.partial_tickets': '{paid}/{total} billets',
    'history.no_match.title': 'Aucune facture ne correspond',
    'history.no_match.text': 'Modifiez la recherche ou les filtres pour élargir les résultats.',
    'history.no_match.reset': 'Réinitialiser les filtres',
    'history.pager.label': 'Pagination',
    'history.pager.info': '{from}–{to} sur {total}',
    'history.pager.prev': 'Précédent',
    'history.pager.next': 'Suivant',
    'history.pager.page': 'Page {page} / {pages}',

    // ── toolbar ──
    'history.filter.label': 'Filtrer les factures',
    'history.filter.search': 'Recherche',
    'history.filter.placeholder': 'N° facture, client, chantier, plaque, N° billet…',
    'history.filter.period': 'Période',
    'history.filter.from': 'Du',
    'history.filter.to': 'Au',
    'history.filter.presets': 'Périodes prédéfinies',
    'history.filter.sort': 'Trier par',
    'history.filter.reset': 'Réinitialiser',
    'history.sort.date_desc': 'Date (récentes)',
    'history.sort.date_asc': 'Date (anciennes)',
    'history.sort.montant_desc': 'Montant (décroissant)',
    'history.preset.month': 'Ce mois',
    'history.preset.30d': '30 derniers jours',
    'history.preset.year': 'Cette année',
    'history.preset.clear': 'Toute la période',

    // ── actions ──
    'history.delete.title': 'Supprimer la facture',
    'history.delete.desc': 'Supprimer la facture {number} ? Le fichier Excel/PDF généré sera aussi supprimé.',
    'history.deleted': 'Facture {number} supprimée',
    'history.pdf_busy': 'PDF...',
    'history.pdf_error': 'Erreur lors de la conversion PDF',
    'history.pdf_done': 'PDF téléchargé !',
  };
});
