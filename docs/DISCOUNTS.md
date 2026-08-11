# Discounts and totals

All totals come from `facturo/invoicing/discounts.py`. The browser preview
(`facturo/web/static/js/discounts.js`) mirrors it formula for formula;
`node tests/js/discounts.test.mjs` checks both against `tests/fixtures/discount_cases.json`.

Billets and invoices each carry `remise_pct` (percent) and `remise_montant` (dollars).
Discounts always apply before taxes.

## Billet line

```
gross = quantite × taux
net   = max(0, gross − gross × remise_pct / 100 − remise_montant)
```

The percent is a share of the gross; the dollar amount comes off after it.

**Credit lines (negative billets) — pending code change.** Intended rule: a billet
whose gross is negative is a credit; it keeps its value as entered and receives no
discount. Status: not yet in the code at `v2` `ad9fdf8`, where `billet_net()`
clamps a negative line to 0. Update this section when the change lands.

## Invoice

```
sous_total            = Σ billet net
remise_pct_amount     = clamp(sous_total × remise_pct / 100, 0, sous_total)
after_pct             = sous_total − remise_pct_amount
remise_montant_amount = clamp(remise_montant, 0, after_pct)
base_taxable          = after_pct − remise_montant_amount
tps   = base_taxable × 0.05
tvq   = base_taxable × 0.09975
total = base_taxable + tps + tvq          (TOTAL DÛ)
```

Nothing goes below zero, and `sous_total − the two REMISE amounts = base_taxable`
exactly, so the printed invoice adds up.

**Split by chantier — pending code change.** A client flagged `separer_chantiers`
gets one invoice per chantier from one submission. Intended rule: the invoice
percentage applies to each generated invoice, the fixed invoice amount to the
first generated invoice only. Status: at `v2` `ad9fdf8`,
`POST /api/factures/generate` still passes both the percent and the fixed amount
to every generated invoice.

## Excel / PDF

- Billet row: the TOTAL column shows the net; when a billet has a discount, its
  description gets a line such as `Remise 10 % + 50.00 $ : -150.00 $`.
- Under `SOUS-TOTAL:` the invoice shows `REMISE (X %):` and/or `REMISE:` (fixed
  amount), each only when it removes something, then TVQ, TPS, `TOTAL DÛ`.
- The PDF is the same workbook converted by LibreOffice (`convert_to_pdf`).

## Legacy v1 discounts (automatic, once)

v1 stored one `remise_type` (`"percent"` | `"montant"`) + `remise_valeur` per
billet and per invoice. `normalize_discount()` reads them when both v2 fields are
empty. When a database below schema 2 is migrated, `migrate_legacy_discounts()`:

1. moves each billet's legacy discount into its v2 fields;
2. for a legacy invoice-level **fixed** amount: v1 applied it in full to every
   billet (clamped to that billet's net), so the migration adds
   `min(amount, billet net)` to each billet's `remise_montant` instead of keeping
   one invoice-level amount;
3. moves a legacy invoice percent into the invoice's `remise_pct`;
4. clears the legacy fields, so a second run changes nothing.

`python -m facturo.tools.migrate_check <data.db>` migrates a temporary copy and
fails if the sum of all invoice totals changes by more than 0.01 $.
`scripts/release.sh` runs it on `data/data.db` when that file exists.

## Tests

`tests/test_discounts.py`, `tests/test_discount_migration.py`,
`tests/test_discount_api.py`, and `tests/js/discounts.test.mjs` (run with `node`;
neither pytest nor CI runs it).
