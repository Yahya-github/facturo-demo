# Paiements tab — proofs of payment

Import a customer's proof of payment (e.g. a quittance listing the billets it
pays), link each listed billet to an invoiced billet, and mark invoices paid.
Code: `facturo/api/payments.py`, `facturo/payments/` (`pdf_text`, `parser`,
`matcher`, `store`).

## Import (`POST /api/paiements`, one file per request)

1. Checks: not empty, ≤ 25 MB, bytes start with `%PDF-` (the extension is not
   checked). Failures → 400 with a French message.
2. `pdf_text.extract_text()` reads the PDF text layer with pypdfium2. No text
   layer (a scan), a password or an unreadable file → 400 in French. No OCR/AI.
3. `parser.parse()` reads émetteur, reference, date (`22-09-2026` or
   `July 19, 2026`), sous-total, TPS, TVQ, escompte, total and billet rows
   (number, date, plate, quantity, price, amount).
4. A bill addressed **to** the company (`COMPANY_NAME` in `facturo/brand.py`) is refused with **422** and nothing is stored:
   > Ce document est une facture adressée à Demo Transport Inc., pas une
   > preuve de paiement. Seules les preuves de paiement peuvent être importées.

   It is detected when the text names the company, no billet row was found and no
   payment wording appears (billet rows always win).
5. The PDF is saved as `paiements/<32 hex>.pdf` under the data folder (synced);
   the original file name is kept in `nom_original`. Then every row is matched
   (below) and paid state is recomputed, in one transaction. If storing fails,
   the saved file is removed.

The UI imports several PDFs at once by calling the endpoint once per file.

## Matching (`matcher.match_ligne`)

Keys, in order:
1. **Billet number** — every wrap candidate the parser produced is tried. If the
   same number exists on several invoices, date + plate + quantity break the tie.
2. **Date + plate + quantity** (±0.01 h) when no number matches.

Price, amount and client are never keys. A billet already linked to another
payment is reported as a duplicate, never re-linked.

## Statuses

Per row (`statut`): `lie` (UI "Lié"), `non_lie` (UI "À vérifier", with ranked
candidates: ambiguous number, same plate, same date), `doublon` (UI "Doublon",
with the holding payment). Only `lie` rows store a link; the others are
computed at read time.

Per payment (`statut_global`, list filter): `a_verifier` if any row is not `lie`,
`complet` if every row is `lie`, `partiel` only when the payment has no rows.

## Auto-paid rules (`store._recompute_paid`)

Run in the same transaction as every link change (import, add row, link, unlink,
delete row, delete payment, invoice edit):
- all billets of an invoice linked and `paye = 0` → `paye = 1, paye_auto = 1`;
- coverage lost and `paye_auto = 1` → `paye = 0, paye_auto = 0`;
- `paye = 1, paye_auto = 0` (paid by hand) is never changed.

The manual toggle (`PATCH /api/factures/{id}/paye`) always sets `paye_auto = 0`.
A manual "non payée" is therefore not permanent: the next link change that
completes coverage marks the invoice paid automatically.

## Invoice edits

Links are positional (`billet_index`). After `PUT /api/factures/{id}` rewrites
billets (including a split into several invoices), `relink_after_invoice_edit()`
re-seats each link on the billet it pointed at (first by that billet's previous
number/date/plate/quantity, then by what the payment row says). A billet that
no longer exists is unlinked; paid state is recomputed for every touched
invoice. The edit and the relink commit in one transaction.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/paiements` | Import one PDF (multipart `file`) |
| GET | `/api/paiements` | All payments, newest first, with `statut_global` and row counts (filtering is client-side) |
| GET | `/api/paiements/file/{name}` | The stored PDF |
| GET | `/api/paiements/{id}` | Header + rows with status and candidates |
| PUT | `/api/paiements/{id}` | Edit header fields (émetteur, reference, date, amounts, notes) |
| DELETE | `/api/paiements/{id}` | Delete payment, its rows and its PDF |
| POST | `/api/paiements/{id}/lignes` | Add a row by billet number (`numero_billet`) |
| PUT | `/api/paiements/lignes/{ligne_id}` | Link (`facture_id` + `billet_index`) or unlink (`facture_id: null`); 409 if the billet is held by another payment |
| DELETE | `/api/paiements/lignes/{ligne_id}` | Delete a row |
| GET | `/api/factures/{id}/paiements` | Per-billet paid state of one invoice |

## UI

- List: search box (émetteur, quittance number, file) and status filter
  Tous / À vérifier / Partiels / Complets; import button (file picker, several PDFs).
- Detail: editable header, amounts, rows with status, "N° de billet" field to add
  a row, link picker (invoice then billet).
- Invoice form: a paid billet shows "Payé — Quittance <reference>".

Tests: `tests/test_payment_parser.py`, `test_payment_matcher.py`,
`test_payment_api.py`, `test_payment_api_errors.py`, `test_payment_relink.py`,
`tests/e2e/test_payments.py`. Tests on real sample PDFs skip unless the gitignored
`tests/fixtures/payments/pdf/` files are present.
