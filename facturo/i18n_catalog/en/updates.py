"""Self-update over GitHub releases (services/updater.py).

The `updates.rollback_*` keys are looked up from the ASCII status code
`update_helper.cmd` writes on exit; the helper itself stays language-free.
"""

MESSAGES = {
    # Checking for a release
    "updates.no_token": "No token configured. Add a read-only GitHub token in Settings.",
    "updates.token_refused": "GitHub token refused or expired.",
    "updates.repo_not_found": "Repository not found or token has no access.",
    "updates.network_error": "Cannot connect. Check your internet connection.",
    "updates.insecure_url": "Download address refused (insecure connection).",
    "updates.github_error": "GitHub answered with an error ({code}). Try again later.",
    "updates.github_unreadable": "Unreadable response from GitHub.",
    "updates.response_too_large": "Server response too large.",
    "updates.none_available": "No update available.",
    "updates.asset_missing": "Version {version} does not contain {exe}; try again later.",

    # Downloading
    "updates.invalid_token": "Invalid token: paste only the GitHub token, with no spaces.",
    "updates.file_too_big": "Update file is abnormally large; update cancelled.",
    "updates.sha_file_invalid": "Invalid version SHA-256 file; update cancelled.",
    "updates.download_empty": "Empty update file; update cancelled.",
    "updates.sha_mismatch": (
        "SHA-256 verification failed: file corrupted or modified. Update cancelled."
    ),
    "updates.download_interrupted": "Download interrupted. Check your internet connection.",

    # Installing
    "updates.already_running": "An update is already in progress.",
    "updates.sync_in_progress": "A sync is in progress. Wait for it to finish.",
    "updates.dev_mode": "Update impossible in development mode: it is only available in Factures.exe.",
    "updates.exe_folder_readonly": (
        "Cannot write in the Factures.exe folder (permission denied). "
        'Move the folder out of "Program Files".'
    ),
    "updates.exe_name_required": "The program must be named {exe} to be updated.",
    "updates.invalid_port": "Invalid port.",
    "updates.windows_only": "Automatic updates are only available on Windows.",
    "updates.db_prepare_failed": "Cannot prepare the database for the update.",
    "updates.backup_failed": "Cannot back up data.db; update cancelled.",
    "updates.helper_launch_failed": "Cannot launch the update installation.",

    # Codes the helper writes when an install goes wrong
    "updates.rollback_health_check_failed": (
        "The update failed: the new version did not start. "
        "Rolling back to the previous version."
    ),
    "updates.rollback_activate_new_failed": (
        "The update failed: the new program could not be put in place. "
        "Rolling back to the previous version."
    ),
    "updates.rollback_rename_current_failed": (
        "The update failed: the program was locked (antivirus?). Nothing was changed."
    ),
    "updates.rollback_old_process_still_running": (
        "The update failed: the old version did not close. Nothing was changed."
    ),
    "updates.rollback_default": "The update failed. Rolling back to the previous version.",
}
