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

    // ── loading, errors and database reset ──
    'a11y.loading': 'Loading',
    'error.server': 'Server error',
    'error.network': 'Cannot reach the server',
    'error.generic': 'Error',
    'load.failed': 'Loading failed',
    'load.failed_note': 'Your data was not changed, it is just not displayed.',
    'load.failed_toast': 'Loading the data failed: {error}',
    'db.reset.title': 'Reset the database',
    'db.reset.desc': 'Delete all clients and all invoices? This cannot be undone.',
    'db.reset.confirm': 'Delete everything',
    'db.reset.done': 'Database reset',
    'boot.pdf_disabled': 'PDF export is disabled: install LibreOffice (free) to enable it. Excel export works normally.',

    // ── more shared actions ──
    'action.download_excel': 'Download Excel',
    'action.download_pdf': 'Download PDF',
    'action.download': 'Download',
    'action.open': 'Open',
    'action.create_invoice': 'Create an invoice',
    'action.mark_paid': 'Mark paid',
    'action.mark_unpaid': 'Mark unpaid',
    'action.mark_paid_tip': 'Mark as paid',
    'action.mark_unpaid_tip': 'Mark as unpaid',

    // ── payment status ──
    'status.paid': 'Paid',
    'status.unpaid': 'Unpaid',
    'status.partial': 'Partial',
    'toast.marked_paid': 'Invoice marked as paid',
    'toast.marked_unpaid': 'Invoice marked as unpaid',
    'toast.close': 'Dismiss notification',
    'dialog.prompt_title': 'Enter a value',
    'sidebar.expand': 'Expand menu',
    'nav.invoice_no': 'Invoice {number}',

    // ── table columns shared by Accueil and Historique ──
    'col.number': 'No.',
    'col.client': 'Client',
    'col.date': 'Date',
    'col.amount': 'Amount',
    'col.status': 'Status',
    'col.actions': 'Actions',
    'invoice.actions': 'Actions for invoice {number}',
    'summary.invoices': 'Invoices',
    'summary.total': 'Total invoiced',
    'summary.unpaid': 'Unpaid balance',
    'filter.all_clients': 'All clients',
    'filter.all': 'All',
    'filter.paid': 'Paid',
    'filter.unpaid': 'Unpaid',
    'filter.partial': 'Partially paid',

    // ── command palette ──
    'cmd.group.recent': 'Recent',
    'cmd.group.navigation': 'Navigation',
    'cmd.group.actions': 'Actions',
    'cmd.group.search': 'Search',
    'cmd.placeholder': 'Search for a page, an action, an invoice…',
    'cmd.results': 'Results',
    'cmd.hint.navigate': 'navigate',
    'cmd.hint.open': 'open',
    'cmd.hint.close': 'close',
    'cmd.key.escape': 'Esc',
    'cmd.empty': 'No results for “{query}”',
    'cmd.count': '{count} results',
    'cmd.count.one': '{count} result',
    'cmd.count.many': '{count} results',
    'cmd.invoice': 'Invoice {number}',
    'cmd.receipt': 'Receipt {ref}',
    'cmd.no_ref': 'no number',
    'cmd.client': 'Client',
    'cmd.act.theme': 'Toggle theme',
    'cmd.act.sidebar': 'Show / hide the sidebar',
    'cmd.act.push': 'Send data to GitHub',
    'cmd.act.pull': 'Get data from GitHub',
    'cmd.kw.home': 'home dashboard overview',
    'cmd.kw.clients': 'clients customers',
    'cmd.kw.facture': 'create invoice new',
    'cmd.kw.history': 'invoices history',
    'cmd.kw.scans': 'scan documents scanned',
    'cmd.kw.payments': 'payments receipts',
    'cmd.kw.settings': 'settings preferences configuration',
    'cmd.kw.new': 'create add',
    'cmd.kw.theme': 'light dark theme appearance',
    'cmd.kw.lang': 'language langue english french en fr bilingual',
    'cmd.kw.sidebar': 'sidebar menu collapse',
    'cmd.kw.push': 'sync upload send',
    'cmd.kw.pull': 'sync download receive',
  };
});