"""
Tests für gui/druck_grossanzeige.format_druck_wert – reine Logik, kein Qt nötig.
"""
import pytest
from gui.druck_grossanzeige import format_druck_wert


def test_gueltiger_wert_zeigt_scientific():
    """Gültiger mbar-Wert → wissenschaftliche Notation + 'mbar'."""
    d = {"mbar": 1.23e-4, "gueltig": True, "status": "OK"}
    text, einheit = format_druck_wert(d)
    assert text == "1.23E-04"
    assert einheit == "mbar"


def test_gueltiger_wert_gross():
    """Auch große Werte werden korrekt formatiert."""
    d = {"mbar": 9.50e+2, "gueltig": True, "status": "OK"}
    text, einheit = format_druck_wert(d)
    assert text == "9.50E+02"
    assert einheit == "mbar"


def test_ungueltig_mit_status():
    """gueltig=False mit Status-Text → Status wird angezeigt, keine Einheit."""
    d = {"mbar": 1.0, "gueltig": False, "status": "Overrange"}
    text, einheit = format_druck_wert(d)
    assert text == "Overrange"
    assert einheit == ""


def test_ungueltig_ohne_status():
    """gueltig=False ohne Status → '---'."""
    d = {"mbar": None, "gueltig": False, "status": ""}
    text, einheit = format_druck_wert(d)
    assert text == "---"
    assert einheit == ""


def test_leeres_dict():
    """Leeres Dict → '---'."""
    text, einheit = format_druck_wert({})
    assert text == "---"
    assert einheit == ""


def test_none_mbar_mit_status():
    """mbar=None + gueltig=True → Status anzeigen (Sensor meldet OK aber kein Wert)."""
    d = {"mbar": None, "gueltig": True, "status": "No sensor"}
    text, einheit = format_druck_wert(d)
    # mbar is None → val is None → fallback to status
    assert text == "No sensor"
    assert einheit == ""


def test_status_wird_abgeschnitten():
    """Langer Status-Text wird auf 14 Zeichen begrenzt."""
    d = {"mbar": None, "gueltig": False, "status": "Identification error XYZ"}
    text, _ = format_druck_wert(d)
    assert len(text) <= 14
