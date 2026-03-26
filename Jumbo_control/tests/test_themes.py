"""
Tests für gui/themes.py – Theme-Konsistenz ohne Qt.

Prüft, dass beide Themes vollständige Schlüssel haben,
build_stylesheet() keine Fehler wirft und alle kritischen
Widget-Selektoren vorhanden sind.
"""
import pytest
from gui.themes import DARK_THEME, LIGHT_THEME, build_stylesheet


PFLICHT_KEYS = [
    "bg", "panel", "card", "border", "border2",
    "accent", "accent2", "accent3", "danger",
    "text", "text_sec", "text_dim",
    "log_info", "log_ok", "log_warn", "log_err", "log_stamp",
]


# ── Theme-Struktur ────────────────────────────────────────────

def test_dark_theme_hat_alle_keys():
    for key in PFLICHT_KEYS:
        assert key in DARK_THEME, f"DARK_THEME: Key '{key}' fehlt"


def test_light_theme_hat_alle_keys():
    for key in LIGHT_THEME:
        assert key in LIGHT_THEME, f"LIGHT_THEME: Key '{key}' fehlt"


def test_themes_haben_gleiche_keys():
    assert set(DARK_THEME.keys()) == set(LIGHT_THEME.keys())


# ── Stylesheet-Generierung ────────────────────────────────────

def test_build_stylesheet_dark_erzeugt_string():
    css = build_stylesheet(DARK_THEME)
    assert isinstance(css, str)
    assert len(css) > 500


def test_build_stylesheet_light_erzeugt_string():
    css = build_stylesheet(LIGHT_THEME)
    assert isinstance(css, str)
    assert len(css) > 500


# ── Kritische Widget-Selektoren vorhanden ─────────────────────

KRITISCHE_SELEKTOREN = [
    "QCheckBox::indicator",
    "QCheckBox::indicator:checked",
    "QRadioButton::indicator",
    "QRadioButton::indicator:checked",
    "QSpinBox::up-button",
    "QSpinBox::down-button",
    "QSpinBox::up-arrow",
    "QSpinBox::down-arrow",
    "QComboBox::drop-down",
    "QComboBox::down-arrow",
    "QGroupBox",
    "QGroupBox::title",
    "QScrollBar:vertical",
    "QScrollBar::handle:vertical",
    "QScrollBar:horizontal",
    "QToolTip",
    "QSplitter::handle",
]


@pytest.mark.parametrize("selektor", KRITISCHE_SELEKTOREN)
def test_dark_stylesheet_enthaelt_selektor(selektor):
    css = build_stylesheet(DARK_THEME)
    assert selektor in css, f"Selektor '{selektor}' fehlt im Dark-Stylesheet"


@pytest.mark.parametrize("selektor", KRITISCHE_SELEKTOREN)
def test_light_stylesheet_enthaelt_selektor(selektor):
    css = build_stylesheet(LIGHT_THEME)
    assert selektor in css, f"Selektor '{selektor}' fehlt im Light-Stylesheet"


# ── Kontrast-Plausibilität ────────────────────────────────────

def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _relative_luminance(r, g, b) -> float:
    """WCAG 2.0 relative Luminanz."""
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = _relative_luminance(*_hex_to_rgb(hex1))
    l2 = _relative_luminance(*_hex_to_rgb(hex2))
    lighter = max(l1, l2)
    darker  = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def test_dark_text_auf_bg_kontrast():
    """WCAG AA: Text auf Hintergrund muss Kontrastverhältnis ≥ 4.5:1 haben."""
    ratio = _contrast_ratio(DARK_THEME["text"], DARK_THEME["bg"])
    assert ratio >= 4.5, f"Dark text/bg Kontrast nur {ratio:.1f}:1"


def test_light_text_auf_bg_kontrast():
    ratio = _contrast_ratio(LIGHT_THEME["text"], LIGHT_THEME["bg"])
    assert ratio >= 4.5, f"Light text/bg Kontrast nur {ratio:.1f}:1"


def test_dark_accent_auf_card_kontrast():
    """Akzentfarbe auf Card muss mindestens 3:1 erreichen (WCAG AA für große Elemente)."""
    ratio = _contrast_ratio(DARK_THEME["accent"], DARK_THEME["card"])
    assert ratio >= 3.0, f"Dark accent/card Kontrast nur {ratio:.1f}:1"


def test_light_accent_auf_card_kontrast():
    ratio = _contrast_ratio(LIGHT_THEME["accent"], LIGHT_THEME["card"])
    assert ratio >= 3.0, f"Light accent/card Kontrast nur {ratio:.1f}:1"
