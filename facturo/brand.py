"""The company this install invoices for — one setting, used everywhere.

COMPANY_NAME appears in the app title, the startup banner, the web UI and the
AI extraction wording, and it is the name the payments parser looks for to
recognise a supplier bill addressed TO the company (which is not a proof of
payment and is refused at import).

Set FACTURO_COMPANY_NAME in the environment to use another name; it is read
once, at import.
"""

import os
import re

from facturo.core.billet_fields import fold

DEFAULT_COMPANY_NAME = "Demo Transport Inc."

COMPANY_NAME: str = os.environ.get("FACTURO_COMPANY_NAME", "").strip() or DEFAULT_COMPANY_NAME

# Legal-form suffixes left off when matching the name in a document: a bill
# may say "DEMO TRANSPORT INC", "Demo Transport inc." or just "Demo Transport".
_LEGAL_SUFFIX = re.compile(r"(inc|ltd|ltee|llc|corp|enr|senc)$")


def company_key(name: str = COMPANY_NAME) -> str:
    """`name` folded (accents, case, spaces, punctuation removed), legal suffix dropped.

    Every spelling of the company name folds to a string containing this key,
    so a folded document text contains it whenever the document names the company.
    """
    folded = fold(name)
    return _LEGAL_SUFFIX.sub("", folded) or folded


# Sales-tax registration numbers printed under the invoice totals. Neutral
# placeholders: a real install sets its own GST/TPS and QST/TVQ numbers here.
TPS_NUMBER = "000000000 RT0001"
TVQ_NUMBER = "0000000000 TQ0001"
