"""
Tests: Druck-Kalibrierung außerhalb des Kalibrierbereichs (Variante 2) und
Umschalter kalibriert/unkalibriert im Druck-Panel/Großanzeige.

  unterhalb des Bereichs → Korrekturfaktor des untersten Punkts konstant
  oberhalb des Bereichs  → unkalibrierter Rohwert
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from daten.kalibrierung import Kalibrierung


@pytest.fixture
def kurve(tmp_path):
    datei = tmp_path / "TEST_1.csv"
    datei.write_text(
        "# Zertifikat: 1\nMesswert_mbar,Wahrer_Wert_mbar\n"
        "1.0E-6,2.0E-7\n"      # unterster Punkt: Faktor 0.2
        "1.0E-4,0.5E-4\n"
        "1.0E-2,1.2E-2\n",     # oberster Punkt: Faktor 1.2
        encoding="utf-8")
    return Kalibrierung("TEST", str(datei))


def test_innerhalb_unveraendert_interpoliert(kurve):
    assert kurve.korrigiere(1.0E-4) == pytest.approx(0.5E-4)
    assert kurve.korrigiere(1.0E-6) == pytest.approx(2.0E-7)
    assert kurve.korrigiere(1.0E-2) == pytest.approx(1.2E-2)
    assert kurve.bereich_status(1.0E-4) == "innen"


def test_unterhalb_konstanter_randfaktor(kurve):
    for x in (9.9E-7, 1.0E-8, 1.0E-10):
        assert kurve.korrigiere(x) == pytest.approx(x * 0.2)
    assert kurve.bereich_status(1.0E-8) == "unten"


def test_unterhalb_stetig_am_rand(kurve):
    assert kurve.korrigiere(0.9999E-6) == pytest.approx(kurve.korrigiere(1.0E-6), rel=1e-3)


def test_oberhalb_rohwert(kurve):
    for x in (1.01E-2, 1.0, 1000.0):
        assert kurve.korrigiere(x) == x
    assert kurve.bereich_status(1000.0) == "oben"


def test_keine_explosion_bei_echter_ba_kurve():
    """Früher: BA bei 1000 mbar → 135 bar (log-lineare Extrapolation)."""
    from daten.kalibrierung import KalibrierManager
    km = KalibrierManager()
    if not km.hat_kalibrierung("BA"):
        pytest.skip("keine BA-Kalibrierung vorhanden")
    assert km.korrigiere("BA", 1000.0) == 1000.0
    assert km.korrigiere("BA", 13.0) == 13.0
    tief = km.korrigiere("BA", 1e-8)
    p0 = km._kurven["BA"].punkte[0]
    assert tief == pytest.approx(1e-8 * p0[1] / p0[0])


# ── Druck-Panel / Großanzeige ─────────────────────────────────

@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _werte(mbar):
    return {n: {"mbar": mbar, "gueltig": True, "status": "OK"}
            for n in ("CENTER", "DOOR", "BA")}


def test_druck_panel_standard_kalibriert_und_umschalten(qapp):
    from gui.druck_panel import DruckPanel, kalibrierter_druck
    p = DruckPanel()
    assert p.kalibriert is True
    p.aktualisieren(_werte(2e-6))
    lbl, st, _, _ = p._anzeigen["DOOR"]
    assert lbl.text() == f"{kalibrierter_druck('DOOR', 2e-6):.2E}"
    assert "kal." in st.text()
    assert "unkal." in p._anzeigen["CENTER"][1].text()   # CENTER ohne Kalibrierung

    modi = []
    p.kalib_modus_geaendert.connect(modi.append)
    p._cmb_kalib.setCurrentIndex(1)
    assert modi == [False]
    assert lbl.text() == "2.00E-06" and st.text() == "mbar"
    # PDF-Daten bleiben Rohwerte
    assert p.get_tages_daten()["door"][-1] == pytest.approx(2e-6 * 100)


def test_druck_panel_kennzeichnet_bereich(qapp):
    from gui.druck_panel import DruckPanel, hat_druck_kalibrierung
    if not hat_druck_kalibrierung("BA"):
        pytest.skip("keine BA-Kalibrierung vorhanden")
    p = DruckPanel()
    p.aktualisieren(_werte(13.0))
    assert p._anzeigen["BA"][0].text() == "1.30E+01"       # Rohwert, kein 300 mbar
    assert "unkal." in p._anzeigen["BA"][1].text()
    p.aktualisieren(_werte(1e-8))
    assert "Randfaktor" in p._anzeigen["BA"][1].text()


def test_grossanzeige_folgt_modus(qapp):
    from gui.druck_grossanzeige import DruckGrossanzeige
    from gui.druck_panel import kalibrierter_druck
    g = DruckGrossanzeige()
    g.aktualisieren(_werte(2e-6))
    wert, st, _ = g._anzeigen["DOOR"]
    assert wert.text() == f"{kalibrierter_druck('DOOR', 2e-6):.2E}"
    g.set_kalibriert(False)
    assert wert.text() == "2.00E-06" and st.text() == "mbar"
