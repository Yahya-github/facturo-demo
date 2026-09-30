"""Server-side i18n: language resolution, tr() fallbacks, catalog parity, middleware."""

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from facturo import i18n
from facturo.i18n_middleware import I18nMiddleware

KEY = "sync.push_failed"  # has a {detail} placeholder
PLACEHOLDER = re.compile(r"\{(\w+)\}")


@pytest.fixture(autouse=True)
def _english():
    token = i18n.set_lang("en")
    yield
    i18n.reset_lang(token)


# -- normalize / Accept-Language / resolve ------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("fr-CA", "fr"), ("fr_CA", "fr"), ("FR", "fr"), ("en-US", "en"),
    ("de", None), ("!!garbage!!", None), ("", None), (None, None),
])
def test_normalize(raw, expected):
    assert i18n.normalize(raw) == expected


def test_accept_language_orders_by_q_value():
    assert i18n.from_accept_language("en;q=0.5, fr;q=0.9") == "fr"
    assert i18n.from_accept_language("de, fr;q=0.4, en;q=0.2") == "fr"


def test_accept_language_ties_keep_header_order():
    assert i18n.from_accept_language("en, fr") == "en"


def test_accept_language_wildcard_and_garbage_give_none():
    assert i18n.from_accept_language("*") is None
    assert i18n.from_accept_language("de, *;q=0.1") is None
    assert i18n.from_accept_language("fr;q=.., en;q=0.5") == "en"
    assert i18n.from_accept_language(None) is None


def test_resolve_precedence():
    assert i18n.resolve("fr", "en") == "fr"  # X-Lang beats Accept-Language
    assert i18n.resolve(None, "fr-CA,en;q=0.5") == "fr"
    assert i18n.resolve("de", "fr") == "fr"  # unsupported X-Lang is ignored
    assert i18n.resolve(None, None) == "en"
    assert i18n.resolve("xx", "*") == "en"


# -- tr() ---------------------------------------------------------------------

def test_tr_is_english_by_default_and_french_when_set():
    en = i18n.tr(KEY, detail="x")
    token = i18n.set_lang("fr")
    try:
        fr = i18n.tr(KEY, detail="x")
    finally:
        i18n.reset_lang(token)
    assert en == i18n.CATALOG["en"][KEY].format(detail="x")
    assert fr == i18n.CATALOG["fr"][KEY].format(detail="x")
    assert en != fr


def test_tr_falls_back_to_english_then_to_the_key(monkeypatch):
    monkeypatch.delitem(i18n.CATALOG["fr"], KEY)
    token = i18n.set_lang("fr")
    try:
        assert i18n.tr(KEY, detail="x") == i18n.CATALOG["en"][KEY].format(detail="x")
        assert i18n.tr("no.such.key") == "no.such.key"
    finally:
        i18n.reset_lang(token)


def test_tr_substitutes_placeholders():
    assert "boom" in i18n.tr(KEY, detail="boom")


def test_tr_mismatched_placeholder_raises_instead_of_leaking_a_brace():
    with pytest.raises(KeyError):
        i18n.tr(KEY, wrong="boom")


def test_tr_or_text():
    assert i18n.tr_or_text("err.file_not_found") == i18n.CATALOG["en"]["err.file_not_found"]
    assert i18n.tr_or_text("plain text") == "plain text"


# -- catalog parity -----------------------------------------------------------

def test_catalogs_have_identical_keys():
    en, fr = set(i18n.CATALOG["en"]), set(i18n.CATALOG["fr"])
    assert en - fr == set(), f"missing in fr: {sorted(en - fr)}"
    assert fr - en == set(), f"missing in en: {sorted(fr - en)}"


def test_catalogs_have_identical_placeholders_per_key():
    fr_cat = i18n.CATALOG["fr"]
    bad = {
        k: (sorted(PLACEHOLDER.findall(v)), sorted(PLACEHOLDER.findall(fr_cat[k])))
        for k, v in i18n.CATALOG["en"].items()
        if k in fr_cat and set(PLACEHOLDER.findall(v)) != set(PLACEHOLDER.findall(fr_cat[k]))
    }
    assert bad == {}


# -- middleware ---------------------------------------------------------------

@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(I18nMiddleware)

    @app.get("/msg")
    def msg():
        return {"lang": i18n.get_lang(), "text": i18n.tr(KEY, detail="d")}

    return TestClient(app)


def test_middleware_x_lang_selects_french(client):
    body = client.get("/msg", headers={"X-Lang": "fr"}).json()
    assert body["lang"] == "fr"
    assert body["text"] == i18n.CATALOG["fr"][KEY].format(detail="d")


def test_middleware_uses_accept_language_and_x_lang_wins(client):
    assert client.get("/msg", headers={"Accept-Language": "fr-CA,en;q=0.5"}).json()["lang"] == "fr"
    both = client.get("/msg", headers={"X-Lang": "en", "Accept-Language": "fr"}).json()
    assert both["lang"] == "en"


def test_middleware_resets_language_between_requests(client):
    assert client.get("/msg", headers={"X-Lang": "fr"}).json()["lang"] == "fr"
    after = client.get("/msg").json()
    assert after["lang"] == "en"
    assert after["text"] == i18n.CATALOG["en"][KEY].format(detail="d")
    assert i18n.get_lang() == "en"
