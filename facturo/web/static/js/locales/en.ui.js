// English shell vocabulary: the sidebar, the topbar, the theme and language
// controls, the generic dialog buttons, toast verbs and empty states.
//
// Page copy lives in its own fragment per area (home, clients, history, facture,
// scans, payments, settings) — see README.md in this folder. Register through
// ui.i18n.define(); loading this file twice with a different value for one key
// logs a warning rather than letting script order decide the winner.
(function (root, factory) {
  const dict = factory();
  if (typeof module === 'object' && module.exports) { module.exports = dict; return; }
  if (root.ui && root.ui.i18n) root.ui.i18n.define('en', dict);
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  return {
    // ── landmarks and accessible names ─────────────────────
    'a11y.skip_link': 'Skip to content',
    'a11y.mobile_bar': 'Mobile bar',
    'a11y.open_menu': 'Open menu',
    'a11y.search': 'Search',
    'a11y.sidebar': 'Sidebar',
    'a11y.main_nav': 'Main navigation',
    'a11y.breadcrumb': 'Breadcrumb',
    'a11y.command_palette': 'Command palette',

    // ── workspace switcher ──────────────────────────────────
    'ws.workspace': 'Workspace',

    // ── sidebar navigation ─────────────────────────────────
    'nav.group.billing': 'Billing',
    'nav.group.documents': 'Documents',
    'nav.group.system': 'System',
    'nav.home': 'Home',
    'nav.clients': 'Clients',
    'nav.facture': 'New invoice',
    'nav.history': 'History',
    'nav.scans': 'Scanned invoices',
    'nav.payments': 'Payments',
    'nav.settings': 'Settings',

    // ── topbar ─────────────────────────────────────────────
    'search.placeholder': 'Search…',
    'sidebar.collapse': 'Collapse menu',
    'update.available': 'Update available',

    // ── theme control ──────────────────────────────────────
    'theme.group': 'Theme',
    'theme.light': 'Light theme',
    'theme.dark': 'Dark theme',
    'theme.system': 'System theme',
    'theme.light_short': 'Light',
    'theme.dark_short': 'Dark',
    'theme.system_short': 'System',
    'theme.toggle': 'Change theme',

    // ── language control ───────────────────────────────────
    // The two buttons keep their endonyms (EN / FR): a language picker that
    // renames its own options is unreadable to the people it is for.
    'lang.group': 'Language',
    'lang.en': 'English',
    'lang.fr': 'French',
    'lang.card_title': 'Language',
    'lang.card_desc': 'Interface language. Dates, amounts and plurals follow it.',
    'lang.action': 'Langue / Language',

    // ── shared actions ─────────────────────────────────────
    'action.cancel': 'Cancel',
    'action.confirm': 'Confirm',
    'action.save': 'Save',
    'action.close': 'Close',
    'action.add': 'Add',
    'action.edit': 'Edit',
    'action.delete': 'Delete',

    // ── toast verbs ────────────────────────────────────────
    'toast.saved': 'Saved',
    'toast.deleted': 'Deleted',
    'toast.loaded': 'Loaded',
    'toast.error': 'Something went wrong',
    'toast.retry': 'Try again',

    // ── empty states ───────────────────────────────────────
    'empty.title': 'Nothing here yet',
    'empty.results': 'No results',
    'empty.choose_client': 'Choose a client to continue',
  };
});