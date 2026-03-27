"""Tests für log_utils.tprint und steckdose._fehler_klasse."""

import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── tprint ───────────────────────────────────────────────────────
class TestTprint:
    def test_format_hat_zeitstempel(self, capsys):
        from log_utils import tprint
        tprint("TestTag", "Hallo Welt")
        out = capsys.readouterr().out.strip()
        # Format: DD.MM.YYYY HH:MM:SS [TestTag] Hallo Welt
        assert re.match(r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2}", out)

    def test_format_enthaelt_tag(self, capsys):
        from log_utils import tprint
        tprint("Sensor", "Messwert ok")
        out = capsys.readouterr().out.strip()
        assert "[Sensor]" in out

    def test_format_enthaelt_nachricht(self, capsys):
        from log_utils import tprint
        tprint("X", "foo bar")
        out = capsys.readouterr().out.strip()
        assert out.endswith("foo bar")


# ── _fehler_klasse ───────────────────────────────────────────────
class TestFehlerKlasse:
    def test_win10061(self):
        from hardware.steckdose import _fehler_klasse
        e = OSError("[WinError 10061] Es konnte keine Verbindung hergestellt werden")
        assert "verweigert" in _fehler_klasse(e).lower()

    def test_timeout(self):
        from hardware.steckdose import _fehler_klasse
        e = TimeoutError("timed out")
        assert "zeit" in _fehler_klasse(e).lower()

    def test_unbekannt(self):
        from hardware.steckdose import _fehler_klasse
        e = RuntimeError("etwas anderes")
        result = _fehler_klasse(e)
        assert "Netzwerkfehler" in result


# ── Zustandswechsel-Logging Steckdose ────────────────────────────
class TestSteckdoseZustandswechsel:
    """Prüft, dass Fehler nur beim Übergang Online→Offline geloggt werden."""

    def test_erster_fehler_loggt(self, capsys, monkeypatch):
        from hardware.steckdose import Steckdose, _get
        monkeypatch.setattr("hardware.steckdose._get",
                            lambda url, timeout: (_ for _ in ()).throw(OSError("timed out")))
        s = Steckdose()
        s.status_alle()
        out = capsys.readouterr().out
        assert "Offline" in out

    def test_zweiter_fehler_schweigt(self, capsys, monkeypatch):
        from hardware.steckdose import Steckdose
        monkeypatch.setattr("hardware.steckdose._get",
                            lambda url, timeout: (_ for _ in ()).throw(OSError("timed out")))
        s = Steckdose()
        s.status_alle()  # erster → loggt
        capsys.readouterr()  # leeren
        s.status_alle()  # zweiter → schweigt
        out = capsys.readouterr().out
        assert out.strip() == ""

    def test_wiederherstellung_loggt(self, capsys, monkeypatch):
        from hardware.steckdose import Steckdose
        aufrufe = [0]

        def fake_get(url, timeout):
            aufrufe[0] += 1
            if aufrufe[0] <= 1:
                raise OSError("timed out")
            return "<xml><actor><id>1</id><state>0</state></actor></xml>"

        monkeypatch.setattr("hardware.steckdose._get", fake_get)
        s = Steckdose()
        s.status_alle()  # Fehler
        capsys.readouterr()
        s.status_alle()  # Wiederherstellung
        out = capsys.readouterr().out
        assert "wiederhergestellt" in out.lower()
