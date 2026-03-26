"""
gui/druck_grossanzeige.py
Großanzeige für die drei Live-Druckwerte CENTER, DOOR, BA.

Separates Fenster – Schließen versteckt nur (bewahrt Zustand).
Font-Größe zur Laufzeit per +/- einstellbar.
Hängt am selben neue_druecke-Signal wie DruckPanel – keine duplizierte Messlogik.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
)
from PyQt6.QtCore import Qt

SENSOR_FARBEN = {"CENTER": "#e63946", "DOOR": "#f4a261", "BA": "#2a9d8f"}

_FONT_MIN  = 28
_FONT_MAX  = 120
_FONT_STEP = 8
_FONT_DEF  = 64


def format_druck_wert(d: dict) -> tuple[str, str]:
    """
    Gibt (wert_text, status_text) für einen Sensor-Dict zurück.
    Reine Logikfunktion, kein Qt nötig – direkt testbar.

    d = {"mbar": float|None, "gueltig": bool, "status": str, ...}
    """
    if not d:
        return "---", ""
    val    = d.get("mbar") if d.get("gueltig") else None
    status = d.get("status", "")
    if val is not None:
        return f"{val:.2E}", "mbar"
    if status:
        return status[:14], ""
    return "---", ""


class DruckGrossanzeige(QWidget):
    """Standalone-Fenster mit großen Live-Druckwerten."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Jumbo Control – Druckwerte Großanzeige")
        self.resize(500, 420)
        self._font_size = _FONT_DEF
        self._anzeigen  = {}   # name → (wert_lbl, status_lbl, farbe)
        self._build_ui()
        # Theme-Farben aus themes.py übernehmen
        from gui.themes import DARK_THEME
        self.setStyleSheet(
            f"background: {DARK_THEME['bg']}; color: {DARK_THEME['text']};"
        )

    # ── UI ────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Schriftgröße-Steuerung
        ctrl = QHBoxLayout()
        ctrl.addStretch()
        hint = QLabel("Schriftgröße:")
        hint.setStyleSheet("color: #a0a8c0; font-size: 11px;")
        ctrl.addWidget(hint)
        for symbol, delta in (("−", -_FONT_STEP), ("+", +_FONT_STEP)):
            btn = QPushButton(symbol)
            btn.setFixedSize(30, 30)
            btn.setStyleSheet("""
                QPushButton {
                    background: #1e2d45; border: 1px solid #4a5e80;
                    border-radius: 5px; color: #cbd5e1;
                    font-size: 18px; font-weight: 700;
                }
                QPushButton:hover { background: #2a3f5f; color: #fff; }
            """)
            btn.clicked.connect(lambda _, d=delta: self._aender_font(d))
            ctrl.addWidget(btn)
        root.addLayout(ctrl)

        # Sensor-Kacheln
        for name, farbe in SENSOR_FARBEN.items():
            box = QGroupBox(name)
            box.setStyleSheet(f"""
                QGroupBox {{
                    font-size: 13px; font-weight: bold; color: {farbe};
                    border: none;
                    border-top: 3px solid {farbe};
                    border-left: 1px solid {farbe}33;
                    border-radius: 3px;
                    margin-top: 14px; padding-top: 8px;
                    background: #1b253899;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin; left: 8px; color: {farbe};
                }}
            """)
            b_layout = QVBoxLayout(box)
            b_layout.setContentsMargins(8, 6, 8, 8)

            wert_lbl = QLabel("---")
            wert_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._stil_wert(wert_lbl, farbe)

            status_lbl = QLabel("")
            status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_lbl.setStyleSheet(
                "font-size: 11px; color: #a0a8c0; "
                "background: transparent; font-weight: 600;"
            )
            b_layout.addWidget(wert_lbl)
            b_layout.addWidget(status_lbl)
            self._anzeigen[name] = (wert_lbl, status_lbl, farbe)
            root.addWidget(box)

    def _stil_wert(self, lbl: QLabel, farbe: str):
        lbl.setStyleSheet(
            f"font-family: 'Consolas','Courier New'; "
            f"font-size: {self._font_size}px; "
            f"font-weight: bold; color: {farbe}; background: transparent;"
        )

    # ── Font-Größe ändern ─────────────────────────────────────
    def _aender_font(self, delta: int):
        self._font_size = max(_FONT_MIN, min(_FONT_MAX, self._font_size + delta))
        for name, (wert_lbl, _, farbe) in self._anzeigen.items():
            self._stil_wert(wert_lbl, farbe)

    # ── Fenster-Verhalten ─────────────────────────────────────
    def closeEvent(self, event):
        """Versteckt statt schließen – Zustand und Signal-Verbindung bleiben."""
        event.ignore()
        self.hide()

    # ── Daten-Update (gleiche Signatur wie DruckPanel.aktualisieren) ──
    def aktualisieren(self, werte: dict):
        # CENT → CENTER normalisieren (kommt selten vor, aber sicher)
        if "CENT" in werte and "CENTER" not in werte:
            werte = {**werte, "CENTER": werte["CENT"]}

        for name, (wert_lbl, status_lbl, _) in self._anzeigen.items():
            text, einheit = format_druck_wert(werte.get(name, {}))
            wert_lbl.setText(text)
            status_lbl.setText(einheit)
