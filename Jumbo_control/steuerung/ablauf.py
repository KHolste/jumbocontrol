"""
steuerung/ablauf.py
Messzyklus der Anlage – verbindet Hardware und Datenspeicherung.
Robuster Start: Programm läuft auch wenn Hardware nicht erreichbar ist.
Reconnect: Hardware wird periodisch neu verbunden.
"""

import time
import threading
import traceback
import math
from daten import CsvSchreiber
from config import TEMP_ALARM_MAX, TEMP_ALARM_MIN

RECONNECT_INTERVALL = 30   # Sekunden zwischen Reconnect-Versuchen


class HardwareStatus:
    """Hält den Verbindungsstatus aller Hardware-Komponenten."""
    def __init__(self):
        self.cdaq      = False   # NI cDAQ (Temperatur)
        self.druck     = False   # TPG 366 (Druck)
        self.steckdose = False   # ALL4076 (Steckdose)

    def als_dict(self) -> dict:
        return {
            "cDAQ":      self.cdaq,
            "Druck":     self.druck,
            "Steckdose": self.steckdose,
        }


class Messzyklus:
    """
    Führt Temperatur- und Druckmessungen in regelmäßigen Abständen durch.
    Startet auch wenn Hardware nicht erreichbar – Reconnect automatisch.

    Callbacks:
        bei_messung_temp(werte)      – nach jeder Temperaturmessung
        bei_messung_druck(werte)     – nach jeder Druckmessung
        bei_alarm(name, wert)        – bei Grenzwertüberschreitung
        bei_hw_status(status_dict)   – bei Änderung des Hardware-Status
    """

    def __init__(self, intervall=5.0):
        self.intervall           = intervall
        self.bei_messung_temp    = None
        self.bei_messung_druck   = None
        self.bei_alarm           = None
        self.bei_hw_status       = None
        self.bei_sprung_alarm    = None   # fn(typ, name, wert, sprung)
        self._aktiv              = False
        self._alarm_einst        = None   # wird von GUI gesetzt
        self._letzter_temp       = {}     # name → letzter Wert
        self._letzter_druck      = {}     # name → (wert, zeit)
        self._thread             = None
        self._temperatur         = None
        self._druck              = None
        self._csv                = None
        self._hw_status          = HardwareStatus()
        self._letzter_reconnect  = 0.0

    def starten(self):
        if self._aktiv:
            return
        self._aktiv = True
        self._csv   = CsvSchreiber()

        # Hardware versuchen zu verbinden – Fehler sind ok
        self._verbinde_temperatur()
        self._verbinde_druck()

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Messzyklus] Gestartet.")

    def stoppen(self):
        self._aktiv = False
        if self._thread:
            self._thread.join(timeout=10)
        if self._temperatur:
            try:
                self._temperatur.beenden()
            except Exception:
                pass
        print("[Messzyklus] Gestoppt.")

    # ── Verbindungsaufbau ─────────────────────────────────────
    def _verbinde_temperatur(self):
        try:
            from hardware import TemperaturMessung
            self._temperatur = TemperaturMessung()
            alt = self._hw_status.cdaq
            self._hw_status.cdaq = True
            if not alt:
                print("[Messzyklus] cDAQ verbunden")
                self._melde_hw_status()
        except Exception as e:
            self._temperatur = None
            alt = self._hw_status.cdaq
            self._hw_status.cdaq = False
            if alt:
                print(f"[Messzyklus] cDAQ nicht erreichbar: {e}")
                self._melde_hw_status()

    def _verbinde_druck(self):
        try:
            from hardware import DruckMessung
            self._druck = DruckMessung()
            alt = self._hw_status.druck
            self._hw_status.druck = True
            if not alt:
                print("[Messzyklus] DruckMessung verbunden")
                self._melde_hw_status()
        except Exception as e:
            self._druck = None
            alt = self._hw_status.druck
            self._hw_status.druck = False
            if alt:
                print(f"[Messzyklus] DruckMessung nicht erreichbar: {e}")
                self._melde_hw_status()

    def _melde_hw_status(self):
        if self.bei_hw_status:
            self.bei_hw_status(self._hw_status.als_dict())

    # ── Messzyklus ────────────────────────────────────────────
    def _loop(self):
        while self._aktiv:
            try:
                t_start = time.perf_counter()

                # Periodischer Reconnect
                jetzt = time.time()
                if jetzt - self._letzter_reconnect > RECONNECT_INTERVALL:
                    self._letzter_reconnect = jetzt
                    if not self._hw_status.cdaq:
                        self._verbinde_temperatur()
                    if not self._hw_status.druck:
                        self._verbinde_druck()

                # Temperatur messen
                if self._temperatur:
                    try:
                        t_werte = self._temperatur.messen()
                        t_werte = self._pruefe_temp_spruenge(t_werte)
                        # CSV-Fehler (z.B. Datei geöffnet) sollen Hardware-Status
                        # nicht auf rot setzen – nur Messfehler tun das
                        try:
                            self._csv.speichere_temperaturen(t_werte)
                        except Exception as csv_e:
                            print(f"[Messzyklus] Temperatur-CSV Fehler: {csv_e}")
                        self._pruefe_alarme(t_werte)
                        if self.bei_messung_temp:
                            self.bei_messung_temp(t_werte)
                    except Exception as e:
                        print(f"[Messzyklus] Temperaturfehler: {e}")
                        self._temperatur = None
                        self._hw_status.cdaq = False
                        self._melde_hw_status()

                # Druck messen
                if self._druck:
                    try:
                        d_werte = self._druck.messen()
                        d_werte = self._pruefe_druck_spruenge(d_werte)
                        try:
                            self._csv.speichere_druecke(d_werte)
                        except Exception as csv_e:
                            print(f"[Messzyklus] Druck-CSV Fehler: {csv_e}")
                        if self.bei_messung_druck:
                            self.bei_messung_druck(d_werte)
                    except Exception as e:
                        print(f"[Messzyklus] Druckfehler: {e}")
                        self._druck = None
                        self._hw_status.druck = False
                        self._melde_hw_status()

                # Wartezeit
                dauer     = time.perf_counter() - t_start
                wartezeit = max(0, self.intervall - dauer)
                time.sleep(wartezeit)

            except Exception as e:
                print(f"[Messzyklus] Unerwarteter Fehler: {e}")
                traceback.print_exc()
                # In Fehlerlog schreiben
                try:
                    import os
                    from config import LOG_PFAD
                    os.makedirs(LOG_PFAD, exist_ok=True)
                    with open(os.path.join(LOG_PFAD, "fehler.log"), "a",
                              encoding="utf-8") as f:
                        from datetime import datetime
                        f.write(f"\n{'='*60}\n")
                        f.write(f"MESSZYKLUS FEHLER – {datetime.now():%Y-%m-%dT%H:%M:%S}\n")
                        f.write(f"{'='*60}\n")
                        traceback.print_exc(file=f)
                except Exception:
                    pass
                time.sleep(2)

    def _pruefe_temp_spruenge(self, werte: dict) -> dict:
        """Prüft Temperatursprünge, filtert Ausreißer heraus."""
        e = self._alarm_einst
        if not e:
            return werte
        te = e.temp
        result = {}
        for name, d in werte.items():
            if not d.get("gueltig") or d.get("celsius") is None:
                result[name] = d
                continue
            wert = d["celsius"]
            if name in self._letzter_temp:
                sprung = abs(wert - self._letzter_temp[name])
                if te["ausreisser_aktiv"] and sprung > te["ausreisser_grad"]:
                    print(f"[Messzyklus] Ausreißer gefiltert: {name} Sprung={sprung:.1f}°C")
                    if self.bei_sprung_alarm:
                        self.bei_sprung_alarm("temp_ausreisser", name, wert, sprung)
                    result[name] = {**d, "gueltig": False, "celsius": None,
                                    "kelvin": None, "fehler": f"Ausreißer ({sprung:.1f}°C)"}
                    continue
                elif te["sprung_alarm_aktiv"] and sprung > te["sprung_alarm_grad"]:
                    if self.bei_sprung_alarm:
                        self.bei_sprung_alarm("temp_alarm", name, wert, sprung)
            self._letzter_temp[name] = wert
            result[name] = d
        return result

    def _pruefe_druck_spruenge(self, werte: dict) -> dict:
        """Prüft Drucksprünge in Dekaden/s, filtert Ausreißer heraus."""
        e = self._alarm_einst
        if not e:
            return werte
        de = e.druck
        jetzt  = time.time()
        result = {}
        for name, d in werte.items():
            if not d.get("gueltig") or d.get("mbar") is None or d["mbar"] <= 0:
                result[name] = d
                continue
            wert = d["mbar"]
            if name in self._letzter_druck:
                alt_wert, alt_zeit = self._letzter_druck[name]
                dt = jetzt - alt_zeit
                if dt > 0 and alt_wert > 0:
                    try:
                        dekaden_s = abs(math.log10(wert) - math.log10(alt_wert)) / dt
                        if de["ausreisser_aktiv"] and dekaden_s > de["ausreisser_dekaden"]:
                            print(f"[Messzyklus] Druck-Ausreißer gefiltert: {name} {dekaden_s:.1f} Dek/s")
                            if self.bei_sprung_alarm:
                                self.bei_sprung_alarm("druck_ausreisser", name, wert, dekaden_s)
                            result[name] = {**d, "gueltig": False, "mbar": None,
                                            "status": f"Ausreißer ({dekaden_s:.1f} Dek/s)"}
                            continue
                        elif de["sprung_alarm_aktiv"] and dekaden_s > de["sprung_alarm_dekaden"]:
                            if self.bei_sprung_alarm:
                                self.bei_sprung_alarm("druck_alarm", name, wert, dekaden_s)
                    except (ValueError, ZeroDivisionError):
                        pass
            self._letzter_druck[name] = (wert, jetzt)
            result[name] = d
        return result

    def _pruefe_alarme(self, werte: dict):
        if not self.bei_alarm:
            return
        for name, d in werte.items():
            if not d.get("gueltig"):
                continue
            t = d.get("celsius")
            if t is not None and (t > TEMP_ALARM_MAX or t < TEMP_ALARM_MIN):
                self.bei_alarm(name, t)

    def __enter__(self):
        self.starten()
        return self

    def __exit__(self, *args):
        self.stoppen()
