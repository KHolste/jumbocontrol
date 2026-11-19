"""
gui/temp_kalibrierung_fenster.py
Separates Fenster: kalibrierte (PT100-Tabelle) und unkalibrierte (CVD-Formel)
Temperaturen im direkten Vergleich – analog zu gui/kalibrierung_fenster.py (Druck).

Gezeigt werden alle Kanäle mit Eintrag in config.PT100_KALIBRIERUNG.
Beide Werte werden aus dem gemessenen Widerstand berechnet. Beim Öffnen wird
die Historie aus der heutigen Temperatur-CSV (Spalten "<Kanal>_ohm") vorbefüllt.
"""

import csv
import os
from collections import deque
from datetime import datetime, timedelta

import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QGroupBox,
    QSizePolicy, QHeaderView, QCheckBox, QComboBox,
    QScrollArea, QLineEdit, QGridLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

import matplotlib
matplotlib.use("QtAgg")
import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavToolbar
from matplotlib.figure import Figure

from config import LOG_PFAD, TEMP_MIN, TEMP_MAX
from daten.kalibrierung import KalibrierManager, cvd_kelvin
from gui.temp_panel import SENSOREN as ALLE_SENSOREN, FARBEN, HISTORY_MAX
from gui.themes import DARK_THEME, build_stylesheet, matplotlib_toolbar_style

ZEITBEREICHE = [("Alles", None), ("Letzte 1 h", 1), ("Letzte 6 h", 6),
                ("Letzte 12 h", 12), ("Letzte 24 h", 24)]


def _gueltig(kelvin):
    """Kelvin-Wert nur zurückgeben, wenn er im zulässigen Temperaturbereich liegt."""
    if kelvin is None:
        return None
    return kelvin if TEMP_MIN <= kelvin - 273.15 <= TEMP_MAX else None


class TempKalibrierFenster(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Jumbo Control – Kalibrierte Temperaturen")
        self.resize(1200, 760)

        self._km       = KalibrierManager()
        self._sensoren = self._km.pt100_sensoren
        self._farben   = {n: FARBEN[ALLE_SENSOREN.index(n) % len(FARBEN)]
                          if n in ALLE_SENSOREN else "#cccccc"
                          for n in self._sensoren}
        self._einheit  = "K"

        self._history_t   = deque(maxlen=HISTORY_MAX)
        self._history_tn  = deque(maxlen=HISTORY_MAX)   # Zeit als matplotlib-Datum
        self._history_cvd = {n: deque(maxlen=HISTORY_MAX) for n in self._sensoren}
        self._history_kal = {n: deque(maxlen=HISTORY_MAX) for n in self._sensoren}
        self._history_ohm = {n: deque(maxlen=HISTORY_MAX) for n in self._sensoren}
        self._lines_cvd   = {}
        self._lines_kal   = {}
        self._checks      = {}

        self._build_ui()
        self._info_anzeigen()
        self.setStyleSheet(build_stylesheet(DARK_THEME))
        self._apply_dark_matplotlib()
        matplotlib_toolbar_style(self._toolbar, dark=True)

        self._aus_csv_laden()
        self._update_tabelle()
        self._update_plot()

    # ── Werte berechnen ───────────────────────────────────────
    def _berechne(self, name: str, R):
        """(cvd_K, kal_K) aus dem Widerstand; ungültige Werte → None."""
        if R is None or R <= 0:
            return None, None
        return (_gueltig(cvd_kelvin(R)),
                _gueltig(self._km.pt100_ohm_zu_kelvin(name, R)))

    def _anhaengen(self, zeit: datetime, ohm: dict):
        self._history_t.append(zeit)
        self._history_tn.append(mdates.date2num(zeit))
        for name in self._sensoren:
            R = ohm.get(name)
            cvd, kal = self._berechne(name, R)
            self._history_ohm[name].append(R)
            self._history_cvd[name].append(cvd)
            self._history_kal[name].append(kal)

    def _aus_csv_laden(self):
        """Heutige Temperatur-CSV einlesen, damit das Fenster nicht leer startet."""
        datei = os.path.join(LOG_PFAD, f"{datetime.now():%Y-%m-%d}_temperatur.csv")
        if not os.path.exists(datei):
            return
        try:
            with open(datei, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f, delimiter="\t"):
                    try:
                        zeit = datetime.fromisoformat(row["ISO_lokal"])
                    except (KeyError, ValueError, TypeError):
                        continue
                    ohm = {}
                    for name in self._sensoren:
                        try:
                            ohm[name] = float(row.get(f"{name}_ohm", "nan"))
                        except (TypeError, ValueError):
                            ohm[name] = None
                        if ohm[name] != ohm[name]:   # NaN
                            ohm[name] = None
                    self._anhaengen(zeit, ohm)
        except Exception as e:
            from log_utils import tprint
            tprint("TempKalibrierFenster", f"CSV-Vorbefüllung fehlgeschlagen: {e}")

    # ── UI ────────────────────────────────────────────────────
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

        for name in self._sensoren:
            farbe = self._farben[name]
            l_cvd, = self._ax.plot([], [], color=farbe, lw=1.2, ls="--",
                                   alpha=0.7, label=f"{name} unkal.")
            l_kal, = self._ax.plot([], [], color=farbe, lw=1.8, ls="-",
                                   label=f"{name} kal.")
            self._lines_cvd[name] = l_cvd
            self._lines_kal[name] = l_kal

        self._ax.set_xlabel("Uhrzeit")
        self._ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        self._ax.grid(True, which="both", alpha=0.3)
        self._update_ylabel()
        self._fig.tight_layout(pad=0.8)
        self._canvas.mpl_connect("scroll_event", self._on_scroll)

        ll.addWidget(self._toolbar)
        ll.addWidget(self._canvas, 1)

        table_box = QGroupBox("Aktuelle Werte  (gestrichelt = unkalibriert/CVD, "
                              "durchgezogen = kalibriert)")
        tl = QVBoxLayout(table_box)
        self._tabelle = QTableWidget(0, 6)
        self._tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tabelle.verticalHeader().setVisible(False)
        self._tabelle.setMaximumHeight(28 + 24 * max(len(self._sensoren), 1))
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
        self._update_tabellenkopf()
        tl.addWidget(self._tabelle)
        ll.addWidget(table_box)
        haupt.addWidget(links, 1)

        # ── Rechte Seite: Optionen ────────────────────────────
        rechts = QWidget()
        rechts.setFixedWidth(230)
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        # Kurventypen
        typ_box = QGroupBox("Kurven")
        typ_layout = QVBoxLayout(typ_box)
        self._chk_cvd = QCheckBox("unkalibriert (CVD) – gestrichelt")
        self._chk_cvd.setChecked(True)
        self._chk_cvd.stateChanged.connect(self._update_sichtbarkeit)
        self._chk_kal = QCheckBox("kalibriert – durchgezogen")
        self._chk_kal.setChecked(True)
        self._chk_kal.stateChanged.connect(self._update_sichtbarkeit)
        typ_layout.addWidget(self._chk_cvd)
        typ_layout.addWidget(self._chk_kal)
        rl.addWidget(typ_box)

        # Sensoren
        sens_box = QGroupBox("Sensoren")
        sens_outer = QVBoxLayout(sens_box)
        sens_outer.setContentsMargins(2, 4, 2, 2)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none;")
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(1)
        inner_layout.setContentsMargins(2, 2, 2, 2)
        for name in self._sensoren:
            farbe = self._farben[name]
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.setStyleSheet(f"""
                QCheckBox {{ font-size: 12px; spacing: 4px; }}
                QCheckBox::indicator:checked {{
                    background-color: {farbe}; border-color: {farbe};
                }}
            """)
            cb.stateChanged.connect(self._update_sichtbarkeit)
            self._checks[name] = cb
            inner_layout.addWidget(cb)
        inner_layout.addStretch()
        scroll.setWidget(inner)
        sens_outer.addWidget(scroll)
        rl.addWidget(sens_box, 1)

        # Anzeige
        anz_box = QGroupBox("Anzeige")
        anz_layout = QGridLayout(anz_box)
        anz_layout.setSpacing(3)
        anz_layout.addWidget(QLabel("Einheit:"), 0, 0)
        self._cmb_einheit = QComboBox()
        self._cmb_einheit.addItems(["K", "°C"])
        self._cmb_einheit.currentTextChanged.connect(self._on_einheit)
        anz_layout.addWidget(self._cmb_einheit, 0, 1)
        anz_layout.addWidget(QLabel("Zeitbereich:"), 1, 0)
        self._cmb_zeit = QComboBox()
        self._cmb_zeit.addItems([z[0] for z in ZEITBEREICHE])
        self._cmb_zeit.currentIndexChanged.connect(self._update_plot)
        anz_layout.addWidget(self._cmb_zeit, 1, 1)
        anz_layout.addWidget(QLabel("Gitter:"), 2, 0)
        self._cmb_grid = QComboBox()
        self._cmb_grid.addItems(["Fein", "Grob", "Aus"])
        self._cmb_grid.currentIndexChanged.connect(self._update_grid)
        anz_layout.addWidget(self._cmb_grid, 2, 1)
        self._chk_punkte = QCheckBox("Datenpunkte anzeigen")
        self._chk_punkte.stateChanged.connect(self._update_marker)
        anz_layout.addWidget(self._chk_punkte, 3, 0, 1, 2)
        rl.addWidget(anz_box)

        # Achsengrenzen
        achse_box = QGroupBox("Y-Achse")
        achse_layout = QGridLayout(achse_box)
        achse_layout.setSpacing(3)
        self._chk_auto_y = QCheckBox("Auto")
        self._chk_auto_y.setChecked(True)
        achse_layout.addWidget(self._chk_auto_y, 0, 0, 1, 2)
        achse_layout.addWidget(QLabel("min:"), 1, 0)
        self._edt_ymin = QLineEdit("0")
        self._edt_ymin.setEnabled(False)
        self._edt_ymin.returnPressed.connect(self._update_achsen)
        achse_layout.addWidget(self._edt_ymin, 1, 1)
        achse_layout.addWidget(QLabel("max:"), 2, 0)
        self._edt_ymax = QLineEdit("310")
        self._edt_ymax.setEnabled(False)
        self._edt_ymax.returnPressed.connect(self._update_achsen)
        achse_layout.addWidget(self._edt_ymax, 2, 1)
        self._chk_auto_y.stateChanged.connect(
            lambda s: [self._edt_ymin.setEnabled(not s),
                       self._edt_ymax.setEnabled(not s),
                       self._update_achsen()]
        )
        rl.addWidget(achse_box)

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
        self._canvas.draw_idle()

    # ── Bedienung ─────────────────────────────────────────────
    def _on_scroll(self, event):
        if event.inaxes != self._ax:
            return
        faktor = 1.15 if event.step < 0 else 1 / 1.15
        xdata, ydata = event.xdata, event.ydata
        if event.key != "control":
            self._ax.set_xlim([xdata + (x - xdata) * faktor for x in self._ax.get_xlim()])
        if event.key != "shift":
            self._ax.set_ylim([ydata + (y - ydata) * faktor for y in self._ax.get_ylim()])
            self._chk_auto_y.setChecked(False)
        self._canvas.draw_idle()

    def _update_sichtbarkeit(self, *_):
        for name in self._sensoren:
            an = self._checks[name].isChecked()
            self._lines_cvd[name].set_visible(an and self._chk_cvd.isChecked())
            self._lines_kal[name].set_visible(an and self._chk_kal.isChecked())
        self._update_plot()

    def _on_einheit(self, einheit: str):
        self._einheit = einheit
        self._update_ylabel()
        self._update_tabellenkopf()
        self._update_tabelle()
        self._update_plot()

    def _update_ylabel(self):
        self._ax.set_ylabel(f"Temperatur [{self._einheit}]")

    def _update_grid(self, idx: int):
        self._ax.grid(False, which="both")
        if idx in (0, 1):
            self._ax.grid(True, which="major", color=DARK_THEME["border"], alpha=0.5)
        if idx == 0:
            self._ax.minorticks_on()
            self._ax.grid(True, which="minor", color=DARK_THEME["border"], alpha=0.2)
        else:
            self._ax.minorticks_off()
        self._canvas.draw_idle()

    def _update_marker(self, state: int):
        marker = "o" if state else "None"
        for line in list(self._lines_cvd.values()) + list(self._lines_kal.values()):
            line.set_marker(marker)
            line.set_markersize(3)
        self._canvas.draw_idle()

    def _update_achsen(self):
        if self._chk_auto_y.isChecked():
            self._ax.relim(visible_only=True)
            self._ax.autoscale_view(scalex=False)
        else:
            try:
                ymin = float(self._edt_ymin.text().replace(",", "."))
                ymax = float(self._edt_ymax.text().replace(",", "."))
                if ymax > ymin:
                    self._ax.set_ylim(ymin, ymax)
                    self._edt_ymin.setStyleSheet("")
                else:
                    self._edt_ymin.setStyleSheet("border: 1px solid red;")
            except ValueError:
                self._edt_ymin.setStyleSheet("border: 1px solid red;")
        self._canvas.draw_idle()

    # ── Tabelle ───────────────────────────────────────────────
    def _update_tabellenkopf(self):
        e = self._einheit
        self._tabelle.setHorizontalHeaderLabels([
            "Sensor", "Widerstand [Ω]", f"Unkalibriert (CVD) [{e}]",
            f"Kalibriert [{e}]", "Differenz kal − unkal [K]", "Kalibriertabelle"
        ])

    def _info_anzeigen(self):
        self._tabelle.setRowCount(len(self._sensoren))
        for row, name in enumerate(self._sensoren):
            item = QTableWidgetItem(name)
            item.setForeground(QColor(self._farben[name]))
            self._tabelle.setItem(row, 0, item)
            for col in (1, 2, 3, 4):
                self._tabelle.setItem(row, col, QTableWidgetItem("---"))
            info = self._km.pt100_info(name)
            lo, hi = info["bereich_k"]
            txt = f"{info['datei']}  ({lo:.0f}–{hi:.0f} K, {info['punkte']} Pkt.)"
            item = QTableWidgetItem(txt)
            item.setForeground(QColor("#16a34a"))
            item.setToolTip("Außerhalb dieses Bereichs: CVD-Formel, "
                            "stetig an den Tabellenrand angeschlossen")
            self._tabelle.setItem(row, 5, item)

    def _anzeige(self, kelvin):
        return kelvin - 273.15 if self._einheit == "°C" else kelvin

    def _update_tabelle(self):
        if not self._history_t:
            return
        for row, name in enumerate(self._sensoren):
            R   = self._history_ohm[name][-1]
            cvd = self._history_cvd[name][-1]
            kal = self._history_kal[name][-1]
            self._tabelle.setItem(row, 1, QTableWidgetItem(
                f"{R:.3f}" if R is not None else "---"))
            self._tabelle.setItem(row, 2, QTableWidgetItem(
                f"{self._anzeige(cvd):.2f}" if cvd is not None else "---"))
            item_kal = QTableWidgetItem(
                f"{self._anzeige(kal):.2f}" if kal is not None else "---")
            item_kal.setForeground(QColor("#16a34a"))
            self._tabelle.setItem(row, 3, item_kal)
            if cvd is not None and kal is not None:
                diff = kal - cvd
                item = QTableWidgetItem(f"{diff:+.2f}")
                col = "#dc2626" if abs(diff) > 5 else "#d97706" if abs(diff) > 2 else "#16a34a"
                item.setForeground(QColor(col))
            else:
                item = QTableWidgetItem("---")
            self._tabelle.setItem(row, 4, item)

    # ── Daten aktualisieren ───────────────────────────────────
    def aktualisieren(self, werte: dict):
        """werte = Rückgabe von TemperaturMessung.messen() (enthält 'ohm')."""
        ohm = {}
        for name in self._sensoren:
            d = werte.get(name) or {}
            ohm[name] = d.get("ohm")
        self._anhaengen(datetime.now(), ohm)
        self._update_tabelle()
        if self.isVisible():
            self._update_plot()

    def _update_plot(self, *_):
        if not self._history_t:
            return
        t_list = list(self._history_t)
        stunden = ZEITBEREICHE[self._cmb_zeit.currentIndex()][1]
        start = 0
        if stunden is not None:
            t_min = datetime.now() - timedelta(hours=stunden)
            start = next((i for i, t in enumerate(t_list) if t >= t_min), len(t_list))
        t_list = t_list[start:]
        x = np.fromiter(self._history_tn, dtype=float)[start:]
        offset = -273.15 if self._einheit == "°C" else 0.0

        for name in self._sensoren:
            for hist, line in ((self._history_cvd[name], self._lines_cvd[name]),
                               (self._history_kal[name], self._lines_kal[name])):
                if not line.get_visible():
                    continue
                # None → NaN: matplotlib unterbricht die Linie an Lücken
                y = np.array(hist, dtype=float)[start:] + offset
                line.set_data(x, y)

        if t_list:
            if stunden is not None:
                self._ax.set_xlim(datetime.now() - timedelta(hours=stunden), datetime.now())
            else:
                self._ax.set_xlim(t_list[0], max(t_list[-1], t_list[0] + timedelta(minutes=1)))
        self._update_achsen()
        self._fig.autofmt_xdate(rotation=30, ha="right")
        self._canvas.draw_idle()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_plot()
