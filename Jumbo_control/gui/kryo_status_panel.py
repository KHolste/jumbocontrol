"""
gui/kryo_status_panel.py
Kryopumpen-Status mit Ampeln und EIN/AUS-Buttons.
Kryo 1+2 via XSP01R, Kryo 3-8 via Coolpack.
"""

import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QFrame, QPushButton, QSizePolicy, QMessageBox
)
from PyQt6.QtCore import QTimer, pyqtSignal, QObject

WARTUNG_GELB_AB = 2000
FARBE_GRUEN = "#16a34a"
FARBE_GELB  = "#d97706"
FARBE_ROT   = "#dc2626"
FARBE_GRAU  = "#94a3b8"


class KryoZeile(QWidget):
    # Signal für thread-sicheres GUI-Update
    status_empfangen = pyqtSignal(dict)

    def __init__(self, name: str, ist_xsp: bool = False, kryo_nr: int = 0, parent=None):
        super().__init__(parent)
        self._name    = name
        self._ist_xsp = ist_xsp
        self._kryo_nr = kryo_nr   # 1 oder 2 für XSP01R
        self.bei_aktion   = None
        self._heater_check = None  # Callback: True wenn Heater an

        # Signal verbinden
        self.status_empfangen.connect(self.aktualisieren)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(5)

        self._ampel = QFrame()
        self._ampel.setFixedSize(12, 12)
        self._ampel.setStyleSheet(f"background: {FARBE_GRAU}; border-radius: 6px;")
        layout.addWidget(self._ampel)

        lbl_name = QLabel(name)
        lbl_name.setFixedWidth(52)
        lbl_name.setStyleSheet("font-size: 10px; font-weight: bold;")
        layout.addWidget(lbl_name)

        self._lbl_stunden = QLabel("--- h")
        self._lbl_stunden.setFixedWidth(62)
        self._lbl_stunden.setStyleSheet("font-family: 'Consolas','Courier New'; font-size: 10px;")
        layout.addWidget(self._lbl_stunden)

        layout.addStretch(1)

        self._btn = QPushButton("AUS")
        self._btn.setCheckable(True)
        self._btn.setFixedSize(56, 28)
        self._btn.setStyleSheet(self._btn_style(False))
        self._btn.clicked.connect(self._schalten)
        layout.addWidget(self._btn)

    def _btn_style(self, an: bool) -> str:
        if an:
            return """QPushButton {
                background: #16a34a; border: 1.5px solid #15803d;
                border-radius: 5px; color: #ffffff;
                font-size: 11px; font-weight: 800; padding: 2px 4px;
            } QPushButton:hover { background: #15803d; }"""
        else:
            return """QPushButton {
                background: #dc2626; border: 1.5px solid #b91c1c;
                border-radius: 5px; color: #ffffff;
                font-size: 11px; font-weight: 800; padding: 2px 4px;
            } QPushButton:hover { background: #b91c1c; }"""

    def _schalten(self, an: bool):
        # Sicherheitscheck: Heater darf nicht an sein
        if an and callable(self._heater_check):
            if self._heater_check():
                self._btn.blockSignals(True)
                self._btn.setChecked(False)
                self._btn.setText("AUS")
                self._btn.setStyleSheet(self._btn_style(False))
                self._btn.blockSignals(False)
                if self.bei_aktion:
                    self.bei_aktion(f"⛔ {self._name}: Kryo gesperrt – Heater ist EIN!")
                return
        # GUI sofort aktualisieren
        self._btn.blockSignals(True)
        self._btn.setText("EIN" if an else "AUS")
        self._btn.setChecked(an)
        self._btn.setStyleSheet(self._btn_style(an))
        self._btn.blockSignals(False)

        # Hardware im Hintergrund schalten
        def _run():
            try:
                if self._ist_xsp:
                    from hardware.geraete import get_xsp01r
                    x = get_xsp01r()
                    if self._kryo_nr == 1:
                        x.kryo1_einschalten() if an else x.kryo1_ausschalten()
                    else:
                        x.kryo2_einschalten() if an else x.kryo2_ausschalten()
                else:
                    from config import COOLPACK_PORTS
                    from hardware.coolpack import Coolpack
                    port = COOLPACK_PORTS.get(self._name)
                    if port:
                        c = Coolpack(port, name=self._name)
                        c.einschalten() if an else c.ausschalten()
                        c.beenden()
                if self.bei_aktion:
                    self.bei_aktion(f"{self._name} → {'EIN' if an else 'AUS'}")
            except Exception as e:
                if self.bei_aktion:
                    self.bei_aktion(f"{self._name} Fehler: {e}")

        threading.Thread(target=_run, daemon=True).start()

    def aktualisieren(self, status: dict):
        if not status.get("gueltig"):
            self._ampel.setStyleSheet(f"background: {FARBE_GRAU}; border-radius: 6px;")
            self._lbl_stunden.setText("n/v")
            return

        stunden    = status.get("betriebsstunden") or 0
        wartung_in = status.get("wartung_in_h")    or 0
        faellig    = status.get("wartung_faellig", False)
        fehler     = status.get("fehler_liste",    [])
        an         = status.get("kompressor_an",   False)

        self._btn.blockSignals(True)
        self._btn.setChecked(an)
        self._btn.setText("EIN" if an else "AUS")
        self._btn.setStyleSheet(self._btn_style(an))
        self._btn.blockSignals(False)

        farbe = FARBE_ROT if fehler else FARBE_GRUEN
        self._ampel.setStyleSheet(f"background: {farbe}; border-radius: 6px;")

        if stunden:
            self._lbl_stunden.setText(f"{stunden:,} h".replace(",", "."))
            self._lbl_stunden.setStyleSheet(
                f"font-family: 'Consolas','Courier New'; font-size: 10px; color: {farbe};"
            )

        if fehler:
            self._lbl_stunden.setToolTip(f"⚠ {fehler[0]}")
        else:
            self._lbl_stunden.setToolTip("")


class KryoStatusPanel(QWidget):
    # Thread-sichere Signale zum Setzen der Buttons
    kryo_ein_signal = pyqtSignal(str)   # name des Kryos
    kryo_aus_signal = pyqtSignal(str)   # name des Kryos

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zeilen         = {}
        self._coolpack_ports = {}
        self.bei_aktion      = None
        self._heater_an_check = None  # Callback: True wenn Heater an
        self._kryos_gesperrt  = False
        self._schalt_lock     = threading.Lock()
        self._build_ui()
        self._laden()
        self.kryo_ein_signal.connect(self._set_kryo_ein)
        self.kryo_aus_signal.connect(self._set_kryo_aus)

        self._timer = QTimer()
        self._timer.timeout.connect(self._aktualisieren)
        self._timer.start(60_000)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._box = QGroupBox("Kryopumpen – Betriebsstunden")
        box_layout = QVBoxLayout(self._box)
        box_layout.setContentsMargins(4, 4, 4, 4)
        box_layout.setSpacing(1)

        # Header
        header = QHBoxLayout()
        for txt, w in [("", 12), ("Kryo", 52), ("Stunden", 62), ("", 48)]:
            lbl = QLabel(txt)
            lbl.setFixedWidth(w)
            lbl.setStyleSheet("font-size: 9px; color: #888; font-weight: bold;")
            header.addWidget(lbl)
        header.addStretch()
        box_layout.addLayout(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #e2e8f0;")
        box_layout.addWidget(sep)

        # Alle EIN / Alle AUS
        btn_row = QHBoxLayout()
        self._btn_alle_ein = QPushButton("Alle EIN")
        self._btn_alle_ein.setStyleSheet(self._alle_ein_style(False))
        self._btn_alle_ein.clicked.connect(lambda: self._alle_schalten(True))
        btn_row.addWidget(self._btn_alle_ein)

        self._btn_alle_aus = QPushButton("Alle AUS")
        self._btn_alle_aus.setStyleSheet("""
            QPushButton {
                background: #f1f5f9; border: 2px solid #94a3b8;
                border-radius: 5px; color: #334155;
                font-size: 11px; font-weight: 700; padding: 5px 12px;
            }
            QPushButton:hover { border-color: #dc2626; color: #dc2626; }
        """)
        self._btn_alle_aus.clicked.connect(lambda: self._alle_schalten(False))
        btn_row.addWidget(self._btn_alle_aus)
        btn_row.addStretch()
        box_layout.addLayout(btn_row)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #e2e8f0;")
        box_layout.addWidget(sep2)

        self._box_layout = box_layout
        layout.addWidget(self._box)
        layout.addStretch()

    def _alle_ein_style(self, aktiv: bool) -> str:
        if aktiv:
            return """QPushButton {
                background: #16a34a; border: none; border-radius: 5px;
                color: white; font-size: 11px; font-weight: 700; padding: 5px 12px;
            } QPushButton:hover { background: #15803d; }"""
        else:
            return """QPushButton {
                background: #f1f5f9; border: 2px solid #94a3b8;
                border-radius: 5px; color: #334155;
                font-size: 11px; font-weight: 700; padding: 5px 12px;
            } QPushButton:hover { border-color: #16a34a; color: #16a34a; }"""

    def _laden(self):
        try:
            from config import COOLPACK_PORTS
            self._coolpack_ports = COOLPACK_PORTS

            # Kryo 1+2 → XSP01R
            for kryo_nr, name in [(1, "Kryo 1"), (2, "Kryo 2")]:
                zeile = KryoZeile(name, ist_xsp=True, kryo_nr=kryo_nr)
                zeile.bei_aktion = self._log
                self._zeilen[name] = zeile
                self._box_layout.addWidget(zeile)

            # Kryo 3-8 → Coolpack
            for name in COOLPACK_PORTS:
                zeile = KryoZeile(name, ist_xsp=False)
                zeile.bei_aktion = self._log
                self._zeilen[name] = zeile
                self._box_layout.addWidget(zeile)

            self._aktualisieren()

        except Exception as e:
            lbl = QLabel(f"Fehler: {e}")
            lbl.setStyleSheet("font-size: 10px; color: #888;")
            self._box_layout.addWidget(lbl)

    
    def _aktualisieren(self):
        def _run():
            status_liste = []
    
            # Kryo 1+2 über XSP01R
            try:
                from hardware.geraete import get_xsp01r
                x = get_xsp01r()
    
                for kryo_nr, name in [(1, "Kryo 1"), (2, "Kryo 2")]:
                    try:
                        st = x.xsp_status_als_kryo(kryo=kryo_nr)
    
                        if name in self._zeilen:
                            self._zeilen[name].status_empfangen.emit(st)
    
                        if isinstance(st, dict) and st.get("gueltig", False):
                            st_csv = dict(st)
                            st_csv["name"] = name
                            status_liste.append(st_csv)
    
                    except Exception as e:
                        from log_utils import tprint
                        tprint("KryoStatusPanel", f"{name} XSP01R: {e}")
    
            except Exception as e:
                tprint("KryoStatusPanel", f"XSP01R allgemein: {e}")
    
            # Kryo 3-8 über Coolpack
            for name, port in self._coolpack_ports.items():
                c = None
                try:
                    from hardware.coolpack import Coolpack
                    c = Coolpack(port, name=name)
                    st = c.status()
    
                    if name in self._zeilen:
                        self._zeilen[name].status_empfangen.emit(st)
    
                    if isinstance(st, dict) and st.get("gueltig", False):
                        status_liste.append(st)
    
                except Exception as e:
                    tprint("KryoStatusPanel", f"{name}: {e}")
    
                finally:
                    if c is not None:
                        try:
                            c.beenden()
                        except Exception:
                            pass
    
            # CSV schreiben
            if status_liste:
                try:
                    from daten.kryo_csv import KryoCsvSchreiber
                    KryoCsvSchreiber().speichere(status_liste)
                except Exception as e:
                    tprint("KryoStatusPanel", f"CSV: {e}")
    
            # GUI-nahes Update
            self._update_alle_ein_button()
    
        threading.Thread(target=_run, daemon=True).start()
    
    
    def _alle_schalten(self, an: bool):
        if an and self._heater_an_check and self._heater_an_check():
            if self.bei_aktion:
                self.bei_aktion("⛔ Alle Kryos EIN blockiert – Heater ist EIN!")
            return
    
        if not an:
            antwort = QMessageBox.question(
                self, "Alle Kryos AUS",
                "Wirklich ALLE Kryopumpen ausschalten?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if antwort != QMessageBox.StandardButton.Yes:
                return
    
        namen = list(self._zeilen.keys())
    
        def _schalte_index(i: int):
            if i >= len(namen):
                if self.bei_aktion:
                    self.bei_aktion(f"Alle Kryos → {'EIN' if an else 'AUS'}")
                return
    
            name = namen[i]
            zeile = self._zeilen[name]
    
            try:
                zeile._btn.blockSignals(True)
                zeile._btn.setChecked(an)
                zeile._btn.blockSignals(False)
    
                zeile._schalten(an)
    
            except Exception as e:
                if self.bei_aktion:
                    self.bei_aktion(f"{name} Fehler: {e}")
    
            delay_ms = 2000
            QTimer.singleShot(delay_ms, lambda: _schalte_index(i + 1))
    
        _schalte_index(0)    


    def _update_alle_ein_button(self):
        alle_an = all(z._btn.isChecked() for z in self._zeilen.values())
        self._btn_alle_ein.setStyleSheet(self._alle_ein_style(alle_an))

    def _set_kryo_ein(self, name: str):
        """Setzt einen Kryo-Button auf EIN – thread-sicher via Signal."""
        if name in self._zeilen:
            zeile = self._zeilen[name]
            zeile._btn.blockSignals(True)
            zeile._btn.setChecked(True)
            zeile._btn.setText("EIN")
            zeile._btn.setStyleSheet(zeile._btn_style(True))
            zeile._btn.blockSignals(False)
        self._update_alle_ein_button()

    def _set_kryo_aus(self, name: str):
        """Setzt einen Kryo-Button auf AUS – thread-sicher via Signal."""
        if name in self._zeilen:
            zeile = self._zeilen[name]
            zeile._btn.blockSignals(True)
            zeile._btn.setChecked(False)
            zeile._btn.setText("AUS")
            zeile._btn.setStyleSheet(zeile._btn_style(False))
            zeile._btn.blockSignals(False)
        self._update_alle_ein_button()

    def _log(self, text: str):
        if self.bei_aktion:
            self.bei_aktion(text)

    # ── Kryos-Verriegelung (von SteckdosenPanel gesteuert) ───
    def kryos_verriegeln(self, grund: str = "Heater aktiv"):
        """Sperrt alle Kryo-Buttons – Heater ist EIN."""
        self._kryos_gesperrt = True
        for zeile in self._zeilen.values():
            zeile._btn.setEnabled(False)
            zeile._btn.setToolTip(f"⚠ Gesperrt: {grund}")
        self._btn_alle_ein.setEnabled(False)
        self._btn_alle_ein.setToolTip(f"⚠ Gesperrt: {grund}")
        if self.bei_aktion:
            self.bei_aktion(f"⚠ Alle Kryos gesperrt: {grund}")

    def kryos_freigeben(self):
        """Gibt alle Kryo-Buttons wieder frei – Heater AUS."""
        self._kryos_gesperrt = False
        for zeile in self._zeilen.values():
            zeile._btn.setEnabled(True)
            zeile._btn.setToolTip("")
        self._btn_alle_ein.setEnabled(True)
        self._btn_alle_ein.setToolTip("")
        if self.bei_aktion:
            self.bei_aktion("Kryos freigegeben – Heater AUS")

    def ist_kryo_an(self) -> bool:
        """True wenn mind. 1 Kryo-Button auf EIN steht."""
        return any(z._btn.isChecked() for z in self._zeilen.values())

    def set_heater_an_check(self, fn):
        """Setzt Callback der prüft ob Heater an ist. Wird an alle KryoZeilen weitergegeben."""
        self._heater_an_check = fn
        for zeile in self._zeilen.values():
            zeile._heater_check = fn

    def set_log_callback(self, fn):
        self.bei_aktion = fn
