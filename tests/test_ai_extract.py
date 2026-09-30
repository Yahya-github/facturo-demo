"""Unit tests for ai_extract's own logic — protocol, not field values.

Covers deciding when a field deserves a second look, and the two places where
talking to a hosted model differs from talking to the local one. Field parsing
lives in tests/test_billet_fields.py. Nothing here touches the network.
"""

import logging

import pytest

from facturo.extraction import ai_extract

# --- _needs_rescue --------------------------------------------------------

def test_needs_rescue_on_a_blank_field():
    assert ai_extract._needs_rescue("plaque", {"plaque": ""})
    assert ai_extract._needs_rescue("chantier", {"chantier": ""})


def test_needs_rescue_when_the_renter_came_back_as_an_address():
    """This failure does not look like one — nothing else in the result is wrong."""
    assert ai_extract._needs_rescue("chantier", {"chantier": "T400CH DU LAC NORD"})


def test_needs_no_rescue_for_a_good_answer():
    assert not ai_extract._needs_rescue("chantier", {"chantier": "NORIX"})
    assert not ai_extract._needs_rescue("plaque", {"plaque": "FK68873"})


def test_only_chantier_is_second_guessed_on_a_non_empty_answer():
    """A plate full of digits must not be mistaken for an address."""
    assert not ai_extract._needs_rescue("plaque", {"plaque": "FK68873"})
    assert not ai_extract._needs_rescue("date_billet", {"date_billet": "2026-06-25"})


# --- _loads_model_json ----------------------------------------------------

def test_loads_model_json_reads_bare_json():
    """What local Ollama returns: the schema is a grammar, so nothing wraps it."""
    assert ai_extract._loads_model_json('{"chantier": "NORIX"}') == {"chantier": "NORIX"}


@pytest.mark.parametrize("raw", [
    '```json\n{"chantier": "NORIX"}\n```',
    '```\n{"chantier": "NORIX"}\n```',
    'Voici le resultat :\n```json\n{"chantier": "NORIX"}\n```\nVoila.',
])
def test_loads_model_json_unwraps_a_hosted_models_fence(raw):
    """Ollama Cloud ignores format=, so hosted models answer like chat models."""
    assert ai_extract._loads_model_json(raw) == {"chantier": "NORIX"}


@pytest.mark.parametrize("raw", ["", "pas du json", "[1, 2, 3]"])
def test_loads_model_json_rejects_what_is_not_an_object(raw):
    with pytest.raises((ValueError, TypeError)):
        ai_extract._loads_model_json(raw)


# --- _is_hosted / _with_json_keys -----------------------------------------

@pytest.mark.parametrize("model, hosted", [
    ("gemma4:31b-cloud", True),     # tagged models take "-cloud" after the tag
    ("minimax-m3:cloud", True),     # untagged ones take ":cloud"
    ("qwen2.5vl:7b", False),
    ("qwen3-vl:8b", False),
])
def test_is_hosted(model, hosted):
    assert ai_extract._is_hosted(model) is hosted


def test_with_json_keys_leaves_local_prompts_untouched():
    """The measured local accuracy depends on these prompts not moving."""
    messages = [{"role": "user", "content": "prompt"}]
    assert ai_extract._with_json_keys(messages, {"model": "qwen2.5vl:7b"}) == messages


def test_with_json_keys_restates_the_schema_for_a_hosted_model():
    messages = [{"role": "user", "content": "prompt", "images": [b"x"]}]
    out = ai_extract._with_json_keys(messages, {"model": "gemma4:31b-cloud"})
    assert out[0]["content"].startswith("prompt")
    assert "date_billet" in out[0]["content"]      # the key gemma4 renamed to "date"
    assert out[0]["images"] == [b"x"]              # the image survives the rewrite
    assert messages[0]["content"] == "prompt"      # and the input is not mutated


# --- listing models: say WHY the service is unusable ------------------------


class _FailingClient:
    def __init__(self, exc):
        self._exc = exc

    def list(self):
        raise self._exc


_CFG = {"host": "http://127.0.0.1:9", "model": ""}


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.usefixtures("french")
def test_model_listing_refused_names_the_api_key(monkeypatch, caplog, status):
    from ollama import ResponseError

    monkeypatch.setattr(ai_extract, "_client",
                        lambda cfg: _FailingClient(ResponseError("unauthorized", status)))
    with caplog.at_level(logging.WARNING), pytest.raises(ai_extract.AIExtractError) as exc:
        ai_extract._pick_model(_CFG)
    assert "Clé d'API" in str(exc.value)
    assert "unauthorized" in caplog.text


@pytest.mark.usefixtures("french")
def test_model_listing_unreachable_names_the_host(monkeypatch, caplog):
    monkeypatch.setattr(ai_extract, "_client",
                        lambda cfg: _FailingClient(ConnectionError("refused")))
    with caplog.at_level(logging.WARNING), pytest.raises(ai_extract.AIExtractError) as exc:
        ai_extract._pick_model(_CFG)
    assert "127.0.0.1:9" in str(exc.value)
    assert "joindre" in str(exc.value)
    assert "refused" in caplog.text


@pytest.mark.usefixtures("french")
def test_describe_config_reports_the_listing_error_without_raising(monkeypatch):
    from ollama import ResponseError

    monkeypatch.setattr(ai_extract, "load_config", lambda: dict(_CFG))
    monkeypatch.setattr(ai_extract, "_client",
                        lambda cfg: _FailingClient(ResponseError("forbidden", 403)))
    info = ai_extract.describe_config()
    assert info["ready"] is False
    assert "Clé d'API" in info["error"]


def test_corrupt_config_is_logged_and_ignored(tmp_path, monkeypatch, caplog):
    path = tmp_path / "ai_config.json"
    path.write_text("{nope", encoding="utf-8")
    monkeypatch.setattr(ai_extract, "CONFIG_PATH", path)
    with caplog.at_level(logging.WARNING):
        assert ai_extract.load_config() == ai_extract.DEFAULT_CONFIG
    assert "ai_config.json" in caplog.text


def test_rescue_uses_the_named_token_cap(monkeypatch):
    seen = []

    class _Client:
        def chat(self, **kwargs):
            seen.append(kwargs["options"]["num_predict"])
            return {"message": {"content": '{"plaque": "FK68873"}'}}

    monkeypatch.setattr(ai_extract, "_client", lambda cfg: _Client())
    monkeypatch.setattr(ai_extract.scan_render, "band", lambda jpeg, top, bottom: b"img")
    ai_extract._rescue_field("plaque", b"jpeg", {"host": "h", "model": "m"})
    assert seen == [ai_extract.RESCUE_NUM_PREDICT]
