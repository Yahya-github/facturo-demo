"""RED tests for `python -m facturo --smoke-test`.

CI runs this exact invocation against the built `Factures.exe` after packaging
(see changes/team-d.md and the planned `.github/workflows/release.yml`): boot
the real server on a temp data dir, GET /api/version, print the version, exit
0 — non-zero on any failure. These tests exercise the same CLI contract via
`python -m facturo` (not the built exe) so they run everywhere pytest does.

Each test spawns a real subprocess with its own temp FACTURO_DATA_DIR — no
shared state with the rest of the suite, no network beyond 127.0.0.1.
"""

from __future__ import annotations

import os
import subprocess
import sys

from facturo import version

TIMEOUT = 30


def _run_smoke_test(data_dir):
    env = {**os.environ, "FACTURO_DATA_DIR": str(data_dir)}
    return subprocess.run(
        [sys.executable, "-m", "facturo", "--smoke-test"],
        env=env, capture_output=True, text=True, timeout=TIMEOUT,
    )


def test_smoke_test_exits_zero_on_a_fresh_data_dir(tmp_path):
    result = _run_smoke_test(tmp_path)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"


def test_smoke_test_prints_the_current_version(tmp_path):
    result = _run_smoke_test(tmp_path)
    assert version.__version__ in result.stdout


def test_smoke_test_exits_nonzero_when_the_data_dir_is_unusable(tmp_path):
    # A regular file where a directory is expected: sqlite3.connect() cannot
    # open a database "inside" a file, so init_db() must raise and the
    # process must exit non-zero instead of silently reporting success.
    unusable = tmp_path / "not_a_directory"
    unusable.write_text("this is a file, not a directory", encoding="utf-8")

    result = _run_smoke_test(unusable)
    assert result.returncode != 0
