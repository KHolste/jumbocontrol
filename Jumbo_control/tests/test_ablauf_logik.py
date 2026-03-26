"""
Tests für steuerung/ablauf.py – Alarm- und Sprunglogik ohne Hardware.

Getestete Methoden:
    _pruefe_temp_spruenge  – Ausreißer-Filterung
    _pruefe_alarme         – Grenzwert-Alarme
"""
import pytest
from steuerung.ablauf import Messzyklus
from config import TEMP_ALARM_MAX


# ── Hilfsobjekte ──────────────────────────────────────────────

class FakeTempEinst:
    """Minimaler Ersatz für AlarmEinstellungen.temp-Dict."""
    def __init__(self, ausreisser_aktiv=True, ausreisser_grad=10.0,
                 sprung_alarm_aktiv=False, sprung_alarm_grad=5.0):
        self.ausreisser_aktiv   = ausreisser_aktiv
        self.ausreisser_grad    = ausreisser_grad
        self.sprung_alarm_aktiv = sprung_alarm_aktiv
        self.sprung_alarm_grad  = sprung_alarm_grad


class FakeAlarmEinst:
    """Minimaler Ersatz für AlarmEinstellungen ohne PyQt6-Abhängigkeit."""
    def __init__(self, **temp_kwargs):
        self.temp  = FakeTempEinst(**temp_kwargs).__dict__
        self.druck = {
            "ausreisser_aktiv":   False,
            "ausreisser_dekaden": 2.0,
            "sprung_alarm_aktiv": False,
            "sprung_alarm_dekaden": 1.0,
        }


def _messzyklus_mit_einst(**temp_kwargs) -> Messzyklus:
    """Erstellt Messzyklus ohne Hardware (kein starten())."""
    m = Messzyklus()
    m._alarm_einst = FakeAlarmEinst(**temp_kwargs)
    return m


# ── _pruefe_temp_spruenge ──────────────────────────────────────

def test_ausreisser_ueber_schwelle_wird_ungueltig():
    """Sprung > ausreisser_grad → Eintrag als ungültig markiert (gueltig=False)."""
    m = _messzyklus_mit_einst(ausreisser_aktiv=True, ausreisser_grad=10.0)

    # Vorheriger Wert: 20 °C; neuer Wert: 35 °C → Sprung 15 °C > 10 °C
    m._letzter_temp["T1"] = 20.0
    werte = {"T1": {"celsius": 35.0, "kelvin": 308.15, "gueltig": True}}

    result = m._pruefe_temp_spruenge(werte)

    assert result["T1"]["gueltig"] is False
    assert result["T1"]["celsius"] is None


def test_wert_unterhalb_schwelle_bleibt_gueltig():
    """Sprung ≤ ausreisser_grad → Eintrag bleibt gültig."""
    m = _messzyklus_mit_einst(ausreisser_aktiv=True, ausreisser_grad=10.0)

    # Vorheriger Wert: 20 °C; neuer Wert: 25 °C → Sprung 5 °C ≤ 10 °C
    m._letzter_temp["T1"] = 20.0
    werte = {"T1": {"celsius": 25.0, "kelvin": 298.15, "gueltig": True}}

    result = m._pruefe_temp_spruenge(werte)

    assert result["T1"]["gueltig"] is True
    assert result["T1"]["celsius"] == pytest.approx(25.0)


def test_ausreisser_filter_deaktiviert_bleibt_gueltig():
    """Wenn ausreisser_aktiv=False, darf kein Ausreißer gefiltert werden."""
    m = _messzyklus_mit_einst(ausreisser_aktiv=False, ausreisser_grad=10.0)

    m._letzter_temp["T1"] = 20.0
    werte = {"T1": {"celsius": 100.0, "kelvin": 373.15, "gueltig": True}}

    result = m._pruefe_temp_spruenge(werte)

    assert result["T1"]["gueltig"] is True


def test_erster_messwert_ohne_vorherigen_bleibt_gueltig():
    """Erster Messwert ohne _letzter_temp-Eintrag darf nicht gefiltert werden."""
    m = _messzyklus_mit_einst(ausreisser_aktiv=True, ausreisser_grad=10.0)
    # _letzter_temp ist leer
    werte = {"T1": {"celsius": 50.0, "kelvin": 323.15, "gueltig": True}}

    result = m._pruefe_temp_spruenge(werte)

    assert result["T1"]["gueltig"] is True


# ── _pruefe_alarme ─────────────────────────────────────────────

def test_alarm_ueber_temp_alarm_max():
    """Temperatur > TEMP_ALARM_MAX (50 °C) muss bei_alarm auslösen."""
    m = Messzyklus()
    ausgeloest = []
    m.bei_alarm = lambda name, wert: ausgeloest.append((name, wert))

    werte = {"T1": {"celsius": TEMP_ALARM_MAX + 1.0, "gueltig": True}}
    m._pruefe_alarme(werte)

    assert len(ausgeloest) == 1
    assert ausgeloest[0] == ("T1", TEMP_ALARM_MAX + 1.0)


def test_kein_alarm_bei_normaltemperatur():
    """Temperatur im Normalbereich darf kein Alarm auslösen."""
    m = Messzyklus()
    ausgeloest = []
    m.bei_alarm = lambda name, wert: ausgeloest.append((name, wert))

    werte = {"T1": {"celsius": 20.0, "gueltig": True}}
    m._pruefe_alarme(werte)

    assert ausgeloest == []


def test_kein_alarm_wenn_ungueltig():
    """Ungültige Messwerte (gueltig=False) dürfen keinen Alarm auslösen."""
    m = Messzyklus()
    ausgeloest = []
    m.bei_alarm = lambda name, wert: ausgeloest.append((name, wert))

    werte = {"T1": {"celsius": 99.0, "gueltig": False}}
    m._pruefe_alarme(werte)

    assert ausgeloest == []
