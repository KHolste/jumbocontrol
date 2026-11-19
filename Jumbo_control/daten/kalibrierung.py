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
import bisect

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


def cvd_kelvin(R: float):
    """Callendar-Van Dusen (quadratisch): PT100-Widerstand [Ohm] → Kelvin."""
    if R is None:
        return None
    A, B = 0.39083, 5.775e-5
    inhalt = A**2 + 4 * B * (100 - R)
    if inhalt < 0:
        return None
    return (-A + math.sqrt(inhalt)) / (-2 * B) + 273.15


class Pt100Kalibrierung:
    """
    Kalibriertabelle für einen PT100-Sensor (Widerstand → Temperatur).

    Dateiformat (Komma-getrennt, Punkt als Dezimaltrennzeichen):
        Temperature,Resistance
        K,Ohm
        19.85,2.0977
        ...

    Innerhalb der Tabelle: lineare Interpolation.
    Außerhalb: CVD-Formel, um die Abweichung am Tabellenrand verschoben
    (stetiger Übergang, kein Sprung an der Tabellengrenze).
    """

    def __init__(self, sensor: str, datei: str):
        self.sensor  = sensor
        self.datei   = datei
        self._punkte = []   # [(ohm, kelvin), ...] nach Widerstand sortiert
        self._laden(datei)
        if len(self._punkte) < 2:
            raise ValueError(f"{datei}: weniger als 2 Kalibrierpunkte")

    def _laden(self, datei: str):
        with open(datei, "r", encoding="utf-8") as f:
            for zeile in f:
                teile = zeile.strip().split(",")
                if len(teile) < 2:
                    continue
                try:
                    kelvin = float(teile[0])
                    ohm    = float(teile[1])
                except ValueError:
                    continue   # Kopfzeilen
                self._punkte.append((ohm, kelvin))
        self._punkte.sort()

    def ohm_zu_kelvin(self, R: float):
        if R is None or R <= 0:
            return None
        p = self._punkte
        if R < p[0][0] or R > p[-1][0]:
            r_rand, t_rand = p[0] if R < p[0][0] else p[-1]
            t_cvd, t_cvd_rand = cvd_kelvin(R), cvd_kelvin(r_rand)
            if t_cvd is None or t_cvd_rand is None:
                return None
            return t_cvd + (t_rand - t_cvd_rand)
        i = bisect.bisect_left(p, (R,))
        if i == 0:
            return p[0][1]
        (r1, t1), (r2, t2) = p[i - 1], p[i]
        if r2 == r1:
            return t1
        return t1 + (t2 - t1) * (R - r1) / (r2 - r1)

    @property
    def bereich_ohm(self) -> tuple:
        return self._punkte[0][0], self._punkte[-1][0]

    @property
    def punkte(self) -> list:
        return self._punkte


class KalibrierManager:
    """
    Verwaltet Kalibrierdaten für alle Sensoren.
    Druck: lädt automatisch alle CSV-Dateien aus dem kalibrierung/-Ordner
           (außer PT100-Dateien).
    PT100: lädt die in config.PT100_KALIBRIERUNG eingetragenen Dateien.
    """

    def __init__(self, pfad: str = KALIB_PFAD):
        self._pfad        = pfad
        self._kurven      = {}   # sensor → Kalibrierung (Druck)
        self._pt100       = {}   # Kanalname → Pt100Kalibrierung
        self._laden_pt100()
        self._laden()

    def _laden_pt100(self):
        try:
            from config import PT100_KALIBRIERUNG
        except ImportError:
            return
        from log_utils import tprint
        for name, dateiname in PT100_KALIBRIERUNG.items():
            datei = os.path.join(self._pfad, dateiname)
            try:
                self._pt100[name] = Pt100Kalibrierung(name, datei)
                tprint("Kalibrierung", f"PT100 {name}: {datei} geladen "
                       f"({len(self._pt100[name].punkte)} Punkte)")
            except Exception as e:
                tprint("Kalibrierung", f"PT100 {name}: Fehler {datei}: {e}")

    def hat_pt100_kalibrierung(self, name: str) -> bool:
        return name in self._pt100

    @property
    def pt100_sensoren(self) -> list:
        """Kanalnamen mit PT100-Kalibriertabelle (Reihenfolge wie in config)."""
        return list(self._pt100.keys())

    def pt100_info(self, name: str) -> dict:
        if name in self._pt100:
            k = self._pt100[name]
            t = [p[1] for p in k.punkte]
            return {
                "datei":     os.path.basename(k.datei),
                "punkte":    len(k.punkte),
                "bereich_k": (min(t), max(t)),
            }
        return {}

    def pt100_ohm_zu_kelvin(self, name: str, R: float):
        """Kelvin aus Widerstand per Kalibriertabelle, None wenn nicht möglich."""
        if name in self._pt100:
            return self._pt100[name].ohm_zu_kelvin(R)
        return None

    def _laden(self):
        if not os.path.isdir(self._pfad):
            return
        for datei in glob.glob(os.path.join(self._pfad, "*.csv")):
            # Sensorname aus Dateiname: DOOR_17779.csv → DOOR
            basis  = os.path.basename(datei)
            if basis.lower().startswith("pt100"):
                continue   # PT100-Tabellen, siehe _laden_pt100
            sensor = basis.split("_")[0].upper()
            try:
                self._kurven[sensor] = Kalibrierung(sensor, datei)
                from log_utils import tprint
                tprint("Kalibrierung", f"{sensor}: {datei} geladen "
                       f"({len(self._kurven[sensor].punkte)} Punkte)")
            except Exception as e:
                from log_utils import tprint
                tprint("Kalibrierung", f"Fehler {datei}: {e}")

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
