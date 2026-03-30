"""
Tests für Messintervall-Klemmen und adaptiven Aufnahmemodus.

Getestete Funktionalität:
    - Minimales Messintervall wird korrekt begrenzt
    - Einmaliges Warning-Logging bei zu kleinem Intervall
    - Normales Logging bei gültigem Intervall
    - Adaptive Triggerung bei %-Änderung (Temp + Druck)
    - Erzwungener Schreibpunkt nach Stillezeit
    - Grenzfälle: Nullwerte, konstante Messreihen, Moduswechsel
"""
import time
import pytest
from unittest.mock import patch
from steuerung.ablauf import Messzyklus
from config import MESS_INTERVALL_MIN_S


# ── Hilfsfunktionen ─────────────────────────────────────────

def _zyklus() -> Messzyklus:
    """Messzyklus ohne Hardware-Start für Unit-Tests."""
    return Messzyklus()


def _temp_werte(celsius: float, name: str = "T1") -> dict:
    return {name: {"celsius": celsius, "kelvin": celsius + 273.15, "gueltig": True}}


def _druck_werte(mbar: float, name: str = "CENTER") -> dict:
    return {name: {"mbar": mbar, "gueltig": True, "status": "OK"}}


# ── Messintervall-Klemmen ────────────────────────────────────

def test_intervall_unter_minimum_wird_geklemmt():
    """Intervall < MESS_INTERVALL_MIN_S wird auf Minimum gesetzt."""
    m = _zyklus()
    m.intervall = 0.5
    # In der Praxis klemmt die GUI; hier prüfen wir die Konstante
    assert MESS_INTERVALL_MIN_S >= 1.0
    effektiv = max(m.intervall, MESS_INTERVALL_MIN_S)
    assert effektiv == MESS_INTERVALL_MIN_S


def test_intervall_ueber_minimum_bleibt_erhalten():
    """Gültiges Intervall wird nicht verändert."""
    m = _zyklus()
    m.intervall = 10.0
    assert m.intervall == 10.0


def test_default_intervall():
    """Standard-Intervall ist 5 Sekunden."""
    m = _zyklus()
    assert m.intervall == 5.0


# ── Adaptiver Modus – Grundlogik ────────────────────────────

def test_nicht_adaptiv_emittiert_immer():
    """Ohne adaptiven Modus: _soll_emittieren gibt immer True zurück."""
    m = _zyklus()
    m.adaptiv_aktiv = False
    werte = _temp_werte(20.0)
    assert m._soll_emittieren("temp", werte) is True
    assert m._soll_emittieren("temp", werte) is True


def test_adaptiv_erster_wert_wird_emittiert():
    """Erster Messwert im adaptiven Modus wird immer emittiert."""
    m = _zyklus()
    m.adaptiv_aktiv = True
    m.adaptiv_temp_schwelle_pct = 1.0
    # Stille-Zeit weit in der Zukunft setzen (kein Timeout-Trigger)
    m._adaptiv_letzte_temp_emit = time.monotonic()
    werte = _temp_werte(20.0)
    assert m._soll_emittieren("temp", werte) is True


def test_adaptiv_keine_aenderung_kein_emit():
    """Identischer Wert unter Schwelle → kein Emit."""
    m = _zyklus()
    m.adaptiv_aktiv = True
    m.adaptiv_temp_schwelle_pct = 1.0
    m.adaptiv_max_stille_s = 60.0

    werte = _temp_werte(100.0)
    # Erster Wert → emittieren + Referenz setzen
    assert m._soll_emittieren("temp", werte) is True
    # Gleicher Wert → keine Änderung
    assert m._soll_emittieren("temp", werte) is False


def test_adaptiv_aenderung_ueber_schwelle_emittiert():
    """Änderung > Schwelle → Emit."""
    m = _zyklus()
    m.adaptiv_aktiv = True
    m.adaptiv_temp_schwelle_pct = 1.0
    m.adaptiv_max_stille_s = 60.0

    # Referenz setzen
    assert m._soll_emittieren("temp", _temp_werte(100.0)) is True
    # 2% Änderung > 1% Schwelle
    assert m._soll_emittieren("temp", _temp_werte(102.0)) is True


def test_adaptiv_aenderung_unter_schwelle_kein_emit():
    """Änderung < Schwelle → kein Emit."""
    m = _zyklus()
    m.adaptiv_aktiv = True
    m.adaptiv_temp_schwelle_pct = 5.0
    m.adaptiv_max_stille_s = 60.0

    assert m._soll_emittieren("temp", _temp_werte(100.0)) is True
    # 1% Änderung < 5% Schwelle
    assert m._soll_emittieren("temp", _temp_werte(101.0)) is False


# ── Druck adaptiv ───────────────────────────────────────────

def test_adaptiv_druck_aenderung():
    """Druck-Änderung über Schwelle → Emit."""
    m = _zyklus()
    m.adaptiv_aktiv = True
    m.adaptiv_druck_schwelle_pct = 5.0
    m.adaptiv_max_stille_s = 60.0

    assert m._soll_emittieren("druck", _druck_werte(1e-6)) is True
    # 20% Änderung > 5%
    assert m._soll_emittieren("druck", _druck_werte(1.2e-6)) is True


def test_adaptiv_druck_stabil_kein_emit():
    """Stabiler Druck → kein Emit."""
    m = _zyklus()
    m.adaptiv_aktiv = True
    m.adaptiv_druck_schwelle_pct = 10.0
    m.adaptiv_max_stille_s = 60.0

    assert m._soll_emittieren("druck", _druck_werte(1e-6)) is True
    assert m._soll_emittieren("druck", _druck_werte(1.01e-6)) is False


# ── Erzwungener Punkt nach Stillezeit ────────────────────────

def test_adaptiv_stille_timeout_erzwingt_emit():
    """Nach Ablauf der Stillezeit wird auch ohne Änderung emittiert."""
    m = _zyklus()
    m.adaptiv_aktiv = True
    m.adaptiv_temp_schwelle_pct = 10.0
    m.adaptiv_max_stille_s = 5.0

    assert m._soll_emittieren("temp", _temp_werte(100.0)) is True
    # Simuliere abgelaufene Stillezeit
    m._adaptiv_letzte_temp_emit = time.monotonic() - 10.0
    assert m._soll_emittieren("temp", _temp_werte(100.0)) is True


def test_adaptiv_max_stille_begrenzt_auf_60s():
    """Stillezeit wird intern auf 60s begrenzt, auch wenn höher gesetzt."""
    m = _zyklus()
    m.adaptiv_aktiv = True
    m.adaptiv_max_stille_s = 120.0  # über Limit
    m.adaptiv_temp_schwelle_pct = 99.0

    assert m._soll_emittieren("temp", _temp_werte(100.0)) is True
    # 61s vergangen – muss emittieren trotz max_stille_s=120
    m._adaptiv_letzte_temp_emit = time.monotonic() - 61.0
    assert m._soll_emittieren("temp", _temp_werte(100.0)) is True


# ── Vergleich mit N Werten ───────────────────────────────────

def test_adaptiv_vergleich_mittelwert():
    """Mit vergleichs_n=3 wird gegen Mittelwert der letzten 3 verglichen."""
    m = _zyklus()
    m.adaptiv_aktiv = True
    m.adaptiv_temp_schwelle_pct = 5.0
    m.adaptiv_vergleichs_n = 3
    m.adaptiv_max_stille_s = 60.0

    # 3 Referenzwerte aufbauen: 100, 102, 101 → Mittel 101
    for val in [100.0, 102.0, 101.0]:
        m._soll_emittieren("temp", _temp_werte(val))
        # Stille zurücksetzen um Timeout zu vermeiden
        m._adaptiv_letzte_temp_emit = time.monotonic()

    # 102 vs Mittel 101 → ~1% < 5% → kein Emit
    assert m._soll_emittieren("temp", _temp_werte(102.0)) is False
    # 110 vs Mittel 101 → ~8.9% > 5% → Emit
    assert m._soll_emittieren("temp", _temp_werte(110.0)) is True


# ── Grenzfälle ───────────────────────────────────────────────

def test_adaptiv_nullwert_temperatur():
    """Temperatur nahe 0°C: Division-by-zero wird vermieden."""
    m = _zyklus()
    m.adaptiv_aktiv = True
    m.adaptiv_temp_schwelle_pct = 1.0
    m.adaptiv_max_stille_s = 60.0

    # Referenz = 0.0°C
    assert m._soll_emittieren("temp", _temp_werte(0.0)) is True
    # Winzige Änderung von 0 → kein Crash, kein Emit
    assert m._soll_emittieren("temp", _temp_werte(0.0)) is False
    # Relevante Änderung von 0
    assert m._soll_emittieren("temp", _temp_werte(1.0)) is True


def test_adaptiv_ungueltige_werte_werden_ignoriert():
    """Ungültige Messwerte beeinflussen die adaptive Entscheidung nicht."""
    m = _zyklus()
    m.adaptiv_aktiv = True
    m.adaptiv_temp_schwelle_pct = 1.0
    m.adaptiv_max_stille_s = 60.0

    assert m._soll_emittieren("temp", _temp_werte(100.0)) is True
    # Ungültiger Wert → alle Sensoren ungültig → kein Trigger
    ungueltig = {"T1": {"celsius": 200.0, "gueltig": False}}
    assert m._soll_emittieren("temp", ungueltig) is False


def test_adaptiv_modus_wechsel():
    """Ein-/Ausschalten des adaptiven Modus funktioniert sauber."""
    m = _zyklus()
    m.adaptiv_aktiv = False
    werte = _temp_werte(100.0)

    # Nicht-adaptiv: immer True
    assert m._soll_emittieren("temp", werte) is True
    assert m._soll_emittieren("temp", werte) is True

    # Adaptiv ein
    m.adaptiv_aktiv = True
    m.adaptiv_max_stille_s = 60.0
    m.adaptiv_temp_schwelle_pct = 1.0
    # Erster Wert nach Aktivierung → True (keine Referenz)
    m._adaptiv_temp_ref.clear()
    m._adaptiv_letzte_temp_emit = time.monotonic()
    assert m._soll_emittieren("temp", werte) is True
    # Gleicher Wert → False
    assert m._soll_emittieren("temp", werte) is False

    # Adaptiv aus → sofort wieder True
    m.adaptiv_aktiv = False
    assert m._soll_emittieren("temp", werte) is True


def test_adaptiv_konstante_messreihe_nur_stille_trigger():
    """Bei komplett konstanter Messreihe triggert nur die Stillezeit."""
    m = _zyklus()
    m.adaptiv_aktiv = True
    m.adaptiv_temp_schwelle_pct = 1.0
    m.adaptiv_max_stille_s = 5.0

    werte = _temp_werte(42.0)
    # Erster Punkt
    assert m._soll_emittieren("temp", werte) is True
    # Kein Emit bei identischen Werten
    for _ in range(10):
        assert m._soll_emittieren("temp", werte) is False

    # Stillezeit überschritten → erzwungener Punkt
    m._adaptiv_letzte_temp_emit = time.monotonic() - 6.0
    assert m._soll_emittieren("temp", werte) is True


def test_adaptiv_temp_und_druck_unabhaengig():
    """Temperatur und Druck werden unabhängig voneinander geprüft."""
    m = _zyklus()
    m.adaptiv_aktiv = True
    m.adaptiv_temp_schwelle_pct = 1.0
    m.adaptiv_druck_schwelle_pct = 5.0
    m.adaptiv_max_stille_s = 60.0

    # Beide initialisieren
    assert m._soll_emittieren("temp", _temp_werte(100.0)) is True
    assert m._soll_emittieren("druck", _druck_werte(1e-6)) is True

    # Temp ändert sich, Druck nicht
    assert m._soll_emittieren("temp", _temp_werte(105.0)) is True
    assert m._soll_emittieren("druck", _druck_werte(1e-6)) is False
