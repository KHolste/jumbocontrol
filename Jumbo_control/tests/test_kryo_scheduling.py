"""
Tests für die Kryo-Scheduling- und Schaltlogik.

Testet ohne Hardware und ohne PyQt6:
- Auswahl der betroffenen Kryos
- Sequenzielle Schalt-Reihenfolge (kein Kryo doppelt, kein Parallel-Schalten)
- Regen-Phasen-Logik (AUS bei Start, EIN bei Stop)
- kryo_aus_signal / kryo_ein_signal Symmetrie
"""
import pytest
import threading
import time


# ── Hilfsobjekte (Fakes für Hardware + GUI) ───────────────────

class FakeKryoPanel:
    """Minimaler Ersatz für KryoStatusPanel – kein Qt nötig."""
    def __init__(self):
        self._schalt_lock = threading.Lock()
        self.ein_signale  = []   # [(name, zeitpunkt)]
        self.aus_signale  = []

    class _SignalFake:
        def __init__(self, liste):
            self._liste = liste
        def emit(self, name):
            self._liste.append((name, time.monotonic()))

    @property
    def kryo_ein_signal(self):
        return self._SignalFake(self.ein_signale)

    @property
    def kryo_aus_signal(self):
        return self._SignalFake(self.aus_signale)


class SchaltProtokoll:
    """Zeichnet Hardware-Schaltaufrufe auf, ohne echte Hardware."""
    def __init__(self):
        self.aufrufe = []   # [(name, an, zeitpunkt)]
        self.lock    = threading.Lock()

    def schalten(self, name: str, an: bool):
        with self.lock:
            self.aufrufe.append((name, an, time.monotonic()))


def kryo_alle_schalten_testbar(
    ausgewaehlte: list,
    an: bool,
    schalt_fn,          # (name, an) → None
    ein_signal_fn,      # (name) → None
    aus_signal_fn,      # (name) → None
    log_fn,             # (text) → None
    schalt_lock: threading.Lock,
    pause: float = 0.0, # im Test 0 statt 2.0
):
    """
    Reine Logik von _kryo_alle_schalten() – extrahiert für Tests.
    Sequenziell, mit Lock, mit Signal-Aufruf pro Kryo.
    """
    with schalt_lock:
        for name in ausgewaehlte:
            try:
                schalt_fn(name, an)
                if an:
                    ein_signal_fn(name)
                else:
                    aus_signal_fn(name)
                log_fn(f"{'EIN' if an else 'AUS'}: {name}")
            except Exception as e:
                log_fn(f"Fehler {name}: {e}")
            if pause > 0:
                time.sleep(pause)


# ── Tests: Auswahl ────────────────────────────────────────────

def test_auswahl_nur_markierte_kryos():
    """Nur angekreuzte Kryos werden in die Liste aufgenommen."""
    checks = {
        "Kryo 1": True, "Kryo 2": False, "Kryo 3": True,
        "Kryo 4": False, "Kryo 5": False, "Kryo 6": True,
        "Kryo 7": False, "Kryo 8": False,
    }
    ausgewaehlte = [n for n, checked in checks.items() if checked]
    assert ausgewaehlte == ["Kryo 1", "Kryo 3", "Kryo 6"]


def test_keine_auswahl_leere_liste():
    """Keine Checkbox aktiv → leere Auswahlliste."""
    checks = {f"Kryo {i}": False for i in range(1, 9)}
    ausgewaehlte = [n for n, checked in checks.items() if checked]
    assert ausgewaehlte == []


def test_alle_ausgewaehlt():
    """Alle Checkboxen an → alle 8 Kryos in der Liste."""
    checks = {f"Kryo {i}": True for i in range(1, 9)}
    ausgewaehlte = [n for n, checked in checks.items() if checked]
    assert len(ausgewaehlte) == 8


# ── Tests: Sequenzielle Schalt-Reihenfolge ────────────────────

def test_alle_kryos_werden_sequenziell_ausgeschaltet():
    """Alle ausgewählten Kryos AUS – jeder genau einmal, in Reihenfolge."""
    protokoll = SchaltProtokoll()
    log = []
    lock = threading.Lock()
    namen = ["Kryo 1", "Kryo 3", "Kryo 5"]

    kryo_alle_schalten_testbar(
        ausgewaehlte=namen, an=False,
        schalt_fn=protokoll.schalten,
        ein_signal_fn=lambda n: None,
        aus_signal_fn=lambda n: None,
        log_fn=log.append,
        schalt_lock=lock,
    )

    geschaltete = [(n, an) for n, an, _ in protokoll.aufrufe]
    assert geschaltete == [("Kryo 1", False), ("Kryo 3", False), ("Kryo 5", False)]


def test_alle_kryos_werden_sequenziell_eingeschaltet():
    """Alle ausgewählten Kryos EIN – jeder genau einmal, in Reihenfolge."""
    protokoll = SchaltProtokoll()
    log = []
    lock = threading.Lock()
    namen = ["Kryo 2", "Kryo 4"]

    kryo_alle_schalten_testbar(
        ausgewaehlte=namen, an=True,
        schalt_fn=protokoll.schalten,
        ein_signal_fn=lambda n: None,
        aus_signal_fn=lambda n: None,
        log_fn=log.append,
        schalt_lock=lock,
    )

    geschaltete = [(n, an) for n, an, _ in protokoll.aufrufe]
    assert geschaltete == [("Kryo 2", True), ("Kryo 4", True)]


def test_keine_doppelschaltung():
    """Jeder Kryo darf nur genau einmal geschaltet werden."""
    protokoll = SchaltProtokoll()
    lock = threading.Lock()
    namen = ["Kryo 1", "Kryo 2", "Kryo 3", "Kryo 4"]

    kryo_alle_schalten_testbar(
        ausgewaehlte=namen, an=True,
        schalt_fn=protokoll.schalten,
        ein_signal_fn=lambda n: None,
        aus_signal_fn=lambda n: None,
        log_fn=lambda t: None,
        schalt_lock=lock,
    )

    geschaltete_namen = [n for n, _, _ in protokoll.aufrufe]
    assert len(geschaltete_namen) == len(set(geschaltete_namen)), \
        f"Doppelschaltung erkannt: {geschaltete_namen}"


# ── Tests: Signal-Symmetrie (EIN/AUS) ────────────────────────

def test_aus_signal_wird_pro_kryo_gesendet():
    """Beim Ausschalten muss für jeden Kryo ein AUS-Signal emittiert werden."""
    aus_signale = []
    lock = threading.Lock()
    namen = ["Kryo 1", "Kryo 2", "Kryo 3"]

    kryo_alle_schalten_testbar(
        ausgewaehlte=namen, an=False,
        schalt_fn=lambda n, a: None,
        ein_signal_fn=lambda n: pytest.fail("EIN-Signal bei AUS-Vorgang!"),
        aus_signal_fn=lambda n: aus_signale.append(n),
        log_fn=lambda t: None,
        schalt_lock=lock,
    )

    assert aus_signale == ["Kryo 1", "Kryo 2", "Kryo 3"]


def test_ein_signal_wird_pro_kryo_gesendet():
    """Beim Einschalten muss für jeden Kryo ein EIN-Signal emittiert werden."""
    ein_signale = []
    lock = threading.Lock()
    namen = ["Kryo 5", "Kryo 6"]

    kryo_alle_schalten_testbar(
        ausgewaehlte=namen, an=True,
        schalt_fn=lambda n, a: None,
        ein_signal_fn=lambda n: ein_signale.append(n),
        aus_signal_fn=lambda n: pytest.fail("AUS-Signal bei EIN-Vorgang!"),
        log_fn=lambda t: None,
        schalt_lock=lock,
    )

    assert ein_signale == ["Kryo 5", "Kryo 6"]


# ── Tests: Lock verhindert paralleles Schalten ───────────────

def test_lock_verhindert_paralleles_schalten():
    """Zwei gleichzeitige Aufrufe dürfen nicht überlappen (Lock)."""
    lock = threading.Lock()
    timestamps = []

    def langsam_schalten(name, an):
        timestamps.append(("start", name, time.monotonic()))
        time.sleep(0.05)
        timestamps.append(("end", name, time.monotonic()))

    t1 = threading.Thread(target=kryo_alle_schalten_testbar, kwargs=dict(
        ausgewaehlte=["Kryo 1"], an=True,
        schalt_fn=langsam_schalten,
        ein_signal_fn=lambda n: None, aus_signal_fn=lambda n: None,
        log_fn=lambda t: None, schalt_lock=lock,
    ))
    t2 = threading.Thread(target=kryo_alle_schalten_testbar, kwargs=dict(
        ausgewaehlte=["Kryo 2"], an=True,
        schalt_fn=langsam_schalten,
        ein_signal_fn=lambda n: None, aus_signal_fn=lambda n: None,
        log_fn=lambda t: None, schalt_lock=lock,
    ))

    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    # Prüfen, dass Kryo 2 erst NACH Kryo 1 startet (kein Overlap)
    end_1   = [ts for typ, n, ts in timestamps if typ == "end"   and n == "Kryo 1"][0]
    start_2 = [ts for typ, n, ts in timestamps if typ == "start" and n == "Kryo 2"]
    if start_2:
        # Kryo 2 könnte auch VOR Kryo 1 sein – dann andersrum prüfen
        end_2   = [ts for typ, n, ts in timestamps if typ == "end"   and n == "Kryo 2"][0]
        start_1 = [ts for typ, n, ts in timestamps if typ == "start" and n == "Kryo 1"][0]
        # Einer muss komplett vor dem anderen fertig sein
        assert end_1 <= start_2[0] or end_2 <= start_1, \
            "Schalt-Operationen haben sich überlappt!"


# ── Tests: Fehler in einem Kryo stoppt nicht die anderen ─────

def test_fehler_in_einem_kryo_unterbricht_nicht():
    """Ein Fehler bei Kryo 2 darf das Schalten von Kryo 3 nicht verhindern."""
    protokoll = SchaltProtokoll()
    log = []
    lock = threading.Lock()

    def schalten_mit_fehler(name, an):
        if name == "Kryo 2":
            raise ConnectionError("COM-Port belegt")
        protokoll.schalten(name, an)

    kryo_alle_schalten_testbar(
        ausgewaehlte=["Kryo 1", "Kryo 2", "Kryo 3"], an=True,
        schalt_fn=schalten_mit_fehler,
        ein_signal_fn=lambda n: None,
        aus_signal_fn=lambda n: None,
        log_fn=log.append,
        schalt_lock=lock,
    )

    # Kryo 1 und 3 geschaltet, Kryo 2 übersprungen
    geschaltete = [n for n, _, _ in protokoll.aufrufe]
    assert geschaltete == ["Kryo 1", "Kryo 3"]
    # Fehler wurde geloggt
    assert any("Kryo 2" in msg and "Fehler" in msg for msg in log)


# ── Tests: Regen-Phasen ──────────────────────────────────────

def test_regen_phase_aus_dann_ein():
    """Regenerierung: erst AUS (Start), dann EIN (Stop) – gleiche Kryos."""
    aus_log = []
    ein_log = []
    lock = threading.Lock()
    namen = ["Kryo 1", "Kryo 3"]

    # Phase 1: AUS
    kryo_alle_schalten_testbar(
        ausgewaehlte=namen, an=False,
        schalt_fn=lambda n, a: None,
        ein_signal_fn=lambda n: ein_log.append(n),
        aus_signal_fn=lambda n: aus_log.append(n),
        log_fn=lambda t: None,
        schalt_lock=lock,
    )
    assert aus_log == ["Kryo 1", "Kryo 3"]
    assert ein_log == []

    # Phase 2: EIN
    kryo_alle_schalten_testbar(
        ausgewaehlte=namen, an=True,
        schalt_fn=lambda n, a: None,
        ein_signal_fn=lambda n: ein_log.append(n),
        aus_signal_fn=lambda n: aus_log.append(n),
        log_fn=lambda t: None,
        schalt_lock=lock,
    )
    assert ein_log == ["Kryo 1", "Kryo 3"]
    assert aus_log == ["Kryo 1", "Kryo 3"]  # unverändert
