"""
gui/temp_panel.py
Temperaturplot (matplotlib) + Sensor-Checkboxen.
"""

from collections import deque
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QCheckBox, QScrollArea, QComboBox, QSpinBox, QGroupBox, QSizePolicy, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QFrame
)
from PyQt6.QtCore import Qt
from gui.plot_fenster import DetachHelper

import matplotlib
matplotlib.use("QtAgg")
import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavToolbar
from matplotlib.figure import Figure

HISTORY_MAX = 10800

SENSOREN = [
    "Kryo 1 In", "Kryo 1", "Kryo 1b",
    "Peltier", "Peltier b",
    "Kryo 2 In", "Kryo 2", "Kryo 2b",
    "Kryo 3 In", "Kryo 3", "Kryo 3b",
    "Kryo 4 In", "Kryo 4", "Kryo 4b",
    "Kryo 5 In", "Kryo 5", "Kryo 5b",
    "Kryo 6 In", "Kryo 6", "Kryo 6b",
    "Kryo 7 In", "Kryo 7",
    "Kryo 9", "Kryo 9b",
    "Kryo 8 In", "Kryo 8",
]

FARBEN = [
    "#e63946","#f4a261","#2a9d8f","#457b9d","#1d3557",
    "#e76f51","#264653","#e9c46a","#a8dadc","#06d6a0",
    "#118ab2","#ffd166","#ef476f","#073b4c","#3a86ff",
    "#8338ec","#fb5607","#ffbe0b","#ff006e","#06d6a0",
    "#f72585","#7209b7","#3a0ca3","#4361ee","#4cc9f0","#80b918",
]


class TempPanel(QWidget):

    def __init__(self):
        super().__init__()
        self._history_t    = deque(maxlen=HISTORY_MAX)
        self._history_wert = {n: deque(maxlen=HISTORY_MAX) for n in SENSOREN}
        self._lines   = {}
        self._checks       = {}
        self._wert_labels  = {}
        self._theme        = None
        self._einheit       = "°C"
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

        self._fig = Figure(figsize=(8, 3), dpi=100)
        self._fig.patch.set_facecolor("#0f1117")
        self._ax  = self._fig.add_subplot(111)
        self._ax.set_facecolor("#1a1d27")
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._toolbar = NavToolbar(self._canvas, self)
        self._toolbar.setMaximumHeight(44)

        for i, name in enumerate(SENSOREN):
            farbe = FARBEN[i % len(FARBEN)]
            line, = self._ax.plot([], [], color=farbe, lw=1.5, label=name)
            self._lines[name] = line

        self._ax.set_ylabel("Temperatur [°C]", color="#f0f2fa")
        self._einheit_init = "°C"
        
        self._ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m.\n%H:%M:%S"))
        self._ax.tick_params(colors="#f0f2fa", which="both", labelsize=8)
        for spine in self._ax.spines.values():
            spine.set_edgecolor("#3a3f58")
        self._ax.grid(True, color="#3a3f58", linewidth=0.6, alpha=0.5)
        self._fig.tight_layout(pad=0.8)
        self._fig.subplots_adjust(bottom=0.28)

        self._hover_annot = self._ax.annotate(
            "", xy=(0, 0), xytext=(12, 12),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc="#20232e", ec="#4f8ef7",
                      alpha=0.95, lw=1.5),
            fontsize=11, color="#f0f2fa",
            arrowprops=dict(arrowstyle="->", color="#4f8ef7", lw=1.2)
        )
        self._hover_annot.set_visible(False)

        # Toolbar-Zeile mit Pop-out-Button
        toolbar_row = QWidget()
        toolbar_row_layout = QHBoxLayout(toolbar_row)
        toolbar_row_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_row_layout.setSpacing(4)
        toolbar_row_layout.addWidget(self._toolbar, 1)
        self._btn_popout = QPushButton("⇱ Pop-out")
        self._btn_popout.setFixedSize(110, 34)
        self._btn_popout.setToolTip("Plot in eigenem Fenster öffnen")
        self._btn_popout.setStyleSheet("""
            QPushButton { background: #1e2d45; border: 1.5px solid #4a5e80;
                border-radius: 6px; color: #cbd5e1; font-size: 11px; font-weight: 700; }
            QPushButton:hover { background: #2a3f5f; border-color: #7db2ff; color: #fff; }
        """)
        toolbar_row_layout.addWidget(self._btn_popout)
        plot_layout.addWidget(toolbar_row)
        plot_layout.addWidget(self._canvas)
        plot_layout.addWidget(self._build_zeitbereich())
        layout.addWidget(plot_container, 1)

        # DetachHelper nach dem Layout-Aufbau initialisieren
        self._detach_helper = DetachHelper(
            panel=self,
            plot_container=self._plot_container,
            container_layout=layout,
            insert_index=0,
            titel="Temperaturplot",
            btn=self._btn_popout,
        )
        self._btn_popout.clicked.connect(self._detach_helper.toggle)

        self._canvas.mpl_connect("motion_notify_event", self._on_hover)
        self._canvas.mpl_connect("axes_leave_event",    self._on_leave)
        layout.addWidget(self._build_checkboxen(), 0)

    def _build_checkboxen(self) -> QWidget:
        box = QGroupBox("Sensoren")
        box.setFixedWidth(210)
        outer = QVBoxLayout(box)
        outer.setContentsMargins(2, 4, 2, 2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none;")

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(1)
        inner_layout.setContentsMargins(2, 2, 2, 2)

        for i, name in enumerate(SENSOREN):
            farbe = FARBEN[i % len(FARBEN)]

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)

            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.setStyleSheet(f"""
                QCheckBox {{ font-size: 12px; spacing: 4px; }}
                QCheckBox::indicator:checked {{
                    background-color: {farbe}; border-color: {farbe};
                }}
            """)
            cb.stateChanged.connect(lambda s, n=name: self._toggle(n, s))
            self._checks[name] = cb
            row_layout.addWidget(cb, 1)

            val_lbl = QLabel("–")
            val_lbl.setStyleSheet(
                f"font-family: 'Consolas','Courier New'; font-size: 11px; "
                f"color: {farbe}; background: transparent;"
            )
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val_lbl.setFixedWidth(54)
            self._wert_labels[name] = val_lbl
            row_layout.addWidget(val_lbl)

            inner_layout.addWidget(row)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return box

    def _build_zeitbereich(self) -> QWidget:
        widget = QWidget()
        widget.setFixedHeight(38)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(6)

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

        # Trennlinie + Einheit
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet("color: #cbd5e1;")
        layout.addWidget(sep)

        layout.addWidget(QLabel("Einheit:"))
        self._cmb_einheit = QComboBox()
        self._cmb_einheit.addItems(["°C", "K"])
        self._cmb_einheit.setToolTip("Temperatureinheit: Celsius oder Kelvin")
        self._cmb_einheit.currentTextChanged.connect(self._on_einheit)
        layout.addWidget(self._cmb_einheit)

        layout.addStretch()

        btn_einst = QPushButton("⚙ Einstellungen")
        btn_einst.setStyleSheet("""
            QPushButton {
                background: #f1f5f9; border: 1.5px solid #94a3b8;
                border-radius: 4px; color: #334155;
                font-size: 10px; font-weight: 700; padding: 3px 10px;
            }
            QPushButton:hover { border-color: #2563eb; color: #2563eb; }
        """)
        btn_einst.clicked.connect(self._einstellungen_oeffnen)
        btn_einst.setToolTip("Achsengrenzen, Gitter und Darstellungsoptionen")
        layout.addWidget(btn_einst)
        return widget

    def _on_hover(self, event):
        if event.inaxes != self._ax or event.xdata is None or event.ydata is None:
            self._hover_annot.set_visible(False)
            self._canvas.draw_idle()
            return
        try:
            import matplotlib.dates as mdates
            zeit = mdates.num2date(event.xdata).strftime("%d.%m.  %H:%M:%S")
            self._hover_annot.set_text(f"{zeit}\n{event.ydata:.2f} {self._einheit}")
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
            titel="Temperaturplot – Einstellungen",
            hat_skala=False, parent=self
        )
        dlg.exec()

    def _on_modus(self, idx):
        self._minuten.setEnabled(idx == 1)
        self._update_plot()

    def _on_einheit(self, einheit: str):
        self._einheit = einheit
        self._ax.set_ylabel(f"Temperatur [{einheit}]")
        self._update_plot()

    def _toggle(self, name: str, state: int):
        self._lines[name].set_visible(bool(state))
        self._canvas.draw_idle()

    def apply_theme(self, t: dict):
        self._theme = t
        self._fig.patch.set_facecolor(t["bg"])
        self._ax.set_facecolor(t["panel"])
        self._ax.tick_params(colors=t["text"], which="both", labelsize=8)
        self._ax.xaxis.label.set_color(t["text"])
        self._ax.yaxis.label.set_color(t["text"])
        for spine in self._ax.spines.values():
            spine.set_edgecolor(t["border"])
        self._ax.grid(True, color=t["border"], linewidth=0.6, alpha=0.5)
        # Legende stylen
        dark = t.get("bg") == "#0f1117"
        leg = self._ax.get_legend()
        if leg:
            leg.get_frame().set_facecolor("#1a1d27" if dark else "#ffffff")
            leg.get_frame().set_edgecolor("#3a3f58" if dark else "#c0c5d4")
            for txt in leg.get_texts():
                txt.set_color("#f0f2fa" if dark else "#12151f")

        self._canvas.draw_idle()
        from gui.themes import matplotlib_toolbar_style
        matplotlib_toolbar_style(self._toolbar, dark=dark)

    def aktualisieren(self, werte: dict):
        jetzt = datetime.now()
        self._history_t.append(jetzt)
        for name in SENSOREN:
            d   = werte.get(name, {})
            val = d.get("celsius") if d and d.get("gueltig") else None
            self._history_wert[name].append(val)
            if name in self._wert_labels:
                if val is not None:
                    v = val + 273.15 if self._einheit == "K" else val
                    self._wert_labels[name].setText(f"{v:.1f} {self._einheit}")
                else:
                    self._wert_labels[name].setText("–")
        self._update_plot()

    def get_tages_daten(self) -> dict:
        """
        Gibt alle Temperaturdaten des heutigen Tages zurück,
        konvertiert für pdf_report: Unix-Timestamps + Kelvin-Werte.
        Nur Sensoren mit mindestens einem gültigen Messwert werden
        ins Ergebnis aufgenommen.
        """
        jetzt     = datetime.now()
        tag_start = jetzt.replace(hour=0, minute=0, second=0, microsecond=0)

        t_list = list(self._history_t)
        idx    = [i for i, t in enumerate(t_list) if t >= tag_start]

        zeiten = [t_list[i].timestamp() for i in idx]

        ergebnis: dict = {"zeiten": zeiten}
        for name in SENSOREN:
            puffer = list(self._history_wert[name])
            werte  = []
            hat_wert = False
            for i in idx:
                val = puffer[i]
                if val is not None:
                    werte.append(val + 273.15)   # °C → K
                    hat_wert = True
                else:
                    werte.append(None)
            if hat_wert:
                ergebnis[name] = werte

        return ergebnis

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
            if not self._checks[name].isChecked():
                continue
            y_all = list(self._history_wert[name])
            y     = [y_all[i] for i in idx]
            xc    = [x[j] for j, v in enumerate(y) if v is not None]
            yc    = [v + 273.15 if self._einheit == "K" and v is not None else v
                     for v in y if v is not None]
            if xc:
                line.set_data(xc, yc)
                updated = True

        if updated:
            self._ax.relim()
            self._ax.autoscale_view()
            self._fig.autofmt_xdate(rotation=30, ha="right")
            self._canvas.draw_idle()
