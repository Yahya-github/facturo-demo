"""GitHub sync (services/sync.py).

The French half names the buttons « Envoyer » and « Recevoir » because that is
what the sync panel has always called them; the English half uses the
translated names.
"""

MESSAGES = {
    # Configuration
    "sync.not_configured": "Sync is not configured.",
    "sync.github_url_only": (
        "Repository address refused: use a GitHub repository "
        "(https://github.com/owner/repository)."
    ),
    "sync.url_required": "Repository URL is required.",
    "sync.token_required": "GitHub token is required.",
    "sync.token_refused": "GitHub token refused. Check the token and its permissions.",
    "sync.disconnect_failed": (
        "Cannot delete the sync configuration ({file}). "
        "Close the other programs using it then try again."
    ),

    # Guards, before anything moves
    "sync.db_newer_than_app": (
        "This database was created by a newer version of Factures. "
        "Update the application before sending."
    ),
    "sync.database_busy": (
        "The database is busy with another operation. "
        "Wait a few seconds then try again. Sync cancelled."
    ),
    "sync.backup_failed": "Safety backup failed; receiving cancelled.",
    "sync.wal_remove_failed": (
        "Database temporary files cannot be removed; receiving cancelled. "
        "Restart Factures then try again."
    ),
    "sync.repo_not_data_only": (
        "This repository already contains other files ({files}). "
        "Use an empty, private GitHub repository, created only for Factures data "
        "— never the source code repository."
    ),

    # Sending
    "sync.connect_failed": "Cannot connect to the repository: {detail}",
    "sync.push_connect_failed": "Sending failed (connection): {detail}",
    "sync.push_failed": "Sending failed: {detail}",
    "sync.push_rejected": "Sending refused: {detail}",
    "sync.remote_has_newer_device": (
        "The remote repository has newer data (another device synced). "
        'Click "Receive" before sending.'
    ),
    "sync.remote_has_newer": (
        'The remote repository has newer data. Click "Receive" before sending.'
    ),

    # Receiving
    "sync.pull_failed": "Receiving failed: {detail}",
    "sync.remote_empty": (
        'The remote repository is empty. Click "Send" from the device that '
        "already has the data."
    ),
    "sync.pulled_wal_failed": (
        "Data received, but the database temporary files could not be removed. "
        'Restart Factures then click "Receive" again.{hint}'
    ),
    "sync.pulled_install_failed": (
        "Data received, but setting it up failed ({detail}). "
        'Restart Factures then click "Receive" again.{hint}'
    ),
    "sync.backup_hint": ' Your previous database is backed up in "{file}" ({folder}).',

    # Warning returned after a sync that actually succeeded
    "sync.stamp_failed": "Sync finished, but the last sync date could not be saved.",
}
