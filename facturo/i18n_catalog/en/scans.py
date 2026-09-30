"""Paper-billet scans (api/scans.py).

Upload guards reuse `err.file_empty`, `err.file_too_large` and
`err.unsupported_format` from errors.py.
"""

MESSAGES = {
    "err.scan_save_failed": "The document could not be saved; nothing was kept. Try again.",
}
