"""
gui/historien_fenster.py
Fenster zum Einlesen und Vergleichen historischer Druck- und Temperaturdaten.
Mehrere Dateien gleichzeitig, gleiche Zeitachse, verschiedene Farben pro Datei.
"""

import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QListWidget, QListWidgetItem, QSplitter,
    QGroupBox, QCheckBox, QScrollArea, QComboBox, QFrame,
    QSizePolicy, QAbstractItemView
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

from daten.csv_leser import CsvLeser
from gui.themes import DARK_THEME, build_stylesheet, matplotlib_toolbar_style

# Farben für bis zu 10 Dateien
DATEI_FARBEN = [
    "#e63946", "#2a9d8f", "#f4a261", "#457b9d", "#8338ec",
    "#06d6a0", "#fb5607", "#3a86ff", "#ffbe0b", "#ef476f"
]

DRUCK_SENSOREN  = ["CENT", "DOOR", "BA"]
TEMP_SENSOREN   = [
    "Kryo 1 In", "Kryo 1", "Kryo 1b", "Peltier", "Peltier b",
    "Kryo 2 In", "Kryo 2", "Kryo 2b",
    "Kryo 3 In", "Kryo 3", "Kryo 3b",
    "Kryo 4 In", "Kryo 4", "Kryo 4b",
    "Kryo 5 In", "Kryo 5", "Kryo 5b",
    "Kryo 6 In", "Kryo 6", "Kryo 6b",
    "Kryo 7 In", "Kryo 7",
    "Kryo 9", "Kryo 9b",
    "Kryo 8 In", "Kryo 8",
]


class DateiEintrag:
    """Repräsentiert eine geladene CSV-Datei."""
    def __init__(self, pfad: str, farbe: str, typ: str):
        self.pfad   = pfad
        self.name   = os.path.basename(pfad)
        self.farbe  = farbe
        self.typ    = typ   # "druck" oder "temperatur"
        self.daten  = {}
        self.aktiv  = True


class HistorienFenster(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Jumbo Control – Historische Daten")
        self.resize(1300, 800)

        self._leser          = CsvLeser()
        self._druck_dateien  = []   # Liste von DateiEintrag
        self._temp_dateien   = []
        self._farb_idx       = 0

        self._build_ui()
        self.setStyleSheet(build_stylesheet(DARK_THEME))
        self._apply_dark_matplotlib()
        matplotlib_toolbar_style(self._toolbar, dark=True)

    def _apply_dark_matplotlib(self):
        t = DARK_THEME
        self._fig.patch.set_facecolor(t["bg"])
        for ax in [self._ax_druck, self._ax_temp]:
            ax.set_facecolor(t["panel"])
            ax.tick_params(colors=t["text"], which="both", labelsize=9)
            ax.xaxis.label.set_color(t["text"])
            ax.yaxis.label.set_color(t["text"])
            for spine in ax.spines.values():
                spine.set_edgecolor(t["border"])
            ax.grid(True, color=t["border"], linewidth=0.6, alpha=0.5)
        self._canvas.draw_idle()

    def _build_ui(self):
        haupt = QHBoxLayout(self)
        haupt.setContentsMargins(6, 6, 6, 6)
        haupt.setSpacing(6)

        # ── Linke Seite: Plots ────────────────────────────────
        links = QWidget()
        ll    = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)

        self._fig = Figure(figsize=(10, 7), dpi=100)
        self._ax_druck = self._fig.add_subplot(211)
        self._ax_temp  = self._fig.add_subplot(212)
        self._canvas   = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._toolbar  = NavToolbar(self._canvas, self)
        self._toolbar.setMaximumHeight(44)

        self._ax_druck.set_ylabel("Druck [mbar]")
        self._ax_druck.set_yscale("log")
        self._ax_druck.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%d.%m"))
        self._ax_druck.grid(True, which="both", alpha=0.3)

        self._ax_temp.set_ylabel("Temperatur [°C]")
        self._ax_temp.set_xlabel("Uhrzeit")
        self._ax_temp.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%d.%m"))
        self._ax_temp.grid(True, alpha=0.3)

        self._fig.tight_layout(pad=1.5)

        # Mausrad-Zoom
        self._canvas.mpl_connect("scroll_event", self._on_scroll)

        ll.addWidget(self._toolbar)
        ll.addWidget(self._canvas)
        ll.addWidget(self._build_plot_optionen())
        haupt.addWidget(links, 1)

        # ── Rechte Seite: Dateiauswahl + Sensorauswahl ───────
        rechts = QWidget()
        rechts.setFixedWidth(320)
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        # Dateien laden
        rl.addWidget(self._build_datei_panel())

        # Sensorauswahl
        rl.addWidget(self._build_sensor_auswahl())
        rl.addStretch()
        haupt.addWidget(rechts, 0)

    def _build_plot_optionen(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(42)
        layout = QHBoxLayout(w)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(10)

        # Druck-Skala
        layout.addWidget(QLabel("Druck-Skala:"))
        self._cmb_druck_skala = QComboBox()
        self._cmb_druck_skala.addItems(["Log", "Linear"])
        self._cmb_druck_skala.currentIndexChanged.connect(
            lambda i: (self._ax_druck.set_yscale("log" if i == 0 else "linear"),
                       self._canvas.draw_idle())
        )
        layout.addWidget(self._cmb_druck_skala)

        layout.addWidget(self._vsep())

        # Gitter
        layout.addWidget(QLabel("Gitter:"))
        self._cmb_grid = QComboBox()
        self._cmb_grid.addItems(["Fein", "Grob", "Aus"])
        self._cmb_grid.currentIndexChanged.connect(self._update_grid)
        layout.addWidget(self._cmb_grid)

        layout.addWidget(self._vsep())

        # Datenpunkte
        self._chk_marker = QCheckBox("Datenpunkte")
        self._chk_marker.stateChanged.connect(self._update_marker)
        layout.addWidget(self._chk_marker)

        layout.addWidget(self._vsep())

        # Tage überlagern
        self._chk_tage = QCheckBox("Tage überlagern")
        self._chk_tage.setToolTip(
            "Zeitachse auf 00:00–24:00 normieren –\n"
            "Daten verschiedener Tage werden übereinander gelegt"
        )
        self._chk_tage.stateChanged.connect(self._neu_zeichnen)
        layout.addWidget(self._chk_tage)

        layout.addWidget(self._vsep())

        # Plot-Einstellungen
        btn_einst = QPushButton("⚙ Einstellungen")
        btn_einst.clicked.connect(self._einstellungen_oeffnen)
        layout.addWidget(btn_einst)

        layout.addStretch()
        return w

    def _build_datei_panel(self) -> QGroupBox:
        box = QGroupBox("Dateien")
        layout = QVBoxLayout(box)

        # Buttons
        btn_row = QHBoxLayout()
        btn_druck = QPushButton("+ Druck")
        btn_druck.setStyleSheet(self._btn_style("#e63946"))
        btn_druck.clicked.connect(lambda: self._datei_laden("druck"))
        btn_temp = QPushButton("+ Temperatur")
        btn_temp.setStyleSheet(self._btn_style("#2a9d8f"))
        btn_temp.clicked.connect(lambda: self._datei_laden("temperatur"))
        btn_clear = QPushButton("Alle entfernen")
        btn_clear.setMinimumWidth(110)

        btn_clear.clicked.connect(self._alle_entfernen)
        btn_row.addWidget(btn_druck)
        btn_row.addWidget(btn_temp)
        btn_row.addWidget(btn_clear)
        layout.addLayout(btn_row)

        # Dateiliste
        self._datei_liste = QListWidget()
        self._datei_liste.setMaximumHeight(200)
        self._datei_liste.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._datei_liste.itemDoubleClicked.connect(self._datei_entfernen)
        self._datei_liste.setToolTip("Doppelklick zum Entfernen")
        layout.addWidget(self._datei_liste)

        hinweis = QLabel("Doppelklick = Datei entfernen")
        hinweis.setStyleSheet("font-size: 9px; color: #7f8daa;")
        layout.addWidget(hinweis)
        return box

    def _build_sensor_auswahl(self) -> QGroupBox:
        box = QGroupBox("Sensoren anzeigen")
        layout = QVBoxLayout(box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(1)
        inner_layout.setContentsMargins(2, 2, 2, 2)

        self._sensor_checks = {}

        # Druck
        lbl_d = QLabel("── Druck ──")
        lbl_d.setStyleSheet("font-size: 9px; color: #7db2ff; font-weight: bold; letter-spacing: 1px;")
        inner_layout.addWidget(lbl_d)
        for name in DRUCK_SENSOREN:
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.setStyleSheet("font-size: 10px;")
            cb.stateChanged.connect(self._neu_zeichnen)
            self._sensor_checks[name] = cb
            inner_layout.addWidget(cb)

        # Temperatur
        lbl_t = QLabel("── Temperatur ──")
        lbl_t.setStyleSheet("font-size: 9px; color: #2dd4bf; font-weight: bold; letter-spacing: 1px; margin-top: 6px;")
        inner_layout.addWidget(lbl_t)

        # Alle an/aus
        cb_alle = QCheckBox("Alle Temp.")
        cb_alle.setChecked(True)
        cb_alle.setStyleSheet("font-size: 10px; font-weight: bold;")
        cb_alle.stateChanged.connect(self._alle_temp_toggle)
        inner_layout.addWidget(cb_alle)
        self._cb_alle_temp = cb_alle

        for name in TEMP_SENSOREN:
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.setStyleSheet("font-size: 10px;")
            cb.stateChanged.connect(self._neu_zeichnen)
            self._sensor_checks[name] = cb
            inner_layout.addWidget(cb)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll)
        return box

    # ── Datei laden ───────────────────────────────────────────
    def _datei_laden(self, typ: str):
        filter_str = "CSV Dateien (*.csv *.txt);;Alle Dateien (*)"
        pfade, _ = QFileDialog.getOpenFileNames(
            self, f"{'Druck' if typ == 'druck' else 'Temperatur'}-Dateien öffnen",
            "daten/logs", filter_str
        )
        for pfad in pfade:
            self._lade_eine_datei(pfad, typ)
        self._neu_zeichnen()

    def _lade_eine_datei(self, pfad: str, typ: str):
        farbe = DATEI_FARBEN[self._farb_idx % len(DATEI_FARBEN)]
        self._farb_idx += 1

        eintrag = DateiEintrag(pfad, farbe, typ)
        try:
            if typ == "druck":
                eintrag.daten = self._leser.lese_druck(pfad)
                self._druck_dateien.append(eintrag)
            else:
                eintrag.daten = self._leser.lese_temperatur(pfad)
                self._temp_dateien.append(eintrag)

            # In Liste eintragen
            item = QListWidgetItem(f"{'D' if typ == 'druck' else 'T'}  {eintrag.name}")
            item.setForeground(QColor(farbe))
            item.setData(Qt.ItemDataRole.UserRole, eintrag)
            self._datei_liste.addItem(item)
        except Exception as e:
            print(f"[Historien] Fehler beim Laden {pfad}: {e}")

    def _datei_entfernen(self, item: QListWidgetItem):
        eintrag = item.data(Qt.ItemDataRole.UserRole)
        if eintrag.typ == "druck":
            self._druck_dateien = [d for d in self._druck_dateien if d is not eintrag]
        else:
            self._temp_dateien = [d for d in self._temp_dateien if d is not eintrag]
        self._datei_liste.takeItem(self._datei_liste.row(item))
        self._neu_zeichnen()

    def _alle_entfernen(self):
        self._druck_dateien.clear()
        self._temp_dateien.clear()
        self._datei_liste.clear()
        self._farb_idx = 0
        self._ax_druck.cla()
        self._ax_temp.cla()
        self._setup_achsen()
        self._canvas.draw_idle()

    # ── Zeichnen ──────────────────────────────────────────────
    def _neu_zeichnen(self):
        self._ax_druck.cla()
        self._ax_temp.cla()
        self._setup_achsen()

        # Druckdateien
        for eintrag in self._druck_dateien:
            self._zeichne_druck(eintrag)

        # Temperaturdateien
        for eintrag in self._temp_dateien:
            self._zeichne_temp(eintrag)

        if self._ax_druck.get_lines():
            self._ax_druck.legend(loc="upper left", fontsize=7)
        if self._ax_temp.get_lines():
            self._ax_temp.legend(loc="upper left", fontsize=7)

        self._fig.autofmt_xdate(rotation=30, ha="right")
        self._canvas.draw_idle()

    def _normiere_zeit(self, t_liste: list) -> list:
        """Normiert Zeitstempel auf 00:00 des ersten Tages (für Tage-Überlagerung)."""
        if not t_liste:
            return t_liste
        erster = t_liste[0]
        if erster is None:
            return t_liste
        basis = erster.replace(hour=0, minute=0, second=0, microsecond=0)
        from datetime import timedelta
        result = []
        for ts in t_liste:
            if ts is None:
                result.append(None)
            else:
                # Tagesanteil behalten, Datum auf Basis setzen
                delta = ts - ts.replace(hour=0, minute=0, second=0, microsecond=0)
                result.append(basis + delta)
        return result

    def _zeichne_druck(self, eintrag: DateiEintrag):
        d = eintrag.daten
        t = d.get("ISO_lokal") or d.get("UTC") or []
        if not t:
            return
        if self._chk_tage.isChecked():
            t = self._normiere_zeit(t)

        # Alle Drucksensoren die in der Datei vorhanden sind
        alle_druck = [s for s in d.keys()
                      if s not in ("ISO_lokal", "UTC", "MJD") and
                      not s.endswith("_status") and not s.endswith("_kal")]

        linestyles = ["-", "--", ":"]
        for i, sensor in enumerate(alle_druck):
            # Checkbox prüfen wenn vorhanden, sonst anzeigen
            if sensor in self._sensor_checks and not self._sensor_checks[sensor].isChecked():
                continue
            werte = d.get(sensor, [])
            if not werte:
                continue
            x = [t[j] for j, v in enumerate(werte) if v is not None and v > 0]
            y = [v for v in werte if v is not None and v > 0]
            if x:
                self._ax_druck.semilogy(
                    x, y,
                    color=eintrag.farbe,
                    ls=linestyles[i % len(linestyles)],
                    lw=1.5,
                    label=f"{eintrag.name} – {sensor}"
                )

    def _zeichne_temp(self, eintrag: DateiEintrag):
        d = eintrag.daten
        t = d.get("ISO_lokal") or d.get("UTC") or []
        if not t:
            return
        if self._chk_tage.isChecked():
            t = self._normiere_zeit(t)

        # Farb-Variation: Helligkeit variieren pro Sensor
        import colorsys
        # Sensoren aus Datei + bekannte Sensoren aus Checkboxen
        sensoren_in_datei = [s for s in d.keys()
                             if s not in ("ISO_lokal", "UTC", "MJD") and
                             not s.endswith(("_status", "_kal"))]
        sensoren = [s for s in sensoren_in_datei
                    if s not in self._sensor_checks or
                    self._sensor_checks[s].isChecked()]
        n = max(len(sensoren), 1)

        basis_hex = eintrag.farbe.lstrip("#")
        r, g, b   = [int(basis_hex[i:i+2], 16)/255 for i in (0, 2, 4)]
        h, s, v   = colorsys.rgb_to_hsv(r, g, b)

        for i, sensor in enumerate(sensoren):
            werte = d.get(sensor, [])
            if not werte:
                continue
            x = [t[j] for j, v in enumerate(werte) if v is not None and j < len(t)]
            y = [v for v in werte if v is not None]
            if not x or not y:
                continue
            # Helligkeit variieren
            v_neu   = max(0.3, v - 0.5 * i / n)
            r2,g2,b2 = colorsys.hsv_to_rgb(h, s, v_neu)
            farbe   = f"#{int(r2*255):02x}{int(g2*255):02x}{int(b2*255):02x}"
            self._ax_temp.plot(x, y, color=farbe, lw=1.2,
                               label=f"{eintrag.name} – {sensor}")

    def _setup_achsen(self):
        self._apply_dark_matplotlib()
        skala = "log" if self._cmb_druck_skala.currentIndex() == 0 else "linear"
        self._ax_druck.set_yscale(skala)
        self._ax_druck.set_ylabel("Druck [mbar]")
        fmt = "%H:%M" if self._chk_tage.isChecked() else "%H:%M\n%d.%m"
        self._ax_druck.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
        self._ax_druck.grid(True, which="both", alpha=0.3)
        self._ax_temp.set_ylabel("Temperatur [°C]")
        self._ax_temp.set_xlabel("Tageszeit" if self._chk_tage.isChecked() else "Uhrzeit")
        self._ax_temp.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
        self._ax_temp.grid(True, alpha=0.3)

    # ── Optionen ──────────────────────────────────────────────
    def _alle_temp_toggle(self, state: int):
        for name in TEMP_SENSOREN:
            cb = self._sensor_checks.get(name)
            if cb:
                cb.blockSignals(True)
                cb.setChecked(bool(state))
                cb.blockSignals(False)
        self._neu_zeichnen()

    def _update_grid(self, idx: int):
        for ax in [self._ax_druck, self._ax_temp]:
            ax.grid(False, which="both")
            if idx == 0:
                ax.grid(True, which="major", alpha=0.4)
                ax.grid(True, which="minor", alpha=0.15)
            elif idx == 1:
                ax.grid(True, which="major", alpha=0.4)
        self._canvas.draw_idle()

    def _update_marker(self, state: int):
        marker = "o" if state else "None"
        for ax in [self._ax_druck, self._ax_temp]:
            for line in ax.get_lines():
                line.set_marker(marker)
                line.set_markersize(3)
        self._canvas.draw_idle()

    def _on_scroll(self, event):
        ax = event.inaxes
        if ax not in [self._ax_druck, self._ax_temp] or event.xdata is None:
            return
        faktor = 1.15 if event.step < 0 else 1/1.15
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        xd, yd = event.xdata, event.ydata
        if event.key == "shift":
            ax.set_xlim([xd + (x - xd) * faktor for x in xlim])
        elif event.key == "control":
            ax.set_ylim([yd + (y - yd) * faktor for y in ylim])
        else:
            ax.set_xlim([xd + (x - xd) * faktor for x in xlim])
            ax.set_ylim([yd + (y - yd) * faktor for y in ylim])
        self._canvas.draw_idle()

    def _einstellungen_oeffnen(self):
        from gui.plot_einstellungen import PlotEinstellungenDialog
        dlg = PlotEinstellungenDialog(
            self._ax_druck, self._canvas, self._fig,
            titel="Druckplot – Einstellungen",
            hat_skala=True, parent=self
        )
        dlg.exec()

    def _vsep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFixedWidth(1)
        f.setStyleSheet("color: #2c3a57;")
        return f

    def _btn_style(self, farbe: str) -> str:
        return f"""QPushButton {{
            background: {farbe}; border: none; border-radius: 4px;
            color: white; font-size: 10px; font-weight: 700; padding: 4px 10px;
        }} QPushButton:hover {{ opacity: 0.85; }}"""
