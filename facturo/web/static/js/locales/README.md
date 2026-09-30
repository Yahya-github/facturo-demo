# locales

One fragment per language per area. The engine is `../i18n.js`; this folder only
holds flat dictionaries of UI copy.

```
locales/
├── README.md
├── en.ui.js       # shell: sidebar, topbar, controls, dialog verbs, empty states
├── fr.ui.js
├── en.home.js     # coming: page fragments, one per area
├── fr.home.js
└── …
```

## File shape

Exactly like `en.ui.js`:

```js
(function (root, factory) {
  const dict = factory();
  if (typeof module === 'object' && module.exports) { module.exports = dict; return; }
  if (root.ui && root.ui.i18n) root.ui.i18n.define('en', dict);
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  return { 'home.greeting': 'Good morning' };
});
```

The file registers itself at load, so all it has to do is return the dict. There
is no import step and no bundler. `define()` **keeps the first value** for a key
that is already registered and logs a console warning when a second file tries to
claim it with different text — a duplicate is always a copy-paste mistake, never
a question of `<script>` order, so it must not silently pick a winner.

## Naming

`<area>.<thing>`, lowercase, dotted, no capitals and no spaces:

| Area | Fragment | Example keys |
| --- | --- | --- |
| shell | `en.ui.js` | `nav.home`, `theme.dark`, `action.cancel` |
| Accueil | `en.home.js` | `home.title`, `home.empty`, `home.cards.revenue` |
| Clients | `en.clients.js` | `clients.title`, `clients.new`, `clients.empty` |
| Facture | `en.facture.js` | `facture.total`, `facture.billet.line` |
| Historique | `en.history.js` | `history.filters.q`, `history.empty` |
| Scans | `en.scans.js` | `scans.dropzone`, `scans.import` |
| Paiements | `en.payments.js` | `payments.title`, `payments.unlinked` |
| Paramètres | `en.settings.js` | `settings.tab.general`, `settings.sync.title` |

Reuse a `ui.*` key instead of adding a near-duplicate: a page that says
"Annuler" should call `t('action.cancel')`, not invent `facture.button.cancel`.

## English is the base

`en.*.js` is written first and `fr.*.js` mirrors it key for key, in the same
order. English is both the default language and the fallback, so a key missing
from French degrades to English instead of leaving a hole in the interface —
which is why an incomplete `fr` file is safe and a *missing* `en` file is not.

## Placeholders

`{name}`, substituted by `t(key, params)`:

```js
t('facture.total', { total: ui.i18n.fmtMoney(m.total) })   // 'Total  1 234,56 $'
```

An unknown `{name}` is left in place rather than blanked, so a typo shows up on
screen instead of silently eating text.

## Plurals

`tn(key, count, params)` selects on the CLDR category of the active language and
falls back to the bare `key`, so English puts the whole sentence there:

```js
// en.facture.js
'facture.billets': '{count} line items',
'facture.billets.one': '{count} line item',

// fr.facture.js
'facture.billets': '{count} lignes',
'facture.billets.one': '{count} ligne',
'facture.billets.many': '{count} lignes',
```

`fr-CA` knows `one`, `many` and `other`; `en-CA` knows `one` and `other`. Only
add the suffixes your language actually selects. `{count}` is always available.

## In markup

Two attributes, both re-applied on every render and on every language change by
the `ui.hydrate` pass registered in `i18n.js`:

```html
<h2 data-i18n="home.title"></h2>
<input data-i18n-attr="placeholder:search.placeholder,aria-label:a11y.search" />
```

Values land through `textContent` and `setAttribute`, never `innerHTML`, so a
translation can never turn into markup.

## In a template string

Escaping is the caller's job — `tests/js/util.test.mjs` fails the build on an
unescaped interpolation:

```js
`<button title="${escAttr(ui.i18n.t('facture.tip'))}">${esc(ui.i18n.t('action.save'))}</button>`
```

## Adding a key

1. Add it to `en.<area>.js` and to `fr.<area>.js`.
2. Load both in `templates/index.html`, English before French.
3. `node --test tests/js/*.test.mjs`, then `node tests/js/i18n-lint.mjs` — the
   count of hardcoded French literals should only ever go down.