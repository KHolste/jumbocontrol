"""
Tests für daten/csv_leser.py – alle drei unterstützten CSV-Formate.

CsvLeser hat keine Hardware-Abhängigkeiten (nur stdlib).
"""
import pytest
from datetime import datetime
from daten.csv_leser import CsvLeser


# ── Testdaten ─────────────────────────────────────────────────

NEUES_DRUCK_CSV = (
    "ISO_lokal\tMJD\tUTC\t"
    "CENT\tCENT_status\tCENT_kal\t"
    "DOOR\tDOOR_status\tDOOR_kal\t"
    "BA\tBA_status\tBA_kal\n"
    "2026-03-20T12:00:00\t61123.500000\t2026-03-20T11:00:00Z\t"
    "1.23E-04\tOK\tNaN\t"
    "9.50E+00\tOK\t9.45E+00\t"
    "NaN\tNo sensor\tNaN\n"
    "2026-03-20T12:00:05\t61123.500058\t2026-03-20T11:00:05Z\t"
    "1.25E-04\tOK\tNaN\t"
    "9.48E+00\tOK\t9.43E+00\t"
    "NaN\tNo sensor\tNaN\n"
)

LABVIEW_DRUCK_CSV = (
    "date\ttime\tCENT\tDOOR\tMASS\tBA\n"
    "20.03.2026\t12:00:00\t1,23E-4\t9,50E+0\t0\t0\n"
    "20.03.2026\t12:00:05\t1,25E-4\t9,48E+0\t0\t0\n"
)


# ── Neues Jumbo-Format ────────────────────────────────────────

def test_neues_format_liefert_korrekte_werte(tmp_path):
    """Neues Format: Tab-CSV mit ISO-Datum, Punkt als Dezimal."""
    datei = tmp_path / "2026-03-20_druck.csv"
    datei.write_text(NEUES_DRUCK_CSV, encoding="utf-8")

    daten = CsvLeser().lese_druck(str(datei))

    assert "CENT" in daten
    assert "DOOR" in daten
    assert len(daten["CENT"]) == 2

    assert daten["CENT"][0] == pytest.approx(1.23e-4, rel=1e-3)
    assert daten["CENT"][1] == pytest.approx(1.25e-4, rel=1e-3)
    assert daten["DOOR"][0] == pytest.approx(9.50,    rel=1e-3)


def test_neues_format_zeitstempel(tmp_path):
    """ISO-Zeitstempel muss als datetime-Objekt zurückkommen."""
    datei = tmp_path / "2026-03-20_druck.csv"
    datei.write_text(NEUES_DRUCK_CSV, encoding="utf-8")

    daten = CsvLeser().lese_druck(str(datei))

    ts = daten["ISO_lokal"][0]
    assert isinstance(ts, datetime)
    assert ts.year == 2026
    assert ts.month == 3
    assert ts.day == 20


def test_neues_format_mjd(tmp_path):
    """MJD-Spalte muss als Float eingelesen werden."""
    datei = tmp_path / "2026-03-20_druck.csv"
    datei.write_text(NEUES_DRUCK_CSV, encoding="utf-8")

    daten = CsvLeser().lese_druck(str(datei))

    assert daten["MJD"][0] == pytest.approx(61123.5, rel=1e-6)


# ── LabVIEW-Format ────────────────────────────────────────────

def test_labview_druck_format(tmp_path):
    """Altes LabVIEW-Format: Datum+Zeit getrennt, Komma als Dezimalzeichen."""
    datei = tmp_path / "alt_druck.csv"
    datei.write_text(LABVIEW_DRUCK_CSV, encoding="utf-8")

    daten = CsvLeser().lese_druck(str(datei))

    assert "CENT" in daten
    assert len(daten["CENT"]) == 2

    # Komma als Dezimal muss korrekt konvertiert werden
    assert daten["CENT"][0] == pytest.approx(1.23e-4, rel=1e-3)
    assert daten["DOOR"][0] == pytest.approx(9.50,    rel=1e-3)


def test_labview_druck_zeitstempel(tmp_path):
    """LabVIEW: date+time-Spalten müssen zu datetime zusammengesetzt werden."""
    datei = tmp_path / "alt_druck.csv"
    datei.write_text(LABVIEW_DRUCK_CSV, encoding="utf-8")

    daten = CsvLeser().lese_druck(str(datei))

    ts = daten["ISO_lokal"][0]
    assert isinstance(ts, datetime)
    assert ts.day == 20 and ts.month == 3 and ts.year == 2026
    assert ts.hour == 12 and ts.minute == 0


# ── Randwerte ─────────────────────────────────────────────────

def test_leere_datei_gibt_leeres_dict(tmp_path):
    """Leere CSV darf nicht crashen – erwartet leeres Dict."""
    datei = tmp_path / "leer.csv"
    datei.write_text("", encoding="utf-8")

    daten = CsvLeser().lese_druck(str(datei))

    assert daten == {}


def test_nur_header_keine_datenzeilen(tmp_path):
    """Datei mit nur Header und ohne Daten muss leere Listen liefern."""
    inhalt = "ISO_lokal\tMJD\tUTC\tCENT\tCENT_status\tCENT_kal\n"
    datei = tmp_path / "nur_header.csv"
    datei.write_text(inhalt, encoding="utf-8")

    daten = CsvLeser().lese_druck(str(datei))

    assert "CENT" in daten
    assert daten["CENT"] == []
