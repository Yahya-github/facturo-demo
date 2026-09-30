"""English messages, split by the module that raises them.

i18n.CATALOG wants one flat MESSAGES, but a single dict would run past the
400-line ceiling. The per-area files are merged here, and tests/test_i18n.py
checks that en and fr carry the same keys and the same placeholders.
"""

from facturo.i18n_catalog.en import (
    ai,
    clients,
    errors,
    factures,
    known_values,
    payments,
    scans,
    settings,
    sync,
    updates,
)

_GROUPS = (
    errors.MESSAGES,
    clients.MESSAGES,
    factures.MESSAGES,
    payments.MESSAGES,
    scans.MESSAGES,
    settings.MESSAGES,
    ai.MESSAGES,
    known_values.MESSAGES,
    sync.MESSAGES,
    updates.MESSAGES,
)

MESSAGES: dict[str, str] = {key: text for group in _GROUPS for key, text in group.items()}
