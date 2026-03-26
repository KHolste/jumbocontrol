"""
daten/csv_leser.py
Liest Druck- und Temperaturdaten aus CSV-Dateien ein.

Unterstützte Formate:
    1. Neues Jumbo-Format (Tab, ISO-Datum, Punkt als Dezimal, °C)
    2. Altes LabVIEW-Druckformat (Tab, DD.MM.YYYY HH:MM:SS, Komma, mbar)
    3. Altes LabVIEW-Temperaturformat (Tab, DD.MM.YYYY HH:MM:SS, Komma, Kelvin,
       leere Zwischenspalten, doppelte Spaltennamen)
"""

import csv
import io
from datetime import datetime, timezone

KELVIN_OFFSET = 273.15


class CsvLeser:

    def lese_druck(self, dateipfad: str) -> dict:
        return self._lese_datei(dateipfad, typ="druck")

    def lese_temperatur(self, dateipfad: str) -> dict:
        return self._lese_datei(dateipfad, typ="temperatur")

    def _lese_datei(self, dateipfad: str, typ: str) -> dict:
        inhalt = self._lese_mit_encoding(dateipfad)
        zeilen = list(csv.reader(io.StringIO(inhalt), delimiter="\t"))
        if not zeilen:
            return {}

        header_roh = [s.strip() for s in zeilen[0]]

        # ── Format erkennen ───────────────────────────────────
        # LabVIEW Temp: "date time" als erste Spalte, leere Zwischenspalten
        labview_temp  = (header_roh[0].lower() == "date time")
        # LabVIEW Druck: "date" + "time" als erste zwei Spalten
        labview_druck = (len(header_roh) >= 2 and
                         "date" in header_roh[0].lower() and
                         "time" in header_roh[1].lower() and
                         not labview_temp)

        if labview_temp:
            return self._lese_labview_temp(zeilen)
        elif labview_druck:
            return self._lese_labview_druck(zeilen)
        else:
            return self._lese_neues_format(zeilen, typ)

    # ── LabVIEW Temperatur ────────────────────────────────────
    def _lese_labview_temp(self, zeilen: list) -> dict:
        """
        Format: "date time" | Sensor | leer | Sensor | leer | ...
        Werte in Kelvin, Komma als Dezimal, leere Zwischenspalten.
        Doppelte Spaltennamen werden mit _2, _3 usw. dedupliziert.
        """
        header_roh = [s.strip() for s in zeilen[0]]

        # Nur benannte, nicht-leere Spalten – jede zweite ab Index 1 ist Wert
        # Format: Datum | Wert1 | leer | Wert2 | leer | ...
        # → Wert-Spalten sind gerade Indizes ab 1: 1, 3, 5, ...
        sensor_pos  = []
        sensor_namen = []
        namen_zaehler = {}

        for i in range(1, len(header_roh)):
            name = header_roh[i].strip()
            if not name:
                continue
            if name in ("NC", "nc"):
                name = f"NC_{i}"
            # Deduplizieren
            if name in namen_zaehler:
                namen_zaehler[name] += 1
                name = f"{name}_{namen_zaehler[name]}"
            else:
                namen_zaehler[name] = 1
            sensor_pos.append(i)
            sensor_namen.append(name)

        daten = {"ISO_lokal": []}
        for name in sensor_namen:
            daten[name] = []

        for zeile in zeilen[1:]:
            if not zeile or not zeile[0].strip():
                continue
            ts = self._parse_zeit(zeile[0].strip())
            daten["ISO_lokal"].append(ts)

            for pos, name in zip(sensor_pos, sensor_namen):
                if pos >= len(zeile):
                    daten[name].append(None)
                    continue
                wert_str = zeile[pos].strip()
                wert = self._zu_float(wert_str)
                # Kelvin → Celsius (nur wenn sinnvoll > 50 K)
                if wert is not None and wert > 50:
                    wert = wert - KELVIN_OFFSET
                daten[name].append(wert)

        return daten

    # ── LabVIEW Druck ─────────────────────────────────────────
    def _lese_labview_druck(self, zeilen: list) -> dict:
        """
        Format: date | time | CENT | DOOR | MASS | BA | ...
        Komma als Dezimal.
        """
        header_roh = [s.strip() for s in zeilen[0]]
        # Erste zwei Spalten = date + time → zusammen als ISO_lokal
        spalten    = ["ISO_lokal"] + [h for h in header_roh[2:] if h]
        daten      = {s: [] for s in spalten}

        for zeile in zeilen[1:]:
            if len(zeile) < 2:
                continue
            datum_zeit = zeile[0].strip() + " " + zeile[1].strip()
            daten["ISO_lokal"].append(self._parse_zeit(datum_zeit))

            for i, col in enumerate(spalten[1:], start=2):
                if i >= len(zeile):
                    daten[col].append(None)
                else:
                    daten[col].append(self._zu_float(zeile[i].strip()))

        return daten

    # ── Neues Jumbo-Format ────────────────────────────────────
    def _lese_neues_format(self, zeilen: list, typ: str) -> dict:
        header = [s.strip() for s in zeilen[0]]
        daten  = {h: [] for h in header if h}

        for zeile in zeilen[1:]:
            for i, col in enumerate(header):
                if not col:
                    continue
                wert = zeile[i].strip() if i < len(zeile) else ""

                if col == "ISO_lokal":
                    daten[col].append(self._parse_zeit(wert))
                elif col == "MJD":
                    daten[col].append(self._zu_float(wert))
                elif col == "UTC":
                    try:
                        ts = datetime.strptime(wert, "%Y-%m-%dT%H:%M:%SZ")
                        daten[col].append(ts.replace(tzinfo=timezone.utc))
                    except ValueError:
                        daten[col].append(None)
                elif col.endswith(("_status", "_kal")):
                    daten[col].append(wert)
                else:
                    daten[col].append(self._zu_float(wert))

        return daten

    # ── Hilfsmethoden ─────────────────────────────────────────
    def _lese_mit_encoding(self, pfad: str) -> str:
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                with open(pfad, "r", encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Konnte Datei nicht lesen: {pfad}")

    def _parse_zeit(self, wert: str) -> datetime | None:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(wert, fmt)
            except ValueError:
                continue
        return None

    def _zu_float(self, wert: str) -> float | None:
        try:
            return float(wert.replace(",", "."))
        except ValueError:
            return None
