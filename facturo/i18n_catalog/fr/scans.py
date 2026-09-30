"""Scans de billets papier (api/scans.py).

Les garde-fous d'envoi réutilisent `err.file_empty`, `err.file_too_large` et
`err.unsupported_format` de errors.py.
"""

MESSAGES = {
    "err.scan_save_failed": (
        "Le document n'a pas pu être enregistré ; rien n'a été conservé. Réessayez."
    ),
}
