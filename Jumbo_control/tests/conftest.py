"""
conftest.py – pytest-Konfiguration für Jumbo-Control-Tests.

Fügt Jumbo_control/ zu sys.path hinzu, damit alle Module ohne
installiertes Package importierbar sind. Hardware-Abhängigkeiten
(nidaqmx, pyserial) werden in diesen Tests nicht benötigt.
"""
import sys
import os

# Jumbo_control/ auf sys.path setzen
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ACHTUNG: Diese Dateien sind keine Unit-Tests, sondern Hardware-Skripte, die
# beim bloßen Importieren echte Geräte ansprechen (z.B. test_steckdose.py
# schaltet die Steckdose "Rotary" AUS, test_temperatur.py übernimmt die
# cDAQ-Reservierung). pytest würde sie beim Sammeln ausführen → ausschließen.
# Manuell starten: python tests/<datei>.py (aus Jumbo_control/).
collect_ignore = [
    "test_druck.py",
    "test_steckdose.py",
    "test_steckdose_check_all.py",
    "test_steckdose_debug.py",
    "test_temperatur.py",
    "test_temperatur_timing.py",
]
