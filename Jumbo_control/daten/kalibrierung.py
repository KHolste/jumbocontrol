"""
daten/kalibrierung.py
Lädt Kalibrierdaten aus CSV und interpoliert Druckwerte (log-linear).

Verwendung:
    from daten.kalibrierung import KalibrierManager
    km = KalibrierManager()
    korrigiert = km.korrigiere("DOOR", 1.89E-6)  # → 1.18E-6
"""

import os
import csv
import math
import glob

KALIB_PFAD = "kalibrierung"


class Kalibrierung:
    """Kalibrierkurve für einen Sensor (log-lineare Interpolation)."""

    def __init__(self, sensor: str, datei: str):
        self.sensor    = sensor
        self.datei     = datei
        self.zertifikat = ""
        self.datum      = ""
        self._punkte    = []   # [(anzeige, kalibriert), ...] sortiert
        self._laden(datei)

    def _laden(self, datei: str):
        with open(datei, "r", encoding="utf-8") as f:
            for zeile in f:
                zeile = zeile.strip()
                if zeile.startswith("#"):
                    if "Zertifikat" in zeile:
                        self.zertifikat = zeile.split(":")[-1].strip()
                    if "Datum" in zeile:
                        self.datum = zeile.split(":")[-1].strip()
                    continue
                if not zeile or "mbar" in zeile.lower():
                    continue
                teile = zeile.split(",")
                if len(teile) >= 2:
                    try:
                        messwert    = float(teile[0].strip())  # MaxiGauge
                        wahrer_wert = float(teile[1].strip())  # Kalibriergerät KG
                        self._punkte.append((messwert, wahrer_wert))
                    except ValueError:
                        pass
        self._punkte.sort(key=lambda p: p[0])

    def korrigiere(self, messwert: float) -> float:
        """
        Interpoliert log-linear zwischen den Kalibrierpunkten.
        Außerhalb des Bereichs: lineare Extrapolation im log-Raum.
        """
        if not self._punkte or messwert <= 0:
            return messwert

        # Unter dem niedrigsten Kalibrierpunkt
        if messwert <= self._punkte[0][0]:
            x1, y1 = self._punkte[0]
            x2, y2 = self._punkte[1]
            return self._log_interp(messwert, x1, y1, x2, y2)

        # Über dem höchsten Kalibrierpunkt
        if messwert >= self._punkte[-1][0]:
            x1, y1 = self._punkte[-2]
            x2, y2 = self._punkte[-1]
            return self._log_interp(messwert, x1, y1, x2, y2)

        # Zwischen zwei Punkten
        for i in range(len(self._punkte) - 1):
            x1, y1 = self._punkte[i]
            x2, y2 = self._punkte[i + 1]
            if x1 <= messwert <= x2:
                return self._log_interp(messwert, x1, y1, x2, y2)

        return messwert

    def _log_interp(self, x, x1, y1, x2, y2) -> float:
        """Log-lineare Interpolation."""
        try:
            lx  = math.log10(x)
            lx1 = math.log10(x1)
            lx2 = math.log10(x2)
            ly1 = math.log10(y1)
            ly2 = math.log10(y2)
            # Lineare Interpolation im Log-Raum
            ly = ly1 + (ly2 - ly1) * (lx - lx1) / (lx2 - lx1)
            return 10 ** ly
        except (ValueError, ZeroDivisionError):
            return x

    def abweichung_prozent(self, messwert: float) -> float:
        """Relative Abweichung in %."""
        korr = self.korrigiere(messwert)
        if korr and korr > 0:
            return (messwert - korr) / korr * 100
        return 0.0

    @property
    def bereich(self) -> tuple:
        """Gültiger Kalibrierbereich (min, max) in mbar."""
        if self._punkte:
            return self._punkte[0][0], self._punkte[-1][0]
        return (0, 0)

    @property
    def punkte(self) -> list:
        return self._punkte


class KalibrierManager:
    """
    Verwaltet Kalibrierdaten für alle Sensoren.
    Lädt automatisch alle CSV-Dateien aus dem kalibrierung/-Ordner.
    """

    def __init__(self, pfad: str = KALIB_PFAD):
        self._pfad        = pfad
        self._kurven      = {}   # sensor → Kalibrierung
        self._laden()

    def _laden(self):
        if not os.path.isdir(self._pfad):
            return
        for datei in glob.glob(os.path.join(self._pfad, "*.csv")):
            # Sensorname aus Dateiname: DOOR_17779.csv → DOOR
            basis  = os.path.basename(datei)
            sensor = basis.split("_")[0].upper()
            try:
                self._kurven[sensor] = Kalibrierung(sensor, datei)
                print(f"[Kalibrierung] {sensor}: {datei} geladen "
                      f"({len(self._kurven[sensor].punkte)} Punkte)")
            except Exception as e:
                print(f"[Kalibrierung] Fehler {datei}: {e}")

    def hat_kalibrierung(self, sensor: str) -> bool:
        return sensor in self._kurven

    def korrigiere(self, sensor: str, messwert: float) -> float:
        """Gibt korrigierten Wert zurück, oder Messwert falls keine Kalibrierung."""
        if sensor in self._kurven and messwert is not None and messwert > 0:
            return self._kurven[sensor].korrigiere(messwert)
        return messwert

    def abweichung(self, sensor: str, messwert: float) -> float:
        """Abweichung in %."""
        if sensor in self._kurven and messwert is not None and messwert > 0:
            return self._kurven[sensor].abweichung_prozent(messwert)
        return 0.0

    def info(self, sensor: str) -> dict:
        if sensor in self._kurven:
            k = self._kurven[sensor]
            return {
                "zertifikat": k.zertifikat,
                "datum":      k.datum,
                "bereich":    k.bereich,
                "punkte":     len(k.punkte),
            }
        return {}

    @property
    def sensoren(self) -> list:
        return list(self._kurven.keys())
