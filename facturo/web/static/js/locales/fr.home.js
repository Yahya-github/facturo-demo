// French copy for the Accueil page and its charts. Same keys as the other language, in the same order.
(function (root, factory) {
  const dict = factory();
  if (typeof module === 'object' && module.exports) { module.exports = dict; return; }
  if (root.ui && root.ui.i18n) root.ui.i18n.define('fr', dict);
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  return {

    // ── page ──
    'home.subtitle': "Vue d'ensemble de la facturation de {company}",
    'home.greet.morning': 'Bonjour',
    'home.greet.evening': 'Bonsoir',
    'home.greeting': '{greeting}, {date}',
    'home.hero.title': 'Prêt à facturer votre prochaine livraison\u00a0?',
    'home.hero.text': 'Sélectionnez un client, ajoutez les billets et générez le fichier Excel en un clic.',

    // ── stat cards ──
    'home.stat.clients': 'Clients',
    'home.stat.invoices': 'Factures',
    'home.hint.clients_active': '{count} avec factures',
    'home.hint.no_clients': 'Aucun client',
    'home.hint.invoices_in': '{count} factures en {month}',
    'home.hint.invoices_in.one': '{count} facture en {month}',
    'home.hint.invoices_in.many': '{count} factures en {month}',
    'home.hint.no_invoices': 'Aucune facture',
    'home.hint.all_invoices': 'Toutes factures confondues',
    'home.hint.pending': '{count} factures en attente',
    'home.hint.pending.one': '{count} facture en attente',
    'home.hint.pending.many': '{count} factures en attente',
    'home.hint.all_settled': 'Tout est réglé',
    'home.trend.stable': 'Stable vs {month}',
    'home.trend.vs': '{change} vs {month}',
    'home.trend.pct': '{sign}{value} %',

    // ── charts and recent invoices ──
    'home.chart.monthly.title': 'Facturé par mois',
    'home.chart.monthly.desc': 'Six derniers mois de facturation',
    'home.chart.split.title': 'Payées et impayées',
    'home.chart.split.desc': 'Répartition du montant facturé',
    'home.chart.top.title': 'Meilleurs clients',
    'home.chart.top.desc': 'Classés par montant facturé',
    'home.chart.aria': '{title} : {items}',
    'home.chart.col_month': 'Mois',
    'home.chart.col_total': 'Total',
    'home.chart.col_invoices': 'Factures',
    'home.chart.col_status': 'Statut',
    'home.chart.col_client': 'Client',
    'home.chart.paid': 'Payées',
    'home.chart.unpaid': 'Impayées',
    'home.chart.paid_label': 'payé',
    'home.chart.no_data': 'Aucune donnée',
    'home.chart.unknown_client': 'Client inconnu',
    'home.chart.count': '{count} factures',
    'home.chart.count.one': '{count} facture',
    'home.chart.count.many': '{count} factures',
    'home.recent.title': 'Dernières factures',
    'home.recent.desc': 'Les plus récentes, avec actions rapides',
    'home.recent.filter': 'Filtrer les dernières factures',
    'home.recent.empty': 'Aucune facture pour ces filtres.',
    'home.view_all': 'Voir tout',
    'home.empty.title': 'Aucune facture pour le moment',
    'home.empty.text': 'Créez votre première facture : vos statistiques et graphiques apparaîtront ici.',
  };
});
