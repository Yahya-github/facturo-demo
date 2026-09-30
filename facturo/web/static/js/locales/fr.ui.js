// French shell vocabulary. Same keys as en.ui.js, in the same order.
//
// French is what this app has always shown, so these are the existing labels
// rather than a reworded set; keep the two files in step when adding a key, and
// let a missing key fall back to English instead of blanking the interface.
(function (root, factory) {
  const dict = factory();
  if (typeof module === 'object' && module.exports) { module.exports = dict; return; }
  if (root.ui && root.ui.i18n) root.ui.i18n.define('fr', dict);
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  return {
    // ── landmarks and accessible names ─────────────────────
    'a11y.skip_link': 'Aller au contenu',
    'a11y.mobile_bar': 'Barre mobile',
    'a11y.open_menu': 'Ouvrir le menu',
    'a11y.search': 'Rechercher',
    'a11y.sidebar': 'Barre latérale',
    'a11y.main_nav': 'Navigation principale',
    'a11y.breadcrumb': "Fil d'Ariane",
    'a11y.command_palette': 'Palette de commandes',

    // ── workspace switcher ──────────────────────────────────
    'ws.workspace': 'Espace de travail',

    // ── sidebar navigation ─────────────────────────────────
    'nav.group.billing': 'Facturation',
    'nav.group.documents': 'Documents',
    'nav.group.system': 'Système',
    'nav.home': 'Accueil',
    'nav.clients': 'Clients',
    'nav.facture': 'Nouvelle facture',
    'nav.history': 'Historique',
    'nav.scans': 'Factures scannées',
    'nav.payments': 'Paiements',
    'nav.settings': 'Paramètres',

    // ── topbar ─────────────────────────────────────────────
    'search.placeholder': 'Rechercher…',
    'sidebar.collapse': 'Réduire le menu',
    'update.available': 'Mise à jour disponible',

    // ── theme control ──────────────────────────────────────
    'theme.group': 'Thème',
    'theme.light': 'Thème clair',
    'theme.dark': 'Thème sombre',
    'theme.system': 'Thème du système',
    'theme.light_short': 'Clair',
    'theme.dark_short': 'Sombre',
    'theme.system_short': 'Système',
    'theme.toggle': 'Changer de thème',

    // ── language control ───────────────────────────────────
    'lang.group': 'Langue',
    'lang.en': 'Anglais',
    'lang.fr': 'Français',
    'lang.card_title': 'Langue',
    'lang.card_desc': "Langue de l'interface. Les dates, les montants et les pluriels suivent.",
    'lang.action': 'Langue / Language',

    // ── shared actions ─────────────────────────────────────
    'action.cancel': 'Annuler',
    'action.confirm': 'Confirmer',
    'action.save': 'Enregistrer',
    'action.close': 'Fermer',
    'action.add': 'Ajouter',
    'action.edit': 'Modifier',
    'action.delete': 'Supprimer',

    // ── toast verbs ────────────────────────────────────────
    'toast.saved': 'Enregistré',
    'toast.deleted': 'Supprimé',
    'toast.loaded': 'Chargé',
    'toast.error': "Une erreur s'est produite",
    'toast.retry': 'Réessayer',

    // ── empty states ───────────────────────────────────────
    'empty.title': 'Rien pour le moment',
    'empty.results': 'Aucun résultat',
    'empty.choose_client': 'Choisissez un client pour continuer',

    // ── loading, errors and database reset ──
    'a11y.loading': 'Chargement',
    'error.server': 'Erreur serveur',
    'error.network': 'Connexion au serveur impossible',
    'error.generic': 'Erreur',
    'load.failed': 'Chargement échoué',
    'load.failed_note': "Vos données n'ont pas été modifiées, elles ne sont simplement pas affichées.",
    'load.failed_toast': 'Chargement des données échoué : {error}',
    'db.reset.title': 'Réinitialiser la base de données',
    'db.reset.desc': 'Supprimer tous les clients et toutes les factures? Cette action est irréversible.',
    'db.reset.confirm': 'Tout supprimer',
    'db.reset.done': 'Base de données réinitialisée',
    'boot.pdf_disabled': "Export PDF désactivé : installez LibreOffice (gratuit) pour l'activer. L'export Excel fonctionne normalement.",

    // ── more shared actions ──
    'action.download_excel': 'Télécharger Excel',
    'action.download_pdf': 'Télécharger PDF',
    'action.download': 'Télécharger',
    'action.open': 'Ouvrir',
    'action.create_invoice': 'Créer une facture',
    'action.mark_paid': 'Marquer payée',
    'action.mark_unpaid': 'Marquer non payée',
    'action.mark_paid_tip': 'Marquer comme payée',
    'action.mark_unpaid_tip': 'Marquer comme non payée',

    // ── payment status ──
    'status.paid': 'Payée',
    'status.unpaid': 'Non payée',
    'status.partial': 'Partielle',
    'toast.marked_paid': 'Facture marquée payée',
    'toast.marked_unpaid': 'Facture marquée non payée',
    'toast.close': 'Fermer la notification',
    'dialog.prompt_title': 'Saisir une valeur',
    'sidebar.expand': 'Développer le menu',
    'nav.invoice_no': 'Facture {number}',

    // ── table columns shared by Accueil and Historique ──
    'col.number': 'N°',
    'col.client': 'Client',
    'col.date': 'Date',
    'col.amount': 'Montant',
    'col.status': 'Statut',
    'col.actions': 'Actions',
    'invoice.actions': 'Actions de la facture {number}',
    'summary.invoices': 'Factures',
    'summary.total': 'Total facturé',
    'summary.unpaid': 'Solde impayé',
    'filter.all_clients': 'Tous les clients',
    'filter.all': 'Toutes',
    'filter.paid': 'Payées',
    'filter.unpaid': 'Non payées',
    'filter.partial': 'Partiellement payées',

    // ── command palette ──
    'cmd.group.recent': 'Récents',
    'cmd.group.navigation': 'Navigation',
    'cmd.group.actions': 'Actions',
    'cmd.group.search': 'Recherche',
    'cmd.placeholder': 'Rechercher une page, une action, une facture…',
    'cmd.results': 'Résultats',
    'cmd.hint.navigate': 'naviguer',
    'cmd.hint.open': 'ouvrir',
    'cmd.hint.close': 'fermer',
    'cmd.key.escape': 'Échap',
    'cmd.empty': 'Aucun résultat pour « {query} »',
    'cmd.count': '{count} résultats',
    'cmd.count.one': '{count} résultat',
    'cmd.count.many': '{count} résultats',
    'cmd.invoice': 'Facture {number}',
    'cmd.receipt': 'Quittance {ref}',
    'cmd.no_ref': 'sans n°',
    'cmd.client': 'Client',
    'cmd.act.theme': 'Basculer le thème',
    'cmd.act.sidebar': 'Afficher / masquer le menu latéral',
    'cmd.act.push': 'Envoyer les données vers GitHub',
    'cmd.act.pull': 'Recevoir les données de GitHub',
    'cmd.kw.home': 'accueil tableau de bord',
    'cmd.kw.clients': 'clients',
    'cmd.kw.facture': 'creer facture',
    'cmd.kw.history': 'factures historique',
    'cmd.kw.scans': 'scan documents',
    'cmd.kw.payments': 'paiements quittances',
    'cmd.kw.settings': 'reglages configuration',
    'cmd.kw.new': 'creer ajouter',
    'cmd.kw.theme': 'clair sombre dark light',
    'cmd.kw.lang': 'langue language english french en fr bilingue',
    'cmd.kw.sidebar': 'barre laterale sidebar',
    'cmd.kw.push': 'sync synchronisation envoyer',
    'cmd.kw.pull': 'sync synchronisation recevoir',
  };
});