"""Local AI-assisted extraction of billet fields from a scanned ticket, photo or
free text, using a local Ollama vision model with structured JSON output.

Never writes to the database and never calls /api/factures/generate — callers
get back plain field dicts for the human to review inside the existing manual
billet form before anything is saved. See facturo/api/ai.py's /api/ai/* endpoints.

A scanned PDF is a *batch*: the client runs a stack of paper billets through the
scanner, so one file holds one billet per page. extract_from_scan therefore
returns a list, one entry per page, which the UI appends as separate billet rows.
"""

import json
import logging
import os
import re

from ollama import Client, ResponseError

from facturo import paths
from facturo.core import billet_fields
from facturo.core.billet_fields import History
from facturo.extraction import scan_render
from facturo.extraction.ai_prompts import (  # noqa: F401 — EXTRACT_SCHEMA re-exported
    _INSTRUCTIONS_FR,
    _VISION_PROMPT_FR,
    EXTRACT_SCHEMA,
)

log = logging.getLogger(__name__)

CONFIG_PATH = paths.app_dir() / "ai_config.json"

# Ollama defaults to a 4096-token context. A page image alone tokenizes past
# that, and the request then fails with a raw 400 that reads like the model is
# missing. Ask for a window with room for the image plus the instructions.
# A cropped page measures ~1670 tokens, so this leaves ample headroom; raising
# it further buys nothing, since the answer is well under a hundred tokens.
NUM_CTX = 8192

# Keep the model resident between pages. Loading it is ~10 GB off disk and
# dwarfs the couple of seconds an individual billet actually takes, so a
# ten-page batch must not pay that cost per page.
KEEP_ALIVE = "10m"

# Hard ceiling on generated tokens. The answer is one small JSON object (~150
# tokens); without a cap a model that fails to emit a stop token keeps going to
# the end of the context, turning one billet into many minutes. Ollama also
# finishes an abandoned request server-side, so a runaway blocks every later
# page in the batch behind it — this bound is what keeps a stuck page cheap.
NUM_PREDICT = 512

# The same ceiling for a rescue read, which asks for one short field only
# ({"plaque": "..."}, a few dozen tokens at most).
RESCUE_NUM_PREDICT = 128


# Preferred local vision models, best first. The configured model always wins;
# this list only decides the fallback when nothing is configured, so a fresh
# install talks to whatever vision model the machine actually has instead of a
# hardcoded name that may never have been pulled.
#
# Non-reasoning models are listed first on purpose. Ollama serves qwen3-vl
# through its "thinking" renderer, which spends the entire generation budget on
# reasoning and returns an EMPTY content field (done_reason=length) — the
# `think=False` flag does not suppress it. Reading labelled boxes off a form
# needs no reasoning, so a straight OCR model is both correct and far faster.
PREFERRED_MODELS = (
    "qwen2.5vl:7b",
    "minicpm-v",
    "granite3.2-vision",
    "llama3.2-vision",
    "qwen3-vl:8b",
)

# Point `host` at https://ollama.com and supply an API key to run the models on
# Ollama's servers instead of this machine — no GPU needed, and no multi-gigabyte
# model on the client's disk. The trade is real and belongs to whoever sets it:
# the billet images leave the machine, so the renter names, plates and worksite
# addresses on them go to a third party, and each page is billed.
DEFAULT_CONFIG = {"model": "", "host": "http://127.0.0.1:11434", "api_key": ""}

# Environment beats the config file, so a key never has to be written to disk
# beside the executable.
API_KEY_ENV = "OLLAMA_API_KEY"

# The billet fields every result carries, successful or not, so that callers
# see one consistent shape across a batch.
_EMPTY_FIELDS = {
    "date_billet": "",
    "chantier": "",
    "plaque": "",
    "numero_billet": "",
    "description": "",
    "quantite": 0.0,
    "taux": 0.0,
    # What history changed, per field: {"chantier": {"lu", "corrige", "raison"}}.
    # Present even on a page that failed, so a caller never has to check `error`
    # before reading it.
    "corrections": {},
}


class AIExtractError(Exception):
    """User-facing failure; message is French and shown as-is in the UI."""


def _api_key(cfg: dict) -> str:
    return (os.environ.get(API_KEY_ENV) or cfg.get("api_key") or "").strip()


def _client(cfg: dict) -> Client:
    """The Ollama client for this config — local socket or hosted, same object.

    The only difference between the two is an Authorization header, so every
    call site builds its client here rather than deciding for itself; a
    hand-rolled `Client(host=...)` anywhere else would silently talk
    unauthenticated to the cloud and fail with a 401 that reads like the model
    is missing.
    """
    key = _api_key(cfg)
    headers = {"Authorization": f"Bearer {key}"} if key else None
    return Client(host=cfg["host"], headers=headers)


def _listing_error(e: Exception, cfg: dict) -> str:
    """French reason the model list could not be read: refused key vs dead host."""
    status = getattr(e, "status_code", None) if isinstance(e, ResponseError) else None
    if status in (401, 403):
        return (
            f"Clé d'API Ollama refusée par {cfg['host']}. Ajoutez une clé valide dans "
            f"ai_config.json (\"api_key\") ou dans la variable d'environnement {API_KEY_ENV}."
        )
    if isinstance(e, OSError):  # ConnectionError included
        return (
            f"Impossible de joindre le service IA à {cfg['host']} — démarrez Ollama, "
            f"puis installez un modèle de vision : ollama pull {PREFERRED_MODELS[0]}"
        )
    return f"Service IA indisponible à {cfg['host']} (détail : {e})."


def _list_models(cfg: dict) -> tuple[list[str], str]:
    """Installed model names, and a French error ("" when the list was read)."""
    try:
        return _installed_models(cfg), ""
    except Exception as e:  # noqa: BLE001 — every failure becomes a message
        log.warning("Liste des modèles Ollama illisible (%s) : %s", cfg["host"], e,
                    exc_info=True)
        return [], _listing_error(e, cfg)


def _installed_models(cfg: dict) -> list[str]:
    """Installed model names; raises whatever the Ollama client raised."""
    resp = _client(cfg).list()
    names = []
    for m in getattr(resp, "models", None) or resp.get("models", []):
        name = getattr(m, "model", None) or (m.get("model") if isinstance(m, dict) else None)
        if name:
            names.append(name)
    return names


def _pick_model(cfg: dict) -> str:
    """Choose a local vision model when the config does not name one.

    Prefers a known-good OCR model, then falls back to any installed model whose
    name looks like a vision model, so the feature works out of the box instead
    of failing on a hardcoded model the user never pulled.
    """
    installed, error = _list_models(cfg)
    if error:
        raise AIExtractError(error)
    if not installed:
        raise AIExtractError(
            "Aucun modele installe dans Ollama. Installez un modele de vision : "
            f"ollama pull {PREFERRED_MODELS[0]}"
        )
    for want in PREFERRED_MODELS:
        for name in installed:
            if name == want or name.startswith(want + ":"):
                return name
    for name in installed:  # any vision-ish model beats failing outright
        if re.search(r"vl|vision|llava|minicpm-v|gemma", name, re.I):
            return name
    raise AIExtractError(
        "Aucun modele de vision installe dans Ollama. Installez-en un : "
        f"ollama pull {PREFERRED_MODELS[0]}"
    )


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return {**DEFAULT_CONFIG, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
        except (ValueError, OSError, TypeError):
            log.warning("%s illisible ; configuration IA par défaut utilisée", CONFIG_PATH.name,
                        exc_info=True)
    return dict(DEFAULT_CONFIG)


def _resolved_config() -> dict:
    cfg = load_config()
    if not (cfg.get("model") or "").strip():
        cfg = {**cfg, "model": _pick_model(cfg)}
    return cfg


def describe_config() -> dict:
    """What the UI can show about the local AI setup, without running a query."""
    cfg = load_config()
    installed, error = _list_models(cfg)
    return {
        "host": cfg["host"],
        "configured_model": cfg.get("model", ""),
        "installed_models": installed,
        "ready": bool(installed),
        "error": error,
        # Whether a key is set, never the key itself — this dict is served to
        # the browser.
        "cloud": bool(_api_key(cfg)),
    }


# A ```json ... ``` wrapper around the answer. Local Ollama constrains
# generation to EXTRACT_SCHEMA, so the reply is bare JSON and this never
# matches. Ollama's *hosted* models ignore `format=` entirely and answer the way
# a chat model does, fence and all — stripping it costs nothing locally and is
# the difference between working and not against the cloud.
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def _loads_model_json(raw_content: str) -> dict:
    """The model's answer as a dict, tolerating a markdown fence around it."""
    text = (raw_content or "").strip()
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def _parse_and_validate(raw_content: str) -> dict:
    try:
        data = _loads_model_json(raw_content)
    except (ValueError, TypeError):
        raise AIExtractError(
            "L'IA a renvoyé une réponse invalide. Réessayez ou entrez le billet manuellement."
        ) from None
    # With every field forced "required" in the schema, the model sometimes
    # fills an unmentioned text field with the literal string "0" instead of
    # leaving it empty — treat that placeholder the same as absent.
    def _text_field(key: str) -> str:
        v = str(data.get(key) or "").strip()
        return "" if v == "0" else v

    # The worksite address is extra context for the human, not its own form
    # field — fold it into the free description rather than dropping it.
    notes = [t for t in (_text_field("lieu_travail"), _text_field("description")) if t]

    chantier = billet_fields.clean_chantier(_text_field("chantier"))

    # The billet number was the one field arriving with no cleaning at all
    # while every sibling had some. It matters more than it looks: the form
    # keys its duplicate check on this value, and the project number printed
    # beside it on the ticket ("#26-112") is exactly what the model reaches for
    # when it misses.
    numero_lu = _text_field("numero_billet")
    numero = billet_fields.tidy_billet_number(numero_lu)

    result = {
        "date_billet": billet_fields.normalize_date(_text_field("date_billet")),
        "chantier": chantier,
        "plaque": billet_fields.clean_plate(_text_field("plaque")),
        "numero_billet": numero,
        "description": " — ".join(notes),
        "quantite": billet_fields.to_number(data.get("quantite")),
        "taux": billet_fields.to_number(data.get("taux")),
        "corrections": (
            {"numero_billet": {"lu": numero_lu, "corrige": numero, "raison": "format"}}
            if numero != numero_lu else {}
        ),
    }
    # Hours are what every real billet carries and what the invoice line is
    # priced from; the rate is agreed per client and usually blank on paper.
    # So "no hours" means this page is not a billet — a scan batch can contain
    # a printed price list or an already-issued invoice, and those pages are
    # full of dollar amounts that would otherwise sail through as a `taux` and
    # produce a fabricated billet line.
    # A single billet covers one shift. Anything past a full day is a parse
    # artifact rather than work done, and must never reach an invoice line.
    if result["quantite"] > billet_fields.MAX_PLAUSIBLE_HOURS:
        result["quantite"] = 0.0

    if result["quantite"] <= 0:
        raise AIExtractError(
            "Aucune heure lisible sur cette page — ce n'est probablement pas un "
            "billet (liste de prix, facture déjà émise…). Entrez-le manuellement "
            "si c'en est un."
        )
    return result


def _friendly_chat_error(e: Exception, model: str, cfg_host: str = "") -> str:
    detail = str(e)
    if "exceed_context_size" in detail or "context size" in detail:
        return (
            "L'image est trop grande pour la fenêtre de contexte du modèle. "
            "Réessayez avec une photo plus petite, ou augmentez le contexte du "
            f"modèle {model}."
        )
    # A hosted run without a usable key fails as a bare 401, which the generic
    # message below turns into "check that Ollama is started" — advice that
    # sends the user to the wrong machine entirely.
    if "401" in detail or "unauthorized" in detail.lower():
        return (
            "Clé d'API Ollama manquante ou invalide pour "
            f"{cfg_host}. Ajoutez-la dans ai_config.json (\"api_key\") ou dans "
            f"la variable d'environnement {API_KEY_ENV}."
        )
    if "not found" in detail.lower() or "404" in detail:
        return (
            f"Le modèle {model} n'est pas installé dans Ollama. "
            f"Installez-le : ollama pull {model}"
        )
    return (
        "Service IA indisponible — vérifiez qu'Ollama est démarré et que le "
        f"modèle {model} est installé. (Détail : {detail})"
    )


def _is_hosted(model: str) -> bool:
    """Whether this model runs on Ollama's servers rather than on this machine.

    Ollama names a hosted model with a "cloud" suffix — ":cloud" when the model
    carries no tag, "-cloud" after the tag when it does.
    """
    return model.endswith(":cloud") or model.endswith("-cloud")


# Ollama's hosted models IGNORE the `format=` schema. Locally, llama.cpp turns
# EXTRACT_SCHEMA into a grammar and the reply cannot be anything but those keys;
# on the cloud there is no grammar, and the model answers like a chat model —
# gemma4 read a billet perfectly but called the date "date", the address
# "adresse", threw in "type_camion", and wrapped the lot in a markdown fence.
# So the schema has to be restated as an instruction, in words, for hosted
# models only. Local prompts stay byte-identical, which is what keeps the
# measured local accuracy from moving when this is switched on.
_JSON_KEYS_FR = (
    "\n\nReponds UNIQUEMENT avec un objet JSON valide, sans aucun texte autour "
    "et sans bloc markdown. Utilise EXACTEMENT ces cles, toutes presentes : "
    '"numero_billet", "chantier", "lieu_travail", "date_billet", "quantite", '
    '"plaque", "taux", "description". N\'utilise aucun autre nom de cle (pas '
    '"date", pas "adresse"). Quand une information est absente, mets une chaine '
    "vide, ou 0 pour un nombre."
    "\n\nIMPORTANT : \"quantite\" et \"date_billet\" sont des CHAINES recopiees "
    "telles qu'elles sont ecrites sur le billet, jamais converties. Ecris "
    '"9h15", pas 9.15 ; "8,25", pas 8.25 ; "10,5 h", pas 10.5. La conversion '
    "est faite ensuite."
)


def _with_json_keys(messages: list[dict], cfg: dict) -> list[dict]:
    """Restate the schema in the prompt when the server will not enforce it."""
    if not _is_hosted(cfg["model"]) or not messages:
        return messages
    last = messages[-1]
    return [*messages[:-1], {**last, "content": last["content"] + _JSON_KEYS_FR}]


def _run_chat(messages: list[dict], cfg: dict) -> str:
    try:
        client = _client(cfg)
        resp = client.chat(
            model=cfg["model"],
            messages=_with_json_keys(messages, cfg),
            format=EXTRACT_SCHEMA,
            # Deterministic reading, a context big enough for a page image, and
            # a bounded answer so one bad page cannot stall the whole batch.
            options={
                "num_ctx": NUM_CTX,
                "temperature": 0,
                "num_predict": NUM_PREDICT,
                # NOTE: do NOT add repeat_penalty here. It looks like the cure
                # for the repetition loop ("Coqcoq, Coqcoq, …") seen on hard
                # pages, but the values on a billet legitimately repeat digits
                # — plate AB12345, total 11,75 — and penalising them wrecked
                # both fields (plaque 3/6 -> 2/6, 11.75 read as 1.0). The
                # per-field maxLength in the schema bounds the loop instead,
                # as a grammar constraint with no effect on what is sampled.
            },
            # Reasoning models otherwise spend thousands of tokens thinking out
            # loud before the JSON — measured at 6522 generated tokens (~317s)
            # versus 50 tokens (~2s) with it off, for identical answers. Reading
            # labelled fields off a form needs no chain of thought.
            think=False,
            # Hold the model in memory across the pages of one scanned batch:
            # reloading it costs far more than the extraction itself.
            keep_alive=KEEP_ALIVE,
        )
        # Reading the reply stays inside the try: an unexpected response shape
        # must surface as an AIExtractError like every other failure, or
        # extract_from_scan's per-page guard misses it and one odd page takes
        # the whole batch down with it.
        content = (resp["message"]["content"] or "").strip()
    except Exception as e:  # noqa: BLE001 — connection refused, model missing, etc.
        raise AIExtractError(_friendly_chat_error(e, cfg["model"], cfg["host"])) from e

    if not content:
        # A reasoning model can burn the whole budget on its thinking channel
        # and return empty content. Say so plainly instead of letting it look
        # like malformed JSON, and name the fix.
        raise AIExtractError(
            f"Le modèle {cfg['model']} n'a renvoyé aucune réponse (il « réfléchit » "
            "sans répondre). Utilisez un modèle de vision sans raisonnement, par "
            f"exemple : ollama pull {PREFERRED_MODELS[0]}"
        )
    return content


# Asking for eight fields at once starves attention on the ones furthest from
# where the model is "looking": on Vrac Beta billets the plate sits in a block at
# the very bottom and came back empty on every single page, even with explicit
# instructions. Asked on its own about that one line, the same model reads it
# correctly every time. So when a field the invoice needs comes back blank, we
# re-ask for just that field — a second, cheap, narrowly-scoped question.
_RESCUE_PROMPTS = {
    # Keep this SHORT and give it no way out. An earlier version ended with
    # "if no such code is visible, answer with an empty string" and the model
    # took that exit on every single bulk-hauler page — 0/4 — even though the plate was
    # plainly there. Asking one direct question about one labelled line filled
    # all four.
    "plaque": (
        "Regarde le bas du billet. Recopie exactement le code lettres+chiffres "
        "ecrit a la main sur la ligne 'N° License :', 'No. Plaque' ou 'Plaque :'."
    ),
    # Name both places a date lives. These are not one layout: three put the
    # date in the table's DATE column, and BILLET DE LOCATION puts it in the
    # header after "Date :". Asking only about the column sent the model
    # hunting inside the table on that layout, and it came back with "09h30" —
    # an hours value, a confident answer to the wrong question.
    "date_billet": (
        "Recopie exactement les caracteres de la premiere date manuscrite du "
        "billet, sans la reformater (ex: '09-08-26', '23/06/2026', "
        "'09.08.2026', '29 JUIN 2026'). Elle se trouve soit dans la premiere "
        "ligne de la colonne 'DATE' du tableau, soit apres 'Date :' en haut a "
        "droite du billet."
    ),
    # The renter is the one field whose wrong answer looks right, so its rescue
    # pins down a line rather than a value: name every label the four layouts
    # use, and say where that line sits relative to the address the model keeps
    # grabbing instead.
    # NO example names here, unlike the schema description. Listing some
    # ("ROXDALE, NORIX, ...") made the model answer with the first one on the
    # list instead of reading the line — a wrong renter that looks entirely
    # plausible. Name the labels, never the values.
    "chantier": (
        "Recopie exactement le NOM ecrit a la main sur la ligne 'Loue a', "
        "'Loue a / Rented to', 'CLIENT :' ou 'Client :'. C'est la premiere "
        "ligne remplie a la main du billet, juste au-dessus de la ligne "
        "d'adresse. Recopie uniquement ce qui est ecrit sur cette ligne-la."
    ),
}

# Which slice of the page each rescue zooms into, best first. Cropping to the
# band that holds the value and enlarging it puts far more pixels on the
# handwriting than the whole-page view does, without costing more image tokens
# — and single digits (a cursive 5 read as 9) are exactly what the full-page
# pass gets wrong.
#
# Each field lists a second band because the layouts disagree about where a
# field lives: the date sits in the table (~40% down) on Transport Alpha, Vrac
# Beta and the company's own layout but in the header (~8%) on BILLET DE
# LOCATION, whose plate is likewise up in the header rather than at the foot. One band wide enough for both would undo the
# zoom that makes a rescue work, so try the usual place first and fall back
# only when it comes up empty.
_RESCUE_BANDS = {
    "chantier": ((0.0, 0.35), (0.0, 0.60)),
    "plaque": ((0.55, 1.0), (0.0, 0.55)),
    "date_billet": ((0.0, 0.50), (0.30, 1.0)),
}

# How each rescued string becomes the value the form takes. A rescue goes
# through exactly the same cleaning as the main pass — a plate found on the
# second look still needs its lookalike letters mapped, a date still needs
# parsing — so a rescue can never smuggle in a value the main path would
# have rejected.
_RESCUE_CLEANERS = {
    "chantier": billet_fields.clean_chantier,
    "plaque": billet_fields.clean_plate,
    "date_billet": billet_fields.normalize_date,
}


def _needs_rescue(field: str, result: dict) -> bool:
    """Whether a field's first answer is worth a second, focused look.

    A blank always is. chantier earns one on top of that when the answer came
    back address-shaped, because that failure does not look like a failure: the
    model answers the renter slot with the line below it and leaves
    lieu_travail empty, so there is nothing to compare against and a street
    reaches the invoice as the client.
    """
    if not result.get(field):
        return True
    return field == "chantier" and billet_fields.looks_like_address(result[field])


def _rescue_field(field: str, jpeg_bytes: bytes, cfg: dict) -> str:
    """Re-ask the model for one field alone. Returns "" if it still cannot read it.

    Each band in _RESCUE_BANDS is tried until one yields something. The extra
    call only ever happens on a page that already failed, so it costs nothing
    on the pages that read cleanly.
    """
    schema = {
        "type": "object",
        "properties": {field: {"type": "string", "maxLength": 30}},
        "required": [field],
    }
    prompt = _RESCUE_PROMPTS[field]
    if _is_hosted(cfg["model"]):
        prompt += (
            "\n\nReponds uniquement avec un objet JSON valide, sans bloc "
            f'markdown, de la forme {{"{field}": "..."}}.'
        )
    for top, bottom in _RESCUE_BANDS[field]:
        zoomed = scan_render.band(jpeg_bytes, top, bottom)
        try:
            resp = _client(cfg).chat(
                model=cfg["model"],
                messages=[{"role": "user", "content": prompt,
                           "images": [zoomed]}],
                format=schema,
                options={"num_ctx": NUM_CTX, "temperature": 0,
                         "num_predict": RESCUE_NUM_PREDICT},
                think=False,
                keep_alive=KEEP_ALIVE,
            )
            value = str(
                _loads_model_json(resp["message"]["content"]).get(field) or ""
            ).strip()
        except Exception:  # noqa: BLE001 — a failed band just moves to the next
            continue
        if value:
            return value
    return ""


def extract_from_jpeg(jpeg_bytes: bytes, cfg: dict | None = None,
                      history: History | None = None) -> dict:
    """One already-prepared page image -> one billet's fields."""
    cfg = cfg or _resolved_config()
    history = history or History()
    content = _run_chat(
        [{"role": "user", "content": _VISION_PROMPT_FR, "images": [jpeg_bytes]}], cfg,
    )
    result = _parse_and_validate(content)

    for field in _RESCUE_PROMPTS:
        if not _needs_rescue(field, result):
            continue
        value = _RESCUE_CLEANERS[field](_rescue_field(field, jpeg_bytes, cfg))
        # A rescue is a second opinion, not an override: an empty answer — or,
        # for the renter, the address all over again — leaves the first answer
        # standing rather than swapping a bad value for a worse one.
        if value and not (field == "chantier" and billet_fields.looks_like_address(value)):
            result[field] = value

    return _settle_against_history(result, history)


def _settle_against_history(result: dict, history: History) -> dict:
    """Correct the two fields the shop's own records can settle — and say so.

    A silent correction is one the user cannot audit. "Foxdale" -> "ROXDALE" is
    right almost every time; on the occasion it is wrong, the only thing
    standing between it and a real invoice is the user noticing a correction
    happened at all. So the reading it replaced travels with the answer, under
    `corrections`, and the form offers it back.

    Runs after the rescue pass, so what it reports as read is the model's final
    answer rather than a first guess that was already superseded.
    """
    corrections = dict(result.get("corrections") or {})
    for field, snap, known in (
        ("chantier", billet_fields.snap_chantier, history.chantiers),
        ("plaque", billet_fields.snap_plate, history.plaques),
    ):
        was = result[field]
        now = snap(was, known)
        if now != was:
            corrections[field] = {"lu": was, "corrige": now, "raison": "historique"}
        result[field] = now
    result["corrections"] = corrections
    return result


def extract_from_image(image_bytes: bytes, history: History | None = None) -> dict:
    """One photo of one billet -> that billet's fields.

    Takes history like every other entry point: a caller that forgets it gets
    silently worse plate and chantier readings, with nothing in the output to
    say why.
    """
    try:
        jpeg = scan_render.image_to_jpeg(image_bytes)
    except scan_render.ScanRenderError as e:
        raise AIExtractError(str(e)) from e
    return extract_from_jpeg(jpeg, history=history)


def extract_from_scan(raw: bytes, history: History | None = None) -> list[dict]:
    """A whole uploaded scan (PDF batch or single photo) -> one entry per billet.

    Pages the model cannot read are reported instead of aborting the batch: a
    single unreadable ticket in a stack of ten should not cost the user the
    other nine.
    """
    try:
        pages = scan_render.to_jpegs(raw)
    except scan_render.ScanRenderError as e:
        raise AIExtractError(str(e)) from e

    cfg = _resolved_config()
    results: list[dict] = []
    for i, jpeg in enumerate(pages, start=1):
        try:
            fields = extract_from_jpeg(jpeg, cfg, history)
            results.append({**fields, "page": i, "error": ""})
        except AIExtractError as e:
            # Same keys as a successful page, so a caller can read a field
            # without having to check `error` first.
            results.append({**_EMPTY_FIELDS, "page": i, "error": str(e)})
    if not any(not r["error"] for r in results):
        raise AIExtractError(
            "Aucun billet n'a pu être lu dans ce document. Entrez-les manuellement."
        )
    return results


def extract_from_text(text: str, history: History | None = None) -> dict:
    """Pasted text describing one billet -> that billet's fields.

    Takes history like every other entry point. Typed text has no handwriting
    to misread, but it still carries whatever spelling the sender used, and
    settling that here is what stops one client arriving as two sites.
    """
    if not (text or "").strip():
        raise AIExtractError("Texte vide.")
    cfg = _resolved_config()
    content = _run_chat(
        [{"role": "user", "content": f"{_INSTRUCTIONS_FR}\n\nTexte à analyser : {text}"}], cfg,
    )
    return _settle_against_history(_parse_and_validate(content), history or History())
