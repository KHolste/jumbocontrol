"""
Regressionstests für gui/tcp_server.py.

Wichtigster Test: Bug #2 (CENT/CENTER-Key-Mismatch im LogDataString).
DruckMessung.messen() liefert {"CENTER": ...}, _build_log_string() suchte
früher nach "CENT" → "P Center,NaN" ging über die Leitung → der
Datengrabber-PC interpretierte das als OVERRANGE. Das ist der gleiche
Bug-Typ wie Bug #1 in daten/csv_schreiber.py (siehe test_csv_schreiber.py).
"""
import pytest
from gui.tcp_server import TcpMessServer


# ── Hilfsfunktion ─────────────────────────────────────────────

def _parse_logstring(s: str) -> dict:
    """Zerlegt 'P Door,1.23E-6;P Center,NaN;...' in {feldname: rohwert}."""
    out = {}
    for item in s.split(";"):
        if "," not in item:
            continue
        key, val = item.split(",", 1)
        out[key.strip()] = val.strip()
    return out


def _vollstaendige_druckwerte():
    return {
        "DOOR":   {"mbar": 7.43e-6, "gueltig": True,  "status": "OK"},
        "CENTER": {"mbar": 5.96e-6, "gueltig": True,  "status": "OK"},
        "BA":     {"mbar": 1.05e-5, "gueltig": True,  "status": "OK"},
    }


# ── Regressionstests CENT/CENTER ──────────────────────────────

def test_center_wert_gelangt_in_logstring():
    """
    Regressionstest Bug #2:
    DruckMessung.messen() liefert Key "CENTER" – _build_log_string()
    muss diesen finden und als Zahl in 'P Center' schreiben.
    Vor dem Fix: druck.get("CENT") → None → 'P Center,NaN' → Grabber
    zeigte OVERRANGE.
    """
    srv = TcpMessServer()
    srv.update_druck(_vollstaendige_druckwerte())

    felder = _parse_logstring(srv._build_log_string())

    assert felder["P Center"] != "NaN", (
        "CENTER-Wert als NaN gesendet – CENT/CENTER-Key-Mismatch nicht behoben"
    )
    assert float(felder["P Center"]) == pytest.approx(5.96e-6, rel=1e-3)


def test_door_und_ba_unveraendert():
    """DOOR und BA hatten keinen Namens-Mismatch – müssen weiter korrekt sein."""
    srv = TcpMessServer()
    srv.update_druck(_vollstaendige_druckwerte())

    felder = _parse_logstring(srv._build_log_string())

    assert float(felder["P Door"]) == pytest.approx(7.43e-6, rel=1e-3)
    assert float(felder["P BA"])   == pytest.approx(1.05e-5, rel=1e-3)


def test_ungueltige_drucksensoren_werden_nan():
    """gueltig=False oder mbar=None → 'NaN' im LogDataString."""
    srv = TcpMessServer()
    srv.update_druck({
        "DOOR":   {"mbar": None, "gueltig": False, "status": "No sensor"},
        "CENTER": {"mbar": None, "gueltig": False, "status": "Sensor error"},
        "BA":     {"mbar": None, "gueltig": False, "status": "Sensor off"},
    })

    felder = _parse_logstring(srv._build_log_string())

    for feld in ("P Door", "P Center", "P BA"):
        assert felder[feld] == "NaN", f"{feld}: erwartet NaN, got '{felder[feld]}'"


def test_logstring_enthaelt_alle_druckfelder():
    """Auch ohne update_druck() müssen alle drei Druckfelder im String stehen."""
    srv = TcpMessServer()
    # bewusst kein update_druck() – Snapshot ist leer

    felder = _parse_logstring(srv._build_log_string())

    for feld in ("P Door", "P Center", "P BA"):
        assert feld in felder, f"Pflichtfeld '{feld}' fehlt im LogDataString"
        assert felder[feld] == "NaN"
