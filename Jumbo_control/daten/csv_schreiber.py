"""
daten/csv_schreiber.py
Speichert Messdaten in CSV-Dateien (Tab-getrennt, Punkt als Dezimaltrennzeichen).
Je eine Datei pro Tag: YYYY-MM-DD_temperatur.csv / YYYY-MM-DD_druck.csv

Zeitstempel: ISO 8601 (lokal), MJD, UTC ISO 8601
Altes LabVIEW-Format (Komma als Dezimal) wird beim Einlesen automatisch konvertiert.

Verwendung:
    from daten.csv_schreiber import CsvSchreiber, CsvLeser

    csv = CsvSchreiber()
    csv.speichere_temperaturen(werte)
    csv.speichere_druecke(werte)
"""

import os
import csv
from datetime import datetime, timezone, timedelta
import calendar
from config import LOG_PFAD
from daten.kalibrierung import KalibrierManager

_km = KalibrierManager()  # einmal laden, global verwenden

# ── Sensorreihenfolge ──────────────────────────────────────────
TEMP_SPALTEN = [
    "Kryo 1 In", "Kryo 1", "Kryo 1b",
    "Peltier", "Peltier b",
    "Kryo 2 In", "Kryo 2", "Kryo 2b",
    "Kryo 3 In", "Kryo 3", "Kryo 3b",
    "Kryo 4 In", "Kryo 4", "Kryo 4b",
    "Kryo 5 In", "Kryo 5", "Kryo 5b",
    "Kryo 6 In", "Kryo 6", "Kryo 6b",
    "Kryo 7 In", "Kryo 7",
    "Kryo 9", "Kryo 9b",
    "Kryo 8 In", "Kryo 8",
]

DRUCK_SPALTEN = ["CENT", "DOOR", "BA"]


# ── Zeitfunktionen ─────────────────────────────────────────────
def _mjd(dt_utc: datetime) -> float:
    """Modifiziertes Julianisches Datum aus UTC-datetime."""
    epoch = datetime(1858, 11, 17, tzinfo=timezone.utc)
    return (dt_utc - epoch).total_seconds() / 86400.0


def _zeitstempel() -> tuple:
    """
    Gibt (iso_lokal, mjd, iso_utc) zurück.
    iso_lokal: 2026-03-16T00:00:03
    mjd:       60384.000035
    iso_utc:   2026-03-16T23:00:03Z
    """
    jetzt_utc  = datetime.now(timezone.utc)
    jetzt_lok  = datetime.now()
    iso_lokal  = jetzt_lok.strftime("%Y-%m-%dT%H:%M:%S")
    iso_utc    = jetzt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    mjd        = _mjd(jetzt_utc)
    return iso_lokal, mjd, iso_utc


# ── CsvSchreiber ───────────────────────────────────────────────
class CsvSchreiber:
    """
    Schreibt Messdaten in tagesweise CSV-Dateien.
    Neue Datei wird automatisch um Mitternacht angelegt.
    """

    def __init__(self, pfad=LOG_PFAD):
        self._pfad = pfad
        os.makedirs(pfad, exist_ok=True)

    def _dateiname(self, typ: str) -> str:
        datum = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self._pfad, f"{datum}_{typ}.csv")

    def _schreibe_zeile(self, datei: str, header: list, zeile: list):
        """
        Schreibt eine Zeile in die CSV-Datei.
        Bei gesperrter Datei (z.B. Excel) → Fallback in .pending-Datei,
        damit keine Messdaten verloren gehen.
        """
        neu = not os.path.exists(datei)
        try:
            with open(datei, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter="\t")
                if neu:
                    writer.writerow(header)
                writer.writerow(zeile)
                f.flush()
                os.fsync(f.fileno())
            # Nach erfolgreichem Schreiben: pending-Daten nachholen
            self._merge_pending(datei, header)
        except PermissionError:
            # Datei gesperrt → in .pending-Datei sichern
            pending = datei + ".pending"
            with open(pending, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(zeile)
                f.flush()

    def _merge_pending(self, datei: str, header: list):
        """Holt Zeilen aus .pending-Datei nach und löscht sie."""
        pending = datei + ".pending"
        if not os.path.exists(pending):
            return
        try:
            with open(pending, "r", encoding="utf-8") as pf:
                zeilen = pf.read().strip()
            if not zeilen:
                os.remove(pending)
                return
            with open(datei, "a", newline="", encoding="utf-8") as f:
                f.write(zeilen + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.remove(pending)
        except Exception:
            pass  # Nächster Zyklus versucht es erneut

    def speichere_temperaturen(self, werte: dict):
        """
        Speichert Temperaturmessung in Kelvin + Rohdaten (Ohm).
        werte = Rückgabe von TemperaturMessung.messen()
        Spalten: Sensorname (K), Sensorname_ohm (Ω)
        """
        iso_lok, mjd, iso_utc = _zeitstempel()

        # Header: erst alle Kelvin-Spalten, dann alle Ohm-Spalten
        header = ["ISO_lokal", "MJD", "UTC"]
        for name in TEMP_SPALTEN:
            header.append(name)
            header.append(f"{name}_ohm")

        zeile = [iso_lok, f"{mjd:.6f}", iso_utc]
        for name in TEMP_SPALTEN:
            d = werte.get(name)
            if d and d["kelvin"] is not None:
                zeile.append(f"{d['kelvin']:.3f}")
            else:
                zeile.append("NaN")
            if d and d.get("ohm") is not None:
                zeile.append(f"{d['ohm']:.3f}")
            else:
                zeile.append("NaN")

        self._schreibe_zeile(self._dateiname("temperatur"), header, zeile)

    def speichere_druecke(self, werte: dict):
        """
        Speichert Druckmessung in mbar mit Statusspalten + kalibrierten Werten.
        werte = Rückgabe von DruckMessung.messen()
        Spalten: CENT, CENT_status, CENT_kal, DOOR, DOOR_status, DOOR_kal, ...
        CENT_kal etc. = NaN wenn keine Kalibrierung vorhanden.
        """
        iso_lok, mjd, iso_utc = _zeitstempel()

        # Header: CENT, CENT_status, CENT_kal, DOOR, ...
        header = ["ISO_lokal", "MJD", "UTC"]
        for name in DRUCK_SPALTEN:
            header += [name, f"{name}_status", f"{name}_kal"]

        zeile = [iso_lok, f"{mjd:.6f}", iso_utc]
        for name in DRUCK_SPALTEN:
            # CSV-Spalte heißt "CENT", hardware/druck.py liefert aber "CENTER"
            hw_name = "CENTER" if name == "CENT" else name
            d = werte.get(hw_name)
            kal_name = hw_name
            if d and d["gueltig"] and d["mbar"] is not None:
                roh = d["mbar"]
                if _km.hat_kalibrierung(kal_name):
                    kal = f"{_km.korrigiere(kal_name, roh):.2E}"
                else:
                    kal = "NaN"
                zeile += [f"{roh:.2E}", d["status"], kal]
            else:
                status = d["status"] if d else "unbekannt"
                zeile += ["NaN", status, "NaN"]

        self._schreibe_zeile(self._dateiname("druck"), header, zeile)