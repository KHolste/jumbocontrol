"""
fehler_log.py
Globaler Exception-Handler – fängt unbehandelte Ausnahmen ab und
schreibt sie in eine Logdatei, bevor das Programm abstürzt.

Einbinden in main.py:
    import fehler_log
    fehler_log.installieren()
"""

import sys
import os
import traceback
from datetime import datetime
from config import LOG_PFAD

FEHLER_LOG_DATEI = os.path.join(LOG_PFAD, "fehler.log")


def _schreibe_fehler(typ, wert, tb):
    """Schreibt unbehandelte Exception in Logdatei."""
    os.makedirs(LOG_PFAD, exist_ok=True)
    zeitstempel = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(FEHLER_LOG_DATEI, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"UNBEHANDELTE EXCEPTION – {zeitstempel}\n")
        f.write(f"{'='*60}\n")
        traceback.print_exception(typ, wert, tb, file=f)
    # Auch auf Konsole ausgeben
    print(f"\n[FEHLER] Unbehandelte Exception – Details in {FEHLER_LOG_DATEI}")
    traceback.print_exception(typ, wert, tb)


def installieren():
    """Installiert den globalen Exception-Handler."""
    sys.excepthook = _schreibe_fehler

    # Auch für Threads
    import threading
    def _thread_excepthook(args):
        _schreibe_fehler(args.exc_type, args.exc_value, args.exc_traceback)
    threading.excepthook = _thread_excepthook

    print(f"[FehlerLog] Aktiv – Logdatei: {FEHLER_LOG_DATEI}")
