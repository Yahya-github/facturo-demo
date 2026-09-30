"""Server-side messages in English and French.

The browser sends its language in the ``X-Lang`` header (falling back to
``Accept-Language``); ``I18nMiddleware`` (see ``i18n_middleware.py``) stores it
in a context variable for the length of the request, and ``tr()`` looks the
message up in that language. English is the default and the fallback.

    raise HTTPException(404, tr("err.client_not_found"))
    raise SyncError(tr("sync.push_failed", detail=_short(e)))

Catalogs live in ``facturo/i18n_catalog/{en,fr}.py`` as plain dicts. Both must
have the same keys and the same ``{placeholders}`` (enforced by tests). The
French text is what the app has always shown; do not reword it casually.
"""

import re
from contextvars import ContextVar

from facturo.i18n_catalog import en as _en
from facturo.i18n_catalog import fr as _fr

DEFAULT_LANG = "en"
SUPPORTED = ("en", "fr")
CATALOG: dict[str, dict[str, str]] = {"en": _en.MESSAGES, "fr": _fr.MESSAGES}

_lang: ContextVar[str] = ContextVar("facturo_lang", default=DEFAULT_LANG)


def normalize(value: str | None) -> str | None:
    """'fr-CA' -> 'fr'; anything unsupported or empty -> None."""
    code = (value or "").strip().lower().replace("_", "-").split("-", 1)[0]
    return code if code in SUPPORTED else None


def from_accept_language(header: str | None) -> str | None:
    """First supported language of an Accept-Language header, by q-value order."""
    ranked = []
    for i, part in enumerate((header or "").split(",")):
        tag, _, params = part.partition(";")
        q = 1.0
        m = re.search(r"q\s*=\s*([0-9.]+)", params)
        if m:
            try:
                q = float(m.group(1))
            except ValueError:
                q = 0.0
        ranked.append((-q, i, tag))
    for _, _, tag in sorted(ranked):
        lang = normalize(tag)
        if lang:
            return lang
    return None


def resolve(x_lang: str | None, accept_language: str | None = None) -> str:
    """X-Lang wins, then Accept-Language, then English."""
    return normalize(x_lang) or from_accept_language(accept_language) or DEFAULT_LANG


def get_lang() -> str:
    return _lang.get()


def set_lang(lang: str | None):
    """Set the language for the current context; returns a token for reset_lang()."""
    return _lang.set(normalize(lang) or DEFAULT_LANG)


def reset_lang(token) -> None:
    _lang.reset(token)


def has_key(key: str) -> bool:
    return key in CATALOG["en"]


def tr(key: str, **params) -> str:
    """The message for `key` in the request's language (English, then the key itself, as fallback)."""
    text = CATALOG.get(get_lang(), {}).get(key)
    if text is None:
        text = CATALOG["en"].get(key, key)
    return text.format_map(params) if params else text


def tr_or_text(value: str) -> str:
    """`value` translated if it is a catalog key, otherwise returned unchanged."""
    return tr(value) if has_key(value) else value
