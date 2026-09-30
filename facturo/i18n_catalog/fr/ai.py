"""Extraction des billets via Ollama (extraction/ai_extract.py, scan_render.py).

Ces messages sont lus par des personnes : chacun nomme la prochaine chose à
essayer. Deux messages restent sans accents (« modele », « installe »), comme
dans le code depuis toujours : ce texte est destiné à être recopié dans un
terminal.
"""

MESSAGES = {
    # Échanges avec Ollama (ai_extract.py)
    "ai.api_key_refused": (
        "Clé d'API Ollama refusée par {host}. Ajoutez une clé valide dans "
        "ai_config.json (\"api_key\") ou dans la variable d'environnement {env}."
    ),
    "ai.service_unreachable": (
        "Impossible de joindre le service IA à {host} — démarrez Ollama, "
        "puis installez un modèle de vision : ollama pull {model}"
    ),
    "ai.service_unavailable": "Service IA indisponible à {host} (détail : {detail}).",
    "ai.no_model_installed": (
        "Aucun modele installe dans Ollama. Installez un modele de vision : "
        "ollama pull {model}"
    ),
    "ai.no_vision_model": (
        "Aucun modele de vision installe dans Ollama. Installez-en un : "
        "ollama pull {model}"
    ),
    "ai.model_not_installed": (
        "Le modèle {model} n'est pas installé dans Ollama. "
        "Installez-le : ollama pull {model}"
    ),
    "ai.api_key_invalid": (
        "Clé d'API Ollama manquante ou invalide pour {host}. Ajoutez-la dans "
        "ai_config.json (\"api_key\") ou dans la variable d'environnement {env}."
    ),
    "ai.image_too_large_for_context": (
        "L'image est trop grande pour la fenêtre de contexte du modèle. "
        "Réessayez avec une photo plus petite, ou augmentez le contexte du "
        "modèle {model}."
    ),
    "ai.chat_failed": (
        "Service IA indisponible — vérifiez qu'Ollama est démarré et que le "
        "modèle {model} est installé. (Détail : {detail})"
    ),
    "ai.no_reply": (
        "Le modèle {model} n'a renvoyé aucune réponse (il « réfléchit » "
        "sans répondre). Utilisez un modèle de vision sans raisonnement, par "
        "exemple : ollama pull {model}"
    ),

    # Lecture de la réponse du modèle
    "ai.invalid_response": (
        "L'IA a renvoyé une réponse invalide. Réessayez ou entrez le billet manuellement."
    ),
    "ai.no_readable_hours": (
        "Aucune heure lisible sur cette page — ce n'est probablement pas un "
        "billet (liste de prix, facture déjà émise…). Entrez-le manuellement "
        "si c'en est un."
    ),
    "ai.no_ticket_read": "Aucun billet n'a pu être lu dans ce document. Entrez-les manuellement.",
    "ai.empty_text": "Texte vide.",

    # Rendu d'une page en image (scan_render.py)
    "ai.file_empty": "Fichier vide.",
    "ai.image_unreadable": "Impossible de lire cette image. Essayez une autre photo (JPG ou PNG).",
    "ai.pdf_support_missing": (
        "Le support PDF n'est pas installé (pypdfium2). Réinstallez l'application."
    ),
    "ai.pdf_unreadable": (
        "Impossible de lire ce PDF. Vérifiez qu'il n'est pas protégé par mot de passe."
    ),
}
