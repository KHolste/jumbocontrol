import nidaqmx
from nidaqmx.system import System
from nidaqmx.constants import (
    ResistanceConfiguration, ExcitationSource, ResistanceUnits,
    AcquisitionType, ADCTimingMode
)
import math
import time

GERAET_NAME = "cDAQ9188-Jumbo"

# --- Konfiguration (identisch mit LabVIEW-Programm) ---
VERDRAHTUNG  = ResistanceConfiguration.FOUR_WIRE
STROM_MA     = 0.001     # 1 mA Speisestrom
R_MIN        = 0.0       # Ohm
R_MAX        = 200.0     # Ohm
NUM_SAMPLES  = 2         # Mittelwert aus 2 Samples
SAMPLERATE   = 1000.0    # 1 kHz (wie im Frontpanel)
TIMING_MODE  = ADCTimingMode.HIGH_SPEED  # High Speed (wie im Frontpanel)

# Plausibler Temperaturbereich
TEMP_MIN = -300.0
TEMP_MAX =  100.0

# Module
MODULE = [
    "cDAQ9188-JumboMod1",
    "cDAQ9188-JumboMod2",
    "cDAQ9188-JumboMod3",
    "cDAQ9188-JumboMod4",
    "cDAQ9188-JumboMod5",
]
KANAELE_PRO_MODUL = 8

# Optional: Kanäle manuell festlegen (None = alle + automatischer Filter)
AKTIVE_KANAELE = None


def callendar_van_dusen(R):
    """
    Callendar-Van Dusen Umrechnung für PT100 (T < 0°C)
    Identisch mit LabVIEW-Formel:
    temp = (-0.39083 + sqrt(0.39083^2 + 4*5.775e-5*(100-R))) / (-2*5.775e-5)
    """
    A = 0.39083
    B = 5.775e-5
    wurzel_inhalt = A**2 + 4 * B * (100 - R)
    if wurzel_inhalt < 0:
        return None
    return (-A + math.sqrt(wurzel_inhalt)) / (-2 * B)


def reserviere_geraet():
    system = System.local()
    chassis = system.devices[GERAET_NAME]
    try:
        chassis.reserve_network_device(override_reservation=False)
    except nidaqmx.errors.DaqError as e:
        if "already reserved" not in str(e).lower():
            print(f"  [WARNUNG] Reservierung: {e}")


def alle_kanaele():
    return [f"{m}/ai{k}" for m in MODULE for k in range(KANAELE_PRO_MODUL)]


def lese_widerstaende():
    """Liest Widerstände (Ohm) aller Kanäle, gibt dict {kanal: widerstand} zurück."""
    kanaele = AKTIVE_KANAELE if AKTIVE_KANAELE else alle_kanaele()
    ergebnis = {}

    with nidaqmx.Task() as task:
        for kanal in kanaele:
            task.ai_channels.add_ai_resistance_chan(
                physical_channel=kanal,
                min_val=R_MIN,
                max_val=R_MAX,
                units=ResistanceUnits.OHMS,
                resistance_config=VERDRAHTUNG,
                current_excit_source=ExcitationSource.INTERNAL,
                current_excit_val=STROM_MA,
            )

        # High Speed Modus setzen (wie LabVIEW)
        task.timing.cfg_samp_clk_timing(
            rate=SAMPLERATE,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=NUM_SAMPLES,
        )
        task.ai_channels.all.ai_adc_timing_mode = TIMING_MODE

        rohdaten = task.read(number_of_samples_per_channel=NUM_SAMPLES)

        if len(kanaele) == 1:
            rohdaten = [rohdaten]

        for i, kanal in enumerate(kanaele):
            samples = rohdaten[i] if NUM_SAMPLES > 1 else [rohdaten[i]]
            ergebnis[kanal] = sum(samples) / len(samples)

    return ergebnis


def ist_plausibel(temp):
    return temp is not None and TEMP_MIN <= temp <= TEMP_MAX


def lese_temperaturen():
    reserviere_geraet()

    print("=" * 60)
    print("  NI 9216 – PT100 Temperaturmessung")
    print("  Methode: Widerstand → Callendar-Van Dusen (T < 0°C)")
    print(f"  Modus: High Speed | {int(SAMPLERATE)} Hz | {NUM_SAMPLES} Samples")
    print(f"  Plausibel: {TEMP_MIN}°C bis {TEMP_MAX}°C")
    print("=" * 60)

    widerstaende = lese_widerstaende()

    aktuelles_modul = None
    gueltige = 0
    ungueltige = 0

    for kanal, R in widerstaende.items():
        modul = kanal.rsplit("/", 1)[0]
        kanal_nr = kanal.rsplit("/", 1)[1]

        if modul != aktuelles_modul:
            print(f"\n  {modul}:")
            aktuelles_modul = modul

        temp = callendar_van_dusen(R)

        if ist_plausibel(temp):
            print(f"    {kanal_nr}:  {R:7.3f} Ω  →  {temp:7.2f} °C  ✓")
            gueltige += 1
        else:
            print(f"    {kanal_nr}:  {R:7.3f} Ω  →  kein Sensor")
            ungueltige += 1

    print(f"\n  Gültige Kanäle: {gueltige}  |  Nicht belegt: {ungueltige}")
    print("=" * 60)


def dauermessung(intervall_sek=2.0):
    """Kontinuierliche Messung – Abbruch mit Strg+C"""
    reserviere_geraet()

    print("=" * 60)
    print(f"  Dauermessung alle {intervall_sek}s  |  Abbruch: Strg+C")
    print("=" * 60)

    try:
        while True:
            widerstaende = lese_widerstaende()
            zeitstempel = time.strftime("%H:%M:%S")
            print(f"\n[{zeitstempel}]")
            aktuelles_modul = None
            for kanal, R in widerstaende.items():
                temp = callendar_van_dusen(R)
                if not ist_plausibel(temp):
                    continue
                modul = kanal.rsplit("/", 1)[0]
                kanal_nr = kanal.rsplit("/", 1)[1]
                if modul != aktuelles_modul:
                    print(f"  {modul}:")
                    aktuelles_modul = modul
                print(f"    {kanal_nr}:  {R:7.3f} Ω  →  {temp:7.2f} °C")
            time.sleep(intervall_sek)
    except KeyboardInterrupt:
        print("\n\n  Messung beendet.")


if __name__ == "__main__":
    # Einmalige Messung:
    lese_temperaturen()

    # Für Dauermessung stattdessen einkommentieren:
    # dauermessung(intervall_sek=2.0)