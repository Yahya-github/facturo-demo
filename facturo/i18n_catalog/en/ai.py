"""Ollama-backed billet extraction (extraction/ai_extract.py, scan_render.py).

These are read by people, so each one names the next thing to try. The French
half keeps two messages un-accented ("modele", "installe") exactly as the code
has always had them: that text is meant to be copied into a terminal.
"""

MESSAGES = {
    # Talking to Ollama (ai_extract.py)
    "ai.api_key_refused": (
        "Ollama API key refused by {host}. Add a valid key in ai_config.json "
        "(\"api_key\") or in the {env} environment variable."
    ),
    "ai.service_unreachable": (
        "Cannot reach the AI service at {host} — start Ollama, then install a "
        "vision model: ollama pull {model}"
    ),
    "ai.service_unavailable": "AI service unavailable at {host} (detail: {detail}).",
    "ai.no_model_installed": (
        "No model installed in Ollama. Install a vision model: ollama pull {model}"
    ),
    "ai.no_vision_model": (
        "No vision model installed in Ollama. Install one: ollama pull {model}"
    ),
    "ai.model_not_installed": (
        "Model {model} is not installed in Ollama. Install it: ollama pull {model}"
    ),
    "ai.api_key_invalid": (
        "Missing or invalid Ollama API key for {host}. Add it in ai_config.json "
        "(\"api_key\") or in the {env} environment variable."
    ),
    "ai.image_too_large_for_context": (
        "The image is too large for the model's context window. Try a smaller photo, "
        "or increase the context of model {model}."
    ),
    "ai.chat_failed": (
        "AI service unavailable — check that Ollama is running and that model "
        "{model} is installed. (Detail: {detail})"
    ),
    "ai.no_reply": (
        "Model {model} returned no reply (it is « thinking » without answering). "
        "Use a vision model without reasoning, for example: ollama pull {model}"
    ),

    # Reading the model's answer
    "ai.invalid_response": (
        "The AI returned an invalid response. Try again or enter the ticket manually."
    ),
    "ai.no_readable_hours": (
        "No readable hours on this page — this is probably not a ticket "
        "(price list, already-issued invoice…). Enter it manually if it is one."
    ),
    "ai.no_ticket_read": "No ticket could be read in this document. Enter them manually.",
    "ai.empty_text": "Empty text.",

    # Rendering a page to an image (scan_render.py)
    "ai.file_empty": "Empty file.",
    "ai.image_unreadable": "Cannot read this image. Try another photo (JPG or PNG).",
    "ai.pdf_support_missing": "PDF support is not installed (pypdfium2). Reinstall the application.",
    "ai.pdf_unreadable": "Cannot read this PDF. Check that it is not password protected.",
}
