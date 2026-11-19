"""
Tests für Stabilitäts-Fixes (2026-11):

1. Hauptfenster.log() ist aus Hintergrund-Threads aufrufbar (Signal statt Widget-Zugriff)
2. XSP01R-Fenster aktualisiert Widgets nur im GUI-Thread
3. tprint wirft nie (geschlossene Konsole), Messzyklus überlebt das
4. Temperaturfehler gibt den NI-Task frei (beenden())
5. Ausreißer-Filter sperrt einen Sensor nicht dauerhaft
6. Watchdog meldet ausbleibende Messwerte / toten Mess-Thread

Keine echte Hardware: alle Geräte werden durch Attrappen ersetzt.
"""
import os
import sys
import threading
import time
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from steuerung.ablauf import Messzyklus, AUSREISSER_MAX_FOLGE


# ── Hilfen ─────────────────────────────────────────────────────

class _Einst:
    def __init__(self, grad=10.0):
        self.temp = {"ausreisser_aktiv": True, "ausreisser_grad": grad,
                     "sprung_alarm_aktiv": False, "sprung_alarm_grad": 5.0}
        self.druck = {"ausreisser_aktiv": False, "ausreisser_dekaden": 2.0,
                      "sprung_alarm_aktiv": False, "sprung_alarm_dekaden": 1.0}


def _zyklus(grad=10.0):
    m = Messzyklus()
    m._alarm_einst = _Einst(grad)
    return m


def _w(c):
    return {"T1": {"celsius": c, "kelvin": c + 273.15, "gueltig": True}}


def _w_ungueltig():
    return {"T1": {"celsius": None, "kelvin": None, "gueltig": False}}


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _warte_bis(bedingung, qapp, timeout=3.0):
    ende = time.time() + timeout
    while time.time() < ende:
        qapp.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    return False


# ── 3. tprint ──────────────────────────────────────────────────

class _KaputteKonsole:
    def write(self, *_):
        raise OSError(22, "Kein Prozess ist am anderen Ende der Pipe")

    def flush(self):
        raise OSError(22, "Kein Prozess ist am anderen Ende der Pipe")


def test_tprint_wirft_nicht_bei_kaputter_konsole(monkeypatch):
    from log_utils import tprint
    monkeypatch.setattr(sys, "stdout", _KaputteKonsole())
    tprint("Test", "darf nicht crashen")          # keine Exception


def test_tprint_wirft_nicht_ohne_konsole(monkeypatch):
    from log_utils import tprint
    monkeypatch.setattr(sys, "stdout", None)
    tprint("Test", "darf nicht crashen")


def test_messzyklus_ueberlebt_kaputte_konsole(monkeypatch, tmp_path):
    """Unerwarteter Fehler im Zyklus + kaputte Konsole → Schleife läuft weiter.

    Früher warf die Fehlerbehandlung selbst (print → OSError) und beendete
    damit den Mess-Thread.
    """
    import config
    import steuerung.ablauf as ablauf
    monkeypatch.setattr(sys, "stdout", _KaputteKonsole())
    monkeypatch.setattr(sys, "stderr", _KaputteKonsole())
    monkeypatch.setattr(ablauf.time, "sleep", lambda s: None)
    monkeypatch.setattr(config, "LOG_PFAD", str(tmp_path))   # echtes fehler.log schonen

    m = Messzyklus(intervall=0)
    durchlaeufe = {"n": 0}

    def _reconnect_wirft():
        # Reconnect liegt außerhalb der inneren try-Blöcke → äußerer except
        durchlaeufe["n"] += 1
        m._letzter_reconnect = 0
        if durchlaeufe["n"] >= 3:
            m._aktiv = False
        raise RuntimeError("unerwartet")

    monkeypatch.setattr(m, "_verbinde_temperatur", _reconnect_wirft)
    m._aktiv = True
    m._loop()   # darf nicht mit Exception enden
    assert durchlaeufe["n"] == 3
    assert "MESSZYKLUS FEHLER" in (tmp_path / "fehler.log").read_text(encoding="utf-8")


# ── 4. cDAQ-Task freigeben ─────────────────────────────────────

def test_temperaturfehler_gibt_task_frei(monkeypatch):
    import steuerung.ablauf as ablauf
    monkeypatch.setattr(ablauf.time, "sleep", lambda s: None)
    m = Messzyklus(intervall=0)
    m._letzter_reconnect = time.time() + 1e6
    beendet = []

    class _Temp:
        def messen(self):
            m._aktiv = False
            raise RuntimeError("cDAQ weg")

        def beenden(self):
            beendet.append(True)

    m._temperatur = _Temp()
    m._hw_status.cdaq = True
    m._aktiv = True
    m._loop()
    assert beendet == [True]
    assert m._temperatur is None
    assert m._hw_status.cdaq is False


def test_letzte_messung_wird_gesetzt(monkeypatch):
    import steuerung.ablauf as ablauf
    monkeypatch.setattr(ablauf.time, "sleep", lambda s: None)
    m = Messzyklus(intervall=0)
    m._letzter_reconnect = time.time() + 1e6

    class _Druck:
        def messen(self):
            m._aktiv = False
            return {}

    class _Csv:
        def speichere_druecke(self, w):
            pass

    m._druck, m._csv = _Druck(), _Csv()
    m._aktiv = True
    vorher = time.time()
    m._loop()
    assert m.letzte_messung >= vorher


# ── 5. Ausreißer-Filter ────────────────────────────────────────

def test_einzelner_ausreisser_wird_gefiltert():
    m = _zyklus()
    m._pruefe_temp_spruenge(_w(20.0))
    assert m._pruefe_temp_spruenge(_w(80.0))["T1"]["gueltig"] is False
    assert m._pruefe_temp_spruenge(_w(20.5))["T1"]["gueltig"] is True


def test_echter_sprung_wird_nach_mehreren_ausreissern_uebernommen():
    """Früher: Sensor blieb nach echtem Sprung > Schwelle für immer ungültig."""
    m = _zyklus()
    m._pruefe_temp_spruenge(_w(20.0))
    ergebnisse = [m._pruefe_temp_spruenge(_w(80.0))["T1"]["gueltig"]
                  for _ in range(AUSREISSER_MAX_FOLGE)]
    assert ergebnisse[:-1] == [False] * (AUSREISSER_MAX_FOLGE - 1)
    assert ergebnisse[-1] is True
    assert m._letzter_temp["T1"] == 80.0
    assert m._pruefe_temp_spruenge(_w(80.3))["T1"]["gueltig"] is True


def test_nicht_aufeinanderfolgende_ausreisser_zaehlen_nicht_zusammen():
    m = _zyklus()
    m._pruefe_temp_spruenge(_w(20.0))
    for _ in range(5):
        assert m._pruefe_temp_spruenge(_w(90.0))["T1"]["gueltig"] is False
        assert m._pruefe_temp_spruenge(_w(20.0))["T1"]["gueltig"] is True


def test_ungueltiger_sensor_setzt_referenz_zurueck():
    """Abgesteckt bei 30 °C, wieder angesteckt bei -150 °C → sofort gültig."""
    m = _zyklus()
    m._pruefe_temp_spruenge(_w(30.0))
    m._pruefe_temp_spruenge(_w_ungueltig())
    assert "T1" not in m._letzter_temp
    assert m._pruefe_temp_spruenge(_w(-150.0))["T1"]["gueltig"] is True


# ── 1. log() thread-sicher ─────────────────────────────────────

def test_log_aus_hintergrund_thread_geht_ueber_signal(qapp):
    from PyQt6.QtCore import QObject
    from gui.hauptfenster import Hauptfenster, SignalBridge

    class _Fenster(QObject):
        log = Hauptfenster.log

        def __init__(self):
            super().__init__()
            self._bridge = SignalBridge()
            self._theme = {"log_info": "#fff", "log_stamp": "#888"}
            self.zeilen = []
            self.log_fenster = types.SimpleNamespace(append=self._append)

        def _append(self, html):
            self.zeilen.append((threading.current_thread() is threading.main_thread(), html))

    f = _Fenster()
    f._bridge.log_msg.connect(f.log)          # wie im Hauptfenster
    t = threading.Thread(target=lambda: f.log("aus Thread", "#f00"))
    t.start(); t.join()
    assert _warte_bis(lambda: f.zeilen, qapp)
    im_gui_thread, html = f.zeilen[0]
    assert im_gui_thread, "Widget wurde aus Hintergrund-Thread angefasst"
    assert "aus Thread" in html and "#f00" in html


# ── 2. XSP01R-Fenster ──────────────────────────────────────────

@pytest.mark.parametrize("fehler", [False, True])
def test_xsp01r_fenster_aktualisiert_nur_im_gui_thread(qapp, monkeypatch, fehler):
    import hardware.geraete as geraete
    import gui.xsp01r_fenster as xf

    class _Xsp:
        def status(self):
            if fehler:
                raise IOError("COM6 belegt")
            return {"kryo1_system": True, "kryo1_remote": False,
                    "kryo2_system": False, "kryo2_remote": False}

    monkeypatch.setattr(geraete, "get_xsp01r", lambda: _Xsp())
    threads = []
    orig = xf.RelaisZeile.aktualisieren

    def _spion(self, st):
        threads.append(threading.current_thread() is threading.main_thread())
        return orig(self, st)

    monkeypatch.setattr(xf.RelaisZeile, "aktualisieren", _spion)
    fenster = xf.Xsp01rFenster()
    fenster._timer.stop()
    assert _warte_bis(lambda: "erbunden" in fenster._lbl_verbindung.text(), qapp)
    assert threads and all(threads)
    if fehler:
        assert "Nicht verbunden" in fenster._lbl_verbindung.text()
        assert "COM6 belegt" in fenster._lbl_verbindung.text()
    else:
        assert fenster._lbl_verbindung.text().startswith("● Verbunden")
    assert fenster._abfrage_laeuft is False
    fenster.close()


# ── 6. Watchdog ────────────────────────────────────────────────

def _watchdog_fenster(qapp, letzte, lebt=True, intervall=5.0):
    from PyQt6.QtWidgets import QLabel
    from gui.hauptfenster import Hauptfenster
    thread = types.SimpleNamespace(is_alive=lambda: lebt)
    f = types.SimpleNamespace(
        _zyklus=types.SimpleNamespace(letzte_messung=letzte, intervall=intervall,
                                      _thread=thread),
        _sb_watchdog=QLabel(),
        _watchdog_start=time.time(),
        _watchdog_alarm=None,
        _theme={"danger": "red", "log_ok": "green"},
        WATCHDOG_MIN_S=Hauptfenster.WATCHDOG_MIN_S,
        logs=[],
    )
    f.log = lambda text, farbe=None: f.logs.append(text)
    pruefen = lambda: Hauptfenster._watchdog_pruefen(f)
    return f, pruefen


def test_watchdog_ok(qapp):
    f, pruefen = _watchdog_fenster(qapp, letzte=time.time() - 3)
    pruefen()
    assert f._watchdog_alarm is None and f.logs == []
    assert "vor 3 s" in f._sb_watchdog.text()


def test_watchdog_veraltet_meldet_einmal_und_entwarnt(qapp):
    f, pruefen = _watchdog_fenster(qapp, letzte=time.time() - 300)
    pruefen(); pruefen()
    assert f._watchdog_alarm == "veraltet"
    assert len(f.logs) == 1 and "WATCHDOG" in f.logs[0]
    assert f._sb_watchdog.text().startswith("⚠")
    f._zyklus.letzte_messung = time.time()
    pruefen()
    assert f._watchdog_alarm is None
    assert "wieder" in f.logs[-1]


def test_watchdog_toter_thread(qapp):
    f, pruefen = _watchdog_fenster(qapp, letzte=time.time(), lebt=False)
    pruefen()
    assert f._watchdog_alarm == "thread"
    assert "gestoppt" in f._sb_watchdog.text()


def test_watchdog_grenze_skaliert_mit_intervall(qapp):
    # Intervall 60 s → Grenze 180 s; 100 s alt ist noch ok
    f, pruefen = _watchdog_fenster(qapp, letzte=time.time() - 100, intervall=60.0)
    pruefen()
    assert f._watchdog_alarm is None
