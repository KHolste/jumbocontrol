"""
log_utils.py
Zentrale Hilfsfunktionen für timestamped Terminal-Logging.
"""

from datetime import datetime


def tprint(tag: str, msg: str) -> None:
    """Gibt eine Meldung mit Zeitstempel und Tag auf der Konsole aus.

    Format: DD.MM.YYYY HH:MM:SS [Tag] Nachricht
    """
    ts = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    print(f"{ts} [{tag}] {msg}")
