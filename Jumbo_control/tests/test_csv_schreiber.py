"""
Regressionstests für daten/csv_schreiber.py.

Wichtigster Test: Bug #1 (CENT/CENTER-Key-Mismatch).
druck.py liefert {"CENTER": ...}, csv_schreiber.py suchte früher
nach "CENT" → CENTER-Wert wurde immer als NaN gespeichert.
"""
import pytest
from daten.csv_schreiber import CsvSchreiber


# ── Hilfsfunktion ─────────────────────────────────────────────

def _lese_druck_csv(tmp_path):
    """Liest die einzige *_druck.csv aus tmp_path und gibt (header, daten) zurück."""
    dateien = list(tmp_path.glob("*_druck.csv"))
    assert dateien, "Keine *_druck.csv angelegt"
    zeilen = dateien[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(zeilen) >= 2, "CSV hat keine Datenzeile"
    header = zeilen[0].split("\t")
    daten  = zeilen[1].split("\t")
    return header, daten


# ── Regressionstests CENT/CENTER ──────────────────────────────

def test_center_wert_wird_gespeichert(tmp_path):
    """
    Regressionstest Bug #1:
    druck.py liefert Key "CENTER" – csv_schreiber muss diesen finden.
    Vor dem Fix: werte.get("CENT") → None → NaN in CSV.
    """
    werte = {
        "CENTER": {"mbar": 1.23e-4, "gueltig": True,  "status": "OK"},
        "DOOR":   {"mbar": 9.50e+0, "gueltig": True,  "status": "OK"},
        "BA":     {"mbar": None,    "gueltig": False,  "status": "No sensor"},
    }

    CsvSchreiber(pfad=str(tmp_path)).speichere_druecke(werte)

    header, daten = _lese_druck_csv(tmp_path)

    cent_idx = header.index("CENT")
    assert daten[cent_idx] != "NaN", (
        "CENTER-Wert als NaN gespeichert – CENT/CENTER-Key-Mismatch nicht behoben"
    )
    assert float(daten[cent_idx]) == pytest.approx(1.23e-4, rel=1e-3)


def test_door_wert_wird_gespeichert(tmp_path):
    """DOOR-Kanal hatte keinen Namens-Mismatch – muss weiterhin korrekt sein."""
    werte = {
        "CENTER": {"mbar": 1.23e-4, "gueltig": True,  "status": "OK"},
        "DOOR":   {"mbar": 9.50e+0, "gueltig": True,  "status": "OK"},
        "BA":     {"mbar": None,    "gueltig": False,  "status": "No sensor"},
    }

    CsvSchreiber(pfad=str(tmp_path)).speichere_druecke(werte)

    header, daten = _lese_druck_csv(tmp_path)

    door_idx = header.index("DOOR")
    assert daten[door_idx] != "NaN"
    assert float(daten[door_idx]) == pytest.approx(9.50, rel=1e-3)


def test_ungueltige_sensoren_werden_nan(tmp_path):
    """Ausgefallene Sensoren (gueltig=False oder mbar=None) → NaN in CSV."""
    werte = {
        "CENTER": {"mbar": None, "gueltig": False, "status": "No sensor"},
        "DOOR":   {"mbar": None, "gueltig": False, "status": "Sensor error"},
        "BA":     {"mbar": None, "gueltig": False, "status": "Sensor off"},
    }

    CsvSchreiber(pfad=str(tmp_path)).speichere_druecke(werte)

    header, daten = _lese_druck_csv(tmp_path)

    for spalte in ("CENT", "DOOR", "BA"):
        idx = header.index(spalte)
        assert daten[idx] == "NaN", f"Spalte {spalte}: erwartet NaN, got '{daten[idx]}'"


def test_csv_header_enthaelt_alle_pflichtspalten(tmp_path):
    """CSV-Header muss Zeitstempel-Spalten und alle Druckspalten enthalten."""
    werte = {
        "CENTER": {"mbar": 1.0e-3, "gueltig": True,  "status": "OK"},
        "DOOR":   {"mbar": 1.0e-3, "gueltig": True,  "status": "OK"},
        "BA":     {"mbar": None,   "gueltig": False,  "status": "No sensor"},
    }

    CsvSchreiber(pfad=str(tmp_path)).speichere_druecke(werte)

    header, _ = _lese_druck_csv(tmp_path)

    for pflicht in ("ISO_lokal", "MJD", "UTC",
                    "CENT", "CENT_status", "CENT_kal",
                    "DOOR", "DOOR_status", "DOOR_kal",
                    "BA",   "BA_status",   "BA_kal"):
        assert pflicht in header, f"Pflichtspalte '{pflicht}' fehlt im Header"
