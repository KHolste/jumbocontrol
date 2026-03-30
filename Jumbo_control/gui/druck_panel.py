"""
gui/druck_panel.py
Druckplot (matplotlib) + Anzeigeelemente für CENTER, DOOR, BA.
Hover-Annotation + Klick-Tabelle für Wertanzeige.
"""

import time
from collections import deque
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QGroupBox, QComboBox, QSpinBox, QSizePolicy, QCheckBox,
    QDoubleSpinBox, QRadioButton, QFrame, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from gui.plot_fenster import DetachHelper

import matplotlib
matplotlib.use("QtAgg")
import matplotlib.dates as mdates
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavToolbar
from matplotlib.figure import Figure

HISTORY_MAX = 10800

SENSOR_FARBEN = {"CENTER": "#e63946", "DOOR": "#f4a261", "BA": "#2a9d8f"}

EINHEITEN = {
    "mbar": 1.0,
    "hPa":  1.0,
    "Pa":   100.0,
    "Torr": 0.750062,
}

OVERRANGE_MBAR = 1013.25


class DruckPanel(QWidget):
    kalib_geoeffnet       = pyqtSignal()
    grossanzeige_anfordern = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._history_t      = deque(maxlen=HISTORY_MAX)
        self._history_wert   = {n: deque(maxlen=HISTORY_MAX) for n in SENSOR_FARBEN}
        self._history_status = {n: deque(maxlen=HISTORY_MAX) for n in SENSOR_FARBEN}
        self._lines          = {}
        self._theme          = None
        self._einheit        = "mbar"
        self._alarm_aktiv    = False
        self._alarm_grenze   = 1e-3
        self._blink_state    = False
        self._blink_timer    = QTimer()
        self._blink_timer.timeout.connect(self._blink)
        self._blink_timer.setInterval(500)
        self._alarmierende   = set()
        self._detach_helper = None
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._plot_container = QWidget()
        plot_container = self._plot_container
        plot_layout = QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.setSpacing(2)

        # ── Figure ────────────────────────────────────────────
        self._fig = Figure(figsize=(8, 2.5), dpi=100)
        self._fig.patch.set_facecolor("#0f1520")
        self._ax  = self._fig.add_subplot(111)
        self._ax.set_facecolor("#151d2e")
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._toolbar = NavToolbar(self._canvas, self)
        self._toolbar.setMaximumHeight(44)

        for name, farbe in SENSOR_FARBEN.items():
            line, = self._ax.semilogy([], [], color=farbe, lw=1.8, label=name)
            self._lines[name] = line

        self._ax.set_ylabel("Druck [mbar]", color="#f0f2fa")
        
        self._ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m.\n%H:%M:%S"))
        self._ax.tick_params(colors="#f0f2fa", which="both", labelsize=8)
        for spine in self._ax.spines.values():
            spine.set_edgecolor("#3a3f58")
        self._ax.grid(True, color="#3a3f58", linewidth=0.6, alpha=0.5)
        self._ax.set_ylim(1e-7, 5e3)
        self._fig.tight_layout(pad=0.8)
        self._fig.subplots_adjust(bottom=0.28)

        # ── Hover-Annotation ──────────────────────────────────
        self._hover_annot = self._ax.annotate(
            "", xy=(0, 0), xytext=(12, 12),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc="#20232e", ec="#4f8ef7",
                      alpha=0.95, lw=1.5),
            fontsize=11, color="#f0f2fa",
            arrowprops=dict(arrowstyle="->", color="#4f8ef7", lw=1.2)
        )
        self._hover_annot.set_visible(False)

        # ── Maus-Events ───────────────────────────────────────
        self._canvas.mpl_connect("motion_notify_event", self._on_hover)
        self._canvas.mpl_connect("axes_leave_event",    self._on_leave)
        self._canvas.mpl_connect("figure_leave_event",  self._on_leave)

        toolbar_row = QWidget()
        toolbar_row_layout = QHBoxLayout(toolbar_row)
        toolbar_row_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_row_layout.setSpacing(4)
        toolbar_row_layout.addWidget(self._toolbar, 1)

        # Alarm-Controls (aus der Steuerungsleiste hierher verschoben)
        self._chk_alarm = QCheckBox("Alarm ≥")
        self._chk_alarm.stateChanged.connect(self._on_alarm)
        self._chk_alarm.setToolTip("Alarm aktivieren wenn Druck den Grenzwert überschreitet")
        toolbar_row_layout.addWidget(self._chk_alarm)
        self._spn_alarm = QLineEdit("1e-3")
        self._spn_alarm.setPlaceholderText("z.B. 1e-5")
        self._spn_alarm.setFixedWidth(80)
        self._spn_alarm.setEnabled(False)
        self._spn_alarm.setToolTip("Alarmgrenze in mbar (z.B. 1e-5, 0.001)")
        self._spn_alarm.textChanged.connect(self._alarm_grenze_setzen)
        toolbar_row_layout.addWidget(self._spn_alarm)
        toolbar_row_layout.addWidget(QLabel("mbar"))

        # Kalibrierung-Button (aus der Steuerungsleiste hierher verschoben)
        btn_kalib = QPushButton("Kalibrierung")
        btn_kalib.setStyleSheet("""
            QPushButton {
                background: #4f8ef7; border: none; border-radius: 4px;
                color: white; font-size: 10px; font-weight: 700; padding: 3px 10px;
            }
            QPushButton:hover { background: #2563eb; }
        """)
        btn_kalib.clicked.connect(self.kalib_geoeffnet.emit)
        btn_kalib.setToolTip("Fenster mit kalibrierten Druckwerten öffnen")
        toolbar_row_layout.addWidget(btn_kalib)

        self._btn_popout = QPushButton("⇱ Pop-out")
        self._btn_popout.setFixedSize(90, 30)
        self._btn_popout.setToolTip("Plot in eigenem Fenster öffnen")
        self._btn_popout.setStyleSheet("""
            QPushButton { background: #1e2d45; border: 1px solid #344868;
                border-radius: 5px; color: #94a3bf; font-size: 10px; font-weight: 700; }
            QPushButton:hover { background: #2a3f5f; border-color: #6ea8f7; color: #fff; }
        """)
        toolbar_row_layout.addWidget(self._btn_popout)
        plot_layout.addWidget(toolbar_row)
        plot_layout.addWidget(self._canvas)
        plot_layout.addWidget(self._build_steuerung())
        layout.addWidget(plot_container, 1)

        self._detach_helper = DetachHelper(
            panel=self,
            plot_container=self._plot_container,
            container_layout=layout,
            insert_index=0,
            titel="Druckplot",
            btn=self._btn_popout,
        )
        self._btn_popout.clicked.connect(self._detach_helper.toggle)
        layout.addWidget(self._build_anzeigen(), 0)

    def _build_steuerung(self) -> QWidget:
        widget = QWidget()
        widget.setFixedHeight(34)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Zeitbereich:"))
        self._modus = QComboBox()
        self._modus.addItems(["Live (läuft durch)", "Letzten X Minuten"])
        self._modus.setToolTip("Zeitfenster: Live läuft kontinuierlich mit,\nbei X Minuten wird ein festes Zeitfenster angezeigt")
        self._modus.currentIndexChanged.connect(self._on_modus)
        layout.addWidget(self._modus)
        self._minuten = QSpinBox()
        self._minuten.setRange(1, 180)
        self._minuten.setValue(30)
        self._minuten.setSuffix(" min")
        self._minuten.setToolTip("Anzahl der angezeigten Minuten im Plot")
        self._minuten.setEnabled(False)
        self._minuten.valueChanged.connect(self._update_plot)
        layout.addWidget(self._minuten)

        layout.addWidget(self._vsep())
        layout.addWidget(QLabel("Einheit:"))
        self._cmb_einheit = QComboBox()
        self._cmb_einheit.addItems(["mbar", "hPa", "Pa", "Torr"])
        self._cmb_einheit.setToolTip("Druckeinheit für Anzeige und Plot")
        self._cmb_einheit.currentTextChanged.connect(self._on_einheit)
        layout.addWidget(self._cmb_einheit)

        layout.addWidget(self._vsep())
        layout.addWidget(QLabel("Skala:"))
        self._rb_log = QRadioButton("Log")
        self._rb_lin = QRadioButton("Linear")
        self._rb_log.setChecked(True)
        self._rb_log.setToolTip("Logarithmische Y-Achse (empfohlen für Vakuummessungen)")
        self._rb_lin.setToolTip("Lineare Y-Achse")
        self._rb_log.toggled.connect(self._on_skala)
        layout.addWidget(self._rb_log)
        layout.addWidget(self._rb_lin)

        layout.addWidget(self._vsep())
        btn_einst = QPushButton("⚙ Einstellungen")
        btn_einst.setStyleSheet("""
            QPushButton {
                background: #f1f5f9; border: 1px solid #94a3b8;
                border-radius: 4px; color: #334155;
                font-size: 10px; font-weight: 600; padding: 3px 10px;
            }
            QPushButton:hover { border-color: #2563eb; color: #2563eb; }
        """)
        btn_einst.clicked.connect(self._einstellungen_oeffnen)
        btn_einst.setToolTip("Achsengrenzen, Gitter und Darstellungsoptionen")
        layout.addWidget(btn_einst)

        layout.addStretch()
        return widget

    def _vsep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFixedWidth(1)
        # Erbt Farbe aus globalem Theme-Stylesheet (border-Farbe via palette)
        f.setStyleSheet("color: palette(mid);")
        return f

    def _build_anzeigen(self) -> QWidget:
        widget = QWidget()
        widget.setFixedWidth(200)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(10)

        # Großanzeige-Button
        btn_gross = QPushButton("⊞ Großanzeige")
        btn_gross.setToolTip("Druckwerte in separatem Fenster groß darstellen")
        btn_gross.setStyleSheet("""
            QPushButton {
                background: #1e2d45; border: 1.5px solid #4a5e80;
                border-radius: 5px; color: #cbd5e1;
                font-size: 10px; font-weight: 700; padding: 4px 8px;
            }
            QPushButton:hover { background: #2a3f5f; border-color: #7db2ff; color: #fff; }
        """)
        btn_gross.clicked.connect(self.grossanzeige_anfordern.emit)
        layout.addWidget(btn_gross)

        self._anzeigen = {}
        for name, farbe in SENSOR_FARBEN.items():
            box = QGroupBox(name)
            box.setStyleSheet(f"""
                QGroupBox {{
                    font-size: 11px; font-weight: bold;
                    color: {farbe}; border: none;
                    border-top: 3px solid {farbe};
                    border-left: 1px solid {farbe}33;
                    border-radius: 3px;
                    margin-top: 12px; padding-top: 8px;
                    background: #1b253888;
                }}
                QGroupBox::title {{ subcontrol-origin: margin; left: 6px; color: {farbe}; font-size: 11px; }}
            """)
            b_layout = QVBoxLayout(box)
            b_layout.setContentsMargins(6, 4, 6, 6)
            lbl = QLabel("---")
            lbl.setStyleSheet(
                f"font-family: 'Consolas','Courier New'; font-size: 26px; "
                f"font-weight: bold; color: {farbe}; background: transparent;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b_layout.addWidget(lbl)
            status = QLabel("")
            status.setStyleSheet(
                f"font-size: 10px; color: #a0a8c0; background: transparent; font-weight: 600;"
            )
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b_layout.addWidget(status)
            self._anzeigen[name] = (lbl, status, farbe, box)
            layout.addWidget(box)

        layout.addStretch()
        return widget

    # ── Hover & Klick ─────────────────────────────────────────
    def _on_hover(self, event):
        if event.inaxes != self._ax or event.xdata is None or event.ydata is None:
            self._hover_annot.set_visible(False)
            self._canvas.draw_idle()
            return
        try:
            zeit = mdates.num2date(event.xdata).strftime("%d.%m.  %H:%M:%S")
            wert = self._umrechnen(event.ydata)
            self._hover_annot.set_text(f"{zeit}\n{wert:.3E} {self._einheit}")
            self._hover_annot.xy = (event.xdata, event.ydata)
            self._hover_annot.set_visible(True)
        except Exception:
            self._hover_annot.set_visible(False)
        self._canvas.draw_idle()

    def _on_leave(self, event):
        self._hover_annot.set_visible(False)
        self._canvas.draw_idle()

    def _einstellungen_oeffnen(self):
        from gui.plot_einstellungen import PlotEinstellungenDialog
        dlg = PlotEinstellungenDialog(
            self._ax, self._canvas, self._fig,
            titel="Druckplot – Einstellungen",
            hat_skala=True, parent=self
        )
        dlg.exec()

    def _alarm_grenze_setzen(self, text: str):
        try:
            wert = float(text.replace(",", "."))
            self._alarm_grenze = wert
            self._spn_alarm.setStyleSheet("")
        except ValueError:
            self._spn_alarm.setStyleSheet("border: 1px solid red;")

    def _on_modus(self, idx):
        self._minuten.setEnabled(idx == 1)
        self._update_plot()

    def _on_einheit(self, einheit: str):
        self._einheit = einheit
        self._ax.set_ylabel(f"Druck [{einheit}]")
        self._update_plot()

    def _on_skala(self, log: bool):
        self._ax.set_yscale("log" if log else "linear")
        self._canvas.draw_idle()

    def _on_alarm(self, state: int):
        self._alarm_aktiv = bool(state)
        self._spn_alarm.setEnabled(self._alarm_aktiv)
        if not self._alarm_aktiv:
            self._blink_timer.stop()
            self._alarmierende.clear()
            self._blink_reset()

    def _blink(self):
        self._blink_state = not self._blink_state
        for name in self._alarmierende:
            if name in self._anzeigen:
                lbl, _, farbe, _ = self._anzeigen[name]
                bg  = farbe if self._blink_state else "transparent"
                col = "#fff" if self._blink_state else farbe
                lbl.setStyleSheet(
                    f"font-family: 'Consolas','Courier New'; font-size: 26px; font-weight: bold; color: {col}; background: {bg}; border-radius: 3px;"
                )

    def _blink_reset(self):
        for name, (lbl, _, farbe, _) in self._anzeigen.items():
            lbl.setStyleSheet(
                f"font-family: 'Consolas','Courier New'; font-size: 26px; "
                f"font-weight: bold; color: {farbe}; background: transparent;"
            )

    def _umrechnen(self, mbar: float) -> float:
        return mbar * EINHEITEN.get(self._einheit, 1.0)

    def apply_theme(self, t: dict):
        self._theme = t
        dark = t.get("bg", "").startswith("#0") or t.get("bg", "").startswith("#1")
        bg    = t["bg"]
        panel = t["panel"]
        text  = t["text"]
        grid  = t["border"]
        self._fig.patch.set_facecolor(bg)
        self._ax.set_facecolor(panel)
        self._ax.tick_params(colors=text, which="both", labelsize=8)
        self._ax.xaxis.label.set_color(text)
        self._ax.yaxis.label.set_color(text)
        for spine in self._ax.spines.values():
            spine.set_edgecolor(grid)
        self._ax.grid(True, color=grid, linewidth=0.6, alpha=0.5)
        leg = self._ax.get_legend()
        if leg:
            leg.get_frame().set_facecolor(panel if dark else "#ffffff")
            leg.get_frame().set_edgecolor(grid if dark else "#c9d3e2")
            for txt in leg.get_texts():
                txt.set_color(text)
        self._canvas.draw_idle()
        from gui.themes import matplotlib_toolbar_style
        matplotlib_toolbar_style(self._toolbar, dark=dark)

    def aktualisieren(self, werte: dict):
        if "CENT" in werte and "CENTER" not in werte:
            werte["CENTER"] = werte.pop("CENT")

        jetzt = datetime.now()
        self._history_t.append(jetzt)

        neue_alarme = set()
        for name in SENSOR_FARBEN:
            d      = werte.get(name, {})
            status = d.get("status", "") if d else ""
            val    = d.get("mbar") if d and d.get("gueltig") else None

            is_overrange = status in ("Overrange", "Underrange", "Sensor error",
                                      "Sensor off", "No sensor", "Identification error") \
                           or (val is None and status)
            plot_val = val if val is not None else (OVERRANGE_MBAR if is_overrange else None)
            self._history_wert[name].append(plot_val)
            self._history_status[name].append(status)

            lbl, status_lbl, farbe, _ = self._anzeigen[name]

            if is_overrange:
                lbl.setText("Overrange")
                status_lbl.setText(status)
                if self._alarm_aktiv:
                    neue_alarme.add(name)
            elif val is not None:
                lbl.setText(f"{self._umrechnen(val):.2E}")
                status_lbl.setText(self._einheit)
                if self._alarm_aktiv and val >= self._alarm_grenze:
                    neue_alarme.add(name)
            else:
                lbl.setText("---")
                status_lbl.setText(status)

        if neue_alarme:
            self._alarmierende = neue_alarme
            if not self._blink_timer.isActive():
                self._blink_timer.start()
        else:
            self._alarmierende.clear()
            self._blink_timer.stop()
            self._blink_reset()

        self._update_plot()

    def get_tages_daten(self) -> dict:
        """
        Gibt alle Druckdaten des heutigen Tages zurück,
        konvertiert für pdf_report: Unix-Timestamps + Pa-Werte.
        Overrange / None → OVERRANGE_MBAR * 100 Pa (= 1013 hPa).
        """
        jetzt      = datetime.now()
        tag_start  = jetzt.replace(hour=0, minute=0, second=0, microsecond=0)

        t_list = list(self._history_t)
        idx    = [i for i, t in enumerate(t_list) if t >= tag_start]

        zeiten = [t_list[i].timestamp() for i in idx]

        def _kanal(name: str) -> list:
            puffer = list(self._history_wert[name])
            ergebnis = []
            for i in idx:
                val = puffer[i]
                if val is None:
                    ergebnis.append(OVERRANGE_MBAR * 100.0)   # Pa
                else:
                    ergebnis.append(val * 100.0)               # mbar → Pa
            return ergebnis

        return {
            "zeiten": zeiten,
            "door":   _kanal("DOOR"),
            "center": _kanal("CENTER"),
            "ba":     _kanal("BA"),
        }

    def _update_plot(self):
        if not self._history_t:
            return

        t_list = list(self._history_t)
        jetzt  = datetime.now()

        if self._modus.currentIndex() == 1:
            t_min = jetzt - timedelta(minutes=self._minuten.value())
            idx   = [i for i, t in enumerate(t_list) if t >= t_min]
        else:
            idx = list(range(len(t_list)))

        if not idx:
            return

        x = [t_list[i] for i in idx]
        updated = False

        for name, line in self._lines.items():
            y_all = list(self._history_wert[name])
            y     = [y_all[i] for i in idx]
            xc    = [x[j] for j, v in enumerate(y) if v is not None and v > 0]
            yc    = [self._umrechnen(v) for v in y if v is not None and v > 0]
            if xc:
                line.set_data(xc, yc)
                updated = True

        if updated:
            self._ax.relim()
            self._ax.autoscale_view(scaley=False)
            self._fig.autofmt_xdate(rotation=30, ha="right")
            self._canvas.draw_idle()
