"""RED tests for the release pipeline: scripts/release.sh, facturo/tools/migrate_check.py
and the GitHub Actions workflow files.

None of `scripts/release.sh`, `facturo/tools/migrate_check.py`,
`.github/workflows/ci.yml` or `.github/workflows/release.yml` exist yet — see
`changes/team-d.md` for the full contract. Every test below fails today
(missing file / missing module) for exactly that reason.

Safety: the release.sh tests run against a **local, no-hardlink git clone** of
this worktree in a tmp_path, never the worktree itself. Right after cloning,
the `origin` remote (which `git clone` points at this very worktree) is
removed, so nothing this script does — including a hypothetical buggy `git
push` — can ever reach the real repository or its shared object store. No
step here pushes anything, and `--push` is never passed.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_BIN = str(Path(sys.executable).resolve().parent)
GIT_TIMEOUT = 30
RELEASE_TIMEOUT = 180


# ── shared helpers ─────────────────────────────────────────


def _clean_env(extra: dict | None = None) -> dict:
    """A subprocess env with this venv's bin first on PATH and no inherited
    FACTURO_DATA_DIR — nested pytest runs must get their own temp data dir
    from tests/conftest.py, not silently reuse the outer session's."""
    env = dict(os.environ)
    env.pop("FACTURO_DATA_DIR", None)
    env["PATH"] = f"{VENV_BIN}:{env.get('PATH', '')}"
    # release.sh runs the whole test suite, which contains these tests: this
    # project-specific switch makes it skip that nested run (with a warning)
    # instead of recursing.
    env["FACTURO_RELEASE_SELFTEST"] = "1"
    if extra:
        env.update(extra)
    return env


def _git(repo_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo_dir), *args],
                           capture_output=True, text=True, timeout=GIT_TIMEOUT)


@pytest.fixture
def release_repo(tmp_path) -> Path:
    """A throwaway, local-only clone of this worktree at HEAD, with a known
    baseline `facturo/version.py` (1.9.0) and `CHANGELOG.md` (one Unreleased
    bullet), committed so the tree starts clean."""
    if sys.platform == "win32":
        # release.sh is a developer-side bash script; on the Windows runner
        # `bash` is the WSL launcher, which has no distribution installed.
        pytest.skip("release.sh runs on the developer's machine, not on Windows")
    repo_dir = tmp_path / "repo"
    clone = subprocess.run(
        ["git", "clone", "--no-hardlinks", "--quiet", str(REPO_ROOT), str(repo_dir)],
        capture_output=True, text=True, timeout=GIT_TIMEOUT,
    )
    assert clone.returncode == 0, clone.stderr

    # Belt and suspenders: this clone must never be able to reach the real
    # repository, even by accident.
    _git(repo_dir, "remote", "remove", "origin")
    # The clone inherits the real release tags (v2.0.0-rc1, ...), which would
    # collide with the versions these tests release.
    for tag in _git(repo_dir, "tag", "--list").stdout.split():
        _git(repo_dir, "tag", "-d", tag)
    _git(repo_dir, "checkout", "-B", "release-test")
    _git(repo_dir, "config", "user.email", "release-test@example.invalid")
    _git(repo_dir, "config", "user.name", "Release Test")

    (repo_dir / "facturo" / "version.py").write_text('__version__ = "1.9.0"\n', encoding="utf-8")
    (repo_dir / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n"
        "- Ajout d'une fonctionnalité de test.\n\n"
        "## [1.9.0] - 2026-01-01\n"
        "- Version précédente.\n",
        encoding="utf-8",
    )
    add = _git(repo_dir, "add", "-A")
    assert add.returncode == 0, add.stderr
    commit = _git(repo_dir, "commit", "-q", "-m", "test: release.sh fixture baseline")
    assert commit.returncode == 0, commit.stderr
    return repo_dir


def _run_release(repo_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(repo_dir / "scripts" / "release.sh"), *args],
        cwd=repo_dir, env=_clean_env(), capture_output=True, text=True, timeout=RELEASE_TIMEOUT,
    )


def _section(changelog_text: str, heading_prefix: str) -> str | None:
    """Body text between a heading starting with `heading_prefix` and the next
    '## [' heading (or end of file)."""
    pattern = rf"^{re.escape(heading_prefix)}.*?\n(.*?)(?=^## \[|\Z)"
    m = re.search(pattern, changelog_text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else None


# ── scripts/release.sh refusal cases ──────────────────────


def test_release_sh_refuses_a_dirty_working_tree(release_repo):
    (release_repo / "CHANGELOG.md").write_text(
        (release_repo / "CHANGELOG.md").read_text(encoding="utf-8") + "\n<!-- dirty -->\n",
        encoding="utf-8",
    )
    result = _run_release(release_repo, "2.0.0")
    assert result.returncode != 0
    assert "commit" in (result.stdout + result.stderr).lower()


def test_release_sh_refuses_a_non_semver_version(release_repo):
    result = _run_release(release_repo, "not-a-version")
    assert result.returncode != 0
    assert "semver" in (result.stdout + result.stderr).lower()


@pytest.mark.parametrize("candidate", ["1.9.0", "1.0.0", "1.8.9"])
def test_release_sh_refuses_a_version_that_is_not_greater(release_repo, candidate):
    result = _run_release(release_repo, candidate)
    assert result.returncode != 0
    assert "supérieure" in (result.stdout + result.stderr).lower() \
        or "superieure" in (result.stdout + result.stderr).lower()


def test_release_sh_refuses_when_changelog_has_no_unreleased_content(release_repo):
    (release_repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [1.9.0] - 2026-01-01\n- Version précédente.\n",
        encoding="utf-8",
    )
    _git(release_repo, "commit", "-aqm", "test: empty the Unreleased section")
    result = _run_release(release_repo, "2.0.0")
    assert result.returncode != 0
    assert "Unreleased" in (result.stdout + result.stderr)


def test_release_sh_validates_before_running_the_expensive_checks(release_repo):
    """Argument/state validation must happen before pytest+ruff+migration dry
    run, so a typo'd version number fails in well under the time a full test
    run would take."""
    import time

    start = time.monotonic()
    result = _run_release(release_repo, "not-a-version")
    elapsed = time.monotonic() - start
    assert result.returncode != 0
    assert elapsed < 5, "invalid input should be rejected before the expensive checks run"


# ── scripts/release.sh success path ───────────────────────


def test_release_sh_bumps_version_moves_changelog_tags_and_never_pushes(release_repo):
    result = _run_release(release_repo, "2.0.0")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    version_after = (release_repo / "facturo" / "version.py").read_text(encoding="utf-8")
    assert "2.0.0" in version_after

    changelog_after = (release_repo / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased_after = _section(changelog_after, "## [Unreleased]")
    assert not unreleased_after, "Unreleased notes must move out, leaving the section empty"
    v2_section = _section(changelog_after, "## [2.0.0]")
    assert v2_section is not None, "a ## [2.0.0] heading must be added"
    assert "Ajout d'une fonctionnalité de test." in v2_section

    log_subject = _git(release_repo, "log", "-1", "--pretty=%s").stdout.strip()
    assert "release" in log_subject.lower()
    assert "2.0.0" in log_subject

    tags = _git(release_repo, "tag", "--list").stdout.split()
    assert "v2.0.0" in tags

    assert "git push" in (result.stdout + result.stderr).lower(), \
        "must print the push command rather than pushing"
    # Defense in depth: prove nothing was ever pushed anywhere by asserting no
    # remote exists to push to (the fixture removed `origin` up front).
    assert _git(release_repo, "remote").stdout.strip() == ""


def test_release_sh_accepts_a_release_candidate_suffix(release_repo):
    result = _run_release(release_repo, "2.0.0-rc1")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    version_after = (release_repo / "facturo" / "version.py").read_text(encoding="utf-8")
    assert "2.0.0-rc1" in version_after
    tags = _git(release_repo, "tag", "--list").stdout.split()
    assert "v2.0.0-rc1" in tags


# ── facturo/tools/migrate_check.py ────────────────────────


def _build_synthetic_v1_db(tmp_path: Path) -> Path:
    """A database shaped like a real client's pre-v2 file: base tables plus
    every column added during v1's life (see core/schema.py:_migrate_v1), but
    none of the v2 additions — built with schema.py's own helpers so this
    fixture can never drift from what `migrate()` actually expects to see."""
    sys.path.insert(0, str(REPO_ROOT))
    from facturo.core import schema as _schema

    db_path = tmp_path / "v1.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_schema._BASE_TABLES)
    _schema._migrate_v1(conn)
    conn.execute(
        "INSERT INTO clients (ref, prefix, nom, adresse) VALUES ('r', 'p', 'Client Test', '1 rue Test')"
    )
    billets = json.dumps([
        {"chantier": "Chantier A", "plaque": "L 123456", "quantite": 8, "prix": 55.0},
        {"chantier": "Chantier B", "plaque": "L 654321", "quantite": 4, "prix": 60.0},
    ])
    conn.execute(
        "INSERT INTO factures (client_id, numero, date, fichier, billets_json, "
        "remise_type, remise_valeur) VALUES (1, 'f001', '2025-06-01', 'f001.xlsx', ?, 'montant', 10.0)",
        (billets,),
    )
    conn.commit()
    conn.close()
    return db_path


def test_migrate_check_reports_success_on_a_synthetic_v1_db(tmp_path):
    from facturo.tools import migrate_check

    db_path = _build_synthetic_v1_db(tmp_path)
    original_bytes = db_path.read_bytes()

    result = migrate_check.check(db_path)

    assert result["ok"] is True
    assert result["before_total"] == pytest.approx(result["after_total"], abs=0.01)
    assert db_path.read_bytes() == original_bytes, "migrate_check must operate on a copy, never the original"


def test_migrate_check_fails_loudly_when_totals_diverge(tmp_path):
    from facturo.tools import migrate_check

    db_path = _build_synthetic_v1_db(tmp_path)
    calls = {"n": 0}

    def flaky_total(conn):
        calls["n"] += 1
        return 100.0 if calls["n"] == 1 else 999.0

    result = migrate_check.check(db_path, total_fn=flaky_total)
    assert result["ok"] is False
    assert "999" in result["message"] or "différent" in result["message"].lower() \
        or "different" in result["message"].lower()


def test_migrate_check_cli_exits_zero_on_success(tmp_path):
    db_path = _build_synthetic_v1_db(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "facturo.tools.migrate_check", str(db_path)],
        cwd=REPO_ROOT, env=_clean_env(), capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"


def test_migrate_check_cli_exits_nonzero_when_file_is_missing(tmp_path):
    missing = tmp_path / "nope.db"
    proc = subprocess.run(
        [sys.executable, "-m", "facturo.tools.migrate_check", str(missing)],
        cwd=REPO_ROOT, env=_clean_env(), capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0


# ── GitHub Actions workflow files ─────────────────────────


def _try_yaml_load(text: str):
    try:
        import yaml
    except ImportError:
        return None  # PyYAML absent in this environment — fall back to substring checks
    return yaml.safe_load(text)


def test_ci_workflow_parses_and_has_required_steps():
    path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert path.exists(), "ci.yml is missing"
    text = path.read_text(encoding="utf-8")
    assert "\t" not in text, "YAML must be indented with spaces, not tabs"

    parsed = _try_yaml_load(text)
    if parsed is not None:
        assert parsed.get("jobs"), "ci.yml must define at least one job"

    for required in ("pytest", "ruff", "playwright install", "requirements-dev.txt"):
        assert required in text, f"ci.yml must mention {required!r}"
    assert re.search(r"on:\s*\n\s*(push|pull_request)", text), \
        "ci.yml must trigger on push and/or pull_request"


def test_release_workflow_parses_and_has_required_steps():
    path = REPO_ROOT / ".github" / "workflows" / "release.yml"
    assert path.exists(), "release.yml is missing"
    text = path.read_text(encoding="utf-8")
    assert "\t" not in text, "YAML must be indented with spaces, not tabs"

    parsed = _try_yaml_load(text)
    if parsed is not None:
        assert parsed.get("jobs"), "release.yml must define at least one job"

    lowered = text.lower()
    for required in ("windows-latest", "pyinstaller", "--smoke-test", "sha256", "pytest"):
        assert required in lowered, f"release.yml must mention {required!r}"
    assert re.search(r"tags:\s*\n\s*-\s*['\"]?v", text), "release.yml must trigger on v* tags"
    assert "prerelease" in lowered, "release.yml must mark -rc tags as prereleases"
    assert re.search(r"rollback|swap", lowered), \
        "release.yml must include a swap/rollback verification job"
