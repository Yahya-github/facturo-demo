"""Messages français, découpés selon le module qui les lève.

i18n.CATALOG veut un seul MESSAGES, mais un dictionnaire unique dépasserait la
limite de 400 lignes. Les fichiers par domaine sont fusionnés ici, et
tests/test_i18n.py vérifie que en et fr portent les mêmes clés et les mêmes
variables.
"""

from facturo.i18n_catalog.fr import (
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
