"""
Kanalzuordnung cDAQ9188-Jumbo → Sensornamen
Gibt alle Messwerte mit Klarnamen in der Konsole aus.
"""

import math
import time
import nidaqmx
from nidaqmx.system import System
from nidaqmx.constants import ResistanceConfiguration, ExcitationSource, ResistanceUnits, AcquisitionType, ADCTimingMode

# ── Konfiguration ──────────────────────────────────────────────
GERAET_NAME = "cDAQ9188-Jumbo"
STROM_MA    = 0.001
R_MIN       = 0.0
R_MAX       = 200.0
NUM_SAMPLES  = 2
SAMPLERATE   = 1000.0   # Hz, wie LabVIEW Frontpanel

TEMP_MIN    = -273.15   # Absoluter Nullpunkt
TEMP_MAX    =  100.0

# ── Kanalzuordnung ─────────────────────────────────────────────
# Mod1 = P1-P8 außen, Mod2 = P1-P8 innen
# Mod3 ai0/ai1 = Peltier X/Y, Rest noch unbekannt
# Mod4, Mod5 noch unbekannt
# Mod7 = NI 9375 (Digital), Mod8 = NI 9476 (Digital) nicht hier

# Kanalzuordnung direkt aus Jumbo.ini (LabVIEW-Konfiguration)
# Kanal 1-32 = Mod1 ai0-ai7, Mod2 ai0-ai7, Mod3 ai0-ai7, Mod4 ai0-ai7
# Mod5 ai0-ai7 = Kanaele 33-40, in INI nicht benannt
KANALZUORDNUNG = [
    # (Modul,                Kanal,  Sensorname aus Jumbo.ini)
    ("cDAQ9188-JumboMod1",  "ai0",  "Kryo 1 In"),
    ("cDAQ9188-JumboMod1",  "ai1",  "Kryo 1"),
    ("cDAQ9188-JumboMod1",  "ai2",  "Kryo 1b"),
    ("cDAQ9188-JumboMod1",  "ai3",  "Peltier"),
    ("cDAQ9188-JumboMod1",  "ai4",  "Peltier b"),
    ("cDAQ9188-JumboMod1",  "ai5",  "Kryo 2 In"),
    ("cDAQ9188-JumboMod1",  "ai6",  "Kryo 2"),
    ("cDAQ9188-JumboMod1",  "ai7",  "Kryo 2b"),

    ("cDAQ9188-JumboMod2",  "ai0",  "Kryo 3 In"),
    ("cDAQ9188-JumboMod2",  "ai1",  "Kryo 3"),
    ("cDAQ9188-JumboMod2",  "ai2",  "Kryo 3b"),
    ("cDAQ9188-JumboMod2",  "ai5",  "Kryo 4 In"),
    ("cDAQ9188-JumboMod2",  "ai6",  "Kryo 4"),
    ("cDAQ9188-JumboMod2",  "ai7",  "Kryo 4b"),

    ("cDAQ9188-JumboMod3",  "ai0",  "Kryo 5 In"),
    ("cDAQ9188-JumboMod3",  "ai1",  "Kryo 5"),
    ("cDAQ9188-JumboMod3",  "ai2",  "Kryo 5b"),
    ("cDAQ9188-JumboMod3",  "ai5",  "Kryo 6 In"),
    ("cDAQ9188-JumboMod3",  "ai6",  "Kryo 6"),
    ("cDAQ9188-JumboMod3",  "ai7",  "Kryo 6b"),

    ("cDAQ9188-JumboMod4",  "ai0",  "Kryo 7 In"),
    ("cDAQ9188-JumboMod4",  "ai1",  "Kryo 7"),
    ("cDAQ9188-JumboMod4",  "ai3",  "Kryo 9"),
    ("cDAQ9188-JumboMod4",  "ai4",  "Kryo 9b"),
    ("cDAQ9188-JumboMod4",  "ai5",  "Kryo 8 In"),
    ("cDAQ9188-JumboMod4",  "ai6",  "Kryo 8"),

]


# ── Callendar-Van Dusen ────────────────────────────────────────
def cvd(R):
    """PT100 Widerstand -> Temperatur in Grad C"""
    A, B = 0.39083, 5.775e-5
    inhalt = A**2 + 4 * B * (100 - R)
    if inhalt < 0:
        return None
    t = (-A + math.sqrt(inhalt)) / (-2 * B)
    return t if TEMP_MIN <= t <= TEMP_MAX else None


# ── Gerät reservieren ─────────────────────────────────────────
def reserviere():
    system = System.local()
    chassis = system.devices[GERAET_NAME]
    try:
        chassis.reserve_network_device(override_reservation=False)
    except nidaqmx.errors.DaqError as e:
        if "already reserved" not in str(e).lower():
            print(f"  [WARNUNG] Reservierung: {e}")


# ── Task einmalig aufbauen (spart Setup-Overhead bei Dauermessung) ──
_task  = None
_kanaele = None

def task_starten():
    global _task, _kanaele
    if _task is not None:
        _task.close()
    _kanaele = [f"{modul}/{kanal}" for modul, kanal, _ in KANALZUORDNUNG]
    _task = nidaqmx.Task()
    for k in _kanaele:
        _task.ai_channels.add_ai_resistance_chan(
            physical_channel=k,
            min_val=R_MIN,
            max_val=R_MAX,
            units=ResistanceUnits.OHMS,
            resistance_config=ResistanceConfiguration.FOUR_WIRE,
            current_excit_source=ExcitationSource.INTERNAL,
            current_excit_val=STROM_MA,
        )
    _task.timing.cfg_samp_clk_timing(
        rate=SAMPLERATE,
        sample_mode=AcquisitionType.FINITE,
        samps_per_chan=NUM_SAMPLES,
    )
    _task.ai_channels.all.ai_adc_timing_mode = ADCTimingMode.HIGH_SPEED

def task_beenden():
    global _task
    if _task is not None:
        _task.close()
        _task = None

# ── Messung ────────────────────────────────────────────────────
def messe():
    global _task
    # Task wiederverwenden statt neu aufbauen
    _task.timing.cfg_samp_clk_timing(
        rate=SAMPLERATE,
        sample_mode=AcquisitionType.FINITE,
        samps_per_chan=NUM_SAMPLES,
    )
    rohdaten = _task.read(number_of_samples_per_channel=NUM_SAMPLES)

    ergebnisse = []
    for i, (modul, kanal, name) in enumerate(KANALZUORDNUNG):
        samples = rohdaten[i]
        R = sum(samples) / len(samples)
        temp = cvd(R)
        ergebnisse.append((modul, kanal, name, R, temp))

    return ergebnisse


# ── Ausgabe ────────────────────────────────────────────────────
def drucke_ergebnisse(ergebnisse):
    zeitstempel = time.strftime("%H:%M:%S")
    print(f"\n{'='*68}")
    print(f"  Kanalzuordnung cDAQ9188-Jumbo  |  {zeitstempel}")
    print(f"{'='*68}")
    print(f"  {'Sensor':<22} {'Kanal':<26} {'R [Ohm]':>8}  {'T [Grad C]':>12}")
    print(f"  {'-'*64}")

    aktuelles_modul = None
    for modul, kanal, name, R, temp in ergebnisse:
        if modul != aktuelles_modul:
            print(f"\n  >> {modul}")
            aktuelles_modul = modul

        kanal_voll = f"{modul}/{kanal}"

        if temp is not None:
            kelvin   = temp + 273.15
            temp_str = f"{temp:>10.2f} C  ({kelvin:.2f} K)  OK"
        else:
            temp_str = "kein Sensor / ausserhalb"

        print(f"    {name:<22} {kanal_voll:<26} {R:>7.3f}   {temp_str}")

    gueltig   = sum(1 for *_, t in ergebnisse if t is not None)
    unbekannt = sum(1 for _, _, n, _, _ in ergebnisse if "unbekannt" in n)
    print(f"\n  Gueltige Sensoren: {gueltig}  |  Unbekannte Kanaele: {unbekannt}")
    print(f"{'='*68}")


# ── Hauptprogramm ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Reserviere Geraet...")
    reserviere()
    print("Task wird aufgebaut...")
    task_starten()

    # Erste Messung (noch mit minimalem Overhead)
    print("Erste Messung (Warmup)...")
    t0 = time.perf_counter()
    messe()
    print(f"  Warmup: {time.perf_counter()-t0:.3f} s")

    # Zweite Messung (Task bereits offen = echte Messzeit)
    print("Zweite Messung (Task offen)...")
    t_start = time.perf_counter()
    ergebnisse = messe()
    t_end = time.perf_counter()
    dauer = t_end - t_start

    drucke_ergebnisse(ergebnisse)
    print(f"  Warmup-Messung:     erste Messung inkl. Task-Init")
    print(f"  Folgemessung:       {dauer:.3f} s  (Task bleibt offen)")
    print(f"  LabVIEW Referenz:   ~3.0 s")
    task_beenden()