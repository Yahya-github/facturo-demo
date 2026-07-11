"""Unit tests for billet_fields — what the model said -> what reaches the invoice.

These are the functions that silently corrupt an invoice when they get it
wrong, and they are pure, so all of it is testable without Ollama or a GPU.
End-to-end extraction accuracy is measured separately against the
hand-verified billet set.
"""

from datetime import date, timedelta

import pytest

from facturo.core import billet_fields

# --- _normalize_date ------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("2026-06-25", "2026-06-25"),          # already normalized
    ("23/06/2026", "2026-06-23"),          # Quebec day/month order
    ("25 6 2026", "2026-06-25"),           # space separated
    ("29 JUIN 2026", "2026-06-29"),        # French month name
    ("22-06-2026", "2026-06-22"),
    ("09.08.2026", "2026-08-09"),
    ("09-08-26", "2026-08-09"),            # two-digit year
])
def test_normalize_date_reads_the_formats_drivers_write(raw, expected):
    assert billet_fields.normalize_date(raw) == expected


@pytest.mark.parametrize("raw", [
    "25/06/2016",       # a 2 read as a 1
    "25-06-2023",       # a 6 read as a 3
    "25/06/20",         # year truncated to two digits
    "2106-06-25",       # digits transposed, and already in ISO form
])
def test_normalize_date_rebuilds_every_way_the_year_gets_misread(raw):
    """The day and month survive; the year is rebuilt from them.

    Each of these is the same billet — 25 June of the year being invoiced —
    written by a model that lost a different digit every time.
    """
    assert billet_fields.normalize_date(raw) == f"{date.today().year}-06-25"


@pytest.mark.parametrize("raw", [
    "",                 # nothing written
    "25/13/2026",       # month past 12 — a misread, not a US-ordered date
    "pas de date",
])
def test_normalize_date_blanks_what_it_cannot_read(raw):
    assert billet_fields.normalize_date(raw) == ""


def test_repair_year_picks_the_most_recent_plausible_year():
    recent = date.today() - timedelta(days=30)
    assert billet_fields.repair_year(recent.month, recent.day) == recent.year


@pytest.mark.parametrize("days_ahead", [30, 60, 120, 200])
def test_repair_year_never_dates_a_billet_in_the_future(days_ahead):
    """A billet records work already done, so a future date is never the answer."""
    today = date.today()
    ahead = today + timedelta(days=days_ahead)
    year = billet_fields.repair_year(ahead.month, ahead.day)
    assert year is not None
    assert date(year, ahead.month, ahead.day) <= today + timedelta(
        days=billet_fields.FUTURE_GRACE_DAYS)


# --- _clean_plate ---------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("FK68873", "FK68873"),
    ("fk 68 873", "FK68873"),          # spacing and case are noise
    ("K86424S", "K864245"),            # S in the numeric tail is a misread 5
    ("FK6B113", "FK68113"),            # B is a misread 8
    ("DTI Inc", "DTIINC"),           # not plate-shaped: passed through
])
def test_clean_plate(raw, expected):
    assert billet_fields.clean_plate(raw) == expected


# --- _snap_plate ----------------------------------------------------------

FLEET = ["FK68873", "FK68113", "K864249", "K864245", "FK68990", "S/O", "0000"]


def test_snap_plate_fixes_a_single_misread_digit():
    assert billet_fields.snap_plate("FK68893", FLEET) == "FK68873"


def test_snap_plate_leaves_a_plate_that_is_already_in_the_fleet():
    """K864245 and K864249 are both real trucks — the rarer one must survive."""
    assert billet_fields.snap_plate("K864245", FLEET) == "K864245"


def test_snap_plate_refuses_when_two_known_plates_are_equally_close():
    # FK68870 sits one character from FK68873 and one from... nothing else, so
    # build the ambiguity explicitly.
    ambiguous = ["FK68873", "FK68874"]
    assert billet_fields.snap_plate("FK68875", ambiguous) == "FK68875"


def test_snap_plate_ignores_junk_history_and_empty_input():
    assert billet_fields.snap_plate("FK68873", ["S/O", "0000", "10.75"]) == "FK68873"
    assert billet_fields.snap_plate("", FLEET) == ""
    assert billet_fields.snap_plate("FK68893", []) == "FK68893"


def test_snap_plate_leaves_a_genuinely_new_truck_alone():
    assert billet_fields.snap_plate("AB12345", FLEET) == "AB12345"


# --- _snap_chantier -------------------------------------------------------

SITES = ["ROXDALE", "La Henard", "M. RIVARD"]


def test_snap_chantier_fixes_a_misread_letter():
    assert billet_fields.snap_chantier("La Lenard", SITES) == "La Henard"


def test_snap_chantier_keeps_a_new_site_as_read():
    assert billet_fields.snap_chantier("SUMMIT EXCAVATION", SITES) == "SUMMIT EXCAVATION"


def test_snap_chantier_normalizes_to_the_spelling_history_uses():
    assert billet_fields.snap_chantier("m-rivard", SITES) == "M. RIVARD"


# --- _clean_chantier ------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("NORIX (equipe pavage)", "NORIX"),
    ("NORIX (equipe pavage", "NORIX"),   # driver ran out of line, never closed it
    ("ROXDALE", "ROXDALE"),
    ("M. RIVARD", "M. RIVARD"),
])
def test_clean_chantier_drops_the_drivers_aside(raw, expected):
    assert billet_fields.clean_chantier(raw) == expected


# --- _looks_like_address --------------------------------------------------

@pytest.mark.parametrize("text", [
    "7400 CH DU LAC NORD",
    "T400CH DU LAC NORD",     # the same line, with the 7 misread as a T
    "8100 rue Fictive Anjou",
    "Aeroport Central",
])
def test_looks_like_address_spots_a_worksite_line(text):
    assert billet_fields.looks_like_address(text)


@pytest.mark.parametrize("text", [
    "NORIX", "ROXDALE", "La Henard", "M. RIVARD", "PAVEX",
    "SUMMIT EXCAVATION", "LAKESIDE", "",
])
def test_looks_like_address_leaves_real_renter_names_alone(text):
    assert not billet_fields.looks_like_address(text)


# --- _to_number -----------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("8,25", 8.25),
    ("10,5 h", 10.5),
    ("6,5H", 6.5),          # decimal comma wins: six and a half, not six-five
    ("9h15", 9.25),         # h separates hours from MINUTES here
    ("6h45", 6.75),
    ("9H", 9.0),
    ("7h Minimum", 7.0),    # contractual floor, still 7 hours
    ("12h60", 0.0),         # unreadable clock — refuse rather than bill 1260
    ("", 0.0),
])
def test_to_number_reads_both_hour_notations(raw, expected):
    assert billet_fields.to_number(raw) == pytest.approx(expected)


# --- History --------------------------------------------------------------

def test_history_defaults_to_empty_so_callers_without_invoices_still_work():
    assert billet_fields.History() == ((), ())


# --- _near1 ---------------------------------------------------------------

@pytest.mark.parametrize("a, b, expected", [
    ("roxdale", "foxdale", True),      # substitution
    ("fk68873", "fk6887", True),       # deletion
    ("fk68873", "fk688733", True),     # insertion
    ("terra", "terral", True),
    ("abc", "abc", False),             # distance 0 is not a near miss
    ("abc", "axd", False),             # distance 2
    ("a", "abc", False),               # length gap > 1
    ("", "", False),
])
def test_near1_counts_exactly_one_edit(a, b, expected):
    assert billet_fields._near1(a, b) is expected


# --- snap_chantier: the gaps the ratio cutoff used to miss -----------------

SITES_REAL = ["ROXDALE", "NORIX", "KALROC", "SOLTEK", "PAVEX", "L A HÉNARD", "QDS"]


@pytest.mark.parametrize("misread, expected", [
    ("Foxdale", "ROXDALE"),      # 7 chars — the ratio already caught this one
    ("Norlx", "NORIX"),          # 5 chars, ratio 0.800 — used to be missed
    ("KALROG", "KALROC"),        # 6 chars, ratio 0.833 — used to be missed
    ("SOLTEC", "SOLTEK"),        # 6 chars, ratio 0.833 — used to be missed
])
def test_snap_chantier_corrects_regardless_of_name_length(misread, expected):
    assert billet_fields.snap_chantier(misread, SITES_REAL) == expected


def test_snap_chantier_refuses_when_two_names_are_equally_close():
    """The ratio used to break this tie by score, which is a coin flip."""
    both = ["Terra", "Terral"]
    assert billet_fields.snap_chantier("terra1", both) == "terra1"


def test_snap_chantier_leaves_short_names_alone():
    """'QBS' is one edit from 'QDS'; at three characters that means nothing."""
    assert billet_fields.snap_chantier("QBS", SITES_REAL) == "QBS"


# --- snap_plate: insertions, deletions, and unshaped reads ----------------

FLEET_REAL = ["FK68873", "FK68113", "K864249", "K864245", "FK68990"]


@pytest.mark.parametrize("misread, expected", [
    ("FK68893", "FK68873"),      # substitution — already worked
    ("FK6887", "FK68873"),       # a digit dropped
    ("FK688733", "FK68873"),     # a digit doubled
    ("K8642A5", "K864245"),      # an A where a 4 belongs: not plate-shaped
])
def test_snap_plate_handles_every_single_character_slip(misread, expected):
    assert billet_fields.snap_plate(misread, FLEET_REAL) == expected


@pytest.mark.parametrize("plate", ["K864245", "K864249"])
def test_snap_plate_never_rewrites_a_truck_already_in_the_fleet(plate):
    assert billet_fields.snap_plate(plate, FLEET_REAL) == plate


@pytest.mark.parametrize("junk", ["SO", "0000", "1075"])
def test_snap_plate_leaves_non_plates_alone(junk):
    assert billet_fields.snap_plate(junk, FLEET_REAL) == junk


# --- tidy_*: values a person typed ----------------------------------------

@pytest.mark.parametrize("typed, expected", [
    ("FK 68113", "FK68113"),          # the exact pollution found in the live DB
    (" fk 68113 ", "FK68113"),
    ("#FK68873", "FK68873"),
    ("K 864249", "K864249"),
])
def test_tidy_plate_compacts_a_real_plate(typed, expected):
    assert billet_fields.tidy_plate(typed) == expected


@pytest.mark.parametrize("typed", ["S/O", "0000", "10.75", "PAS DE PLAQUE", ""])
def test_tidy_plate_leaves_a_non_plate_visible_as_typed(typed):
    """'S/O' is the user saying there is no plate — mangling it invents a truck."""
    assert billet_fields.tidy_plate(typed) == typed


def test_tidy_chantier_only_fixes_whitespace():
    assert billet_fields.tidy_chantier("  L A  HÉNARD ") == "L A HÉNARD"


@pytest.mark.parametrize("typed, expected", [
    ("No. 50742", "50742"),
    ("#50742", "50742"),
    ("N° 4211", "4211"),
    ("04231", "04231"),        # leading zero is part of the number
    ("ABC123", "ABC123"),      # not decoration — leave it
])
def test_tidy_billet_number_strips_only_decoration(typed, expected):
    assert billet_fields.tidy_billet_number(typed) == expected


@pytest.mark.parametrize("project", ["#26-112", "26-112"])
def test_tidy_billet_number_refuses_a_project_number(project):
    """A wrong billet number is worse than none — it drives the duplicate check."""
    assert billet_fields.tidy_billet_number(project) == ""


# --- canonical_spelling ----------------------------------------------------

def test_canonical_spelling_prefers_the_spelling_actually_used_most():
    assert billet_fields.canonical_spelling(
        [("L A HÉNARD", 5), ("La Henard", 4), ("L A HENARD", 1)]) == "L A HÉNARD"


@pytest.mark.parametrize("variants, expected", [
    ([("excavation northwind", 1), ("EXCAVATION NORTHWIND", 1)], "EXCAVATION NORTHWIND"),
    ([("qds", 1), ("QDS", 1)], "QDS"),
])
def test_canonical_spelling_breaks_a_tie_towards_how_billets_are_printed(variants, expected):
    assert billet_fields.canonical_spelling(variants) == expected


def test_canonical_spelling_is_deterministic_on_a_total_tie():
    variants = [("bbb", 1), ("aaa", 1)]
    assert billet_fields.canonical_spelling(variants) == "aaa"
