#!/usr/bin/env bash
# Prepare a release: validate, run the checks, bump facturo/version.py, roll
# CHANGELOG.md's [Unreleased] notes into a dated section, commit and tag.
#
#   scripts/release.sh X.Y.Z[-rcN] [--push]
#
# Nothing is pushed unless --push is given; the push command is printed
# instead. Pushing the tag triggers .github/workflows/release.yml.
#
# Environment:
#   PYTHON  interpreter with requirements-dev.txt installed (default: python3)
#   DATA_DB database for the migration dry run (default: data/data.db, the
#           dev-mode database; skipped when absent)
#   FACTURO_RELEASE_SELFTEST=1  test-suite only: skip the nested test run
set -euo pipefail

die() { echo "Erreur : $*" >&2; exit 1; }

cd "$(git rev-parse --show-toplevel)"
PY="${PYTHON:-python3}"
NEW_VERSION="${1:-}"
PUSH="no"
[ "${2:-}" = "--push" ] && PUSH="yes"
[ -n "$NEW_VERSION" ] || die "usage : scripts/release.sh X.Y.Z[-rcN] [--push]"

# ── 1-4. Cheap validation first (seconds, before any test run) ──
if [ -n "$(git status --porcelain)" ]; then
    die "des modifications non commitées existent. Faites un commit (ou git stash) avant de publier."
fi

if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-rc[0-9]+)?$ ]]; then
    die "« $NEW_VERSION » n'est pas une version semver valide (X.Y.Z ou X.Y.Z-rcN)."
fi

CURRENT_VERSION=$("$PY" -c "from facturo.version import __version__; print(__version__)")
CMP=$("$PY" -c "import sys; from facturo.services.updater import compare_versions as c; print(c(sys.argv[1], sys.argv[2]))" "$NEW_VERSION" "$CURRENT_VERSION")
if [ "$CMP" != "1" ]; then
    die "la version $NEW_VERSION doit être strictement supérieure à la version actuelle $CURRENT_VERSION."
fi

# Body of [Unreleased]: lines after its heading up to the next "## [" heading.
unreleased_body() {
    awk '/^## \[Unreleased\]/{f=1; next} /^## \[/{f=0} f' CHANGELOG.md
}
grep -q '^## \[Unreleased\]' CHANGELOG.md || die "CHANGELOG.md n'a pas de section ## [Unreleased]."
if ! unreleased_body | grep -q '[^[:space:]]'; then
    die "la section ## [Unreleased] de CHANGELOG.md est vide : décrivez les changements."
fi

# ── 5. Tests and lint ──
# FACTURO_RELEASE_SELFTEST=1 is set only by tests/test_release_tooling.py,
# which drives this script from inside the test suite: re-running the suite
# there would recurse (suite -> release.sh -> suite ...). Never set it for a
# real release.
if [ "${FACTURO_RELEASE_SELFTEST:-}" = "1" ]; then
    echo "############################################################" >&2
    echo "# ATTENTION : FACTURO_RELEASE_SELFTEST=1 -> tests IGNORÉS.  #" >&2
    echo "# Réservé aux tests de release.sh. Ne publiez pas ainsi.   #" >&2
    echo "############################################################" >&2
else
    echo "Tests..."
    "$PY" -m pytest -q -p no:cacheprovider || die "les tests échouent."
fi
echo "Ruff..."
"$PY" -m ruff check . || die "ruff signale des erreurs."

# ── 6. Migration dry run on a copy of the dev database ──
DATA_DB="${DATA_DB:-data/data.db}"
if [ -f "$DATA_DB" ]; then
    echo "Migration à blanc sur une copie de $DATA_DB..."
    "$PY" -m facturo.tools.migrate_check "$DATA_DB" || die "la migration modifie des totaux."
else
    echo "Pas de $DATA_DB : migration à blanc ignorée."
fi

# ── 7-8. Bump version, roll the changelog ──
printf '__version__ = "%s"\n' "$NEW_VERSION" > facturo/version.py

TODAY=$(date +%Y-%m-%d)
awk -v ver="$NEW_VERSION" -v today="$TODAY" '
    /^## \[Unreleased\]/ && !done { print; print ""; print "## [" ver "] - " today; done=1; next }
    { print }
' CHANGELOG.md > CHANGELOG.md.tmp
# Drop the blank lines directly under the new heading duplicated from Unreleased.
awk 'prev_heading && /^[[:space:]]*$/ {next} {prev_heading = /^## \[[0-9]/; print}' \
    CHANGELOG.md.tmp > CHANGELOG.md
rm -f CHANGELOG.md.tmp

# ── 9-10. Commit and tag ──
git add facturo/version.py CHANGELOG.md
git commit -q -m "chore: release v$NEW_VERSION"
git tag -a "v$NEW_VERSION" -m "Factures v$NEW_VERSION"

# ── 11. Push (only on request) ──
echo "Version $NEW_VERSION prête (commit + tag v$NEW_VERSION)."
if [ "$PUSH" = "yes" ]; then
    git push origin HEAD "v$NEW_VERSION"
else
    echo "Pour publier : git push origin HEAD v$NEW_VERSION"
fi
