"""Errors more than one router can answer with: lookups, uploads, versions.

Keys name what failed, not which endpoint asked, so `err.client_not_found`
serves invoices, scans and payments alike.
"""

MESSAGES = {
    # Lookups
    "err.document_not_found": "Document not found",
    "err.file_not_found": "File not found",

    # Uploads
    "err.file_empty": "Empty file",
    "err.file_too_large": "File too large (25 MB maximum)",
    "err.pdf_only": "Only PDF files are accepted.",
    "err.unsupported_format": "Unsupported format. Use a PDF or an image.",

    # Storage
    "err.database_busy": (
        "The database is busy with another operation. Wait a few seconds then try again."
    ),
    "err.update_failed": "The update failed. Nothing was changed; try again.",

    # Version and platform
    "err.version_mismatch": "A version other than the expected one.",
    "err.sync_failed": "Sync error: {detail}",

    # Local-only refusals (local_guard.py)
    "guard.host_not_allowed": "Host not allowed.",
    "guard.foreign_origin": "Request from another origin refused.",
    "guard.foreign_site": "Request from another site refused.",
}
