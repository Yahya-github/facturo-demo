"""Print the CHANGELOG.md section of one version (release.yml's release body).

Usage: python packaging/release_notes.py 2.1.0 [CHANGELOG.md]
Exits 1 when the version has no section or the section is empty.
"""

import re
import sys
from pathlib import Path


def section(text: str, version: str) -> str:
    pattern = rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)"
    m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def main(argv: list[str]) -> int:
    if not 1 <= len(argv) <= 2:
        print(__doc__, file=sys.stderr)
        return 1
    version = argv[0].lstrip("v")
    path = Path(argv[1] if len(argv) == 2 else "CHANGELOG.md")
    body = section(path.read_text(encoding="utf-8"), version)
    if not body:
        print(f"CHANGELOG.md has no notes for {version}", file=sys.stderr)
        return 1
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
