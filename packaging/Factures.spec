# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the Factures app — produces a single Factures.exe.

Build on Windows:  build.bat   (or: pyinstaller --noconfirm Factures.spec)
Output:            dist\\Factures.exe

The xlsx template, static/ and templates/ are bundled read-only inside the exe
(paths.bundle_dir() finds them at runtime). The database and output/ folder are
created next to the exe at first run (paths.app_dir()), so the client's data is
visible and persists across upgrades.
"""

import os
import sys

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
# collect_submodules() imports the package in this interpreter, so the repo root
# must be importable before it runs — otherwise it silently returns [].
sys.path.insert(0, ROOT)

# uvicorn imports its protocol/loop/lifespan implementations dynamically, so
# PyInstaller cannot see them by static analysis — collect them explicitly.
# PIL (Pillow) is imported lazily inside functions (logo handling), so collect
# its submodules explicitly to be safe.
# dulwich (GitHub sync) pulls in many submodules dynamically and ships TLS certs
# via certifi, so collect both so push/pull over HTTPS works in the frozen exe.
# pypdfium2 (rasterizing scanned PDF billets for the AI) reaches its native
# pdfium library through ctypes, which static analysis also cannot see — the
# binary is collected below, or PDF extraction fails only in the frozen exe.
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("PIL")
    + collect_submodules("dulwich")
    + collect_submodules("pypdfium2")
    + collect_submodules("pypdfium2_raw")
    + collect_submodules("facturo")
    + [
        "anyio",
        "sniffio",
        "urllib3",
        "certifi",
        "pillow_heif",
    ]
)

binaries = collect_dynamic_libs("pypdfium2_raw") + collect_dynamic_libs("pypdfium2")

# Mirrors paths.bundle_dir(): assets and web UI live under facturo/ inside the bundle.
datas = [
    (os.path.join(ROOT, "facturo", "assets"), os.path.join("facturo", "assets")),
    (os.path.join(ROOT, "facturo", "web"), os.path.join("facturo", "web")),
] + collect_data_files("certifi")

# CI-only: FACTURO_BUILD_BROKEN=1 bakes in a hook that exits at startup, used by
# release.yml's swap/rollback job. Normal builds never set it.
runtime_hooks = []
if os.environ.get("FACTURO_BUILD_BROKEN") == "1":
    runtime_hooks.append(os.path.join(ROOT, "packaging", "broken_startup_hook.py"))

a = Analysis(
    [os.path.join(ROOT, "packaging", "run_facturo.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=runtime_hooks,
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Factures",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed exes trigger antivirus false positives
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # keep the small server window; closing it quits the app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="static/favicon.ico",  # optional: add an .ico to brand the exe
)
