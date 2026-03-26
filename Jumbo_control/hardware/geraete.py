"""
hardware/geraete.py
Globale Singleton-Instanzen der Hardware-Geräte.
Verhindert dass COM-Ports mehrfach geöffnet werden.
"""

_xsp01r = None

def get_xsp01r():
    """Gibt die globale XSP01R-Instanz zurück (lazy init)."""
    global _xsp01r
    if _xsp01r is None:
        from hardware.xsp01r import XSP01R
        _xsp01r = XSP01R()
    return _xsp01r
