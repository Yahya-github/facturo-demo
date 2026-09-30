"""Erreurs que plusieurs routeurs peuvent renvoyer : recherches, envois, versions.

Les clés nomment ce qui a échoué, pas le point d'entrée, pour que
`err.client_not_found` serve aussi bien aux factures, aux scans et aux paiements.
"""

MESSAGES = {
    # Recherches
    "err.document_not_found": "Document introuvable",
    "err.file_not_found": "Fichier introuvable",

    # Envois
    "err.file_empty": "Fichier vide",
    "err.file_too_large": "Fichier trop volumineux (max 25 Mo)",
    "err.pdf_only": "Seuls les fichiers PDF sont acceptés.",
    "err.unsupported_format": "Format non supporté. Utilisez un PDF ou une image.",

    # Stockage
    "err.database_busy": (
        "La base de données est occupée par une autre opération. "
        "Patientez quelques secondes puis réessayez."
    ),
    "err.update_failed": "La mise à jour a échoué. Rien n'a été modifié ; réessayez.",

    # Version et plateforme
    "err.version_mismatch": "Version différente de celle attendue.",
    "err.sync_failed": "Erreur de synchronisation : {detail}",

    # Refus hors tout local (local_guard.py)
    "guard.host_not_allowed": "Hôte non autorisé.",
    "guard.foreign_origin": "Requête d'une autre origine refusée.",
    "guard.foreign_site": "Requête d'un autre site refusée.",
}
