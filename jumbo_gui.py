"""
Kryostat Control GUI – PyQt6
Benötigt: pip install PyQt6 pyqtgraph

Dummy-Modus: läuft ohne cDAQ-Hardware
Live-Modus:  LIVE_MODUS = True setzen (benötigt nidaqmx)
"""

import sys
import math
import random
from collections import deque
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QCheckBox, QComboBox,
    QLineEdit, QGroupBox, QSplitter, QFrame, QScrollArea,
    QSizePolicy, QStatusBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette, QFontDatabase

import pyqtgraph as pg

# ── Konfiguration ──────────────────────────────────────────────
LIVE_MODUS      = False        # True = echte cDAQ-Messung
GERAET_NAME     = "cDAQ9188-Jumbo"
UPDATE_INTERVAL = 2000         # ms
HISTORY_LEN     = 120          # Datenpunkte im Chart

# Farben (wie LabVIEW)
FARBEN = {
    "bg":       "#0d1117",
    "bg2":      "#161b22",
    "bg3":      "#1c2333",
    "border":   "#30363d",
    "accent":   "#00d4ff",
    "green":    "#39d353",
    "orange":   "#f78166",
    "yellow":   "#e3b341",
    "red":      "#ff4444",
    "text":     "#c9d1d9",
    "dim":      "#6e7681",
}

SENSOR_FARBEN = [
    "#39d353", "#f78166", "#e3b341", "#79c0ff",
    "#d2a8ff", "#ffa657", "#58a6ff", "#bc8cff",
    "#ff7b72", "#56d364", "#f0c040", "#6e7681",
]

# Sensornamen (wie im LabVIEW-Frontpanel)
TEMP_SENSOREN = [
    "Kryo 1 In", "Kryo 1", "Kryo 1b",
    "Peltier",   "Peltier b",
    "Kryo 2 In", "Kryo 2", "Kryo 2b",
    "Kryo 3 In", "Kryo 3", "Kryo 3b",
    "NC",
]

DRUCK_SENSOREN = ["CENT", "DOOR", "MASS", "BA"]


# ── Stylesheet ─────────────────────────────────────────────────
def make_stylesheet():
    return f"""
    QMainWindow, QWidget {{
        background-color: {FARBEN['bg']};
        color: {FARBEN['text']};
        font-family: 'Exo 2', 'Segoe UI', sans-serif;
        font-size: 12px;
    }}
    QGroupBox {{
        border: 1px solid {FARBEN['border']};
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 6px;
        font-size: 10px;
        color: {FARBEN['accent']};
        letter-spacing: 2px;
        text-transform: uppercase;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 8px;
        color: {FARBEN['accent']};
    }}
    QLabel {{
        color: {FARBEN['text']};
    }}
    QLabel#value {{
        font-family: 'Share Tech Mono', 'Courier New', monospace;
        font-size: 20px;
        color: {FARBEN['accent']};
        background: {FARBEN['bg3']};
        border: 1px solid {FARBEN['border']};
        border-radius: 3px;
        padding: 4px 8px;
    }}
    QLabel#small_value {{
        font-family: 'Courier New', monospace;
        font-size: 11px;
        color: {FARBEN['accent']};
        min-width: 70px;
    }}
    QLabel#dim {{
        color: {FARBEN['dim']};
        font-size: 10px;
    }}
    QPushButton {{
        background: {FARBEN['bg3']};
        border: 1px solid {FARBEN['border']};
        border-radius: 3px;
        padding: 6px 12px;
        color: {FARBEN['text']};
        font-family: 'Courier New', monospace;
        font-size: 10px;
        letter-spacing: 1px;
    }}
    QPushButton:hover {{
        border-color: {FARBEN['accent']};
        color: {FARBEN['accent']};
    }}
    QPushButton#red {{
        background: rgba(255,68,68,0.15);
        border-color: {FARBEN['red']};
        color: {FARBEN['red']};
    }}
    QPushButton#red:hover {{
        background: {FARBEN['red']};
        color: white;
    }}
    QPushButton#green {{
        background: rgba(57,211,83,0.15);
        border-color: {FARBEN['green']};
        color: {FARBEN['green']};
    }}
    QPushButton#green:hover {{
        background: {FARBEN['green']};
        color: black;
    }}
    QPushButton#blue {{
        background: rgba(0,212,255,0.1);
        border-color: {FARBEN['accent']};
        color: {FARBEN['accent']};
    }}
    QPushButton#blue:hover {{
        background: {FARBEN['accent']};
        color: black;
    }}
    QLineEdit {{
        background: {FARBEN['bg3']};
        border: 1px solid {FARBEN['border']};
        border-radius: 3px;
        padding: 4px 6px;
        color: {FARBEN['accent']};
        font-family: 'Courier New', monospace;
        font-size: 10px;
    }}
    QLineEdit:focus {{
        border-color: {FARBEN['accent']};
    }}
    QComboBox {{
        background: {FARBEN['bg3']};
        border: 1px solid {FARBEN['border']};
        border-radius: 3px;
        padding: 4px 6px;
        color: {FARBEN['text']};
        font-size: 10px;
    }}
    QScrollArea {{
        border: none;
    }}
    QCheckBox {{
        color: {FARBEN['text']};
        font-size: 11px;
        spacing: 6px;
    }}
    QCheckBox::indicator {{
        width: 12px;
        height: 12px;
        border: 1px solid {FARBEN['border']};
        border-radius: 2px;
        background: {FARBEN['bg3']};
    }}
    QCheckBox::indicator:checked {{
        background: {FARBEN['accent']};
        border-color: {FARBEN['accent']};
    }}
    QStatusBar {{
        background: {FARBEN['bg2']};
        border-top: 1px solid {FARBEN['border']};
        font-family: 'Courier New', monospace;
        font-size: 10px;
        color: {FARBEN['dim']};
    }}
    QSplitter::handle {{
        background: {FARBEN['border']};
        width: 1px;
        height: 1px;
    }}
    """


# ── Dummy-Datengenerator ───────────────────────────────────────
class DummyDaten:
    def __init__(self):
        self.temp_base = [269.2, 274.0, 273.8, 293.2, 292.6,
                          262.8, 267.3, 267.7, 258.5, 270.4, 270.3, None]
        self.druck_base = [9.95, 9.48, 0.0403, 11.0]

    def lese_temperaturen(self):
        result = {}
        for i, name in enumerate(TEMP_SENSOREN):
            base = self.temp_base[i]
            if base is None:
                result[name] = None
            else:
                result[name] = base + random.uniform(-0.5, 0.5)
        return result

    def lese_druecke(self):
        result = {}
        for i, name in enumerate(DRUCK_SENSOREN):
            result[name] = self.druck_base[i] * (1 + random.uniform(-0.01, 0.01))
        return result


# ── Live-Datengenerator (nidaqmx) ─────────────────────────────
class LiveDaten:
    def __init__(self):
        import nidaqmx
        from nidaqmx.system import System
        from nidaqmx.constants import ResistanceConfiguration, ExcitationSource, ResistanceUnits
        self.nidaqmx = nidaqmx
        self.ResistanceConfiguration = ResistanceConfiguration
        self.ExcitationSource = ExcitationSource
        self.ResistanceUnits = ResistanceUnits

        system = System.local()
        chassis = system.devices[GERAET_NAME]
        try:
            chassis.reserve_network_device(override_reservation=False)
        except Exception:
            pass

        self.module = [
            "cDAQ9188-JumboMod1", "cDAQ9188-JumboMod2",
            "cDAQ9188-JumboMod3", "cDAQ9188-JumboMod4",
            "cDAQ9188-JumboMod5",
        ]

    def cvd(self, R):
        """Callendar-Van Dusen → Temperatur in °C"""
        A, B = 0.39083, 5.775e-5
        inhalt = A**2 + 4 * B * (100 - R)
        if inhalt < 0:
            return None
        t = (-A + math.sqrt(inhalt)) / (-2 * B)
        return t if -300 <= t <= 100 else None

    def lese_temperaturen(self):
        kanaele = [f"{m}/ai{k}" for m in self.module for k in range(8)]
        result = {}
        try:
            with self.nidaqmx.Task() as task:
                for k in kanaele:
                    task.ai_channels.add_ai_resistance_chan(
                        physical_channel=k, min_val=0, max_val=200,
                        units=self.ResistanceUnits.OHMS,
                        resistance_config=self.ResistanceConfiguration.FOUR_WIRE,
                        current_excit_source=self.ExcitationSource.INTERNAL,
                        current_excit_val=0.001,
                    )
                werte = task.read(number_of_samples_per_channel=2)
                for i, k in enumerate(kanaele):
                    R = sum(werte[i]) / 2
                    result[k] = self.cvd(R)
        except Exception as e:
            print(f"[FEHLER] Temperaturmessung: {e}")
        return result

    def lese_druecke(self):
        return {name: None for name in DRUCK_SENSOREN}


# ── Haupt-GUI ──────────────────────────────────────────────────
class KryostatGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kryostat Control System")
        self.resize(1400, 800)

        # Datenquelle
        self.daten = DummyDaten() if not LIVE_MODUS else LiveDaten()

        # History-Buffer für Charts
        self.temp_history  = {n: deque([None]*HISTORY_LEN, maxlen=HISTORY_LEN)
                               for n in TEMP_SENSOREN}
        self.druck_history = {n: deque([None]*HISTORY_LEN, maxlen=HISTORY_LEN)
                               for n in DRUCK_SENSOREN}

        self._build_ui()
        self._apply_chart_style()

        # Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self._update)
        self.timer.start(UPDATE_INTERVAL)

        # Uhr
        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)
        self._update_clock()

        # Erste Messung
        self._update()

    # ── UI aufbauen ───────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Linke Spalte: Sensoren
        main_layout.addWidget(self._build_sensor_panel(), 0)

        # Mitte: Charts
        main_layout.addWidget(self._build_chart_panel(), 1)

        # Rechte Spalte: Controls
        main_layout.addWidget(self._build_control_panel(), 0)

        # Statusbar
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.lbl_status = QLabel("● VERBUNDEN  |  cDAQ9188-Jumbo  |  " +
                                  ("LIVE" if LIVE_MODUS else "DUMMY-MODUS"))
        self.lbl_status.setStyleSheet(f"color: {'#39d353' if LIVE_MODUS else '#e3b341'}")
        self.lbl_clock = QLabel()
        self.lbl_clock.setStyleSheet("font-family: 'Courier New'; color: #6e7681;")
        self.statusbar.addWidget(self.lbl_status)
        self.statusbar.addPermanentWidget(self.lbl_clock)

        # Footer-Buttons
        self._build_footer(main_layout)

    def _build_sensor_panel(self):
        panel = QGroupBox("Sensoren")
        layout = QVBoxLayout(panel)
        panel.setFixedWidth(230)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(2)

        # Drucksensoren
        druck_box = QGroupBox("Druck [mbar]")
        druck_layout = QVBoxLayout(druck_box)
        self.druck_labels = {}
        self.druck_checks = {}
        for i, name in enumerate(DRUCK_SENSOREN):
            row = QHBoxLayout()
            cb = QCheckBox()
            cb.setChecked(name != "MASS")
            self.druck_checks[name] = cb
            cb.stateChanged.connect(lambda _, n=name: self._toggle_druck_kurve(n))

            farbfeld = QLabel("──")
            farbfeld.setStyleSheet(f"color: {SENSOR_FARBEN[i]}; font-size:10px;")
            farbfeld.setFixedWidth(20)

            lbl_name = QLabel(name)
            lbl_name.setFixedWidth(45)

            lbl_val = QLabel("---")
            lbl_val.setObjectName("small_value")
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.druck_labels[name] = lbl_val

            row.addWidget(cb)
            row.addWidget(farbfeld)
            row.addWidget(lbl_name)
            row.addWidget(lbl_val)
            druck_layout.addLayout(row)

        inner_layout.addWidget(druck_box)

        # Temperatursensoren
        temp_box = QGroupBox("Temperatur [K]")
        temp_layout = QVBoxLayout(temp_box)
        self.temp_labels = {}
        self.temp_checks = {}
        for i, name in enumerate(TEMP_SENSOREN):
            row = QHBoxLayout()
            cb = QCheckBox()
            cb.setChecked(name not in ["Peltier", "Peltier b", "NC"])
            self.temp_checks[name] = cb
            cb.stateChanged.connect(lambda _, n=name: self._toggle_temp_kurve(n))

            farbfeld = QLabel("──")
            farbfeld.setStyleSheet(f"color: {SENSOR_FARBEN[i]}; font-size:10px;")
            farbfeld.setFixedWidth(20)

            lbl_name = QLabel(name)
            lbl_name.setFixedWidth(60)
            lbl_name.setStyleSheet("font-size:11px;")

            lbl_val = QLabel("---")
            lbl_val.setObjectName("small_value")
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.temp_labels[name] = lbl_val

            row.addWidget(cb)
            row.addWidget(farbfeld)
            row.addWidget(lbl_name)
            row.addWidget(lbl_val)
            temp_layout.addLayout(row)

        inner_layout.addWidget(temp_box)
        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll)
        return panel

    def _build_chart_panel(self):
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Druckchart
        self.druck_plot = pg.PlotWidget(title="Druck [mbar]")
        self.druck_kurven = {}
        for i, name in enumerate(DRUCK_SENSOREN):
            kurve = self.druck_plot.plot(
                pen=pg.mkPen(color=SENSOR_FARBEN[i], width=1.5),
                name=name
            )
            self.druck_kurven[name] = kurve

        # Temperaturchart
        self.temp_plot = pg.PlotWidget(title="Temperatur [°C]")
        self.temp_kurven = {}
        for i, name in enumerate(TEMP_SENSOREN):
            kurve = self.temp_plot.plot(
                pen=pg.mkPen(color=SENSOR_FARBEN[i], width=1.5),
                name=name
            )
            self.temp_kurven[name] = kurve

        splitter.addWidget(self.druck_plot)
        splitter.addWidget(self.temp_plot)
        splitter.setSizes([300, 300])
        return splitter

    def _apply_chart_style(self):
        bg = pg.mkColor(FARBEN['bg'])
        fg = pg.mkColor(FARBEN['dim'])

        for plot in [self.druck_plot, self.temp_plot]:
            plot.setBackground(FARBEN['bg'])
            plot.getAxis('left').setPen(fg)
            plot.getAxis('bottom').setPen(fg)
            plot.getAxis('left').setTextPen(fg)
            plot.getAxis('bottom').setTextPen(fg)
            plot.showGrid(x=True, y=True, alpha=0.15)
            plot.addLegend(offset=(10, 10))

        self.druck_plot.setLabel('left', 'mbar')
        self.temp_plot.setLabel('left', '°C')

    def _build_control_panel(self):
        panel = QWidget()
        panel.setFixedWidth(200)
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)

        # Readouts
        readout_box = QGroupBox("Readouts")
        readout_layout = QVBoxLayout(readout_box)
        self.readout_labels = {}
        for name in ["Center", "Door", "BA"]:
            lbl_title = QLabel(name)
            lbl_title.setObjectName("dim")
            lbl_val = QLabel("0E+0")
            lbl_val.setObjectName("value")
            self.readout_labels[name] = lbl_val
            readout_layout.addWidget(lbl_title)
            readout_layout.addWidget(lbl_val)
        layout.addWidget(readout_box)

        # Zeitsteuerung
        zeit_box = QGroupBox("Zeitsteuerung")
        zeit_layout = QGridLayout(zeit_box)
        zeit_layout.addWidget(QLabel("Start"), 0, 0)
        self.edit_start = QLineEdit("14:23  23/12/2012")
        zeit_layout.addWidget(self.edit_start, 1, 0, 1, 2)
        zeit_layout.addWidget(QLabel("Stop"), 2, 0)
        self.edit_stop = QLineEdit("14:23  23/12/2012")
        zeit_layout.addWidget(self.edit_stop, 3, 0, 1, 2)
        btn_regen = QPushButton("Regenerate")
        btn_regen.setObjectName("blue")
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("red")
        zeit_layout.addWidget(btn_regen, 4, 0)
        zeit_layout.addWidget(btn_cancel, 4, 1)
        layout.addWidget(zeit_box)

        # Kryo Timer
        timer_box = QGroupBox("Kryo Timer")
        timer_layout = QVBoxLayout(timer_box)
        self.edit_timer = QLineEdit("14:23  23/12/2012")
        timer_layout.addWidget(self.edit_timer)
        self.btn_kryo_timer = QPushButton("▶ Kryo Timer")
        self.btn_kryo_timer.setObjectName("green")
        self.btn_kryo_timer.setCheckable(True)
        self.btn_kryo_timer.toggled.connect(self._toggle_kryo_timer)
        timer_layout.addWidget(self.btn_kryo_timer)
        layout.addWidget(timer_box)

        # Cycle time
        cycle_box = QGroupBox("Cycle Time")
        cycle_layout = QHBoxLayout(cycle_box)
        cycle_layout.addWidget(QLabel("Intervall"))
        self.combo_cycle = QComboBox()
        self.combo_cycle.addItems(["min.", "sec.", "h."])
        cycle_layout.addWidget(self.combo_cycle)
        layout.addWidget(cycle_box)

        # Options / Ende
        btn_options = QPushButton("⚙ Options")
        btn_options.clicked.connect(lambda: self.statusbar.showMessage("Optionen – noch nicht implementiert", 3000))
        layout.addWidget(btn_options)

        btn_ende = QPushButton("■ Ende")
        btn_ende.setObjectName("red")
        btn_ende.clicked.connect(self.close)
        layout.addWidget(btn_ende)

        layout.addStretch()
        return panel

    def _build_footer(self, parent_layout):
        """Footer-Buttons als eigene Zeile unter dem Hauptlayout."""
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(4, 2, 4, 2)

        self.footer_buttons = {}
        btn_defs = [
            ("V1 Closed",     "red"),
            ("Rotary Off",    "red"),
            ("Roots Off",     "red"),
            ("Vu Closed",     "red"),
            ("Heat Off",      "green"),
            ("Slider Closed", "red"),
            ("Cryo Off",      "red"),
        ]
        for label, farbe in btn_defs:
            btn = QPushButton(label)
            btn.setObjectName(farbe)
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setFont(QFont("Courier New", 9))
            self.footer_buttons[label] = btn
            footer_layout.addWidget(btn)

        footer_layout.addStretch()

        cb_auto = QCheckBox("Autorange")
        footer_layout.addWidget(cb_auto)

        # Footer unter alles setzen
        outer = self.centralWidget()
        outer_layout = outer.layout()
        outer_layout.addWidget(footer)
        # footer soll ganz unten sein → nicht ideal mit addWidget,
        # daher nutzen wir die Statusbar-Alternative oben

    # ── Update-Schleife ───────────────────────────────────────
    def _update(self):
        # Temperaturen
        temps = self.daten.lese_temperaturen()
        for name, val in temps.items():
            # History
            self.temp_history[name].append(val)
            # Label
            if name in self.temp_labels:
                if val is None:
                    self.temp_labels[name].setText("NaN")
                    self.temp_labels[name].setStyleSheet("color: #6e7681; font-family:'Courier New'; font-size:11px;")
                else:
                    kelvin = val + 273.15
                    self.temp_labels[name].setText(f"{kelvin:.1f} K")
                    self.temp_labels[name].setStyleSheet("color: #00d4ff; font-family:'Courier New'; font-size:11px;")

        # Drücke
        druecke = self.daten.lese_druecke()
        for name, val in druecke.items():
            self.druck_history[name].append(val)
            if name in self.druck_labels:
                if val is None:
                    self.druck_labels[name].setText("---")
                else:
                    self.druck_labels[name].setText(f"{val:.2E}")

        # Readouts (Center = CENT, Door = DOOR, BA = BA)
        mapping = {"Center": "CENT", "Door": "DOOR", "BA": "BA"}
        for r_name, d_name in mapping.items():
            val = druecke.get(d_name)
            if r_name in self.readout_labels:
                self.readout_labels[r_name].setText(
                    f"{val:.2E}" if val is not None else "0E+0"
                )

        # Charts aktualisieren
        x = list(range(HISTORY_LEN))
        for name, kurve in self.temp_kurven.items():
            if not self.temp_checks[name].isChecked():
                kurve.setData([], [])
                continue
            y = [v for v in self.temp_history[name] if v is not None]
            xi = [i for i, v in enumerate(self.temp_history[name]) if v is not None]
            kurve.setData(xi, y)

        for name, kurve in self.druck_kurven.items():
            if not self.druck_checks[name].isChecked():
                kurve.setData([], [])
                continue
            y = [v for v in self.druck_history[name] if v is not None]
            xi = [i for i, v in enumerate(self.druck_history[name]) if v is not None]
            kurve.setData(xi, y)

    def _update_clock(self):
        now = datetime.now().strftime("%H:%M:%S  %d.%m.%Y")
        self.lbl_clock.setText(now)

    def _toggle_temp_kurve(self, name):
        checked = self.temp_checks[name].isChecked()
        if not checked:
            self.temp_kurven[name].setData([], [])

    def _toggle_druck_kurve(self, name):
        checked = self.druck_checks[name].isChecked()
        if not checked:
            self.druck_kurven[name].setData([], [])

    def _toggle_kryo_timer(self, aktiv):
        if aktiv:
            self.btn_kryo_timer.setText("■ Stop Timer")
            self.btn_kryo_timer.setObjectName("red")
        else:
            self.btn_kryo_timer.setText("▶ Kryo Timer")
            self.btn_kryo_timer.setObjectName("green")
        self.btn_kryo_timer.setStyle(self.btn_kryo_timer.style())


# ── Start ──────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(make_stylesheet())
    window = KryostatGUI()
    window.show()
    sys.exit(app.exec())