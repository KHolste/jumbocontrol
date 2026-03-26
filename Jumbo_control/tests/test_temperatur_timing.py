"""Detailliertes Timing um Flaschenhals zu finden."""
import time
import nidaqmx
from nidaqmx.system import System
from nidaqmx.constants import ResistanceConfiguration, ExcitationSource, ResistanceUnits, AcquisitionType, ADCTimingMode
from config import CDAQ_GERAET as GERAET_NAME, TEMP_STROM_MA as STROM_MA, TEMP_SAMPLERATE as SAMPLERATE, TEMP_SAMPLES as NUM_SAMPLES

KANALZUORDNUNG = [
    ("cDAQ9188-JumboMod1", "ai0"), ("cDAQ9188-JumboMod1", "ai1"),
    ("cDAQ9188-JumboMod2", "ai0"), ("cDAQ9188-JumboMod2", "ai1"),
    ("cDAQ9188-JumboMod3", "ai0"), ("cDAQ9188-JumboMod4", "ai0"),
]

def t(label, t0):
    dt = time.perf_counter() - t0
    print(f"  {label:<35} {dt:.3f} s")
    return time.perf_counter()

t0 = time.perf_counter()

# 1. Reservierung
system = System.local()
chassis = system.devices[GERAET_NAME]
try:
    chassis.reserve_network_device(override_reservation=False)
except:
    chassis.reserve_network_device(override_reservation=True)
t0 = t("Reservierung", t0)

# 2. Task anlegen
task = nidaqmx.Task()
t0 = t("Task() erstellen", t0)

# 3. Kanäle hinzufügen (nur 6 als Test)
for modul, kanal in KANALZUORDNUNG:
    task.ai_channels.add_ai_resistance_chan(
        physical_channel=f"{modul}/{kanal}",
        min_val=0, max_val=200,
        units=ResistanceUnits.OHMS,
        resistance_config=ResistanceConfiguration.FOUR_WIRE,
        current_excit_source=ExcitationSource.INTERNAL,
        current_excit_val=STROM_MA,
    )
t0 = t("6 Kanäle hinzufügen", t0)

# 4. Timing setzen
task.timing.cfg_samp_clk_timing(
    rate=SAMPLERATE,
    sample_mode=AcquisitionType.FINITE,
    samps_per_chan=NUM_SAMPLES,
)
t0 = t("Timing setzen", t0)

# 5. ADC Modus
task.ai_channels.all.ai_adc_timing_mode = ADCTimingMode.HIGH_SPEED
t0 = t("ADC High Speed setzen", t0)

# 6. Lesen
daten = task.read(number_of_samples_per_channel=NUM_SAMPLES)
t0 = t("task.read()", t0)

task.close()
t0 = t("task.close()", t0)
