"""
gui/hauptfenster.py
Hauptfenster der Jumbo-Weltraumsimulationsanlage.
"""

import calendar
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QTextEdit, QPushButton, QSizePolicy, QSplitter,
    QGroupBox, QDateTimeEdit, QTabWidget, QCheckBox, QStatusBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QSize
from PyQt6.QtGui import QFont, QAction

from gui.druck_panel      import DruckPanel
from gui.temp_panel       import TempPanel
from gui.steckdosen_panel import SteckdosenPanel
from gui.themes              import DARK_THEME, LIGHT_THEME, build_stylesheet
from gui.kalibrierung_fenster  import KalibrierFenster
from gui.historien_fenster      import HistorienFenster
from gui.alarm_einstellungen   import AlarmEinstellungen, AlarmEinstellungenDialog
from steuerung            import Messzyklus
from gui.pdf_report       import erstelle_tagesbericht


class SignalBridge(QObject):
    neue_temperaturen = pyqtSignal(dict)
    neue_druecke      = pyqtSignal(dict)
    alarm             = pyqtSignal(str, float)
    entwarnung        = pyqtSignal(str, float)
    hw_status         = pyqtSignal(dict)
    log_msg           = pyqtSignal(str, str)               # (text, farbe)
    sprung_alarm      = pyqtSignal(str, str, float, float) # (typ, name, wert, sprung)


def _giessen_tz() -> timezone:
    now_utc = datetime.now(timezone.utc)
    year    = now_utc.year
    def last_sunday(yr, mo):
        import calendar as cal
        last_day = cal.monthrange(yr, mo)[1]
        d = datetime(yr, mo, last_day, 1, 0, tzinfo=timezone.utc)
        d -= timedelta(days=(d.weekday() + 1) % 7)
        return d
    if last_sunday(year, 3) <= now_utc < last_sunday(year, 10):
        return timezone(timedelta(hours=2), "CEST")
    return timezone(timedelta(hours=1), "CET")

def _mjd(dt_utc: datetime) -> float:
    epoch = datetime(1858, 11, 17, tzinfo=timezone.utc)
    return (dt_utc - epoch).total_seconds() / 86400.0


class Hauptfenster(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jumbo Control  |  JLU Giessen – IPI")
        self.setMinimumSize(1100, 700)

        self._theme  = DARK_THEME
        self._bridge = SignalBridge()
        self._zyklus = Messzyklus(intervall=5.0)

        self._kalib_fenster    = None
        self._grossanzeige     = None
        self._historien_fenster = None
        self._hw_leds = {}   # keine LEDs im Header mehr, nur Statusleiste
        self._alarm_einst    = AlarmEinstellungen()
        self._build_ui()
        self._build_menubar()
        self._build_statusbar()
        self._verbinde_signale()
        self._zyklus_starten()
        self._apply_theme(self._theme, still=True)
        self._uhr_timer = QTimer()
        self._uhr_timer.timeout.connect(self._update_uhr)
        self._uhr_timer.start(1000)
        self._update_uhr()

        # PDF-Ordner (Unterordner 'PDF/' neben dieser Datei)
        self._projekt_ordner = Path(os.path.dirname(os.path.abspath(__file__))).parent

        # Mitternachts-Timer für automatischen Tagesbericht
        self._mitternachts_timer = QTimer(self)
        self._mitternachts_timer.setSingleShot(True)
        self._mitternachts_timer.timeout.connect(self._mitternacht_callback)
        self._plane_mitternachts_timer()

    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.setStyleSheet("font-size: 12px;")

        # HW-Ampeln in Statusleiste
        self._sb_leds = {}
        for name in ["cDAQ", "Druck", "Steckdose", "XSP01R"]:
            led = QFrame()
            led.setFixedSize(16, 16)
            led.setStyleSheet(
                "background: #94a3b8; border-radius: 8px; "
                "border: 2px solid #5a6080;"
            )
            led.setToolTip(f"{name}: unbekannt")
            lbl = QLabel(name)
            lbl.setStyleSheet(
                "font-size: 12px; font-weight: 700; "
                "padding-right: 14px; color: #b7c4de;"
            )
            sb.addWidget(led)
            sb.addWidget(lbl)
            self._sb_leds[name] = led

        # Dauerhafte Meldung rechts
        self._sb_msg = QLabel("Bereit")
        sb.addPermanentWidget(self._sb_msg)

    # ── UI ────────────────────────────────────────────────────
    def _build_ui(self):
        zentral = QWidget()
        self.setCentralWidget(zentral)
        haupt = QHBoxLayout(zentral)
        haupt.setContentsMargins(10, 10, 10, 10)
        haupt.setSpacing(10)

        # Linke Seite
        links = QWidget()
        ll    = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(8)

        ll.addWidget(self._build_header())
        ll.addWidget(self._hrule())

        self.druck_panel = DruckPanel()
        # Splitter für Druck und Temp – Buttons bleiben immer sichtbar
        from PyQt6.QtWidgets import QSplitter
        plot_splitter = QSplitter(Qt.Orientation.Vertical)
        plot_splitter.addWidget(self.druck_panel)

        self.temp_panel = TempPanel()
        plot_splitter.addWidget(self.temp_panel)
        plot_splitter.setSizes([280, 380])
        ll.addWidget(plot_splitter, 1)
        ll.addWidget(self._hrule())

        self.steckdosen_panel = SteckdosenPanel()
        self.steckdosen_panel.setFixedHeight(56)
        self.steckdosen_panel.bei_aktion = self.log
        ll.addWidget(self.steckdosen_panel, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(links)

        rechts_panel = self._build_log_panel()
        splitter.addWidget(rechts_panel)

        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([900, 500])
        haupt.addWidget(splitter)

    def _build_header(self) -> QWidget:
        self._header = QWidget()
        self._header.setFixedHeight(58)
        layout = QHBoxLayout(self._header)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(6)

        # Zeitfelder
        self.lbl_datum   = self._time_lbl("--.--.----", small=True)
        self.lbl_uhrzeit = self._time_lbl("--:--:--", big=True)
        self.lbl_kw      = self._time_lbl("KW --", small=True)
        self.lbl_mjd     = self._time_lbl("MJD ----------", small=True)
        self.lbl_utc     = self._time_lbl("UTC --:--:--", small=True)

        self.lbl_datum.setObjectName("date")
        self.lbl_uhrzeit.setObjectName("time")
        self.lbl_kw.setObjectName("kw")
        self.lbl_mjd.setObjectName("mjd")
        self.lbl_utc.setObjectName("utc")

        for i, (lbl, sep) in enumerate([
            (self.lbl_datum,   True),
            (self.lbl_uhrzeit, True),
            (self.lbl_kw,      True),
            (self.lbl_mjd,     True),
            (self.lbl_utc,     False),
        ]):
            layout.addWidget(lbl)
            if sep:
                layout.addWidget(self._vsep())

        layout.addWidget(self._vsep())

        btn_info = QPushButton("Support")
        btn_info.setObjectName("supportButton")
        btn_info.setFixedHeight(34)
        btn_info.setToolTip("Systemübersicht anzeigen")
        btn_info.clicked.connect(self._zeige_bild)
        layout.addWidget(btn_info)

        self._btn_pdf = QPushButton("📄 PDF")
        self._btn_pdf.setObjectName("pdfButton")
        self._btn_pdf.setFixedHeight(34)
        self._btn_pdf.setToolTip("Tagesbericht als PDF erzeugen\nSpeichert in: PDF/")
        self._btn_pdf.clicked.connect(self._pdf_manuell)
        layout.addWidget(self._btn_pdf)

        self._btn_vollbild = QPushButton("⛶ Vollbild")
        self._btn_vollbild.setObjectName("fullscreenButton")
        self._btn_vollbild.setFixedHeight(34)
        self._btn_vollbild.setToolTip("Vollbildmodus ein-/ausschalten")
        self._btn_vollbild.clicked.connect(self._vollbild_toggle)
        layout.addWidget(self._btn_vollbild)

        layout.addStretch()

        # Speicherdatei
        self._datei_box = QWidget()
        self._datei_box.setObjectName("fileInfoBox")
        self._datei_box.setMinimumWidth(360)
        db_layout = QVBoxLayout(self._datei_box)
        db_layout.setContentsMargins(12, 6, 12, 6)
        db_layout.setSpacing(2)
        lbl_titel = QLabel("Speicherdatei:")
        lbl_titel.setObjectName("fileInfoTitle")
        lbl_titel.setStyleSheet("font-size: 11px; letter-spacing: 0.5px;")
        self.lbl_datei = QLabel("–")
        self.lbl_datei.setObjectName("fileInfoValue")
        self.lbl_datei.setStyleSheet(
            "font-family: 'Consolas','Courier New'; font-size: 11px; font-weight: bold;"
        )
        db_layout.setDirection(QVBoxLayout.Direction.LeftToRight)
        db_layout.addWidget(lbl_titel)
        db_layout.addWidget(self.lbl_datei)
        layout.addWidget(self._datei_box)

        return self._header

    def _time_lbl(self, text: str, big=False, small=False) -> QLabel:
        lbl = QLabel(text)
        size = 16 if big else 14
        if small:
            size = 14
        lbl.setStyleSheet(
            f"font-family: 'Consolas','Courier New'; font-size: {size}px; "
            "font-weight: 700; padding: 0 12px;"
        )
        return lbl

    def _vsep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFixedWidth(1)
        f.setStyleSheet("margin: 6px 0;")
        return f

    def _hrule(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setFixedHeight(1)
        return f

    def _build_log_panel(self) -> QWidget:
        widget = QWidget()
        widget.setMinimumWidth(200)
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # Tab 1: Log
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(2, 2, 2, 2)
        self.log_fenster = QTextEdit()
        self.log_fenster.setReadOnly(True)
        log_layout.addWidget(self.log_fenster)
        tabs.addTab(log_widget, "Log")

        # Tab 2: Timing
        tabs.addTab(self._build_timing_panel(), "Timing")

        # Tab 3: Kryopumpen
        from gui.kryo_status_panel import KryoStatusPanel
        self._kryo_panel = KryoStatusPanel()
        self._kryo_panel.set_log_callback(self.log)
        tabs.addTab(self._kryo_panel, "Kryopumpen")

        outer.addWidget(tabs)
        return widget

    def _build_timing_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # ── Globale Kryoauswahl (für Timer + Regenerierung) ──
        auswahl_box = QGroupBox("Kryoauswahl")
        auswahl_layout = QVBoxLayout(auswahl_box)
        auswahl_layout.setSpacing(2)
        auswahl_layout.setContentsMargins(6, 4, 6, 4)

        self._chk_alle_kryo = QCheckBox("Alle auswählen")
        self._chk_alle_kryo.setChecked(True)
        self._chk_alle_kryo.setStyleSheet("font-weight: bold; font-size: 10px;")
        self._chk_alle_kryo.stateChanged.connect(self._kryo_timer_alle_toggle)
        auswahl_layout.addWidget(self._chk_alle_kryo)

        sep_a = QFrame(); sep_a.setFrameShape(QFrame.Shape.HLine)
        auswahl_layout.addWidget(sep_a)

        # 2 Spalten für die Checkboxen
        self._kryo_timer_checks = {}
        alle_kryos = [f"Kryo {i}" for i in range(1, 9)]
        grid_widget = QWidget()
        grid = QHBoxLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        col1 = QVBoxLayout(); col2 = QVBoxLayout()
        for i, name in enumerate(alle_kryos):
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.setStyleSheet("font-size: 10px;")
            cb.stateChanged.connect(self._kryo_timer_check_update)
            self._kryo_timer_checks[name] = cb
            if i < 4: col1.addWidget(cb)
            else:      col2.addWidget(cb)
        grid.addLayout(col1); grid.addLayout(col2)
        auswahl_layout.addWidget(grid_widget)
        layout.addWidget(auswahl_box)

        # ── Regenerierung ────────────────────────────────────
        regen_box = QGroupBox("Regenerierung")
        regen_layout = QVBoxLayout(regen_box)
        regen_layout.setSpacing(4)

        row = QHBoxLayout()
        lbl = QLabel("Start:")
        lbl.setFixedWidth(35)
        lbl.setStyleSheet("font-size: 10px; color: #666;")
        self._dt_regen_start = QDateTimeEdit()
        self._dt_regen_start.setDisplayFormat("HH:mm  dd/MM/yyyy")
        self._dt_regen_start.setDateTime(
            self._dt_regen_start.dateTime().currentDateTime().addSecs(
                -self._dt_regen_start.dateTime().currentDateTime().time().second()
            ))
        self._dt_regen_start.setCalendarPopup(True)
        row.addWidget(lbl); row.addWidget(self._dt_regen_start)
        regen_layout.addLayout(row)

        row2 = QHBoxLayout()
        lbl2 = QLabel("Stop:")
        lbl2.setFixedWidth(35)
        lbl2.setStyleSheet("font-size: 10px; color: #666;")
        self._dt_regen_stop = QDateTimeEdit()
        self._dt_regen_stop.setDisplayFormat("HH:mm  dd/MM/yyyy")
        self._dt_regen_stop.setDateTime(
            self._dt_regen_stop.dateTime().currentDateTime().addSecs(
                -self._dt_regen_stop.dateTime().currentDateTime().time().second()
            ))
        self._dt_regen_stop.setCalendarPopup(True)
        row2.addWidget(lbl2); row2.addWidget(self._dt_regen_stop)
        regen_layout.addLayout(row2)

        btn_row = QHBoxLayout()
        self._btn_regen = QPushButton("Regenerate")
        self._btn_regen.setCheckable(True)
        self._btn_regen.setStyleSheet("""
            QPushButton {
                background: #16a34a; color: white; border: none;
                border-radius: 5px; font-weight: 700; font-size: 12px; padding: 6px 12px;
            }
            QPushButton:hover { background: #15803d; }
            QPushButton:checked {
                background: #f59e0b;
            }
        """)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: #f1f5f9; color: #334155;
                border: 1.5px solid #94a3b8; border-radius: 5px;
                font-weight: 700; font-size: 12px; padding: 6px 12px;
            }
            QPushButton:hover { border-color: #e63946; color: #e63946; }
        """)
        self._btn_regen.clicked.connect(self._regen_toggle)
        btn_cancel.clicked.connect(self._regen_abbrechen)
        btn_row.addWidget(self._btn_regen)
        btn_row.addWidget(btn_cancel)
        regen_layout.addLayout(btn_row)

        self._lbl_regen_status = QLabel("")
        self._lbl_regen_status.setStyleSheet("font-size: 10px; color: #666;")
        regen_layout.addWidget(self._lbl_regen_status)
        layout.addWidget(regen_box)

        # ── Kryo Timer ───────────────────────────────────────
        timer_box = QGroupBox("Kryo Timer")
        timer_layout = QVBoxLayout(timer_box)

        row3 = QHBoxLayout()
        lbl3 = QLabel("EIN um:")
        lbl3.setFixedWidth(45)
        lbl3.setStyleSheet("font-size: 10px; color: #666;")
        self._dt_kryo = QDateTimeEdit()
        self._dt_kryo.setDisplayFormat("HH:mm  dd/MM/yyyy")
        self._dt_kryo.setDateTime(
            self._dt_kryo.dateTime().currentDateTime().addSecs(
                -self._dt_kryo.dateTime().currentDateTime().time().second()
            ))
        self._dt_kryo.setCalendarPopup(True)
        row3.addWidget(lbl3); row3.addWidget(self._dt_kryo)
        timer_layout.addLayout(row3)

        self._btn_kryo_timer = QPushButton("Kryo timer starten")
        self._btn_kryo_timer.setCheckable(True)
        self._btn_kryo_timer.setStyleSheet(self._kryo_timer_style(False))
        self._btn_kryo_timer.clicked.connect(self._kryo_timer_toggle)
        timer_layout.addWidget(self._btn_kryo_timer)

        self._lbl_timer_status = QLabel("")
        self._lbl_timer_status.setStyleSheet("font-size: 10px; color: #666;")
        timer_layout.addWidget(self._lbl_timer_status)
        layout.addWidget(timer_box)

        # Timer-Objekte
        self._kryo_timer_qt = QTimer()
        self._kryo_timer_qt.timeout.connect(self._kryo_timer_tick)
        self._regen_timer = QTimer()
        self._regen_timer.timeout.connect(self._regen_tick)
        self._regen_phase = None  # "warte_start" | "warte_stop"

        layout.addStretch()
        return widget

    # ── Menubar ───────────────────────────────────────────────
    def _build_menubar(self):
        mb = self.menuBar()
        ansicht = mb.addMenu("Ansicht")

        extras = mb.addMenu("Extras")
        act_kalib = QAction("Kalibrierte Druckwerte...", self)
        act_kalib.triggered.connect(self._kalib_fenster_oeffnen)
        extras.addAction(act_kalib)

        act_alarm = QAction("Alarm && Filter...", self)
        act_alarm.triggered.connect(self._alarm_einstellungen_oeffnen)
        extras.addAction(act_alarm)

        act_hist = QAction("Historische Daten...", self)
        act_hist.triggered.connect(self._historien_fenster_oeffnen)
        extras.addAction(act_hist)

        extras.addSeparator()

        self._act_auto_druck = QAction("Tagesbericht automatisch drucken", self)
        self._act_auto_druck.setCheckable(True)
        self._act_auto_druck.setChecked(False)
        self._act_auto_druck.setToolTip(
            "PDF des Vortags wird jeden Morgen automatisch gedruckt. Drucker: siehe DRUCKER_NAME in config.py"
        )
        extras.addAction(self._act_auto_druck)

        act_dark  = QAction("Dunkles Theme",  self)
        act_light = QAction("Helles Theme",   self)
        act_dark.triggered.connect(lambda: self._apply_theme(DARK_THEME))
        act_light.triggered.connect(lambda: self._apply_theme(LIGHT_THEME))
        ansicht.addAction(act_dark)
        ansicht.addAction(act_light)

    # ── Theme ─────────────────────────────────────────────────
    def _apply_theme(self, t: dict, still: bool = False):
        self._theme = t
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().setStyleSheet(build_stylesheet(t))

        # Matplotlib Plots
        self.druck_panel.apply_theme(t)
        self.temp_panel.apply_theme(t)

        from gui.themes import matplotlib_toolbar_style
        dark = t.get("bg", "").lower() != LIGHT_THEME["bg"].lower()
        matplotlib_toolbar_style(self.druck_panel._toolbar, dark)
        matplotlib_toolbar_style(self.temp_panel._toolbar, dark)

        if not still:
            self.log("Theme gewechselt", farbe=t["log_ok"])

    # ── Signale ───────────────────────────────────────────────
    def _verbinde_signale(self):
        self._bridge.neue_temperaturen.connect(self.temp_panel.aktualisieren)
        self._bridge.neue_druecke.connect(self.druck_panel.aktualisieren)
        self._bridge.neue_druecke.connect(self.steckdosen_panel.update_druck)
        self._bridge.alarm.connect(self._zeige_alarm)
        self._bridge.entwarnung.connect(self._zeige_entwarnung)
        self._bridge.hw_status.connect(self._update_hw_status)
        self._bridge.log_msg.connect(self.log)
        self._bridge.sprung_alarm.connect(self._zeige_sprung_alarm)
        self.druck_panel.kalib_geoeffnet.connect(self._kalib_fenster_oeffnen)
        self.druck_panel.grossanzeige_anfordern.connect(self._grossanzeige_oeffnen)

        # ── Sicherheitsverriegelung Heater ↔ Kryos ──────────
        # SteckdosenPanel: Heater-Button prüft ob Kryos an sind
        self.steckdosen_panel.set_kryo_an_check(
            self._kryo_panel.ist_kryo_an
        )
        # KryoStatusPanel: Kryo-Buttons prüfen ob Heater an ist
        self._kryo_panel.set_heater_an_check(
            self.steckdosen_panel.ist_heater_an
        )
        # Wenn Heater eingeschaltet wird → Kryos sperren
        # Wenn Kryos eingeschaltet werden → Heater sperren
        # Das geschieht reaktiv über die _schalten-Methoden;
        # zusätzlich beim Statusladen des Steckdosen-Panels
        # via _heater_status_sync aufrufen:
        self._sync_heater_kryo_sperre()
        # Referenz für externen Heater-Status-Poll
        self.steckdosen_panel._kryo_panel_ref = self._kryo_panel

    def _zyklus_starten(self):
        self._zyklus.bei_messung_temp  = self._bridge.neue_temperaturen.emit
        self._zyklus.bei_messung_druck = self._bridge.neue_druecke.emit
        self._zyklus.bei_alarm         = self._bridge.alarm.emit
        self._zyklus.bei_entwarnung    = self._bridge.entwarnung.emit
        self._zyklus.bei_hw_status     = self._bridge.hw_status.emit
        self._zyklus.bei_sprung_alarm  = self._bridge.sprung_alarm.emit
        self._zyklus._alarm_einst      = self._alarm_einst
        self._zyklus.starten()
        self.log("System gestartet")
        self._startup_checks()

    # ── Uhr ───────────────────────────────────────────────────
    def _update_uhr(self):
        jetzt_utc = datetime.now(timezone.utc)
        jetzt_lok = datetime.now(_giessen_tz())
        kw        = jetzt_lok.isocalendar()[1]

        self.lbl_datum.setText(jetzt_lok.strftime("  %d.%m.%Y"))
        self.lbl_uhrzeit.setText(jetzt_lok.strftime("%H:%M:%S"))
        self.lbl_kw.setText(f"KW {kw:02d}")
        self.lbl_mjd.setText(f"MJD {_mjd(jetzt_utc):.5f}")
        self.lbl_utc.setText(f"UTC {jetzt_utc.strftime('%H:%M:%S')}")

        datum = datetime.now().strftime("%Y-%m-%d")
        self.lbl_datei.setText(
            f"{datum}_temperatur.csv  |  {datum}_druck.csv"
        )

    # ── Log ───────────────────────────────────────────────────
    def log(self, text: str, farbe: str = None):
        t = self._theme
        farbe = farbe or t["log_info"]
        stamp = t["log_stamp"]
        zeit  = datetime.now().strftime("%d.%m.%Y  %H:%M:%S")
        self.log_fenster.append(
            f'<span style="color:{stamp}">{zeit}</span> '
            f'<span style="color:{farbe}">{text}</span>'
        )

    def _zeige_alarm(self, sensor: str, wert: float):
        self.log(f"⚠ ALARM: {sensor} = {wert:.2f} °C", farbe=self._theme["danger"])

    def _zeige_entwarnung(self, sensor: str, wert: float):
        self.log(f"✓ Entwarnung: {sensor} = {wert:.2f} °C", farbe=self._theme["log_ok"])

    def _startup_checks(self):
        """Prüft beim Start welche Hardware erreichbar ist und loggt den Status."""
        import threading
        def _run():
            import time
            time.sleep(1.0)  # kurz warten bis Verbindungen aufgebaut sind

            # ── cDAQ ──────────────────────────────────────────
            try:
                import nidaqmx
                from nidaqmx.system import System
                geraete = System().devices
                namen   = [d.name for d in geraete]
                from config import CDAQ_GERAET
                if any(CDAQ_GERAET in n for n in namen):
                    self._bridge.log_msg.emit(f"✓ cDAQ erreichbar ({CDAQ_GERAET})", self._theme["log_ok"])
                else:
                    self._bridge.log_msg.emit(f"⚠ cDAQ nicht gefunden (erwartet: {CDAQ_GERAET})", self._theme["log_warn"])
            except Exception as e:
                self._bridge.log_msg.emit(f"⚠ cDAQ nicht erreichbar: {e}", self._theme["log_warn"])

            # ── TPG 366 – Status aus Messzyklus lesen ─────────
            if self._zyklus._hw_status.druck:
                self._bridge.log_msg.emit("✓ TPG 366 (Druck) erreichbar", self._theme["log_ok"])
            else:
                self._bridge.log_msg.emit("⚠ TPG 366 nicht erreichbar – Reconnect läuft automatisch",
                                          self._theme["log_warn"])

            # ── Steckdose (mit 3 Versuchen – Netzwerk kann kurz zögern) ─
            _steckdose_status = None
            for _versuch in range(3):
                try:
                    from hardware.steckdose import Steckdose
                    _s = Steckdose()
                    _steckdose_status = _s.status_alle()
                    self._bridge.log_msg.emit("✓ Steckdose (ALL4076) erreichbar", self._theme["log_ok"])
                    self._bridge.hw_status.emit({"Steckdose": True})
                    break
                except Exception as _e:
                    if _versuch < 2:
                        time.sleep(2.0)
                    else:
                        self._bridge.log_msg.emit(f"⚠ Steckdose nicht erreichbar: {_e}",
                                                  self._theme["log_warn"])
                        self._bridge.hw_status.emit({"Steckdose": False})

            if _steckdose_status is not None:
                # V1 Inkonsistenz-Check
                v1_an   = _steckdose_status.get("V1", {}).get("an", False)
                druecke = self.steckdosen_panel.get_druck_werte()

                if v1_an:
                    gueltig = {n: d for n, d in druecke.items()
                               if d.get("gueltig") and d.get("mbar") is not None}
                    unter   = {n: d for n, d in gueltig.items()
                               if d["mbar"] < 1.0}
                    if not druecke:
                        self._bridge.log_msg.emit("⚠ V1 ist EIN – Druckstatus noch nicht verfügbar",
                                                  self._theme["log_warn"])
                    elif unter:
                        details = ", ".join(
                            f"{n}: {d['mbar']:.2E} mbar" for n, d in unter.items())
                        self._bridge.log_msg.emit(
                            f"⛔ INKONSISTENZ: V1 ist EIN aber Druck < 1 mbar "
                            f"({details}) – bitte prüfen!", self._theme["danger"])
                    elif not gueltig:
                        self._bridge.log_msg.emit(
                            "⛔ INKONSISTENZ: V1 ist EIN aber alle Drucksensoren ausgefallen!",
                            self._theme["danger"])
                    else:
                        self._bridge.log_msg.emit("✓ V1 EIN – Druck OK (≥ 1 mbar)", self._theme["log_ok"])
                else:
                    self._bridge.log_msg.emit("✓ V1 AUS – kein Sicherheitsrisiko", self._theme["log_ok"])

            # ── XSP01R ────────────────────────────────────────
            try:
                from hardware.geraete import get_xsp01r
                x  = get_xsp01r()
                st = x.status()
                k1 = "EIN" if st["kryo1_system"] else "AUS"
                k2 = "EIN" if st["kryo2_system"] else "AUS"
                self._bridge.log_msg.emit(f"✓ XSP01R erreichbar (Kryo1={k1}, Kryo2={k2})",
                                          self._theme["log_ok"])
                self._bridge.hw_status.emit({"XSP01R": True})
            except Exception as e:
                self._bridge.log_msg.emit(f"⚠ XSP01R nicht erreichbar: {e}", self._theme["log_warn"])
                self._bridge.hw_status.emit({"XSP01R": False})

        threading.Thread(target=_run, daemon=True).start()

    def _update_hw_status(self, status: dict):
        farben = {True: "#16a34a", False: "#dc2626"}
        for name, ok in status.items():
            for leds in [self._hw_leds, self._sb_leds]:
                if name in leds:
                    leds[name].setStyleSheet(
                        f"background: {farben[ok]}; border-radius: 8px; "
                        f"border: 2px solid {'#00ff88' if ok else '#ff5555'};"
                    )
                    leds[name].setToolTip(
                        f"{name}: {'verbunden' if ok else 'nicht erreichbar'}"
                    )
        # Statusmeldung
        nicht_ok = [n for n, ok in status.items() if not ok]
        if nicht_ok:
            self._sb_msg.setText(f"⚠ Nicht erreichbar: {', '.join(nicht_ok)}")
            self._sb_msg.setStyleSheet("color: #dc2626; font-size: 10px;")
        else:
            self._sb_msg.setText("✓ Alle Geräte verbunden")
            self._sb_msg.setStyleSheet("color: #16a34a; font-size: 10px;")


    def _historien_fenster_oeffnen(self):
        if self._historien_fenster is None:
            self._historien_fenster = HistorienFenster()
        self._historien_fenster.show()
        self._historien_fenster.raise_()
        self.log("Historische Daten geöffnet")

    def _alarm_einstellungen_oeffnen(self):
        dlg = AlarmEinstellungenDialog(self._alarm_einst, parent=self)
        dlg.exec()
        self.log("Alarm & Filter Einstellungen gespeichert")

    def _zeige_sprung_alarm(self, typ: str, name: str, wert: float, sprung: float):
        if typ == "temp_alarm":
            self.log(
                f"⚠ Temperatursprung: {name} = {wert:.1f} °C (Δ {sprung:.1f} °C)",
                farbe=self._theme["log_warn"]
            )
        elif typ == "druck_alarm":
            self.log(
                f"⚠ Drucksprung: {name} = {wert:.2E} mbar ({sprung:.1f} Dek/s)",
                farbe=self._theme["log_warn"]
            )

    def _zeige_bild(self):
        import os
        gif_pfad  = os.path.join("pics", "jorde.gif")
        jpeg_pfad = os.path.join("pics", "jorde.jpeg")

        if os.path.exists(gif_pfad):
            self._zeige_gif(gif_pfad)
        elif os.path.exists(jpeg_pfad):
            self._zeige_jpeg(jpeg_pfad)
        else:
            self.log("⚠ Kein Bild gefunden (pics/jorde.gif oder jorde.jpeg)",
                     farbe=self._theme["log_warn"])

    def _zeige_gif(self, pfad: str):
        """Öffnet ein Fenster mit animiertem GIF via QMovie."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel
        from PyQt6.QtGui import QMovie
        from PyQt6.QtCore import Qt, QSize

        dlg = QDialog(self)
        dlg.setWindowTitle("Jumbo – Support")
        dlg.setModal(False)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        movie = QMovie(pfad)
        movie.jumpToFrame(0)
        native = movie.currentImage().size()
        screen = self.screen().availableGeometry()
        max_w  = int(screen.width()  * 0.8)
        max_h  = int(screen.height() * 0.8)
        if native.width() > max_w or native.height() > max_h:
            factor = min(max_w / native.width(), max_h / native.height())
            w = int(native.width()  * factor)
            h = int(native.height() * factor)
            movie.setScaledSize(QSize(w, h))
        else:
            w, h = native.width(), native.height()

        lbl.setMovie(movie)
        movie.start()
        dlg._movie = movie   # Referenz halten, sonst GC löscht QMovie

        layout.addWidget(lbl)
        dlg.resize(max(w, 200), max(h, 200))
        dlg.exec()
        movie.stop()

    def _zeige_jpeg(self, pfad: str):
        """Öffnet ein Fenster mit statischem Bild."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea
        from PyQt6.QtGui import QPixmap
        from PyQt6.QtCore import Qt

        dlg = QDialog(self)
        dlg.setWindowTitle("Jumbo – Systemübersicht")
        dlg.setModal(True)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(4, 4, 4, 4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        lbl = QLabel()
        pixmap = QPixmap(pfad)
        lbl.setPixmap(pixmap)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setWidget(lbl)
        screen = self.screen().availableGeometry()
        w = min(pixmap.width()  + 20, int(screen.width()  * 0.9))
        h = min(pixmap.height() + 20, int(screen.height() * 0.9))
        dlg.resize(w, h)
        layout.addWidget(scroll)
        dlg.exec()

    def _grossanzeige_oeffnen(self):
        from gui.druck_grossanzeige import DruckGrossanzeige
        if self._grossanzeige is None:
            self._grossanzeige = DruckGrossanzeige()
            self._bridge.neue_druecke.connect(self._grossanzeige.aktualisieren)
        self._grossanzeige.show()
        self._grossanzeige.raise_()
        self.log("Druck-Großanzeige geöffnet")

    def _kalib_fenster_oeffnen(self):
        if self._kalib_fenster is None:
            self._kalib_fenster = KalibrierFenster()
            # Druckwerte weiterleiten
            self._bridge.neue_druecke.connect(self._kalib_fenster.aktualisieren)
        self._kalib_fenster.show()
        self._kalib_fenster.raise_()
        self.log("Kalibrierungsfenster geöffnet")

    def _regen_toggle(self, aktiv: bool):
        if aktiv:
            from datetime import datetime
            from datetime import timedelta
            start = self._dt_regen_start.dateTime().toPyDateTime().replace(second=0, microsecond=0)
            stop  = self._dt_regen_stop.dateTime().toPyDateTime().replace(second=0, microsecond=0)
            if stop <= start:
                self.log("Regenerierung: Stop muss nach Start liegen", farbe=self._theme["log_warn"])
                self._btn_regen.setChecked(False)
                return
            if stop <= datetime.now():
                self.log("Regenerierung: Zeitraum liegt in der Vergangenheit", farbe=self._theme["log_warn"])
                self._btn_regen.setChecked(False)
                return
            ausgewaehlte = [n for n, cb in self._kryo_timer_checks.items() if cb.isChecked()]
            if not ausgewaehlte:
                self.log("Regenerierung: keine Kryos ausgewählt", farbe=self._theme["log_warn"])
                self._btn_regen.setChecked(False)
                return
            self._regen_phase = "warte_start"
            self._regen_timer.start(1000)
            self.log(f"Regenerierung geplant: AUS um {start.strftime('%H:%M %d.%m.%Y')}, "
                     f"EIN um {stop.strftime('%H:%M %d.%m.%Y')}")
        else:
            self._regen_abbrechen()

    def _regen_abbrechen(self):
        self._regen_timer.stop()
        self._regen_phase = None
        self._btn_regen.setChecked(False)
        self._lbl_regen_status.setText("")
        self.log("Regenerierung abgebrochen")

    def _regen_tick(self):
        from datetime import datetime
        jetzt = datetime.now()
        start = self._dt_regen_start.dateTime().toPyDateTime().replace(second=0, microsecond=0)
        stop  = self._dt_regen_stop.dateTime().toPyDateTime().replace(second=0, microsecond=0)
        ausgewaehlte = [n for n, cb in self._kryo_timer_checks.items() if cb.isChecked()]

        if self._regen_phase == "warte_start":
            verbleibend = (start - jetzt).total_seconds()
            if verbleibend <= 0:
                # Kryos ausschalten
                self._regen_phase = "warte_stop"
                self.log("⏰ Regenerierung: schalte Kryos AUS", farbe=self._theme["log_warn"])
                self._kryo_alle_schalten(ausgewaehlte, an=False)
            else:
                h, m, s = int(verbleibend//3600), int((verbleibend%3600)//60), int(verbleibend%60)
                self._lbl_regen_status.setText(f"⏱ AUS in {h:02d}:{m:02d}:{s:02d}")

        elif self._regen_phase == "warte_stop":
            verbleibend = (stop - jetzt).total_seconds()
            if verbleibend <= 0:
                # Kryos einschalten
                self._regen_phase = None
                self._regen_timer.stop()
                self._btn_regen.setChecked(False)
                self._lbl_regen_status.setText("")
                self.log("⏰ Regenerierung: schalte Kryos EIN", farbe=self._theme["log_ok"])
                self._kryo_alle_schalten(ausgewaehlte, an=True)
            else:
                h, m, s = int(verbleibend//3600), int((verbleibend%3600)//60), int(verbleibend%60)
                self._lbl_regen_status.setText(f"⏱ Regenerierung läuft – EIN in {h:02d}:{m:02d}:{s:02d}")



    def _kryo_alle_schalten(self, ausgewaehlte: list, an: bool):
        import threading
        import time

        def _run():
            lock = self._kryo_panel._schalt_lock
            lock.acquire()
            try:
                from hardware.geraete import get_xsp01r
                x = get_xsp01r()

                for name in ausgewaehlte:
                    try:
                        if name == "Kryo 1":
                            x.kryo1_einschalten() if an else x.kryo1_ausschalten()
                        elif name == "Kryo 2":
                            x.kryo2_einschalten() if an else x.kryo2_ausschalten()
                        else:
                            from config import COOLPACK_PORTS
                            from hardware.coolpack import Coolpack
                            port = COOLPACK_PORTS.get(name)
                            if port:
                                c = Coolpack(port, name=name)
                                c.einschalten() if an else c.ausschalten()
                                c.beenden()

                        # GUI-Button thread-sicher aktualisieren
                        if an:
                            self._kryo_panel.kryo_ein_signal.emit(name)
                        else:
                            self._kryo_panel.kryo_aus_signal.emit(name)
                        self.log(
                            f"{'EIN' if an else 'AUS'}: {name}",
                            farbe=self._theme["log_ok"] if an else self._theme["log_warn"]
                        )
                        time.sleep(2.0)

                    except Exception as e:
                        self.log(f"Fehler {name}: {e}", farbe=self._theme["log_err"])
            finally:
                lock.release()

        threading.Thread(target=_run, daemon=True).start()


    def _kryo_timer_style(self, aktiv: bool) -> str:
        if aktiv:
            return """QPushButton {
                background: #f59e0b; border: none; border-radius: 5px;
                color: white; font-weight: 700; font-size: 12px; padding: 6px 12px;
            } QPushButton:hover { background: #d97706; }"""
        else:
            return """QPushButton {
                background: #2563eb; border: none; border-radius: 5px;
                color: white; font-weight: 700; font-size: 12px; padding: 6px 12px;
            } QPushButton:hover { background: #1d4ed8; }"""

    def _kryo_timer_alle_toggle(self, state: int):
        for cb in self._kryo_timer_checks.values():
            cb.blockSignals(True)
            cb.setChecked(bool(state))
            cb.blockSignals(False)

    def _kryo_timer_check_update(self):
        alle = all(cb.isChecked() for cb in self._kryo_timer_checks.values())
        self._chk_alle_kryo.blockSignals(True)
        self._chk_alle_kryo.setChecked(alle)
        self._chk_alle_kryo.blockSignals(False)

    def _kryo_timer_toggle(self, aktiv: bool):
        if aktiv:
            ausgewaehlte = [n for n, cb in self._kryo_timer_checks.items() if cb.isChecked()]
            if not ausgewaehlte:
                self.log("Kryo Timer: keine Kryos ausgewählt", farbe=self._theme["log_warn"])
                self._btn_kryo_timer.setChecked(False)
                return
            ziel = self._dt_kryo.dateTime().toPyDateTime().replace(second=0, microsecond=0)
            from datetime import datetime
            if ziel <= datetime.now():
                self.log("Kryo Timer: Zeitpunkt liegt in der Vergangenheit", farbe=self._theme["log_warn"])
                self._btn_kryo_timer.setChecked(False)
                return
            self._btn_kryo_timer.setText("Timer läuft – abbrechen")
            self._btn_kryo_timer.setStyleSheet(self._kryo_timer_style(True))
            self._kryo_timer_qt.start(1000)
            self.log(f"Kryo Timer gestartet: {', '.join(ausgewaehlte)} um {ziel.strftime('%H:%M %d.%m.%Y')}")
        else:
            self._kryo_timer_qt.stop()
            self._btn_kryo_timer.setText("Kryo timer starten")
            self._btn_kryo_timer.setStyleSheet(self._kryo_timer_style(False))
            self._lbl_timer_status.setText("")
            self.log("Kryo Timer abgebrochen")

    def _kryo_timer_tick(self):
        from datetime import datetime
        jetzt = datetime.now()
        ziel  = self._dt_kryo.dateTime().toPyDateTime().replace(second=0, microsecond=0)
        verbleibend = (ziel - jetzt).total_seconds()

        if verbleibend <= 0:
            # Zeit erreicht – Kryos einschalten
            self._kryo_timer_qt.stop()
            self._btn_kryo_timer.setChecked(False)
            self._btn_kryo_timer.setText("Kryo timer starten")
            self._btn_kryo_timer.setStyleSheet(self._kryo_timer_style(False))
            self._lbl_timer_status.setText("")

            ausgewaehlte = [n for n, cb in self._kryo_timer_checks.items() if cb.isChecked()]
            self.log(f"⏰ Kryo Timer ausgelöst: schalte {', '.join(ausgewaehlte)} EIN",
                     farbe=self._theme["log_ok"])
            self._kryo_alle_schalten(ausgewaehlte, an=True)
        else:
            # Countdown anzeigen
            h = int(verbleibend // 3600)
            m = int((verbleibend % 3600) // 60)
            s = int(verbleibend % 60)
            self._lbl_timer_status.setText(f"⏱ noch {h:02d}:{m:02d}:{s:02d}")

    # ── Vollbild ──────────────────────────────────────────────
    def _vollbild_toggle(self):
        if self.isFullScreen():
            self.showNormal()
            self._btn_vollbild.setText("⛶ Vollbild")
            self._btn_vollbild.setToolTip("Vollbildmodus einschalten")
        else:
            self.showFullScreen()
            self._btn_vollbild.setText("✕ Vollbild")
            self._btn_vollbild.setToolTip("Vollbildmodus ausschalten")

    # ── PDF-Tagesbericht ─────────────────────────────────────
    def _pdf_manuell(self):
        """PDF-Button im Header: Tagesbericht sofort erzeugen."""
        self._btn_pdf.setEnabled(False)
        self._btn_pdf.setText("⏳ …")
        try:
            pfad = self._pdf_erstellen()
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "PDF gespeichert",
                f"Tagesbericht gespeichert:\n{pfad}"
            )
            self.log(f"📄 PDF erstellt: {Path(pfad).name}", farbe=self._theme["log_ok"])
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "PDF-Fehler", str(e))
            self.log(f"⚠ PDF-Fehler: {e}", farbe=self._theme["log_err"])
        finally:
            self._btn_pdf.setEnabled(True)
            self._btn_pdf.setText("📄 PDF")

    def _mitternacht_callback(self):
        """Automatischer Tagesbericht kurz nach Mitternacht (UTC).
        Liest CSV des Vortags – RAM-Puffer ist zu diesem Zeitpunkt leer.
        """
        gestern = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
        try:
            druck_daten = self._druck_aus_csv(gestern)
            temp_daten  = self._temp_aus_csv(gestern)
            pfad = erstelle_tagesbericht(
                druck_daten=druck_daten,
                temp_daten=temp_daten,
                ausgabe_verzeichnis=self._projekt_ordner,
                datum=gestern,
            )
            self.log(f"📄 Automatischer Tagesbericht: {Path(pfad).name}",
                     farbe=self._theme["log_ok"])
        except Exception as e:
            self.log(f"⚠ Automatischer PDF-Fehler: {e}", farbe=self._theme["log_err"])
        finally:
            self._plane_mitternachts_timer()

    def _pdf_erstellen(self, datum: datetime | None = None) -> str:
        """Holt Daten aus den RAM-Panels (manueller Aufruf tagsüber)."""
        druck_daten = self.druck_panel.get_tages_daten()
        temp_daten  = self.temp_panel.get_tages_daten()
        pfad = erstelle_tagesbericht(
            druck_daten=druck_daten,
            temp_daten=temp_daten,
            ausgabe_verzeichnis=self._projekt_ordner,
            datum=datum,
        )
        return str(pfad)

    def _druck_aus_csv(self, datum: datetime) -> dict:
        """Liest Druck-CSV des Vortags. mbar -> Pa (*100)."""
        import csv as csv_mod
        from config import LOG_PFAD
        dateiname = Path(LOG_PFAD) / f"{datum.strftime('%Y-%m-%d')}_druck.csv"
        ergebnis = {"zeiten": [], "door": [], "center": [], "ba": []}
        if not dateiname.exists():
            self.log(f"⚠ Druck-CSV nicht gefunden: {dateiname.name}",
                     farbe=self._theme["log_warn"])
            return ergebnis
        with open(dateiname, newline="", encoding="utf-8") as f:
            reader = csv_mod.DictReader(f, delimiter="\t")
            for row in reader:
                try:
                    ts = datetime.fromisoformat(row["ISO_lokal"]).timestamp()
                    ergebnis["zeiten"].append(ts)
                    for csv_key, out_key in [("CENT","center"),("DOOR","door"),("BA","ba")]:
                        val = row.get(csv_key, "NaN")
                        try:
                            ergebnis[out_key].append(float(val) * 100.0)
                        except (ValueError, TypeError):
                            ergebnis[out_key].append(None)
                except Exception:
                    continue
        return ergebnis

    def _temp_aus_csv(self, datum: datetime) -> dict:
        """Liest Temperatur-CSV des Vortags.
        Unterstützt neues Format mit _ohm-Spalten (werden ignoriert).
        Kelvin direkt übernommen.
        """
        import csv as csv_mod
        from config import LOG_PFAD
        from daten.csv_schreiber import TEMP_SPALTEN
        dateiname = Path(LOG_PFAD) / f"{datum.strftime('%Y-%m-%d')}_temperatur.csv"
        ergebnis = {"zeiten": []}
        puffer = {name: [] for name in TEMP_SPALTEN}
        if not dateiname.exists():
            self.log(f"⚠ Temp-CSV nicht gefunden: {dateiname.name}",
                     farbe=self._theme["log_warn"])
            return ergebnis
        with open(dateiname, newline="", encoding="utf-8") as f:
            reader = csv_mod.DictReader(f, delimiter="\t")
            for row in reader:
                try:
                    ts = datetime.fromisoformat(row["ISO_lokal"]).timestamp()
                    ergebnis["zeiten"].append(ts)
                    for name in TEMP_SPALTEN:
                        val = row.get(name, "NaN")  # _ohm-Spalten werden ignoriert
                        try:
                            v = float(val)
                            puffer[name].append(None if (v != v) else v)
                        except (ValueError, TypeError):
                            puffer[name].append(None)
                except Exception:
                    continue
        for name, werte in puffer.items():
            if any(v is not None for v in werte):
                ergebnis[name] = werte
        return ergebnis

    def _drucke_pdf(self, pfad: str):
        """Schickt das PDF an den in config.py konfigurierten Drucker (Windows)."""
        try:
            from config import DRUCKER_NAME
        except ImportError:
            DRUCKER_NAME = None

        import subprocess, sys
        pfad_str = str(pfad)

        if sys.platform != "win32":
            self.log("Auto-Druck: nur unter Windows unterstützt",
                     farbe=self._theme["log_warn"])
            return

        try:
            if DRUCKER_NAME:
                # SumatraPDF (bevorzugt, weil lautlos)
                sumatra = r"C:\Program Files\SumatraPDF\SumatraPDF.exe"
                import os
                if os.path.exists(sumatra):
                    subprocess.Popen([
                        sumatra, "-print-to", DRUCKER_NAME,
                        "-print-settings", "fit",
                        "-silent", pfad_str
                    ])
                    self.log(f"🖨 Druckauftrag gesendet → {DRUCKER_NAME}",
                             farbe=self._theme["log_ok"])
                    return
                # Fallback: Windows-Shell-Druck (öffnet kurz ein Fenster)
                subprocess.Popen([
                    "rundll32.exe",
                    "mshtml.dll,PrintHTML",  # nur für HTML – stattdessen:
                ], shell=False)
            # Fallback ohne Druckername: Standarddrucker via Shell
            import os
            os.startfile(pfad_str, "print")
            self.log(f"🖨 Druckauftrag (Standarddrucker) gesendet",
                     farbe=self._theme["log_ok"])
        except Exception as e:
            self.log(f"⚠ Druckfehler: {e}", farbe=self._theme["log_err"])

    def _plane_mitternachts_timer(self):
        """Startet den Timer so, dass er 5 s nach Mitternacht UTC feuert."""
        jetzt = datetime.now(tz=timezone.utc)
        naechste_mitternacht = (jetzt + timedelta(days=1)).replace(
            hour=0, minute=0, second=5, microsecond=0
        )
        ms = int((naechste_mitternacht - jetzt).total_seconds() * 1000)
        self._mitternachts_timer.start(ms)
        pass  # Timer läuft still im Hintergrund

    def _sync_heater_kryo_sperre(self):
        """Initiale Synchronisation nach Programmstart:
        Sperrt Heater falls Kryos an, sperrt Kryos falls Heater an.
        Wird auch nach jedem Schaltvorgang über die Callbacks ausgelöst.
        """
        if self.steckdosen_panel.ist_heater_an():
            self._kryo_panel.kryos_verriegeln("Heater ist EIN")
        else:
            self._kryo_panel.kryos_freigeben()

        if self._kryo_panel.ist_kryo_an():
            self.steckdosen_panel.heater_verriegeln("mind. ein Kryo ist EIN")
        else:
            self.steckdosen_panel.heater_freigeben()

    def closeEvent(self, event):
        # Alarm-Einstellungen sichern
        try:
            self._alarm_einst.speichern()
        except Exception as e:
            from log_utils import tprint
            tprint("Shutdown", f"Alarm-Einstellungen nicht gespeichert: {e}")
        # Messzyklus stoppen (gibt Hardware frei)
        try:
            self._zyklus.stoppen()
        except Exception as e:
            tprint("Shutdown", f"Messzyklus-Fehler: {e}")
        # Steckdosen-Poll-Timer stoppen
        try:
            if hasattr(self.steckdosen_panel, '_timer'):
                self.steckdosen_panel._timer.stop()
        except Exception:
            pass
        # Fenster schließen
        for fenster in (self._grossanzeige, self._kalib_fenster,
                        self._historien_fenster):
            if fenster is not None:
                try:
                    fenster.close()
                except Exception:
                    pass
        event.accept()
