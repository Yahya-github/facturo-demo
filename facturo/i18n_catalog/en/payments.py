"""Importing payment proofs and linking them to a ticket (invoice -> payment).

The PDF import refusals come from payments/pdf_text.py; the linking refusals
from payments/store.py.
"""

MESSAGES = {
    # Import
    "err.bill_refused": (
        "This document is an invoice addressed to {company}, not a proof of payment. "
        "Only proofs of payment can be imported."
    ),
    "err.payment_save_failed": (
        "Saving the file failed; nothing was imported. Check the disk space and try again."
    ),

    # Reading the proof (payments/pdf_text.py)
    "err.payment_pdf_protected": (
        "This PDF is password protected. Remove the protection and import it again."
    ),
    "err.payment_pdf_unreadable": "This file is not a readable PDF.",
    "err.payment_pdf_no_text": (
        "This PDF has no readable text (scanned document?). "
        "Import the original PDF produced by the issuer's software."
    ),

    # Linking to a ticket
    "err.payment_not_found": "Payment not found",
    "err.payment_line_not_found": "Line not found",
    "err.ticket_number_required": "Ticket number is required",
    "err.not_a_ticket_number": (
        "This is not a valid ticket number (a project number, for example)."
    ),
    "err.choose_ticket": "Choose a ticket",
    "err.ticket_not_on_invoice": "This ticket does not exist on this invoice",
    "err.ticket_already_linked": "This ticket is already linked to payment #{payment_id}.",
}
