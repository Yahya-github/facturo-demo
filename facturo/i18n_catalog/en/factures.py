"""Invoice generation, editing, deletion and PDF export.

The `err.stored_*` fragments are lower-case on purpose: api/factures.py joins
them into a longer sentence, and the browser shows that whole string.
"""

MESSAGES = {
    # Lookups
    "err.invoice_not_found": "Invoice not found",

    # Generation
    "err.billet_required": "At least one ticket is required",
    "err.generate_failed": "Error while generating: {detail}",
    "err.regenerate_failed": "Error while regenerating: {detail}",
    "err.concurrent_invoice_created": (
        "Invoices were created in the meantime for this client; nothing was saved. Try again."
    ),

    # Persistence. Each of these promises the file or row is untouched.
    "err.invoice_not_saved": (
        "Invoice {numero} could not be saved to the database; "
        "no file was kept for it. Try again."
    ),
    "err.invoice_not_saved_after_edit": (
        "Invoice {numero} could not be saved to the database; "
        "it is unchanged from before the edit. Try again."
    ),
    "err.invoice_not_deleted": (
        "Invoice {numero} could not be deleted; it is still intact. Try again."
    ),

    # Already-created notices, appended after the line-level message
    "err.invoice_already_created": "Invoice already created: {numeros}.",
    "err.invoices_already_created": "Invoices already created: {numeros}.",

    # Reading the tickets back out of a stored workbook
    "err.billets_unreadable": (
        "The tickets on this invoice cannot be read. The original file has not been changed."
    ),
    "err.save_would_overwrite": "Saving now would overwrite the existing invoice.",
    "err.stored_billets_unreadable": "stored tickets unreadable",
    "err.excel_unreadable": "Excel file unreadable",
    "err.excel_not_found": "Excel file not found",

    # PDF export, via LibreOffice (invoicing/excel_generator.py)
    "err.pdf_conversion_failed": "Error while converting to PDF: {detail}",
    "invoice.soffice_missing": (
        "LibreOffice is required for PDF export but was not found. "
        "Install LibreOffice (free) from libreoffice.org, then try again. "
        "Excel export works without LibreOffice."
    ),
    "invoice.source_file_not_found": "Source file not found: {path}",
    "invoice.pdf_conversion_error": "PDF conversion failed: {detail}",
}
