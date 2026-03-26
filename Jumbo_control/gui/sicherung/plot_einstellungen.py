"""
gui/plot_einstellungen.py
Einstellungsfenster für Druckplot und Temperaturplot.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QLineEdit, QComboBox, QPushButton,
    QGroupBox, QGridLayout
)
from PyQt6.QtCore import Qt


class PlotEinstellungenDialog(QDialog):
    """
    Modales Einstellungsfenster für einen Matplotlib-Plot.
    Unterstützt: Achsengrenzen, Gitter, Skala, Datenpunkte.
    """

    def __init__(self, ax, canvas, fig, titel="Plot-Einstellungen", hat_skala=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titel)
        self.setMinimumWidth(300)
        self._ax     = ax
        self._canvas = canvas
        self._fig    = fig

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Achsengrenzen Y ───────────────────────────────────
        y_box = QGroupBox("Y-Achse")
        y_layout = QGridLayout(y_box)

        self._chk_auto_y = QCheckBox("Auto")
        self._chk_auto_y.setChecked(True)
        self._chk_auto_y.stateChanged.connect(self._on_auto_y)
        y_layout.addWidget(self._chk_auto_y, 0, 0, 1, 2)

        y_layout.addWidget(QLabel("Min:"), 1, 0)
        self._lne_ymin = QLineEdit()
        self._lne_ymin.setPlaceholderText("z.B. 1e-8 oder -300")
        self._lne_ymin.setEnabled(False)
        y_layout.addWidget(self._lne_ymin, 1, 1)

        y_layout.addWidget(QLabel("Max:"), 2, 0)
        self._lne_ymax = QLineEdit()
        self._lne_ymax.setPlaceholderText("z.B. 1e-2 oder 50")
        self._lne_ymax.setEnabled(False)
        y_layout.addWidget(self._lne_ymax, 2, 1)

        btn_apply_y = QPushButton("Übernehmen")
        btn_apply_y.clicked.connect(self._apply_y)
        y_layout.addWidget(btn_apply_y, 3, 0, 1, 2)
        layout.addWidget(y_box)

        # ── Skala ─────────────────────────────────────────────
        if hat_skala:
            skala_box = QGroupBox("Y-Skala")
            skala_layout = QHBoxLayout(skala_box)
            skala_layout.addWidget(QLabel("Skala:"))
            self._cmb_skala = QComboBox()
            self._cmb_skala.addItems(["Log", "Linear"])
            # Aktuellen Zustand setzen
            if ax.get_yscale() == "linear":
                self._cmb_skala.setCurrentIndex(1)
            self._cmb_skala.currentIndexChanged.connect(self._apply_skala)
            skala_layout.addWidget(self._cmb_skala)
            layout.addWidget(skala_box)

        # ── Gitter ────────────────────────────────────────────
        grid_box = QGroupBox("Gitterlinien")
        grid_layout = QHBoxLayout(grid_box)
        grid_layout.addWidget(QLabel("Gitter:"))
        self._cmb_grid = QComboBox()
        self._cmb_grid.addItems(["Fein (major+minor)", "Grob (major)", "Aus"])
        self._cmb_grid.currentIndexChanged.connect(self._apply_grid)
        grid_layout.addWidget(self._cmb_grid)
        layout.addWidget(grid_box)

        # ── Datenpunkte ───────────────────────────────────────
        marker_box = QGroupBox("Datenpunkte")
        marker_layout = QHBoxLayout(marker_box)
        self._chk_marker = QCheckBox("Datenpunkte anzeigen")
        self._chk_marker.stateChanged.connect(self._apply_marker)
        marker_layout.addWidget(self._chk_marker)
        layout.addWidget(marker_box)

        # ── Schließen ─────────────────────────────────────────
        btn_close = QPushButton("Schließen")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

        # Aktuelle Y-Grenzen eintragen
        try:
            ymin, ymax = ax.get_ylim()
            self._lne_ymin.setText(f"{ymin:.2E}")
            self._lne_ymax.setText(f"{ymax:.2E}")
        except Exception:
            pass

    def _on_auto_y(self, state: int):
        self._lne_ymin.setEnabled(not state)
        self._lne_ymax.setEnabled(not state)
        if state:
            self._ax.autoscale(axis="y")
            self._canvas.draw_idle()

    def _apply_y(self):
        if self._chk_auto_y.isChecked():
            return
        try:
            ymin = float(self._lne_ymin.text())
            ymax = float(self._lne_ymax.text())
            if ymax > ymin:
                self._ax.set_ylim(ymin, ymax)
                self._lne_ymin.setStyleSheet("")
                self._lne_ymax.setStyleSheet("")
                self._canvas.draw_idle()
            else:
                self._lne_ymin.setStyleSheet("border: 1px solid red;")
        except ValueError:
            self._lne_ymin.setStyleSheet("border: 1px solid red;")

    def _apply_skala(self, idx: int):
        self._ax.set_yscale("log" if idx == 0 else "linear")
        self._canvas.draw_idle()

    def _apply_grid(self, idx: int):
        self._ax.grid(False, which="both")
        if idx == 0:
            self._ax.grid(True, which="major", alpha=0.4)
            self._ax.grid(True, which="minor", alpha=0.15)
        elif idx == 1:
            self._ax.grid(True, which="major", alpha=0.4)
        self._canvas.draw_idle()

    def _apply_marker(self, state: int):
        marker = "o" if state else "None"
        for line in self._ax.get_lines():
            if line.get_label().startswith("_"):
                continue
            line.set_marker(marker)
            line.set_markersize(3)
        self._canvas.draw_idle()
