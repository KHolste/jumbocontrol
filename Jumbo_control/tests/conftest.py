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
