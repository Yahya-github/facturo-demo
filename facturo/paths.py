"""Every filesystem location the app uses, in development and as a frozen exe.

Two roots:
  * bundle_dir() — read-only assets shipped inside the program (xlsx template,
    web UI). When frozen they live in PyInstaller's extraction dir (sys._MEIPASS).
  * app_dir()    — writable data that must survive upgrades (database, invoices,
    scans, payment PDFs, configs, backups). When frozen this is the folder holding
    Factures.exe, so the client sees their files next to the program. In
    development it is <repo>/data/, which git ignores.

FACTURO_DATA_DIR overrides app_dir() — the test suite points it at a temp dir.
"""

import os
import sys
from pathlib import Path

IS_FROZEN = bool(getattr(sys, "frozen", False))

_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parent


def bundle_dir() -> Path:
    """The `facturo` package directory holding read-only assets."""
    if IS_FROZEN:
        return Path(sys._MEIPASS) / "facturo"  # type: ignore[attr-defined]
    return _PACKAGE_DIR


def app_dir() -> Path:
    """Directory for persistent, user-visible data."""
    override = os.environ.get("FACTURO_DATA_DIR")
    if override:
        return Path(override)
    if IS_FROZEN:
        return Path(sys.executable).resolve().parent
    return _REPO_ROOT / "data"


def template_path() -> Path:
    return bundle_dir() / "assets" / "facture_template.xlsx"


def web_dir() -> Path:
    return bundle_dir() / "web"


def db_path() -> Path:
    return app_dir() / "data.db"


def output_dir() -> Path:
    return app_dir() / "output"


def scans_dir() -> Path:
    return app_dir() / "scans"


def payments_dir() -> Path:
    """Imported payment / received-invoice PDFs."""
    return app_dir() / "paiements"


def backups_dir() -> Path:
    return app_dir() / "backups"


def logo_path() -> Path:
    """Company logo baked into every export. Always stored as PNG."""
    return app_dir() / "company_logo.png"
