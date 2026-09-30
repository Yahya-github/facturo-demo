"""Synchronisation GitHub (services/sync.py).

Ces messages nomment les boutons « Envoyer » et « Recevoir », qui ont toujours
été les libellés du panneau de synchronisation.
"""

MESSAGES = {
    # Configuration
    "sync.not_configured": "La synchronisation n'est pas configurée.",
    "sync.github_url_only": (
        "Adresse du dépôt refusée : utilisez un dépôt GitHub "
        "(https://github.com/propriétaire/dépôt)."
    ),
    "sync.url_required": "URL du dépôt requise.",
    "sync.token_required": "Jeton GitHub requis.",
    "sync.token_refused": "Jeton GitHub refusé. Vérifiez le jeton et ses autorisations.",
    "sync.disconnect_failed": (
        "Impossible de supprimer la configuration de synchronisation ({file}). "
        "Fermez les autres programmes qui l'utilisent puis réessayez."
    ),

    # Gardes, avant tout déplacement
    "sync.db_newer_than_app": (
        "Cette base de données a été créée par une version plus récente de "
        "Factures. Mettez à jour l'application avant d'envoyer."
    ),
    "sync.database_busy": (
        "La base de données est occupée par une autre opération. "
        "Patientez quelques secondes puis réessayez. Synchronisation annulée."
    ),
    "sync.backup_failed": "Sauvegarde de sécurité impossible ; réception annulée.",
    "sync.wal_remove_failed": (
        "Fichiers temporaires de la base impossibles à supprimer ; réception annulée. "
        "Redémarrez Facturo puis réessayez."
    ),
    "sync.repo_not_data_only": (
        "Ce dépôt contient déjà d'autres fichiers ({files}). "
        "Utilisez un dépôt GitHub vide et privé, créé uniquement pour les "
        "données de Factures — jamais le dépôt du code source."
    ),

    # Envoi
    "sync.connect_failed": "Connexion au dépôt impossible : {detail}",
    "sync.push_connect_failed": "Envoi impossible (connexion) : {detail}",
    "sync.push_failed": "Envoi impossible : {detail}",
    "sync.push_rejected": "Envoi refusé : {detail}",
    "sync.remote_has_newer_device": (
        "Le dépôt distant contient des données plus récentes "
        "(un autre appareil a synchronisé). Cliquez « Recevoir » avant d'envoyer."
    ),
    "sync.remote_has_newer": (
        "Le dépôt distant contient des données plus récentes. "
        "Cliquez « Recevoir » avant d'envoyer."
    ),

    # Réception
    "sync.pull_failed": "Réception impossible : {detail}",
    "sync.remote_empty": (
        "Le dépôt distant est vide. Cliquez « Envoyer » depuis l'appareil "
        "qui possède déjà les données."
    ),
    "sync.pulled_wal_failed": (
        "Données reçues, mais les fichiers temporaires de la base n'ont "
        "pas pu être supprimés. Redémarrez Facturo puis cliquez de nouveau "
        "sur « Recevoir ».{hint}"
    ),
    "sync.pulled_install_failed": (
        "Données reçues, mais leur mise en place a échoué ({detail}). "
        "Redémarrez Facturo puis cliquez de nouveau sur « Recevoir ».{hint}"
    ),
    "sync.backup_hint": " Votre base précédente est sauvegardée dans « {file} » ({folder}).",

    # Avertissement renvoyé après une synchronisation réussie
    "sync.stamp_failed": (
        "Synchronisation terminée, mais la date de dernière synchronisation "
        "n'a pas pu être enregistrée."
    ),
}
