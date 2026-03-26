"""
gui/xsp01r_fenster.py
Statusfenster für den ZEB XSP01R Digital-I/O.
Zeigt den genauen Zustand aller 4 Relais und erlaubt direktes Schalten
mit Sicherheitsabfrage.
"""

import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFrame, QMessageBox, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


FARBE_AN   = "#16a34a"
FARBE_AUS  = "#dc2626"
FARBE_UNBEKANNT = "#94a3b8"

RELAIS_INFO = [
    ("Kryo 1 – System",  "kryo1_system", "kryo1_system_ein", "kryo1_system_aus",
     "Steuert den Hauptschalter von Kryo 1.\nMuss VOR Remote eingeschaltet werden."),
    ("Kryo 1 – Remote",  "kryo1_remote", "kryo1_remote_ein", "kryo1_remote_aus",
     "Aktiviert die Remote-Steuerung von Kryo 1.\nNur schalten wenn System EIN ist."),
    ("Kryo 2 – System",  "kryo2_system", "kryo2_system_ein", "kryo2_system_aus",
     "Steuert den Hauptschalter von Kryo 2.\nMuss VOR Remote eingeschaltet werden."),
    ("Kryo 2 – Remote",  "kryo2_remote", "kryo2_remote_ein", "kryo2_remote_aus",
     "Aktiviert die Remote-Steuerung von Kryo 2.\nNur schalten wenn System EIN ist."),
]


class RelaisZeile(QWidget):
    """Eine Zeile pro Relais: Name | LED | Status | EIN-Button | AUS-Button"""

    def __init__(self, label: str, status_key: str,
                 fn_ein: str, fn_aus: str, tooltip: str, parent=None):
        super().__init__(parent)
        self._status_key = status_key
        self._fn_ein     = fn_ein
        self._fn_aus     = fn_aus
        self.log_callback = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        # LED
        self._led = QFrame()
        self._led.setFixedSize(14, 14)
        self._led.setStyleSheet(f"background: {FARBE_UNBEKANNT}; border-radius: 7px;")
        layout.addWidget(self._led)

        # Name
        lbl = QLabel(label)
        lbl.setFixedWidth(130)
        lbl.setStyleSheet("font-size: 11px; font-weight: bold;")
        lbl.setToolTip(tooltip)
        layout.addWidget(lbl)

        # Status-Text
        self._lbl_status = QLabel("unbekannt")
        self._lbl_status.setFixedWidth(80)
        self._lbl_status.setStyleSheet("font-size: 11px; color: #7f8daa;")
        layout.addWidget(self._lbl_status)

        layout.addStretch()

        # EIN-Button
        self._btn_ein = QPushButton("EIN")
        self._btn_ein.setFixedSize(70, 30)
        self._btn_ein.setStyleSheet(self._btn_style(True))
        self._btn_ein.setToolTip(f"{label} einschalten")
        self._btn_ein.clicked.connect(lambda: self._schalten(True))
        layout.addWidget(self._btn_ein)

        # AUS-Button
        self._btn_aus = QPushButton("AUS")
        self._btn_aus.setFixedSize(70, 30)
        self._btn_aus.setStyleSheet(self._btn_style(False))
        self._btn_aus.setToolTip(f"{label} ausschalten")
        self._btn_aus.clicked.connect(lambda: self._schalten(False))
        layout.addWidget(self._btn_aus)

    def _btn_style(self, ein: bool) -> str:
        if ein:
            return ("QPushButton { background: #16a34a; border: 1px solid #15803d; "
                    "border-radius: 5px; color: white; font-size: 10px; font-weight: 800; } "
                    "QPushButton:hover { background: #15803d; }")
        else:
            return ("QPushButton { background: #1e2d45; border: 1.5px solid #4a5e80; "
                    "border-radius: 5px; color: #cbd5e1; font-size: 10px; font-weight: 800; } "
                    "QPushButton:hover { background: #dc2626; border-color: #b91c1c; color: white; }")

    def aktualisieren(self, status: dict):
        an = status.get(self._status_key, None)
        if an is None:
            self._led.setStyleSheet(f"background: {FARBE_UNBEKANNT}; border-radius: 7px;")
            self._lbl_status.setText("unbekannt")
            self._lbl_status.setStyleSheet("font-size: 11px; color: #7f8daa;")
        elif an:
            self._led.setStyleSheet(f"background: {FARBE_AN}; border-radius: 7px; "
                                    f"border: 1px solid #15803d;")
            self._lbl_status.setText("EIN")
            self._lbl_status.setStyleSheet(f"font-size: 11px; color: {FARBE_AN}; font-weight: bold;")
        else:
            self._led.setStyleSheet(f"background: {FARBE_AUS}; border-radius: 7px; "
                                    f"border: 1px solid #b91c1c;")
            self._lbl_status.setText("AUS")
            self._lbl_status.setStyleSheet(f"font-size: 11px; color: {FARBE_AUS}; font-weight: bold;")

    def _schalten(self, ein: bool):
        aktion = "EIN" if ein else "AUS"
        name   = self._status_key.replace("_", " ").upper()

        antwort = QMessageBox.question(
            self,
            f"Relais {aktion} schalten",
            f"Relais  \"{name}\"  wirklich {aktion} schalten?\n\n"
            f"{'⚠ Reihenfolge beachten: System vor Remote EIN schalten.' if ein else '⚠ Reihenfolge beachten: Remote vor System AUS schalten.'}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if antwort != QMessageBox.StandardButton.Yes:
            return

        def _run():
            try:
                from hardware.geraete import get_xsp01r
                x   = get_xsp01r()
                fn  = getattr(x, self._fn_ein if ein else self._fn_aus)
                fn()
                if self.log_callback:
                    self.log_callback(f"XSP01R Relais {name} → {aktion}")
            except Exception as e:
                if self.log_callback:
                    self.log_callback(f"XSP01R Fehler: {e}")

        threading.Thread(target=_run, daemon=True).start()


class Xsp01rFenster(QWidget):
    """Statusfenster für den XSP01R mit Relais-Anzeige und Einzelsteuerung."""

    def __init__(self, log_callback=None, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("XSP01R – Relais-Status")
        self.setFixedSize(580, 400)
        self.log_callback = log_callback
        self._zeilen: list[RelaisZeile] = []
        self._build_ui()

        # Auto-Update alle 2 Sekunden
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._aktualisieren)
        self._timer.start(2000)
        self._aktualisieren()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QLabel("ZEB XSP01R – Digitale Relaissteuerung")
        header.setStyleSheet("font-size: 13px; font-weight: bold; color: #7db2ff;")
        layout.addWidget(header)

        sub = QLabel("Kryo 1+2 System- und Remote-Relais  |  COM6")
        sub.setStyleSheet("font-size: 10px; color: #7f8daa;")
        layout.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2c3a57;")
        layout.addWidget(sep)

        # Kryo 1
        box1 = QGroupBox("Kryo 1")
        box1.setStyleSheet("QGroupBox { font-weight: bold; color: #e63946; "
                           "border: 1px solid #e63946; border-radius: 6px; margin-top: 8px; padding-top: 6px; } "
                           "QGroupBox::title { subcontrol-origin: margin; left: 8px; }")
        b1l = QVBoxLayout(box1)
        b1l.setSpacing(2)
        for label, key, fn_ein, fn_aus, tip in RELAIS_INFO[:2]:
            z = RelaisZeile(label, key, fn_ein, fn_aus, tip)
            z.log_callback = self.log_callback
            self._zeilen.append(z)
            b1l.addWidget(z)
        layout.addWidget(box1)

        # Kryo 2
        box2 = QGroupBox("Kryo 2")
        box2.setStyleSheet("QGroupBox { font-weight: bold; color: #f4a261; "
                           "border: 1px solid #f4a261; border-radius: 6px; margin-top: 8px; padding-top: 6px; } "
                           "QGroupBox::title { subcontrol-origin: margin; left: 8px; }")
        b2l = QVBoxLayout(box2)
        b2l.setSpacing(2)
        for label, key, fn_ein, fn_aus, tip in RELAIS_INFO[2:]:
            z = RelaisZeile(label, key, fn_ein, fn_aus, tip)
            z.log_callback = self.log_callback
            self._zeilen.append(z)
            b2l.addWidget(z)
        layout.addWidget(box2)

        # Schnellzugriff
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #2c3a57;")
        layout.addWidget(sep2)

        schnell = QHBoxLayout()
        for text, fn_name, farbe in [
            ("Kryo 1 EIN",  "kryo1_einschalten",  "#16a34a"),
            ("Kryo 1 AUS",  "kryo1_ausschalten",  "#dc2626"),
            ("Kryo 2 EIN",  "kryo2_einschalten",  "#16a34a"),
            ("Kryo 2 AUS",  "kryo2_ausschalten",  "#dc2626"),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(32)
            btn.setStyleSheet(
                f"QPushButton {{ background: {farbe}; border: none; border-radius: 5px; "
                f"color: white; font-size: 10px; font-weight: 800; }} "
                f"QPushButton:hover {{ opacity: 0.85; }}"
            )
            btn.clicked.connect(lambda _, f=fn_name, t=text: self._schnell_schalten(f, t))
            schnell.addWidget(btn)
        layout.addLayout(schnell)

        # Hinweis
        hinweis = QLabel("⚠  Schnellzugriff schaltet System+Remote in der korrekten Reihenfolge mit Wartezeit.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("font-size: 9px; color: #7f8daa; padding: 2px;")
        layout.addWidget(hinweis)

        # Status-Zeile
        self._lbl_verbindung = QLabel("● Verbindung wird geprüft ...")
        self._lbl_verbindung.setStyleSheet("font-size: 10px; color: #7f8daa;")
        layout.addWidget(self._lbl_verbindung)

    def _aktualisieren(self):
        def _run():
            try:
                from hardware.geraete import get_xsp01r
                st = get_xsp01r().status()
                # GUI-Update im Hauptthread
                from PyQt6.QtCore import QMetaObject, Q_ARG
                for zeile in self._zeilen:
                    zeile.aktualisieren(st)
                self._lbl_verbindung.setText("● Verbunden  (COM6)")
                self._lbl_verbindung.setStyleSheet("font-size: 10px; color: #16a34a;")
            except Exception as e:
                for zeile in self._zeilen:
                    zeile.aktualisieren({})
                self._lbl_verbindung.setText(f"● Nicht verbunden: {e}")
                self._lbl_verbindung.setStyleSheet("font-size: 10px; color: #dc2626;")

        threading.Thread(target=_run, daemon=True).start()

    def _schnell_schalten(self, fn_name: str, label: str):
        ein = "EIN" in label
        antwort = QMessageBox.question(
            self, f"{label}",
            f"Wirklich: {label}?\n\n"
            f"{'System EIN → 0.8s → Remote EIN' if ein else 'System AUS → 0.8s → Remote AUS'}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if antwort != QMessageBox.StandardButton.Yes:
            return

        def _run():
            try:
                from hardware.geraete import get_xsp01r
                x  = get_xsp01r()
                fn = getattr(x, fn_name)
                fn()
                if self.log_callback:
                    self.log_callback(f"XSP01R: {label}")
            except Exception as e:
                if self.log_callback:
                    self.log_callback(f"XSP01R Fehler: {e}")

        threading.Thread(target=_run, daemon=True).start()

    def closeEvent(self, event):
        self._timer.stop()
        event.accept()
