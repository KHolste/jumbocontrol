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
from collections import deque
from daten import CsvSchreiber
from config import TEMP_ALARM_MAX, TEMP_ALARM_MIN, MESS_INTERVALL_MIN_S
from log_utils import tprint

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
        self.bei_entwarnung      = None   # fn(name, wert) – Alarm vorbei
        self.bei_hw_status       = None
        self.bei_sprung_alarm    = None   # fn(typ, name, wert, sprung)
        self._aktiv              = False
        self._alarm_einst        = None   # wird von GUI gesetzt
        self._letzter_temp       = {}     # name → letzter Wert
        self._letzter_druck      = {}     # name → (wert, zeit)
        self._aktive_temp_alarme = set()  # Sensornamen aktuell im Alarm
        self._letzte_csv_warnung = 0.0    # Cooldown für CSV-Fehlermeldungen
        self._thread             = None
        self._temperatur         = None
        self._druck              = None
        self._csv                = None
        self._hw_status          = HardwareStatus()
        self._letzter_reconnect  = 0.0

        # ── Adaptiver Modus ──────────────────────────────────
        self.adaptiv_aktiv              = False
        self.adaptiv_temp_schwelle_pct  = 1.0
        self.adaptiv_druck_schwelle_pct = 5.0
        self.adaptiv_vergleichs_n       = 1
        self.adaptiv_max_stille_s       = 30.0   # hart begrenzt auf 60
        self._adaptiv_temp_ref          = {}     # name → deque(float)
        self._adaptiv_druck_ref         = {}     # name → deque(float)
        self._adaptiv_letzte_temp_emit  = 0.0    # time.monotonic
        self._adaptiv_letzte_druck_emit = 0.0

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
        tprint("Messzyklus", "Gestartet.")

    def stoppen(self):
        self._aktiv = False
        if self._thread:
            self._thread.join(timeout=30)
            if self._thread.is_alive():
                tprint("Messzyklus", "Warnung: Thread-Shutdown Timeout nach 30s")
        # Hardware einzeln freigeben – jeder Schritt unabhängig
        for label, geraet in [("cDAQ", self._temperatur), ("Druck", self._druck)]:
            if geraet is not None:
                try:
                    geraet.beenden()
                    tprint("Messzyklus", f"{label} freigegeben")
                except Exception as e:
                    tprint("Messzyklus", f"{label} Freigabe-Fehler: {e}")
        self._temperatur = None
        self._druck = None
        tprint("Messzyklus", "Gestoppt.")

    # ── Verbindungsaufbau ─────────────────────────────────────
    def _verbinde_temperatur(self):
        try:
            from hardware import TemperaturMessung
            self._temperatur = TemperaturMessung()
            alt = self._hw_status.cdaq
            self._hw_status.cdaq = True
            if not alt:
                tprint("Messzyklus", "cDAQ verbunden")
                self._melde_hw_status()
        except Exception as e:
            self._temperatur = None
            alt = self._hw_status.cdaq
            self._hw_status.cdaq = False
            if alt:
                tprint("Messzyklus", f"cDAQ nicht erreichbar: {e}")
                self._melde_hw_status()

    def _verbinde_druck(self):
        try:
            from hardware import DruckMessung
            self._druck = DruckMessung()
            alt = self._hw_status.druck
            self._hw_status.druck = True
            if not alt:
                tprint("Messzyklus", "DruckMessung verbunden")
                self._melde_hw_status()
        except Exception as e:
            self._druck = None
            alt = self._hw_status.druck
            self._hw_status.druck = False
            if alt:
                tprint("Messzyklus", f"DruckMessung nicht erreichbar: {e}")
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
                        self._pruefe_alarme(t_werte)
                        if self._soll_emittieren("temp", t_werte):
                            try:
                                self._csv.speichere_temperaturen(t_werte)
                            except Exception as csv_e:
                                if time.time() - self._letzte_csv_warnung > 60:
                                    self._letzte_csv_warnung = time.time()
                                    tprint("Messzyklus", f"Temperatur-CSV Fehler: {csv_e}")
                            if self.bei_messung_temp:
                                self.bei_messung_temp(t_werte)
                    except Exception as e:
                        tprint("Messzyklus", f"Temperaturfehler: {e}")
                        self._temperatur = None
                        self._hw_status.cdaq = False
                        self._melde_hw_status()

                # Druck messen
                if self._druck:
                    try:
                        d_werte = self._druck.messen()
                        d_werte = self._pruefe_druck_spruenge(d_werte)
                        if self._soll_emittieren("druck", d_werte):
                            try:
                                self._csv.speichere_druecke(d_werte)
                            except Exception as csv_e:
                                if time.time() - self._letzte_csv_warnung > 60:
                                    self._letzte_csv_warnung = time.time()
                                    tprint("Messzyklus", f"Druck-CSV Fehler: {csv_e}")
                            if self.bei_messung_druck:
                                self.bei_messung_druck(d_werte)
                    except Exception as e:
                        tprint("Messzyklus", f"Druckfehler: {e}")
                        try:
                            self._druck.beenden()
                        except Exception:
                            pass
                        self._druck = None
                        self._hw_status.druck = False
                        self._melde_hw_status()

                # Wartezeit
                dauer     = time.perf_counter() - t_start
                wartezeit = max(0, self.intervall - dauer)
                time.sleep(wartezeit)

            except Exception as e:
                tprint("Messzyklus", f"Unerwarteter Fehler: {e}")
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

    # ── Adaptiver Modus ──────────────────────────────────────

    def _soll_emittieren(self, typ: str, werte: dict) -> bool:
        """Prüft ob Messwerte in CSV/Plot geschrieben werden sollen.

        Im nicht-adaptiven Modus: immer True.
        Im adaptiven Modus: True wenn %-Schwelle überschritten ODER
        die maximale Stillezeit abgelaufen ist.
        Aktualisiert Referenzwerte und Zeitstempel bei Emission.
        """
        if not self.adaptiv_aktiv:
            return True

        if typ == "temp":
            ref       = self._adaptiv_temp_ref
            letzte    = self._adaptiv_letzte_temp_emit
            schwelle  = self.adaptiv_temp_schwelle_pct
            wert_key  = "celsius"
        else:
            ref       = self._adaptiv_druck_ref
            letzte    = self._adaptiv_letzte_druck_emit
            schwelle  = self.adaptiv_druck_schwelle_pct
            wert_key  = "mbar"

        jetzt = time.monotonic()
        max_stille = min(self.adaptiv_max_stille_s, 60.0)

        # Stille-Timeout → erzwungener Punkt
        if (jetzt - letzte) >= max_stille:
            self._adaptiv_update_ref(typ, werte, jetzt, wert_key)
            return True

        # Änderungsprüfung: ein relevanter Sensor reicht
        n = max(1, self.adaptiv_vergleichs_n)
        for name, d in werte.items():
            if not d.get("gueltig") or d.get(wert_key) is None:
                continue
            wert = d[wert_key]
            if name not in ref or not ref[name]:
                self._adaptiv_update_ref(typ, werte, jetzt, wert_key)
                return True
            vals = list(ref[name])[-n:]
            mittel = sum(vals) / len(vals)
            # Division-by-zero-sicher: bei Referenz nahe Null absolute Schwelle
            if abs(mittel) < 1e-12:
                if abs(wert) > 1e-12:
                    self._adaptiv_update_ref(typ, werte, jetzt, wert_key)
                    return True
            elif abs(wert - mittel) / abs(mittel) * 100.0 > schwelle:
                self._adaptiv_update_ref(typ, werte, jetzt, wert_key)
                return True

        return False

    def _adaptiv_update_ref(self, typ: str, werte: dict,
                            jetzt: float, wert_key: str):
        """Aktualisiert Referenzwerte und Zeitstempel nach Emission."""
        if typ == "temp":
            self._adaptiv_letzte_temp_emit = jetzt
            ref = self._adaptiv_temp_ref
        else:
            self._adaptiv_letzte_druck_emit = jetzt
            ref = self._adaptiv_druck_ref
        for name, d in werte.items():
            if not d.get("gueltig") or d.get(wert_key) is None:
                continue
            if name not in ref:
                ref[name] = deque(maxlen=20)
            ref[name].append(d[wert_key])

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
        aktuelle = set()
        for name, d in werte.items():
            if not d.get("gueltig"):
                continue
            t = d.get("celsius")
            if t is not None and (t > TEMP_ALARM_MAX or t < TEMP_ALARM_MIN):
                aktuelle.add(name)

        # Neu eingetretene Alarme → melden
        neue = aktuelle - self._aktive_temp_alarme
        if self.bei_alarm:
            for name in neue:
                self.bei_alarm(name, werte[name]["celsius"])

        # Beendete Alarme → Entwarnung
        beendete = self._aktive_temp_alarme - aktuelle
        if self.bei_entwarnung:
            for name in beendete:
                t = werte.get(name, {}).get("celsius")
                self.bei_entwarnung(name, t if t is not None else 0.0)

        self._aktive_temp_alarme = aktuelle

    def __enter__(self):
        self.starten()
        return self

    def __exit__(self, *args):
        self.stoppen()
