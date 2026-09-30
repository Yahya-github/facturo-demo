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
  };
});