"""
cdaq_temperatur.py
Modul zum Auslesen der PT100-Temperatursensoren am NI cDAQ9188-Jumbo.

Verwendung:
    from cdaq_temperatur import TemperaturMessung

    t = TemperaturMessung()
    werte = t.messen()
    t.beenden()
"""

import math
import time
import nidaqmx
from nidaqmx.system import System
from nidaqmx.constants import (
    ResistanceConfiguration, ExcitationSource,
    ResistanceUnits, AcquisitionType, ADCTimingMode
)
from daten.kalibrierung import KalibrierManager as _KM
from daten.csv_schreiber import _km  # globaler KalibrierManager (mit PT100)

from config import (
    CDAQ_GERAET  as GERAET_NAME,
    TEMP_STROM_MA as STROM_MA,
    TEMP_SAMPLERATE as SAMPLERATE,
    TEMP_SAMPLES  as NUM_SAMPLES,
    TEMP_MIN, TEMP_MAX,
)

R_MIN = 0.0
R_MAX = 200.0

# ── Kanalzuordnung (aus Jumbo.ini) ─────────────────────────────
KANALZUORDNUNG = [
    ("cDAQ9188-JumboMod1", "ai0", "Kryo 1 In"),
    ("cDAQ9188-JumboMod1", "ai1", "Kryo 1"),
    ("cDAQ9188-JumboMod1", "ai2", "Kryo 1b"),
    ("cDAQ9188-JumboMod1", "ai3", "Peltier"),
    ("cDAQ9188-JumboMod1", "ai4", "Peltier b"),
    ("cDAQ9188-JumboMod1", "ai5", "Kryo 2 In"),
    ("cDAQ9188-JumboMod1", "ai6", "Kryo 2"),
    ("cDAQ9188-JumboMod1", "ai7", "Kryo 2b"),

    ("cDAQ9188-JumboMod2", "ai0", "Kryo 3 In"),
    ("cDAQ9188-JumboMod2", "ai1", "Kryo 3"),
    ("cDAQ9188-JumboMod2", "ai2", "Kryo 3b"),
    ("cDAQ9188-JumboMod2", "ai5", "Kryo 4 In"),
    ("cDAQ9188-JumboMod2", "ai6", "Kryo 4"),
    ("cDAQ9188-JumboMod2", "ai7", "Kryo 4b"),

    ("cDAQ9188-JumboMod3", "ai0", "Kryo 5 In"),
    ("cDAQ9188-JumboMod3", "ai1", "Kryo 5"),
    ("cDAQ9188-JumboMod3", "ai2", "Kryo 5b"),
    ("cDAQ9188-JumboMod3", "ai5", "Kryo 6 In"),
    ("cDAQ9188-JumboMod3", "ai6", "Kryo 6"),
    ("cDAQ9188-JumboMod3", "ai7", "Kryo 6b"),

    ("cDAQ9188-JumboMod4", "ai0", "Kryo 7 In"),
    ("cDAQ9188-JumboMod4", "ai1", "Kryo 7"),
    ("cDAQ9188-JumboMod4", "ai3", "Kryo 9"),
    ("cDAQ9188-JumboMod4", "ai4", "Kryo 9b"),
    ("cDAQ9188-JumboMod4", "ai5", "Kryo 8 In"),
    ("cDAQ9188-JumboMod4", "ai6", "Kryo 8"),
]


def _cvd(R):
    """Callendar-Van Dusen: PT100 Widerstand -> Temperatur in Grad C"""
    A, B = 0.39083, 5.775e-5
    inhalt = A**2 + 4 * B * (100 - R)
    if inhalt < 0:
        return None
    t = (-A + math.sqrt(inhalt)) / (-2 * B)
    return t if TEMP_MIN <= t <= TEMP_MAX else None


class TemperaturMessung:
    """
    Verwaltet die Verbindung zum cDAQ und liest PT100-Temperaturen aus.

    Beispiel:
        t = TemperaturMessung()
        werte = t.messen()
        # werte["Kryo 3 In"] = {
        #     "celsius":  9.55,
        #     "kelvin":   282.70,
        #     "ohm":      103.73,
        #     "kanal":    "cDAQ9188-JumboMod2/ai0",
        #     "gueltig":  True
        # }
        t.beenden()

    Oder als Context Manager:
        with TemperaturMessung() as t:
            werte = t.messen()
    """

    def __init__(self):
        self._task = None
        self._reserviere()
        try:
            self._task_starten()
        except Exception:
            self.beenden()
            raise

    def _reserviere(self):
        system = System.local()
        chassis = system.devices[GERAET_NAME]
        try:
            # Immer mit Override – erzwingt frische Reservierung (schnelleres task.read())
            chassis.reserve_network_device(override_reservation=True)
        except nidaqmx.errors.DaqError as e:
            from log_utils import tprint
            tprint("TemperaturMessung", f"Reservierung fehlgeschlagen: {e}")

    def _task_starten(self):
        self._task = nidaqmx.Task()
        for modul, kanal, _ in KANALZUORDNUNG:
            self._task.ai_channels.add_ai_resistance_chan(
                physical_channel=f"{modul}/{kanal}",
                min_val=R_MIN,
                max_val=R_MAX,
                units=ResistanceUnits.OHMS,
                resistance_config=ResistanceConfiguration.FOUR_WIRE,
                current_excit_source=ExcitationSource.INTERNAL,
                current_excit_val=STROM_MA,
            )
        self._task.timing.cfg_samp_clk_timing(
            rate=SAMPLERATE,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=NUM_SAMPLES,
        )
        self._task.ai_channels.all.ai_adc_timing_mode = ADCTimingMode.HIGH_SPEED

    def messen(self):
        """
        Führt eine Messung durch.

        Rückgabe: dict mit Sensorname als Schlüssel, z.B.:
        {
            "Kryo 3 In": {
                "celsius":  9.55,
                "kelvin":   282.70,
                "ohm":      103.73,
                "kanal":    "cDAQ9188-JumboMod2/ai0",
                "gueltig":  True
            },
            "Kryo 1 In": {
                "celsius":  None,
                "kelvin":   None,
                "ohm":      499.97,
                "kanal":    "cDAQ9188-JumboMod1/ai0",
                "gueltig":  False   # kein Sensor angeschlossen
            },
            ...
        }
        """
        self._task.timing.cfg_samp_clk_timing(
            rate=SAMPLERATE,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=NUM_SAMPLES,
        )
        rohdaten = self._task.read(number_of_samples_per_channel=NUM_SAMPLES)

        ergebnis = {}
        for i, (modul, kanal, name) in enumerate(KANALZUORDNUNG):
            R = sum(rohdaten[i]) / NUM_SAMPLES

            # Kalibrierung: Tabelle hat Vorrang vor CVD-Formel
            if hasattr(_km, "hat_pt100_kalibrierung") and _km.hat_pt100_kalibrierung(name):
                kelvin = _km.pt100_ohm_zu_kelvin(name, R)
                if kelvin is not None:
                    celsius = kelvin - 273.15
                    gueltig = TEMP_MIN <= celsius <= TEMP_MAX
                    ergebnis[name] = {
                        "celsius": round(celsius, 3) if gueltig else None,
                        "kelvin":  round(kelvin,  3) if gueltig else None,
                        "ohm":     round(R, 3),
                        "kanal":   f"{modul}/{kanal}",
                        "gueltig": gueltig,
                        "kalib":   "tabelle",
                    }
                    continue
            # Fallback: CVD-Formel
            temp = _cvd(R)
            ergebnis[name] = {
                "celsius": round(temp, 3) if temp is not None else None,
                "kelvin":  round(temp + 273.15, 3) if temp is not None else None,
                "ohm":     round(R, 3),
                "kanal":   f"{modul}/{kanal}",
                "gueltig": temp is not None,
                "kalib":   "cvd",
            }

        return ergebnis

    def beenden(self):
        """Task schließen und Ressourcen freigeben."""
        if self._task is not None:
            self._task.close()
            self._task = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.beenden()


# ── Direktaufruf zum Testen ────────────────────────────────────
if __name__ == "__main__":
    with TemperaturMessung() as t:
        t_start = time.perf_counter()
        werte = t.messen()
        dauer = time.perf_counter() - t_start

        print(f"\n{'='*55}")
        print(f"  Temperaturmessung  |  {time.strftime('%H:%M:%S')}")
        print(f"{'='*55}")
        for name, d in werte.items():
            if d["gueltig"]:
                print(f"  {name:<12}  {d['celsius']:>8.2f} C  "
                      f"({d['kelvin']:.2f} K)  {d['ohm']:.3f} Ohm")
            else:
                print(f"  {name:<12}  kein Sensor  ({d['ohm']:.3f} Ohm)")
        print(f"\n  Messdauer: {dauer:.3f} s")
        print(f"{'='*55}")
