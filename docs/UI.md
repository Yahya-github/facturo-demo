# Interface

The UI is vanilla JavaScript and CSS served as static files, with no build
step, no npm dependency at runtime and no network access. It follows the
shadcn/ui design language (tokens, radii, component anatomy) and is written by
hand. Fonts and icons are bundled, so it works offline.

Screenshots: [`docs/screenshots/`](screenshots/), regenerated with
`python scripts/screenshots.py`. Fictional data: `python scripts/seed_demo.py`.
Text and languages: [I18N.md](I18N.md). Pages take their text from `t()`
rather than writing it inline.

## Design tokens

Defined in `facturo/web/static/css/tokens.css` as CSS custom properties. Light
is the default on `:root`. Dark is applied by `:root[data-theme="dark"]` and,
for the "system" mode, by a `prefers-color-scheme` media query. Never hardcode
a colour in a component: use a token, so both themes stay correct.

| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `--background` | `#ffffff` | `#09090b` | Page and input ground |
| `--foreground` | `#09090b` | `#fafafa` | Body text |
| `--card`, `--popover` | `#ffffff` | dark surface | Cards, menus, dialogs |
| `--primary` | `#1a4d2e` | `#4ea672` | Buttons, links, active states |
| `--primary-foreground` | `#fafafa` | `#04150b` | Text on `--primary` |
| `--muted` | `#f4f4f5` | `#1c1c1f` | Quiet surfaces |
| `--muted-foreground` | `#52525b` | `#adadb5` | Secondary text (4.5:1 or better) |
| `--accent` | `#f0f4f1` | `#1f2622` | Hover surfaces |
| `--destructive` | `#dc2626` | dark variant | Delete actions |
| `--border`, `--input` | `#e4e4e7`, `#d4d4d8` | `#27272a`, `#3a3a3f` | Borders, field outlines |
| `--ring` | `#2f7d4a` | `#4ea672` | Focus ring |
| `--gold`, `--gold-light` | `#d4a853`, `#e8c97a` | same family | Highlight accent, avatars |
| `--success-*`, `--danger-*`, `--info-*`, `--gold-*` | fg / bg / border sets | dark sets | Status chips, alerts |
| `--chart-1` … `--chart-5` | green, gold, mid green, brown, grey | lighter variants | Charts |
| `--sidebar-*` | sidebar surface, text, accent | dark sidebar | Sidebar |
| `--brand-deep`, `--brand-deep-2`, `--on-brand` | `#1a4d2e`, `#256b41`, `#fafafa` | same | Hero and invoice total card (always dark green) |
| `--radius` (+ `sm`, `md`, `lg`, `xl`, `full`) | `0.625rem` | same | Shape |
| `--shadow-xs` … | soft shadows | stronger shadows | Elevation |

Typography is Geist (sans) and Geist Mono, self-hosted from
`static/fonts/` (`font-display: swap`, latin and latin-ext subsets, licence in
`OFL.txt`). Sizes come from the `--text-xs` … `--text-3xl` tokens.

## File map

### `facturo/web/static/css/`

| File | Role |
|------|------|
| `tokens.css` | Fonts, all tokens, light and dark palettes |
| `base.css` | Reset, typography, focus ring, scrollbars, icons, `kbd` |
| `shell.css` | App shell: floating panel, header, breadcrumb, mobile layout |
| `sidebar.css` | Sidebar, collapsed rail, mobile drawer |
| `background.css` | Decorative backdrop (grid, blobs, pauses under reduced motion) |
| `components.css` | Buttons, inputs, selects, badges, cards, tables |
| `components-overlays.css` | Dialogs, sheets, menus, popovers, tooltips, toasts, tabs |
| `combobox.css` | Autocomplete and combobox panels |
| `charts.css` | SVG charts and their tooltips |
| `motion.css` | Transitions, spotlight glow, skeletons, `prefers-reduced-motion` |
| `home.css`, `pages*.css`, `payments.css`, `filters.css`, `facture-dialogs.css` | One file per page or feature |
| `app.css` | Older shared rules still in use (nav, status chips, billet cards) |

### `facturo/web/static/js/ui/`

Every primitive hangs off one global `ui` namespace (`ui.h`, `ui.dialog`,
`ui.menu`, `ui.toast`, …). Pure logic lives in files without DOM access so
node can test it.

| File | Role |
|------|------|
| `dom.js` | `ui.h` element builder, `ui.uid`, `ui.focusable` |
| `dialog.js` | Dialog, AlertDialog, PromptDialog, Sheet on one focus trap |
| `menu.js` | DropdownMenu and ContextMenu (roving tabindex, typeahead, submenus) |
| `popover.js`, `tooltip.js`, `floating.js`, `position.js` | Floating layers; `position.js` is pure placement maths |
| `tabs.js` | Accessible tabs from `data-tab` / `data-tab-panel` |
| `toast.js` | Sonner-style toasts |
| `command.js`, `fuzzy.js`, `keys.js` | Command palette, fuzzy matcher, keyboard helpers |
| `sidebar.js`, `shell.js` | Collapsible sidebar, workspace switcher, breadcrumb, theme buttons |
| `theme.js` | Light, dark, system; loaded in `<head>` to avoid a flash |
| `chart.js`, `chart-data.js` | SVG charts and their data shaping |
| `countup.js`, `spotlight.js`, `backdrop.js`, `avatar.js` | Motion and decoration |
| `hydrate.js` | One `MutationObserver` that wires tabs, tooltips and menus after each re-render |

`static/js/icons.js` is the Lucide (ISC) icon registry.

## How to add things

### A component

1. Put the markup helper in a `ui/*.js` file as an IIFE that attaches to `ui`
   (copy the header comment style of `popover.js`).
2. Put its CSS in `components.css` or `components-overlays.css`, using tokens
   only.
3. Add the `<script>` tag to `templates/index.html` after its dependencies and
   bump the `?v=` query string of every file you changed (cache busting).
4. Cover the keyboard path with a Playwright test in `tests/e2e/`. Pure logic
   gets a node test in `tests/js/`.

### An icon

Find the icon on [lucide.dev](https://lucide.dev), copy the inner SVG markup
(the `<path>` / `<circle>` elements, without the `<svg>` wrapper) into the
`PATHS` object in `static/js/icons.js` under its Lucide name, then call
`icon('name')`. Sizes: `xs` 14, `sm` 16, default 18, `lg` 24, `xl` 40 px.
Bump the `icons.js` version in `index.html`.

### A theme colour

1. Add the variable to the light block (`:root`) **and** to both dark blocks
   (`:root[data-theme="dark"]` and the `prefers-color-scheme` media query) in
   `tokens.css`. Keep the two dark blocks identical.
2. Check the contrast of any text using it: 4.5:1 for normal text, 3:1 for
   large text and UI borders, in both themes.
3. Use `var(--your-token)` in components. Do not use raw hex values.

## Test contract

E2E tests depend on these hooks. Renaming one means updating the tests.

- Ids: `#sidebar`, `#sidebar-toggle`, `#skip-link`, `#main-content`,
  `#theme-toggle`, `#theme-cycle`, `#ui-tooltip`, `#tb`, `#flt-q`,
  `#flt-client`, `#flt-statut`, `#flt-tri`, `#flt-du`, `#flt-au`,
  `#fac-client`, `#fac-numero`, `#fac-date`, `#b{n}-date|chantier|plaque|numero|quantite|taux`,
  `#payment-detail`, `#payments-list`, `#scan-dropzone`, `#pay-dropzone`,
  `#update-card`, `#db-newer-banner`, `#c-bar`, `#c-hbar`.
- Attributes: `data-page` (nav buttons), `data-tab` / `data-tab-panel`,
  `data-theme-set`, `data-tip` (tooltip text), `data-row-menu`,
  `data-facture-id`, `data-fac-total`, `data-cmd-open` (palette trigger).
- Classes: `.nav-btn`, `.command-overlay`, `.command-input`, `.command-item`,
  `.modal-overlay`, `.sheet-right`, `.toast-container`, `.toast-error`,
  `.toast-action`, `.toast-close`, `.toast-progress`, `.tabs-indicator`,
  `.chart-tip`, `.chart-hit`, `.ac-panel`, `.fac-checks`, `.fac-actionbar`,
  `.app-backdrop`, `.payment-row`, `.ligne-row`, `.flt-summary`, `.flt-empty`.
- Accessible names: the skip link text ("Aller au contenu"), exactly one `h1`
  per page that matches the breadcrumb, and the labelled landmarks.

## Accessibility

- Skip link to `#main-content`; one `h1` per page; `header`, `nav`, `main`
  landmarks with labels.
- Every icon-only button has an `aria-label`; tooltips come from `data-tip`.
- Dialogs trap focus, close on Escape and return focus to the opener. Menus use
  a roving tabindex with typeahead. Toasts are announced through an
  `aria-live` region (errors use `role="alert"`).
- Charts have text alternatives: values are reachable without hover.
- `prefers-reduced-motion` stops the backdrop, count-up, spotlight and
  transitions, and the app runs no animation-frame loop.
- Contrast was checked with axe-core 4 on all seven pages, both themes, at
  1440 and 390 px: no serious or critical violations. Text on gradients (which
  axe reports as "needs review") was checked by sampling pixels; the muted
  foreground and the invoice checklist colours were raised as a result.
  `tests/e2e/test_accessibility.py` guards the fixes.
- Layout has no horizontal scroll at 390, 768 and 1440 px (e2e test).

## Performance

- No build step and no third-party runtime: about 160 KB of CSS and plain
  `<script>` tags, all cacheable.
- Fonts are variable woff2 subsets with `font-display: swap`.
- Animation favours `transform` and `opacity`, and pauses under
  `prefers-reduced-motion`.
- Everything is served from `127.0.0.1`. An e2e test blocks the network and
  checks the app still loads, so no CDN can creep back in.
