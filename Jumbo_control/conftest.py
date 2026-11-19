"""
conftest.py (Projektordner) – schützt vor versehentlichem Ausführen von
Hardware-Skripten durch pytest.

Die test_*.py-Dateien hier im Projektordner (und einige in tests/) sind
KEINE Unit-Tests, sondern Hardware-Skripte, die beim bloßen Importieren echte
Geräte ansprechen bzw. schalten (z.B. test_kryo2.py schaltet Kryo 1/2,
tests/test_steckdose.py schaltet die Steckdose "Rotary" AUS). pytest führt
Modulcode beim Sammeln aus – deshalb werden sie hier ausgeschlossen.

Manuell starten: python <datei>.py (aus Jumbo_control/).
Echte Unit-Tests liegen in tests/ und laufen mit:  python -m pytest
"""

collect_ignore = [
    # Hardware-Skripte im Projektordner
    "test_coolpack.py",
    "test_coolpack_discovery.py",
    "test_druck.py",
    "test_druck_raw.py",
    "test_drucken.py",
    "test_kryo2.py",
    "test_tcp_server.py",
    # Hardware-Skripte in tests/ (zusätzlich in tests/conftest.py)
    "tests/test_druck.py",
    "tests/test_steckdose.py",
    "tests/test_steckdose_check_all.py",
    "tests/test_steckdose_debug.py",
    "tests/test_temperatur.py",
    "tests/test_temperatur_timing.py",
]
# Sicherungskopien nie sammeln
collect_ignore_glob = ["gui/sicherung/*", "hardware/backup/*"]
