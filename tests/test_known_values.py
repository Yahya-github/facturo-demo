"""Tests for the curated known-values list.

Every test runs against a throwaway database, never the real one:
database.get_conn reads DB_PATH at call time, so pointing it at a tmp_path is
enough to isolate all of this from the user's invoices.
"""

import json

import pytest

from facturo.core import billet_fields
from facturo.core import database as db
from facturo.core import known_values as kv


def _invoice(conn, date, billets):
    conn.execute(
        "INSERT INTO factures (client_id, numero, date, fichier, billets_json) "
        "VALUES (1, 'x', ?, 'f.xlsx', ?)",
        (date, json.dumps(billets)),
    )


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """An empty database with one client and no known values yet."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    conn = db.get_conn()
    conn.execute("INSERT INTO clients (id, ref, prefix, nom) VALUES (1, 'r', 'p', 'C')")
    conn.commit()
    conn.close()


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    """A database seeded from invoices reproducing the real-world pollution."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "seeded.db")
    db.init_db()
    conn = db.get_conn()
    conn.execute("INSERT INTO clients (id, ref, prefix, nom) VALUES (1, 'r', 'p', 'C')")
    # One truck and one client, spelled the several ways they really appear in
    # the live database, plus the junk that must not survive seeding.
    _invoice(conn, "2026-06-01", [
        {"chantier": "La Henard", "plaque": "FK 68113", "quantite": 8},
        {"chantier": "ROXDALE", "plaque": "FK68873", "quantite": 8},
    ])
    _invoice(conn, "2026-07-01", [
        {"chantier": "L A HÉNARD", "plaque": "FK68113", "quantite": 8},
        {"chantier": "l a henard", "plaque": "S/O", "quantite": 8},
        {"chantier": "ROXDALE", "plaque": "0000", "quantite": 8},
    ])
    conn.commit()
    conn.close()
    # init_db seeds only when it creates the table, and it created an empty one
    # above — so seed explicitly now that there are invoices to read.
    conn = db.get_conn()
    kv.seed(conn)
    conn.commit()
    conn.close()


# --- usable ---------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("FK 68113", "FK68113"),
    ("fk68113", "FK68113"),
    ("#FK68873", "FK68873"),
])
def test_usable_accepts_a_real_plate(raw, expected):
    assert kv.usable("plaque", raw) == expected


@pytest.mark.parametrize("junk", ["S/O", "0000", "10.75", ""])
def test_usable_refuses_what_is_not_a_plate(junk):
    """Left in, these become authorities the AI snaps real plates towards."""
    assert kv.usable("plaque", junk) == ""


def test_usable_refuses_a_worksite_address_as_a_renter():
    assert kv.usable("chantier", "7400 CH DU LAC NORD") == ""
    assert kv.usable("chantier", "ROXDALE") == "ROXDALE"


# --- seeding --------------------------------------------------------------

def test_seed_merges_every_spelling_of_one_client(seeded_db):
    henard = [r for r in kv.list_all("chantier") if r["cle"] == "lahenard"]
    assert len(henard) == 1, "three spellings should collapse to one row"
    assert henard[0]["times_used"] == 3
    # A frequency tie breaks towards how billets are actually printed.
    assert henard[0]["valeur"] == "L A HÉNARD"


def test_seed_merges_a_plate_written_with_and_without_a_space(seeded_db):
    plates = {r["valeur"]: r["times_used"] for r in kv.list_all("plaque")}
    assert plates["FK68113"] == 2, "'FK 68113' and 'FK68113' are one truck"


def test_seed_drops_junk_plates(seeded_db):
    assert {r["valeur"] for r in kv.list_all("plaque")} == {"FK68113", "FK68873"}


def test_seed_records_the_most_recent_use(seeded_db):
    henard = [r for r in kv.list_all("chantier") if r["cle"] == "lahenard"][0]
    assert henard["last_used"] == "2026-07-01"


def test_seed_runs_only_when_the_table_is_created(fresh_db):
    """A user who clears the list must not find it grown back on restart."""
    kv.add("plaque", "AB12345")
    conn = db.get_conn()
    conn.execute("DELETE FROM known_values")
    conn.commit()
    conn.close()
    db.init_db()
    assert kv.list_all() == []


def test_seed_ignores_free_description_billets(fresh_db):
    """Their fields are leftovers from before the switch and were never billed."""
    conn = db.get_conn()
    _invoice(conn, "2026-06-01",
             [{"chantier": "FANTOME", "plaque": "LE11111",
               "desc_libre": True, "quantite": 8}])
    kv.seed(conn)
    conn.commit()
    conn.close()
    assert kv.list_all() == []


# --- add / update / remove ------------------------------------------------

def test_add_tidies_and_marks_the_value_curated(fresh_db):
    row = kv.add("plaque", " le 99999 ")
    assert row["valeur"] == "LE99999"
    assert row["curated"] == 1
    assert row["times_used"] == 0


def test_add_lets_a_new_truck_be_protected_before_its_first_billet(fresh_db):
    """The whole reason this list is curated rather than derived."""
    kv.add("plaque", "LE99999")
    fleet = kv.for_history("plaque")
    assert billet_fields.snap_plate("LE99999", fleet) == "LE99999"


def test_add_refuses_a_spelling_variant_of_something_present(fresh_db):
    kv.add("plaque", "FK68113")
    with pytest.raises(kv.KnownValueError):
        kv.add("plaque", "fk 68113")


def test_add_refuses_an_unknown_kind(fresh_db):
    with pytest.raises(kv.KnownValueError):
        kv.add("camion", "FK68113")


def test_update_renames_and_pins(fresh_db):
    row = kv.add("chantier", "La Henard")
    updated = kv.update(row["id"], valeur="L A HÉNARD")
    assert updated["valeur"] == "L A HÉNARD"
    assert updated["curated"] == 1
    # Same identity, so the key does not move and nothing is duplicated.
    assert updated["cle"] == row["cle"]
    assert len(kv.list_all("chantier")) == 1


def test_hiding_a_value_removes_it_from_suggestions_and_from_the_ai(fresh_db):
    row = kv.add("chantier", "service")
    kv.update(row["id"], hidden=True)
    assert "service" not in kv.for_history("chantier")
    assert len(kv.list_all("chantier")) == 1, "still listed for curation"


def test_remove_deletes_outright(fresh_db):
    row = kv.add("chantier", "ERREUR")
    kv.remove(row["id"])
    assert kv.list_all("chantier") == []


# --- merge ----------------------------------------------------------------

def test_merge_keeps_the_target_and_moves_the_count(fresh_db):
    terra = kv.add("chantier", "Terra")
    terral = kv.add("chantier", "Terral")
    kv.record([{"chantier": "Terra", "quantite": 1}], "2026-08-01")

    kv.merge(terra["id"], terral["id"])
    rows = {r["valeur"]: r for r in kv.list_all("chantier")}
    assert rows["Terral"]["times_used"] == 1
    assert rows["Terra"]["alias_of"] == terral["id"]
    assert "Terra" not in kv.for_history("chantier")


def test_a_merged_spelling_still_credits_the_survivor(fresh_db):
    terra = kv.add("chantier", "Terra")
    terral = kv.add("chantier", "Terral")
    kv.merge(terra["id"], terral["id"])

    kv.record([{"chantier": "Terra", "quantite": 1}], "2026-08-02")
    rows = {r["valeur"]: r for r in kv.list_all("chantier")}
    assert rows["Terral"]["times_used"] == 1
    assert rows["Terra"]["times_used"] == 0


def test_merge_refuses_the_cases_that_would_corrupt_the_list(fresh_db):
    a = kv.add("chantier", "A NAME")
    b = kv.add("chantier", "B NAME")
    plate = kv.add("plaque", "FK68113")
    with pytest.raises(kv.KnownValueError):
        kv.merge(a["id"], a["id"])              # into itself
    with pytest.raises(kv.KnownValueError):
        kv.merge(a["id"], plate["id"])          # across kinds
    kv.merge(a["id"], b["id"])
    with pytest.raises(kv.KnownValueError):
        kv.merge(b["id"], a["id"])              # into something already merged


def test_remove_does_not_orphan_an_alias(fresh_db):
    a = kv.add("chantier", "A NAME")
    b = kv.add("chantier", "B NAME")
    kv.merge(a["id"], b["id"])
    kv.remove(b["id"])
    survivor = kv.list_all("chantier")[0]
    assert survivor["valeur"] == "A NAME"
    assert survivor["alias_of"] is None


# --- record ---------------------------------------------------------------

def test_record_counts_a_new_value_and_bumps_an_existing_one(fresh_db):
    kv.record([{"chantier": "ROXDALE", "plaque": "FK68113", "quantite": 8}], "2026-08-01")
    kv.record([{"chantier": "ROXDALE", "plaque": "FK68113", "quantite": 8}], "2026-08-05")
    rows = {r["kind"]: r for r in kv.list_all()}
    assert rows["chantier"]["times_used"] == 2
    assert rows["chantier"]["last_used"] == "2026-08-05"


def test_record_never_overwrites_the_spelling_on_file(fresh_db):
    """The stored spelling is what autocomplete offers; it must hold still."""
    kv.add("chantier", "L A HÉNARD")
    kv.record([{"chantier": "la henard", "quantite": 8}], "2026-08-01")
    assert kv.list_all("chantier")[0]["valeur"] == "L A HÉNARD"


def test_record_skips_junk_so_it_never_becomes_an_authority(fresh_db):
    kv.record([{"chantier": "ROXDALE", "plaque": "S/O", "quantite": 8}], "2026-08-01")
    assert kv.for_history("plaque") == []


def test_record_ignores_free_description_billets(fresh_db):
    kv.record([{"chantier": "FANTOME", "desc_libre": True, "quantite": 8}], "2026-08-01")
    assert kv.list_all() == []


# --- for_history ----------------------------------------------------------

def test_for_history_is_ordered_by_use(fresh_db):
    kv.add("chantier", "RARE")
    kv.add("chantier", "COMMON")
    for _ in range(3):
        kv.record([{"chantier": "COMMON", "quantite": 1}], "2026-08-01")
    assert kv.for_history("chantier")[0] == "COMMON"
