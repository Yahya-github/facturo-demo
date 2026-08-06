"""PyInstaller runtime hook for CI only: makes the built exe fail at startup.

Factures.spec adds it when FACTURO_BUILD_BROKEN=1, so release.yml can build a
deliberately broken "next version" and prove update_helper.cmd rolls back.
Never part of a normal build.
"""

import sys

sys.stderr.write("FACTURO_BUILD_BROKEN: this build fails at startup on purpose (CI rollback test)\n")
sys.exit(3)
