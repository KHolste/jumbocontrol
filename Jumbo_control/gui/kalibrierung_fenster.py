"""
gui/kalibrierung_fenster.py
Separates Fenster für kalibrierte Druckwerte mit erweiterten Plot-Optionen.
"""

from collections import deque
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QGroupBox,
    QSizePolicy, QHeaderView, QCheckBox, QPushButton,
    QDoubleSpinBox, QComboBox, QColorDialog, QScrollArea, QLineEdit,
    QFrame, QGridLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

import matplotlib
matplotlib.use("QtAgg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavToolbar
from matplotlib.figure import Figure

from daten.kalibrierung import KalibrierManager
from gui.themes import DARK_THEME, build_stylesheet, matplotlib_toolbar_style

SENSOREN = ["CENTER", "DOOR", "BA"]
FARBEN_DEFAULT = {
    "CENTER_roh":  "#ff6b6b",
    "CENTER_kal":  "#e63946",
    "DOOR_roh":    "#ffd166",
    "DOOR_kal":    "#f4a261",
    "BA_roh":      "#06d6a0",
    "BA_kal":      "#2a9d8f",
}
HISTORY_MAX = 10800


class KalibrierFenster(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Jumbo Control – Kalibrierte Druckwerte")
        self.resize(1100, 700)

        self._km         = KalibrierManager()
        self._history_t  = deque(maxlen=HISTORY_MAX)
        self._history    = {n: deque(maxlen=HISTORY_MAX) for n in SENSOREN}
        self._lines_roh  = {}
        self._lines_kal  = {}
        self._farben     = dict(FARBEN_DEFAULT)
        self._checks_roh = {}
        self._checks_kal = {}

        self._build_ui()
        self._info_anzeigen()
        self.setStyleSheet(build_stylesheet(DARK_THEME))
        self._apply_dark_matplotlib()
        matplotlib_toolbar_style(self._toolbar, dark=True)

    def _build_ui(self):
        haupt = QHBoxLayout(self)
        haupt.setContentsMargins(6, 6, 6, 6)
        haupt.setSpacing(6)

        # ── Linke Seite: Plot + Tabelle ───────────────────────
        links = QWidget()
        ll    = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)

        self._fig = Figure(figsize=(8, 4), dpi=100)
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._toolbar = NavToolbar(self._canvas, self)
        self._toolbar.setMaximumHeight(44)

        for name in SENSOREN:
            l_roh, = self._ax.semilogy([], [],
                color=self._farben[f"{name}_roh"], lw=1.2,
                ls="--", label=f"{name} roh", alpha=0.7)
            l_kal, = self._ax.semilogy([], [],
                color=self._farben[f"{name}_kal"], lw=2.0,
                ls="-", label=f"{name} kalibriert")
            self._lines_roh[name] = l_roh
            self._lines_kal[name] = l_kal

        self._ax.set_ylabel("Druck [mbar]")
        self._ax.set_xlabel("Uhrzeit")
        self._ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        self._legend = self._ax.legend(loc="upper left", fontsize=8)
        self._ax.grid(True, which="both", alpha=0.3)
        self._fig.tight_layout(pad=0.8)

        # Mausrad-Zoom
        self._canvas.mpl_connect("scroll_event", self._on_scroll)

        ll.addWidget(self._toolbar)
        ll.addWidget(self._canvas)

        # Tabelle
        table_box = QGroupBox("Aktuelle Werte")
        tl = QVBoxLayout(table_box)
        self._tabelle = QTableWidget(0, 5)
        self._tabelle.setHorizontalHeaderLabels([
            "Sensor", "Roh [mbar]", "Kalibriert [mbar]",
            "Abweichung [%]", "Kalibrierung"
        ])
        self._tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tabelle.setMaximumHeight(130)
        self._tabelle.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabelle.setAlternatingRowColors(True)
        self._tabelle.setStyleSheet("""
            QTableWidget { gridline-color: #2c3a57; }
            QHeaderView::section {
                background: #121b2b; color: #7db2ff;
                font-weight: 700; font-size: 11px; padding: 4px;
                border: 1px solid #2c3a57;
            }
            QTableWidget::item:alternate { background: #182336; }
        """)
        tl.addWidget(self._tabelle)
        ll.addWidget(table_box)
        haupt.addWidget(links, 1)

        # ── Rechte Seite: Optionen ────────────────────────────
        rechts = QWidget()
        rechts.setFixedWidth(220)
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        # Kurven ein/ausblenden
        sicht_box = QGroupBox("Kurven anzeigen")
        sicht_layout = QVBoxLayout(sicht_box)
        sicht_layout.setSpacing(2)
        for name in SENSOREN:
            cb_roh = QCheckBox(f"{name} roh")
            cb_roh.setStyleSheet("font-size: 11px;")
            cb_roh.setChecked(True)
            cb_roh.stateChanged.connect(lambda s, n=name: self._toggle(n, "roh", s))
            cb_kal = QCheckBox(f"{name} kalibriert")
            cb_kal.setStyleSheet("font-size: 11px;")
            cb_kal.setChecked(True)
            cb_kal.stateChanged.connect(lambda s, n=name: self._toggle(n, "kal", s))
            self._checks_roh[name] = cb_roh
            self._checks_kal[name] = cb_kal
            sicht_layout.addWidget(cb_roh)
            sicht_layout.addWidget(cb_kal)
        rl.addWidget(sicht_box)

        # Farben
        farb_box = QGroupBox("Farben")
        farb_layout = QGridLayout(farb_box)
        farb_layout.setSpacing(3)
        row = 0
        for name in SENSOREN:
            for typ in ["roh", "kal"]:
                key = f"{name}_{typ}"
                lbl = QLabel(f"{name} {typ}:")
                lbl.setStyleSheet("font-size: 11px; color: #b3c0dc;")
                btn = QPushButton()
                btn.setFixedSize(40, 18)
                btn.setStyleSheet(f"background: {self._farben[key]}; border-radius: 3px;")
                btn.clicked.connect(lambda _, k=key, b=btn: self._farbe_waehlen(k, b))
                farb_layout.addWidget(lbl, row, 0)
                farb_layout.addWidget(btn, row, 1)
                row += 1
        rl.addWidget(farb_box)

        # Achsengrenzen
        achse_box = QGroupBox("Achsengrenzen")
        achse_layout = QGridLayout(achse_box)
        achse_layout.setSpacing(3)

        self._chk_auto_x = QCheckBox("X Auto")
        self._chk_auto_x.setChecked(True)
        self._chk_auto_x.stateChanged.connect(self._update_achsen)
        self._chk_auto_y = QCheckBox("Y Auto")
        self._chk_auto_y.setChecked(True)
        self._chk_auto_y.stateChanged.connect(self._update_achsen)
        achse_layout.addWidget(self._chk_auto_x, 0, 0, 1, 2)
        achse_layout.addWidget(self._chk_auto_y, 1, 0, 1, 2)

        row_ymin = QHBoxLayout()
        row_ymin.addWidget(QLabel("Y-min:"))
        self._spn_ymin = QLineEdit("1e-8")
        self._spn_ymin.setEnabled(False)
        self._spn_ymin.setPlaceholderText("z.B. 1e-8")
        self._spn_ymin.returnPressed.connect(self._update_achsen)
        row_ymin.addWidget(self._spn_ymin)

        row_ymax = QHBoxLayout()
        row_ymax.addWidget(QLabel("Y-max:"))
        self._spn_ymax = QLineEdit("1e-2")
        self._spn_ymax.setEnabled(False)
        self._spn_ymax.setPlaceholderText("z.B. 1e-2")
        self._spn_ymax.returnPressed.connect(self._update_achsen)
        row_ymax.addWidget(self._spn_ymax)

        achse_layout.addLayout(row_ymin, 2, 0, 1, 2)
        achse_layout.addLayout(row_ymax, 3, 0, 1, 2)
        self._chk_auto_y.stateChanged.connect(
            lambda s: [self._spn_ymin.setEnabled(not s),
                       self._spn_ymax.setEnabled(not s)]
        )
        rl.addWidget(achse_box)

        # Darstellungsoptionen
        darst_box = QGroupBox("Darstellung")
        darst_layout = QVBoxLayout(darst_box)

        self._chk_punkte = QCheckBox("Datenpunkte anzeigen")
        self._chk_punkte.stateChanged.connect(self._update_marker)
        darst_layout.addWidget(self._chk_punkte)

        grid_row = QHBoxLayout()
        grid_row.addWidget(QLabel("Gitter:"))
        self._cmb_grid = QComboBox()
        self._cmb_grid.addItems(["Fein (major+minor)", "Grob (major)", "Aus"])
        self._cmb_grid.currentIndexChanged.connect(self._update_grid)
        grid_row.addWidget(self._cmb_grid)
        darst_layout.addLayout(grid_row)

        skala_row = QHBoxLayout()
        skala_row.addWidget(QLabel("Skala:"))
        self._cmb_skala = QComboBox()
        self._cmb_skala.addItems(["Log", "Linear"])
        self._cmb_skala.currentIndexChanged.connect(self._update_skala)
        skala_row.addWidget(self._cmb_skala)
        darst_layout.addLayout(skala_row)

        rl.addWidget(darst_box)
        rl.addStretch()
        haupt.addWidget(rechts, 0)

    def _apply_dark_matplotlib(self):
        t = DARK_THEME
        self._fig.patch.set_facecolor(t["bg"])
        self._ax.set_facecolor(t["panel"])
        self._ax.tick_params(colors=t["text"], which="both", labelsize=9)
        self._ax.xaxis.label.set_color(t["text"])
        self._ax.yaxis.label.set_color(t["text"])
        for spine in self._ax.spines.values():
            spine.set_edgecolor(t["border"])
        self._ax.grid(True, which="both", color=t["border"], linewidth=0.6, alpha=0.5)
        # Legende
        leg = self._ax.get_legend()
        if leg:
            leg.get_frame().set_facecolor(t["panel"])
            leg.get_frame().set_edgecolor(t["border"])
            for lt in leg.get_texts():
                lt.set_color(t["text"])
        self._canvas.draw_idle()

    # ── Mausrad-Zoom ──────────────────────────────────────────
    def _on_scroll(self, event):
        if event.inaxes != self._ax:
            return
        faktor = 1.15 if event.step < 0 else 1/1.15
        xlim = self._ax.get_xlim()
        ylim = self._ax.get_ylim()
        xdata, ydata = event.xdata, event.ydata

        if event.key == "shift":
            # Nur X
            self._ax.set_xlim([xdata + (x - xdata) * faktor for x in xlim])
        elif event.key == "control":
            # Nur Y
            self._ax.set_ylim([ydata + (y - ydata) * faktor for y in ylim])
        else:
            # Beide Achsen
            self._ax.set_xlim([xdata + (x - xdata) * faktor for x in xlim])
            self._ax.set_ylim([ydata + (y - ydata) * faktor for y in ylim])

        self._canvas.draw_idle()

    # ── Kurven togglen ────────────────────────────────────────
    def _toggle(self, name: str, typ: str, state: int):
        line = self._lines_roh[name] if typ == "roh" else self._lines_kal[name]
        line.set_visible(bool(state))
        self._canvas.draw_idle()

    # ── Farbe wählen ─────────────────────────────────────────
    def _farbe_waehlen(self, key: str, btn: QPushButton):
        farbe = QColorDialog.getColor(QColor(self._farben[key]), self)
        if farbe.isValid():
            self._farben[key] = farbe.name()
            btn.setStyleSheet(f"background: {farbe.name()}; border-radius: 3px;")
            name, typ = key.rsplit("_", 1)
            line = self._lines_roh[name] if typ == "roh" else self._lines_kal[name]
            line.set_color(farbe.name())
            self._canvas.draw_idle()

    # ── Achsengrenzen ─────────────────────────────────────────
    def _update_achsen(self):
        if not self._chk_auto_y.isChecked():
            try:
                ymin = float(self._spn_ymin.text())
                ymax = float(self._spn_ymax.text())
                if ymin > 0 and ymax > ymin:
                    self._ax.set_ylim(ymin, ymax)
                    self._spn_ymin.setStyleSheet("")
                    self._spn_ymax.setStyleSheet("")
                else:
                    self._spn_ymin.setStyleSheet("border: 1px solid red;")
            except ValueError:
                self._spn_ymin.setStyleSheet("border: 1px solid red;")
        else:
            self._ax.autoscale(axis="y")
        self._canvas.draw_idle()

    # ── Marker ───────────────────────────────────────────────
    def _update_marker(self, state: int):
        marker = "o" if state else "None"
        for line in list(self._lines_roh.values()) + list(self._lines_kal.values()):
            line.set_marker(marker)
            line.set_markersize(3)
        self._canvas.draw_idle()

    # ── Gitter ───────────────────────────────────────────────
    def _update_grid(self, idx: int):
        self._ax.grid(False, which="both")
        if idx == 0:
            self._ax.grid(True, which="major", alpha=0.4)
            self._ax.grid(True, which="minor", alpha=0.15)
        elif idx == 1:
            self._ax.grid(True, which="major", alpha=0.4)
        self._canvas.draw_idle()

    # ── Skala ─────────────────────────────────────────────────
    def _update_skala(self, idx: int):
        self._ax.set_yscale("log" if idx == 0 else "linear")
        self._canvas.draw_idle()

    # ── Tabelle initialisieren ────────────────────────────────
    def _info_anzeigen(self):
        self._tabelle.setRowCount(len(SENSOREN))
        for row, name in enumerate(SENSOREN):
            self._tabelle.setItem(row, 0, QTableWidgetItem(name))
            for col in [1, 2, 3]:
                self._tabelle.setItem(row, col, QTableWidgetItem("---"))
            if self._km.hat_kalibrierung(name):
                info = self._km.info(name)
                txt  = f"Zert. {info['zertifikat']} ({info['datum']})"
                item = QTableWidgetItem(txt)
                item.setForeground(QColor("#16a34a"))
            else:
                item = QTableWidgetItem("keine Kalibrierung")
                item.setForeground(QColor("#94a3b8"))
            self._tabelle.setItem(row, 4, item)

    # ── Daten aktualisieren ───────────────────────────────────
    def aktualisieren(self, werte: dict):
        if "CENT" in werte and "CENTER" not in werte:
            werte["CENTER"] = werte.pop("CENT")

        jetzt = datetime.now()
        self._history_t.append(jetzt)

        for row, name in enumerate(SENSOREN):
            d      = werte.get(name, {})
            status = d.get("status", "") if d else ""
            val    = d.get("mbar") if d and d.get("gueltig") and d.get("mbar", 0) > 0 else None
            is_or  = status in ("Overrange", "Underrange", "Sensor error",
                                "Sensor off", "No sensor") or (val is None and status)
            self._history[name].append(val)

            if is_or:
                self._tabelle.setItem(row, 1, QTableWidgetItem("Overrange"))
                self._tabelle.setItem(row, 2, QTableWidgetItem("Overrange"))
                self._tabelle.setItem(row, 3, QTableWidgetItem("---"))
            elif val is not None:
                kal = self._km.korrigiere(name, val)
                abw = self._km.abweichung(name, val)
                self._tabelle.setItem(row, 1, QTableWidgetItem(f"{val:.3E}"))
                item_kal = QTableWidgetItem(f"{kal:.3E}")
                item_abw = QTableWidgetItem(f"{abw:+.1f} %")
                if self._km.hat_kalibrierung(name):
                    item_kal.setForeground(QColor("#16a34a"))
                    col = "#dc2626" if abs(abw) > 30 else "#d97706" if abs(abw) > 15 else "#16a34a"
                    item_abw.setForeground(QColor(col))
                self._tabelle.setItem(row, 2, item_kal)
                self._tabelle.setItem(row, 3, item_abw)
            else:
                for col in [1, 2, 3]:
                    self._tabelle.setItem(row, col, QTableWidgetItem("---"))

        self._update_plot()

    def _update_plot(self):
        if not self._history_t:
            return
        t_list = list(self._history_t)
        updated = False
        for name in SENSOREN:
            y_all = list(self._history[name])
            x   = [t_list[i] for i, v in enumerate(y_all) if v is not None and v > 0]
            y_r = [v for v in y_all if v is not None and v > 0]
            y_k = [self._km.korrigiere(name, v) for v in y_r]
            if x:
                self._lines_roh[name].set_data(x, y_r)
                self._lines_kal[name].set_data(x, y_k)
                updated = True
        if updated:
            if self._chk_auto_y.isChecked():
                self._ax.relim()
                self._ax.autoscale_view()
            self._fig.autofmt_xdate(rotation=30, ha="right")
            self._canvas.draw_idle()
