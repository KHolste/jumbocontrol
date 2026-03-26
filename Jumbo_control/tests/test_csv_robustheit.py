"""
Tests für CSV-Schreiber Robustheit: Pending-Mechanismus bei gesperrter Datei.
"""
import os
import pytest
from daten.csv_schreiber import CsvSchreiber


HEADER = ["ISO_lokal", "MJD", "UTC", "T1"]
ZEILE1 = ["2026-03-26T12:00:00", "61129.5", "2026-03-26T11:00:00Z", "293.15"]
ZEILE2 = ["2026-03-26T12:00:05", "61129.5001", "2026-03-26T11:00:05Z", "293.20"]


def test_normale_schreiboperation(tmp_path):
    """Normales Schreiben: Datei wird mit Header + Zeile erstellt."""
    csv = CsvSchreiber(pfad=str(tmp_path))
    datei = str(tmp_path / "test.csv")

    csv._schreibe_zeile(datei, HEADER, ZEILE1)

    inhalt = open(datei, encoding="utf-8").read()
    assert "ISO_lokal" in inhalt
    assert "293.15" in inhalt


def test_zweite_zeile_ohne_doppelten_header(tmp_path):
    """Zweite Zeile an bestehende Datei: kein doppelter Header."""
    csv = CsvSchreiber(pfad=str(tmp_path))
    datei = str(tmp_path / "test.csv")

    csv._schreibe_zeile(datei, HEADER, ZEILE1)
    csv._schreibe_zeile(datei, HEADER, ZEILE2)

    zeilen = open(datei, encoding="utf-8").read().strip().splitlines()
    assert len(zeilen) == 3  # 1 Header + 2 Datenzeilen
    # Header nur einmal
    header_count = sum(1 for z in zeilen if z.startswith("ISO_lokal"))
    assert header_count == 1


def test_pending_datei_bei_gesperrter_hauptdatei(tmp_path):
    """Wenn Hauptdatei gesperrt → Zeile in .pending gesichert."""
    csv = CsvSchreiber(pfad=str(tmp_path))
    datei = str(tmp_path / "test.csv")
    pending = datei + ".pending"

    # Erste Zeile normal schreiben
    csv._schreibe_zeile(datei, HEADER, ZEILE1)

    # Hauptdatei sperren (exklusiv öffnen und halten)
    # Simuliere PermissionError durch schreibgeschützte Datei
    os.chmod(datei, 0o444)
    try:
        csv._schreibe_zeile(datei, HEADER, ZEILE2)
    finally:
        os.chmod(datei, 0o666)

    # Pending-Datei muss existieren und die Daten enthalten
    assert os.path.exists(pending), "Pending-Datei wurde nicht erstellt"
    inhalt = open(pending, encoding="utf-8").read()
    assert "293.20" in inhalt


def test_pending_merge_bei_naechstem_schreiben(tmp_path):
    """Pending-Daten werden beim nächsten erfolgreichen Schreiben nachgeholt."""
    csv = CsvSchreiber(pfad=str(tmp_path))
    datei = str(tmp_path / "test.csv")
    pending = datei + ".pending"

    # Erste Zeile normal
    csv._schreibe_zeile(datei, HEADER, ZEILE1)

    # Pending-Datei manuell simulieren
    with open(pending, "w", newline="", encoding="utf-8") as f:
        f.write("\t".join(ZEILE2) + "\n")

    # Dritte Zeile schreiben → pending sollte gemergt werden
    zeile3 = ["2026-03-26T12:00:10", "61129.5002", "2026-03-26T11:00:10Z", "293.25"]
    csv._schreibe_zeile(datei, HEADER, zeile3)

    # Pending-Datei muss weg sein
    assert not os.path.exists(pending), "Pending-Datei wurde nicht aufgeräumt"

    # Hauptdatei muss alle 3 Datenzeilen enthalten
    inhalt = open(datei, encoding="utf-8").read()
    zeilen = inhalt.strip().splitlines()
    assert len(zeilen) == 4  # Header + 3 Zeilen
    # Neue Zeile zuerst, dann Pending-Daten nachgeholt
    assert "293.25" in inhalt
    assert "293.20" in inhalt


def test_leere_pending_wird_aufgeraeumt(tmp_path):
    """Leere Pending-Datei wird sauber entfernt."""
    csv = CsvSchreiber(pfad=str(tmp_path))
    datei = str(tmp_path / "test.csv")
    pending = datei + ".pending"

    # Leere pending-Datei erstellen
    open(pending, "w").close()

    csv._schreibe_zeile(datei, HEADER, ZEILE1)

    assert not os.path.exists(pending)
