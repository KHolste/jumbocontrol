"""
gui/adaptiv_dialog.py
Konfigurationsdialog für den adaptiven Aufnahme-Modus.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QSpinBox, QGroupBox, QGridLayout,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt


class AdaptivDialog(QDialog):
    """Dialog zur Konfiguration der adaptiven Datenaufnahme.

    Parameter:
        temp_schwelle_pct  – Änderungsschwelle Temperatur in %
        druck_schwelle_pct – Änderungsschwelle Druck in %
        vergleichs_n       – Anzahl Vergleichswerte (1 = letzter Wert)
        max_stille_s       – Erzwungener Punkt nach N Sekunden (max 60)
    """

    def __init__(self, parent=None, *,
                 temp_schwelle_pct=1.0,
                 druck_schwelle_pct=5.0,
                 vergleichs_n=1,
                 max_stille_s=30.0):
        super().__init__(parent)
        self.setWindowTitle("Adaptiver Modus – Einstellungen")
        self.setMinimumWidth(340)
        self._build_ui(temp_schwelle_pct, druck_schwelle_pct,
                       vergleichs_n, max_stille_s)

    def _build_ui(self, temp_pct, druck_pct, vgl_n, stille_s):
        layout = QVBoxLayout(self)

        # ── Schwellenwerte ──────────────────────────────────
        grp = QGroupBox("Änderungsschwelle")
        grid = QGridLayout(grp)

        grid.addWidget(QLabel("Temperatur (%):"), 0, 0)
        self.sp_temp = QDoubleSpinBox()
        self.sp_temp.setRange(0.01, 50.0)
        self.sp_temp.setDecimals(2)
        self.sp_temp.setSingleStep(0.5)
        self.sp_temp.setValue(temp_pct)
        self.sp_temp.setToolTip("Prozentuale Änderung zum Referenzwert")
        grid.addWidget(self.sp_temp, 0, 1)

        grid.addWidget(QLabel("Druck (%):"), 1, 0)
        self.sp_druck = QDoubleSpinBox()
        self.sp_druck.setRange(0.01, 50.0)
        self.sp_druck.setDecimals(2)
        self.sp_druck.setSingleStep(1.0)
        self.sp_druck.setValue(druck_pct)
        self.sp_druck.setToolTip("Prozentuale Änderung zum Referenzwert")
        grid.addWidget(self.sp_druck, 1, 1)

        layout.addWidget(grp)

        # ── Vergleichsbasis ─────────────────────────────────
        grp2 = QGroupBox("Vergleichsbasis")
        row = QHBoxLayout(grp2)
        row.addWidget(QLabel("Letzte N Werte:"))
        self.sp_n = QSpinBox()
        self.sp_n.setRange(1, 10)
        self.sp_n.setValue(vgl_n)
        self.sp_n.setToolTip("1 = Vergleich mit letztem Wert, >1 = Mittelwert")
        row.addWidget(self.sp_n)
        layout.addWidget(grp2)

        # ── Maximale Stillezeit ─────────────────────────────
        grp3 = QGroupBox("Erzwungener Messpunkt")
        row2 = QHBoxLayout(grp3)
        row2.addWidget(QLabel("Max. Stillezeit (s):"))
        self.sp_stille = QDoubleSpinBox()
        self.sp_stille.setRange(1.0, 60.0)
        self.sp_stille.setDecimals(1)
        self.sp_stille.setSingleStep(5.0)
        self.sp_stille.setValue(min(stille_s, 60.0))
        self.sp_stille.setToolTip("Spätestens nach dieser Zeit wird ein Punkt geschrieben")
        row2.addWidget(self.sp_stille)
        layout.addWidget(grp3)

        # ── Buttons ─────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── Ergebnis auslesen ───────────────────────────────────
    def ergebnis(self) -> dict:
        return {
            "temp_schwelle_pct":  self.sp_temp.value(),
            "druck_schwelle_pct": self.sp_druck.value(),
            "vergleichs_n":       self.sp_n.value(),
            "max_stille_s":       min(self.sp_stille.value(), 60.0),
        }
