"""Mise à jour via les versions publiées sur GitHub (services/updater.py).

Les clés `updates.rollback_*` sont choisies à partir du code ASCII écrit par
`update_helper.cmd` en sortie ; le script reste sans langue.
"""

MESSAGES = {
    # Recherche d'une version
    "updates.no_token": (
        "Aucun jeton configuré. Ajoutez un jeton GitHub en lecture seule dans Paramètres."
    ),
    "updates.token_refused": "Jeton GitHub refusé ou expiré.",
    "updates.repo_not_found": "Dépôt introuvable ou jeton sans accès.",
    "updates.network_error": "Connexion impossible. Vérifiez votre connexion internet.",
    "updates.insecure_url": "Adresse de téléchargement refusée (connexion non sécurisée).",
    "updates.github_error": "GitHub a répondu avec une erreur ({code}). Réessayez plus tard.",
    "updates.github_unreadable": "Réponse de GitHub illisible.",
    "updates.response_too_large": "Réponse du serveur trop volumineuse.",
    "updates.none_available": "Aucune mise à jour disponible.",
    "updates.asset_missing": "La version {version} ne contient pas {exe} ; réessayez plus tard.",

    # Téléchargement
    "updates.invalid_token": "Jeton invalide : collez uniquement le jeton GitHub, sans espace.",
    "updates.file_too_big": "Fichier de mise à jour anormalement volumineux ; mise à jour annulée.",
    "updates.sha_file_invalid": "Fichier SHA-256 de la version invalide ; mise à jour annulée.",
    "updates.download_empty": "Fichier de mise à jour vide ; mise à jour annulée.",
    "updates.sha_mismatch": (
        "Échec de la vérification SHA-256 : fichier corrompu ou modifié. Mise à jour annulée."
    ),
    "updates.download_interrupted": "Téléchargement interrompu. Vérifiez votre connexion internet.",

    # Installation
    "updates.already_running": "Une mise à jour est déjà en cours.",
    "updates.sync_in_progress": "Une synchronisation est en cours. Attendez qu'elle se termine.",
    "updates.dev_mode": (
        "Mise à jour impossible en mode développement : elle n'est disponible que dans Factures.exe."
    ),
    "updates.exe_folder_readonly": (
        "Impossible d'écrire dans le dossier de Factures.exe (permission refusée). "
        "Déplacez le dossier hors de « Program Files »."
    ),
    "updates.exe_name_required": "Le programme doit s'appeler {exe} pour être mis à jour.",
    "updates.invalid_port": "Port invalide.",
    "updates.windows_only": "La mise à jour automatique n'est disponible que sous Windows.",
    "updates.db_prepare_failed": "Impossible de préparer la base de données pour la mise à jour.",
    "updates.backup_failed": "Impossible de sauvegarder data.db ; mise à jour annulée.",
    "updates.helper_launch_failed": "Impossible de lancer l'installation de la mise à jour.",

    # Codes écrits par le script lorsqu'une installation tourne mal
    "updates.rollback_health_check_failed": (
        "La mise à jour a échoué : la nouvelle version n'a pas démarré. "
        "Retour à la version précédente."
    ),
    "updates.rollback_activate_new_failed": (
        "La mise à jour a échoué : le nouveau programme n'a pas pu être mis "
        "en place. Retour à la version précédente."
    ),
    "updates.rollback_rename_current_failed": (
        "La mise à jour a échoué : le programme était verrouillé "
        "(antivirus ?). Aucune modification n'a été faite."
    ),
    "updates.rollback_old_process_still_running": (
        "La mise à jour a échoué : l'ancienne version ne s'est pas "
        "fermée. Aucune modification n'a été faite."
    ),
    "updates.rollback_default": "La mise à jour a échoué. Retour à la version précédente.",
}
