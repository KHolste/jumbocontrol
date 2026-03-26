"""
daten/kryo_csv.py
Speichert Betriebsstunden der Coolpack-Kompressoren in tagesweiser CSV-Datei.
Format: ISO-Zeitstempel, MJD, UTC, dann pro Kryo: Stunden, Status, Wartung_in_h

Verwendung:
    from daten.kryo_csv import KryoCsvSchreiber
    k = KryoCsvSchreiber()
    k.speichere(status_liste)   # Liste von Coolpack.status()-Dicts
"""

import os
import csv
from datetime import datetime, timezone, timedelta

from config import LOG_PFAD

def _mjd(dt_utc: datetime) -> float:
    epoch = datetime(1858, 11, 17, tzinfo=timezone.utc)
    return (dt_utc - epoch).total_seconds() / 86400.0


class KryoCsvSchreiber:

    def __init__(self, pfad=LOG_PFAD):
        self._pfad = pfad
        os.makedirs(pfad, exist_ok=True)

    def _dateiname(self) -> str:
        datum = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self._pfad, f"{datum}_kryos.csv")

    def speichere(self, status_liste: list):
        """
        Schreibt eine Zeile mit Betriebsstunden aller Kryos.
        status_liste = Liste von Coolpack.status()-Dicts
        """
        jetzt_utc = datetime.now(timezone.utc)
        jetzt_lok = datetime.now()
        iso_lok   = jetzt_lok.strftime("%Y-%m-%dT%H:%M:%S")
        iso_utc   = jetzt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        mjd       = f"{_mjd(jetzt_utc):.6f}"

        # Header dynamisch aus Namen der Kryos aufbauen
        namen = [st["name"] for st in status_liste]
        header_felder = []
        for name in namen:
            header_felder += [
                f"{name}_h",
                f"{name}_status",
                f"{name}_wartung_in_h",
                f"{name}_fehler",
            ]

        datei = self._dateiname()
        neu   = not os.path.exists(datei)

        with open(datei, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter="\t")
            if neu:
                writer.writerow(["ISO_lokal", "MJD", "UTC"] + header_felder)

            zeile = [iso_lok, mjd, iso_utc]
            for st in status_liste:
                stunden    = st.get("betriebsstunden", "")
                status     = st.get("command_status",  "")
                wartung    = st.get("wartung_in_h",    "")
                fehler_str = "; ".join(st.get("fehler_liste", [])) or "OK"
                zeile += [stunden, status, wartung, fehler_str]

            writer.writerow(zeile)
