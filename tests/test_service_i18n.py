"""Service errors are translated when they are raised, in the request's language.

Services call tr() at raise time, so an exception message is already English
(the default) or French (X-Lang: fr) by the time the API layer passes str(e)
through. These tests pin that contract for the updater, sync and the payment
PDF reader, at service level and through HTTP.
"""

import io

import pytest
from fastapi.testclient import TestClient

from facturo import i18n
from facturo.core import database as db
from facturo.payments import pdf_text
from facturo.server import app
from facturo.services import sync, updater
from tests.helpers.pdf_writer import make_blank_pdf

# ── Service level: English by default, French under set_lang('fr') ──


@pytest.fixture
def no_configs(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "CONFIG_PATH", tmp_path / "update_config.json")
    monkeypatch.setattr(sync, "load_config", lambda: None)
    updater.reset_cache()
    yield
    updater.reset_cache()


def _message(exc_type, call):
    with pytest.raises(exc_type) as info:
        call()
    return str(info.value)


def test_updater_error_is_english_by_default(no_configs):
    msg = _message(updater.UpdateError, updater.check)
    assert msg == i18n.CATALOG["en"]["updates.no_token"]


def test_updater_error_is_french_under_set_lang(no_configs):
    token = i18n.set_lang("fr")
    try:
        msg = _message(updater.UpdateError, updater.check)
    finally:
        i18n.reset_lang(token)
    assert msg == i18n.CATALOG["fr"]["updates.no_token"]
    assert msg != i18n.CATALOG["en"]["updates.no_token"]


def test_sync_error_is_english_by_default(no_configs):
    msg = _message(sync.SyncError, sync._require_config)
    assert msg == i18n.CATALOG["en"]["sync.not_configured"]


def test_sync_error_params_are_filled_in_both_languages():
    for lang in ("en", "fr"):
        token = i18n.set_lang(lang)
        try:
            msg = sync._friendly_push_error(RuntimeError("boom"), io.BytesIO())
        finally:
            i18n.reset_lang(token)
        assert msg == i18n.CATALOG[lang]["sync.push_failed"].format(detail="boom")


def test_pdf_parse_error_is_english_by_default():
    msg = _message(pdf_text.PaymentParseError, lambda: pdf_text.extract_text(make_blank_pdf()))
    assert msg == i18n.CATALOG["en"]["err.payment_pdf_no_text"]


def test_pdf_parse_error_is_french_under_set_lang(french):
    msg = _message(pdf_text.PaymentParseError, lambda: pdf_text.extract_text(make_blank_pdf()))
    assert msg == i18n.CATALOG["fr"]["err.payment_pdf_no_text"]


def test_helper_rollback_code_is_translated_when_status_is_read(monkeypatch):
    monkeypatch.setattr(updater, "_last_update_failure",
                        updater._rollback_message("ROLLBACK HEALTH_CHECK_FAILED"))
    token = i18n.set_lang("fr")
    try:
        msg = updater.status(consume_failure=True)["update_failed_message"]
    finally:
        i18n.reset_lang(token)
    assert msg == i18n.CATALOG["fr"]["updates.rollback_health_check_failed"]


# ── Through HTTP: X-Lang picks the language of the same failure ──


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "i18n-api.db")
    monkeypatch.setattr(updater, "CONFIG_PATH", tmp_path / "update_config.json")
    monkeypatch.setattr(sync, "load_config", lambda: None)
    updater.reset_cache()
    with TestClient(app) as c:
        yield c
    updater.reset_cache()


def test_updates_check_answers_in_the_request_language(client):
    en = client.get("/api/updates/check")
    fr = client.get("/api/updates/check", headers={"X-Lang": "fr"})
    assert en.status_code == fr.status_code == 400
    assert en.json()["detail"] == i18n.CATALOG["en"]["updates.no_token"]
    assert fr.json()["detail"] == i18n.CATALOG["fr"]["updates.no_token"]


def test_sync_push_answers_in_the_request_language(client):
    en = client.post("/api/sync/push")
    fr = client.post("/api/sync/push", headers={"X-Lang": "fr"})
    assert en.status_code == fr.status_code == 400
    assert en.json()["detail"] == i18n.CATALOG["en"]["sync.not_configured"]
    assert fr.json()["detail"] == i18n.CATALOG["fr"]["sync.not_configured"]


def test_payment_import_of_a_textless_pdf_answers_in_the_request_language(client, tmp_path,
                                                                          monkeypatch):
    from facturo.api import payments as payments_api
    monkeypatch.setattr(payments_api, "PAYMENTS_DIR", tmp_path / "paiements")

    def upload(headers):
        return client.post("/api/paiements", headers=headers, files={
            "file": ("p.pdf", io.BytesIO(make_blank_pdf()), "application/pdf")})

    en, fr = upload({}), upload({"X-Lang": "fr"})
    assert en.status_code == fr.status_code == 400
    assert en.json()["detail"] == i18n.CATALOG["en"]["err.payment_pdf_no_text"]
    assert fr.json()["detail"] == i18n.CATALOG["fr"]["err.payment_pdf_no_text"]
