"""Tests für pdf_report Hilfsfunktionen."""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gui.pdf_report import (
    _datum_zu_mjd, _stunden_achse, _bereinige_druck,
    _zeitbasis_label, _druck_ylim, OVERRANGE_PA,
)
from datetime import datetime, timezone


# ── _zeitbasis_label ─────────────────────────────────────────────
class TestZeitbasisLabel:
    def test_enthaelt_zeitbasis(self):
        label = _zeitbasis_label()
        assert "Zeitbasis" in label

    def test_enthaelt_lokalzeit(self):
        label = _zeitbasis_label()
        assert "Lokalzeit" in label

    def test_enthaelt_utc_offset(self):
        label = _zeitbasis_label()
        assert "UTC" in label


# ── _druck_ylim ──────────────────────────────────────────────────
class TestDruckYlim:
    def test_fallback_ohne_daten(self):
        ymin, ymax = _druck_ylim([])
        assert ymin == 1e-5
        assert ymax == 1e-1

    def test_fallback_bei_leeren_arrays(self):
        ymin, ymax = _druck_ylim([np.array([])])
        assert ymin == 1e-5
        assert ymax == 1e-1

    def test_fallback_bei_nur_overrange(self):
        arr = np.array([OVERRANGE_PA, OVERRANGE_PA])
        ymin, ymax = _druck_ylim([arr])
        assert ymin == 1e-5
        assert ymax == 1e-1

    def test_bereich_umschliesst_daten(self):
        arr = np.array([1e-3, 1e-2, 5e-2])
        ymin, ymax = _druck_ylim([arr])
        assert ymin < 1e-3, f"ymin={ymin} sollte < 1e-3 sein"
        assert ymax > 5e-2, f"ymax={ymax} sollte > 5e-2 sein"

    def test_mehrere_arrays(self):
        a1 = np.array([1e-6, 1e-5])
        a2 = np.array([1e-1, 1e0])
        ymin, ymax = _druck_ylim([a1, a2])
        assert ymin < 1e-6
        assert ymax > 1e0

    def test_ignoriert_overrange_werte(self):
        arr = np.array([1e-4, OVERRANGE_PA, 1e-3])
        ymin, ymax = _druck_ylim([arr])
        assert ymin < 1e-4
        assert ymax < OVERRANGE_PA

    def test_ignoriert_none_arrays(self):
        ymin, ymax = _druck_ylim([None, np.array([1e-3])])
        assert ymin < 1e-3
        assert ymax > 1e-3

    def test_einzelner_wert(self):
        arr = np.array([5e-4])
        ymin, ymax = _druck_ylim([arr])
        assert ymin < 5e-4
        assert ymax > 5e-4

    def test_hohe_druecke(self):
        """Bei frisch belüfteter Kammer (hoher Druck) soll nichts abgeschnitten werden."""
        arr = np.array([1e2, 5e3, 1e4])
        ymin, ymax = _druck_ylim([arr])
        assert ymin < 1e2
        assert ymax > 1e4


# ── _datum_zu_mjd ────────────────────────────────────────────────
class TestDatumZuMjd:
    def test_bekannter_mjd(self):
        # 2000-01-01 12:00 UTC = MJD 51544
        dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert _datum_zu_mjd(dt) == 51544

    def test_naive_datetime(self):
        dt = datetime(2000, 1, 1, 12, 0, 0)
        assert _datum_zu_mjd(dt) == 51544


# ── _stunden_achse ───────────────────────────────────────────────
class TestStundenAchse:
    def test_mitternacht_ist_null(self):
        tag = datetime(2026, 3, 27).timestamp()
        result = _stunden_achse([tag], tag)
        assert abs(result[0]) < 1e-9

    def test_mittag_ist_zwoelf(self):
        tag = datetime(2026, 3, 27).timestamp()
        mittag = tag + 12 * 3600
        result = _stunden_achse([mittag], tag)
        assert abs(result[0] - 12.0) < 1e-9


# ── _bereinige_druck ─────────────────────────────────────────────
class TestBereinigeDruck:
    def test_none_wird_overrange(self):
        result = _bereinige_druck([1.0, None, 3.0])
        assert result[1] == OVERRANGE_PA

    def test_nan_wird_overrange(self):
        result = _bereinige_druck([float("nan")])
        assert result[0] == OVERRANGE_PA

    def test_normale_werte_bleiben(self):
        result = _bereinige_druck([1.5, 2.5])
        np.testing.assert_array_almost_equal(result, [1.5, 2.5])
