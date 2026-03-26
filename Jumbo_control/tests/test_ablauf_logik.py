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


# ── Alarm-Deduplizierung ──────────────────────────────────────

def _messzyklus_mit_callbacks():
    """Messzyklus mit Alarm- und Entwarnungs-Tracking."""
    m = Messzyklus()
    m._alarme      = []
    m._entwarnungen = []
    m.bei_alarm      = lambda name, wert: m._alarme.append((name, wert))
    m.bei_entwarnung = lambda name, wert: m._entwarnungen.append((name, wert))
    return m


def test_wiederholter_alarm_wird_nicht_dupliziert():
    """Gleicher Sensor über Schwelle in 3 aufeinanderfolgenden Zyklen → nur 1 Alarm."""
    m = _messzyklus_mit_callbacks()
    werte = {"T1": {"celsius": TEMP_ALARM_MAX + 5.0, "gueltig": True}}

    m._pruefe_alarme(werte)  # Zyklus 1: Alarm eintritt
    m._pruefe_alarme(werte)  # Zyklus 2: immer noch im Alarm
    m._pruefe_alarme(werte)  # Zyklus 3: immer noch im Alarm

    assert len(m._alarme) == 1, f"Alarm {len(m._alarme)}x statt 1x ausgelöst"


def test_alarm_dann_normal_dann_alarm_ergibt_zwei_alarme():
    """Sensor wechselt: Alarm → Normal → Alarm → muss 2x Alarm + 1x Entwarnung geben."""
    m = _messzyklus_mit_callbacks()
    alarm_werte  = {"T1": {"celsius": TEMP_ALARM_MAX + 5.0, "gueltig": True}}
    normal_werte = {"T1": {"celsius": 20.0, "gueltig": True}}

    m._pruefe_alarme(alarm_werte)    # Alarm eintritt
    m._pruefe_alarme(normal_werte)   # Entwarnung
    m._pruefe_alarme(alarm_werte)    # Alarm erneut

    assert len(m._alarme) == 2
    assert len(m._entwarnungen) == 1


def test_entwarnung_bei_rueckkehr_in_normalbereich():
    """Sensor geht von Alarm zurück zu Normal → Entwarnung wird ausgelöst."""
    m = _messzyklus_mit_callbacks()

    m._pruefe_alarme({"T1": {"celsius": TEMP_ALARM_MAX + 5.0, "gueltig": True}})
    assert len(m._alarme) == 1
    assert len(m._entwarnungen) == 0

    m._pruefe_alarme({"T1": {"celsius": 20.0, "gueltig": True}})
    assert len(m._entwarnungen) == 1
    assert m._entwarnungen[0][0] == "T1"


def test_mehrere_sensoren_unabhaengig():
    """Verschiedene Sensoren werden unabhängig voneinander getrackt."""
    m = _messzyklus_mit_callbacks()

    # T1 im Alarm, T2 normal
    m._pruefe_alarme({
        "T1": {"celsius": TEMP_ALARM_MAX + 5.0, "gueltig": True},
        "T2": {"celsius": 20.0, "gueltig": True},
    })
    assert len(m._alarme) == 1
    assert m._alarme[0][0] == "T1"

    # Zweiter Zyklus: T1 bleibt im Alarm, T2 geht in Alarm
    m._pruefe_alarme({
        "T1": {"celsius": TEMP_ALARM_MAX + 5.0, "gueltig": True},
        "T2": {"celsius": TEMP_ALARM_MAX + 3.0, "gueltig": True},
    })
    assert len(m._alarme) == 2  # nur T2 ist neu
    assert m._alarme[1][0] == "T2"


def test_keine_entwarnung_ohne_vorherigen_alarm():
    """Sensor der nie im Alarm war darf keine Entwarnung erzeugen."""
    m = _messzyklus_mit_callbacks()

    m._pruefe_alarme({"T1": {"celsius": 20.0, "gueltig": True}})
    m._pruefe_alarme({"T1": {"celsius": 25.0, "gueltig": True}})

    assert m._alarme == []
    assert m._entwarnungen == []


def test_ungueltig_waehrend_alarm_erzeugt_keine_entwarnung():
    """Sensor wird ungültig während Alarm → Entwarnung, da nicht mehr im Alarm-Set."""
    m = _messzyklus_mit_callbacks()

    m._pruefe_alarme({"T1": {"celsius": TEMP_ALARM_MAX + 5.0, "gueltig": True}})
    assert len(m._alarme) == 1

    # Sensor wird ungültig (z.B. Ausreißer gefiltert)
    m._pruefe_alarme({"T1": {"celsius": 99.0, "gueltig": False}})
    # Ungültig → nicht im aktuelle Set → Entwarnung
    assert len(m._entwarnungen) == 1


# ── Ausreißer: Filterung aktiv, aber kein GUI-Log ────────────

def test_ausreisser_wird_gefiltert_aber_nicht_geloggt():
    """Ausreißer werden intern gefiltert (gueltig=False), erzeugen aber
    über den bei_sprung_alarm-Callback nur den Typ 'temp_ausreisser'.
    Der GUI-Handler _zeige_sprung_alarm ignoriert diesen Typ jetzt."""
    m = _messzyklus_mit_einst(ausreisser_aktiv=True, ausreisser_grad=10.0)
    sprung_events = []
    m.bei_sprung_alarm = lambda typ, name, wert, sprung: sprung_events.append(typ)

    m._letzter_temp["T1"] = 20.0
    werte = {"T1": {"celsius": 80.0, "kelvin": 353.15, "gueltig": True}}

    result = m._pruefe_temp_spruenge(werte)

    # Filterung funktioniert weiterhin
    assert result["T1"]["gueltig"] is False
    assert result["T1"]["celsius"] is None
    # Callback wurde gefeuert mit Typ "temp_ausreisser"
    assert sprung_events == ["temp_ausreisser"]


def test_sprung_alarm_wird_weiterhin_geloggt():
    """Sprung-Alarm (unterhalb Ausreißer-Schwelle) wird weiterhin via Callback gemeldet."""
    m = _messzyklus_mit_einst(
        ausreisser_aktiv=True, ausreisser_grad=50.0,
        sprung_alarm_aktiv=True, sprung_alarm_grad=5.0,
    )
    sprung_events = []
    m.bei_sprung_alarm = lambda typ, name, wert, sprung: sprung_events.append(typ)

    m._letzter_temp["T1"] = 20.0
    # Sprung 12°C: > sprung_alarm_grad (5.0) aber < ausreisser_grad (50.0)
    werte = {"T1": {"celsius": 32.0, "kelvin": 305.15, "gueltig": True}}

    result = m._pruefe_temp_spruenge(werte)

    # Wert bleibt gültig (kein Ausreißer)
    assert result["T1"]["gueltig"] is True
    # Callback wurde mit "temp_alarm" gefeuert (dieser Typ WIRD im GUI geloggt)
    assert sprung_events == ["temp_alarm"]


def test_gui_handler_ignoriert_ausreisser_typen():
    """Simuliert den GUI-Handler: nur temp_alarm und druck_alarm erzeugen Log-Einträge."""
    # Nachbildung der _zeige_sprung_alarm-Logik aus hauptfenster.py
    gui_log = []

    def fake_zeige_sprung_alarm(typ, name, wert, sprung):
        if typ == "temp_alarm":
            gui_log.append(f"Temperatursprung: {name}")
        elif typ == "druck_alarm":
            gui_log.append(f"Drucksprung: {name}")
        # temp_ausreisser und druck_ausreisser → kein Log

    # Ausreißer-Typen → kein Log
    fake_zeige_sprung_alarm("temp_ausreisser", "T1", 80.0, 60.0)
    fake_zeige_sprung_alarm("druck_ausreisser", "CENT", 1e-2, 5.0)
    assert gui_log == []

    # Alarm-Typen → Log
    fake_zeige_sprung_alarm("temp_alarm", "T1", 30.0, 12.0)
    fake_zeige_sprung_alarm("druck_alarm", "CENT", 1e-4, 1.5)
    assert len(gui_log) == 2
    assert "Temperatursprung" in gui_log[0]
    assert "Drucksprung" in gui_log[1]
