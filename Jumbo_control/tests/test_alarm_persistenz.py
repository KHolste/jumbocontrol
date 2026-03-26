"""
Tests für AlarmEinstellungen-Persistenz (JSON) und Validierung.
Kein PyQt6 nötig – testet nur die Datenlogik.
"""
import json
import os
import pytest
from gui.alarm_einstellungen import (
    AlarmEinstellungen, DEFAULTS, _validiere, _JSON_PFAD,
)


# ── Validierung ───────────────────────────────────────────────

def test_validiere_leeres_dict_gibt_defaults():
    """Leeres Dict → alle Defaults zurück."""
    result = _validiere({})
    assert result["temp"] == DEFAULTS["temp"]
    assert result["druck"] == DEFAULTS["druck"]


def test_validiere_teilweise_daten():
    """Nur temp gesetzt → druck bekommt Defaults."""
    daten = {"temp": {"sprung_alarm_grad": 5.0}}
    result = _validiere(daten)
    assert result["temp"]["sprung_alarm_grad"] == 5.0
    assert result["temp"]["ausreisser_grad"] == DEFAULTS["temp"]["ausreisser_grad"]
    assert result["druck"] == DEFAULTS["druck"]


def test_validiere_ungueltige_typen():
    """String statt Float → Default."""
    daten = {"temp": {"sprung_alarm_grad": "abc"}}
    result = _validiere(daten)
    assert result["temp"]["sprung_alarm_grad"] == DEFAULTS["temp"]["sprung_alarm_grad"]


def test_validiere_negative_werte():
    """Negative Schwellenwerte → Default (muss positiv sein)."""
    daten = {"temp": {"sprung_alarm_grad": -5.0}}
    result = _validiere(daten)
    assert result["temp"]["sprung_alarm_grad"] == DEFAULTS["temp"]["sprung_alarm_grad"]


def test_validiere_bool_felder():
    """Bool-Felder akzeptieren truthy/falsy Werte."""
    daten = {"temp": {"sprung_alarm_aktiv": False}}
    result = _validiere(daten)
    assert result["temp"]["sprung_alarm_aktiv"] is False


def test_validiere_extra_keys_werden_ignoriert():
    """Unbekannte Keys werden nicht in Ergebnis übernommen."""
    daten = {"temp": {"unbekannt": 42, "sprung_alarm_grad": 7.0}}
    result = _validiere(daten)
    assert "unbekannt" not in result["temp"]
    assert result["temp"]["sprung_alarm_grad"] == 7.0


def test_validiere_section_nicht_dict():
    """Wenn eine Section kein Dict ist → komplette Defaults."""
    daten = {"temp": "falsch", "druck": [1, 2, 3]}
    result = _validiere(daten)
    assert result["temp"] == DEFAULTS["temp"]
    assert result["druck"] == DEFAULTS["druck"]


# ── Speichern/Laden (Roundtrip) ───────────────────────────────

def test_speichern_laden_roundtrip(tmp_path, monkeypatch):
    """Werte speichern und laden muss identische Ergebnisse liefern."""
    json_pfad = str(tmp_path / "alarm.json")
    monkeypatch.setattr("gui.alarm_einstellungen._JSON_PFAD", json_pfad)

    # Speichern
    e = AlarmEinstellungen()
    e.temp["sprung_alarm_grad"] = 42.0
    e.druck["ausreisser_dekaden"] = 7.5
    e.speichern()

    assert os.path.exists(json_pfad)

    # Laden
    e2 = AlarmEinstellungen()
    assert e2.temp["sprung_alarm_grad"] == 42.0
    assert e2.druck["ausreisser_dekaden"] == 7.5


def test_laden_ohne_datei_gibt_defaults(tmp_path, monkeypatch):
    """Wenn keine JSON-Datei existiert → Defaults."""
    json_pfad = str(tmp_path / "nicht_vorhanden.json")
    monkeypatch.setattr("gui.alarm_einstellungen._JSON_PFAD", json_pfad)

    e = AlarmEinstellungen()
    assert e.temp == DEFAULTS["temp"]
    assert e.druck == DEFAULTS["druck"]


def test_laden_kaputte_datei_gibt_defaults(tmp_path, monkeypatch):
    """Kaputtes JSON → Defaults statt Crash."""
    json_pfad = str(tmp_path / "kaputt.json")
    monkeypatch.setattr("gui.alarm_einstellungen._JSON_PFAD", json_pfad)

    with open(json_pfad, "w") as f:
        f.write("{kaputtes json!!!")

    e = AlarmEinstellungen()
    assert e.temp == DEFAULTS["temp"]
