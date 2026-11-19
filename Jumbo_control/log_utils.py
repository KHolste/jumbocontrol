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
    # Konsolenausgabe darf niemals das Programm stören: Ist die Konsole
    # geschlossen/nicht vorhanden (OSError WinError 233, sys.stdout None) oder
    # kann ein Zeichen nicht kodiert werden, wird die Meldung verworfen.
    # Früher konnte das den Messzyklus-Thread beenden.
    try:
        print(f"{ts} [{tag}] {msg}", flush=True)
    except Exception:
        pass
