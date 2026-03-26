"""
gui/steckdosen_panel.py
Buttons für die IP-Steckdosenleiste.

Sicherheitsfeature V1:
    V1 ist gesperrt wenn mindestens ein gültiger Drucksensor < 1 mbar anzeigt.
    Overrange gilt als >= 1 mbar (Druck zu hoch = kein Vakuum = sicher).
    Wenn alle Sensoren ausgefallen sind (kein Signal) → gesperrt.
    Wenn alle Sensoren Overrange → freigegeben.
"""

import threading
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QFrame,
    QMenu, QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox,
    QGroupBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMessageBox
from hardware.steckdose import Steckdose, DOSEN
from PyQt6.QtWidgets import QSizePolicy

V1_DRUCKGRENZE     = 1.0    # mbar
ROOTS_DRUCKGRENZE  = 40.0   # mbar
ROOTS_MODUS        = "any"  # "any"=mind.1 Sensor, "all"=alle drei
OVERRANGE_MBAR  = 1013.25

ALLE_KRYOS = [f"Kryo {i}" for i in range(1, 9)]
KRYO_XSP   = ["Kryo 1", "Kryo 2"]
KRYO_COOL  = [f"Kryo {i}" for i in range(3, 9)]


class KryoKonfigDialog(QDialog):

    def __init__(self, aktive_kryos: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kryo-Button Konfiguration")
        self.setMinimumWidth(280)
        layout = QVBoxLayout(self)

        box = QGroupBox("Kryopumpen über Button steuern")
        box_layout = QVBoxLayout(box)
        self._checks = {}
        for name in ALLE_KRYOS:
            cb = QCheckBox(name)
            cb.setChecked(name in aktive_kryos)
            suffix = "(XSP01R Relais)" if name in KRYO_XSP else "(Coolpack)"
            cb.setText(f"{name}  {suffix}")
            box_layout.addWidget(cb)
            self._checks[name] = cb
        layout.addWidget(box)

        hinweis = QLabel("Nicht ausgewählte Kryos werden beim\nDrücken des Buttons ignoriert.")
        hinweis.setStyleSheet("font-size: 10px; color: #666; padding: 4px;")
        layout.addWidget(hinweis)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def ausgewaehlte_kryos(self) -> list:
        return [name for name, cb in self._checks.items() if cb.isChecked()]


class SteckdosenPanel(QWidget):
    _status_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(48)
        self._steckdose   = Steckdose()
        self._buttons     = {}
        self.bei_aktion   = None
        self._druck_werte = {}
        self._v1_gesperrt     = True
        self._roots_gesperrt  = True
        self._heater_gesperrt = False
        self._kryo_an_check   = None
        self._xsp01r_fenster  = None
        self._aktive_kryos    = list(ALLE_KRYOS)
        self._build_ui()
        self._status_laden()
        self._status_signal.connect(self._status_anwenden)

        # Status-Poll alle 3s – erkennt manuelles Schalten
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._status_aktualisieren)
        self._poll_timer.start(3_000)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        lbl = QLabel("Steckdosen:")
        lbl.setStyleSheet("font-size: 10px; color: #666;")
        layout.addWidget(lbl)

        for name in DOSEN:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedSize(90, 36)
            btn.setStyleSheet(self._style(False))
            btn.clicked.connect(lambda checked, n=name, b=btn: self._schalten(n, b))
            self._buttons[name] = btn
            layout.addWidget(btn)

        self._v1_sperren("Druckstatus noch unbekannt")
        self._roots_sperren("Druckstatus noch unbekannt")

        # XSP01R-Button – farblich abgehoben (nicht zu Steckdosen)
        sep_xsp = QFrame()
        sep_xsp.setFrameShape(QFrame.Shape.VLine)
        sep_xsp.setFixedWidth(1)
        sep_xsp.setStyleSheet("background: #2c3a57; margin: 6px 4px;")
        layout.addWidget(sep_xsp)

        self._btn_xsp = QPushButton("⚡ XSP01R")
        self._btn_xsp.setFixedSize(100, 36)
        self._btn_xsp.setToolTip(
            "XSP01R Relais-Status anzeigen\n"
            "Kryo 1+2 System- und Remote-Relais"
        )
        self._btn_xsp.setStyleSheet("""
            QPushButton {
                background: #7c3aed; border: 2px solid #6d28d9;
                border-radius: 6px; color: #ffffff;
                font-size: 11px; font-weight: 800;
            }
            QPushButton:hover { background: #8b5cf6; border-color: #7c3aed; }
            QPushButton:pressed { background: #6d28d9; }
        """)
        self._btn_xsp.clicked.connect(self._xsp01r_oeffnen)
        layout.addWidget(self._btn_xsp)

        layout.addStretch()

    # ── Drucksicherheit V1 ────────────────────────────────────
    def update_druck(self, werte: dict):
        """Wird vom Hauptfenster nach jeder Druckmessung aufgerufen."""
        self._druck_werte = werte
        self._v1_sicherheit_pruefen()
        self._roots_sicherheit_pruefen()

    def _v1_sicherheit_pruefen(self):
        werte = self._druck_werte
        if not werte:
            self._v1_sperren("Druckstatus unbekannt")
            return

        # Sensoren kategorisieren
        gueltig   = {n: d for n, d in werte.items() if d.get("gueltig") and d.get("mbar") is not None}
        overrange = {n: d for n, d in werte.items()
                     if d.get("status") in ("Overrange",) or
                     (d.get("mbar") is not None and d["mbar"] >= OVERRANGE_MBAR)}

        # Alle ausgefallen?
        if not gueltig and not overrange:
            self._v1_sperren("Alle Drucksensoren ausgefallen")
            return

        # Mindestens ein gültiger Sensor unter Grenzwert?
        unter = {n: d for n, d in gueltig.items() if d["mbar"] < V1_DRUCKGRENZE}
        if unter:
            details = ", ".join(
                f"{n}: {d['mbar']:.2E} mbar" for n, d in unter.items()
            )
            self._v1_sperren(f"Druck zu niedrig – {details}")
            return

        # Alles OK → freigeben
        self._v1_freigeben()

    def _v1_sperren(self, grund: str):
        btn = self._buttons.get("V1")
        if not btn:
            return
        war_frei = self._v1_gesperrt is False
        self._v1_gesperrt = True
        btn.setEnabled(False)
        btn.setToolTip(f"⚠ V1 gesperrt:\n{grund}")
        btn.setStyleSheet("""
            QPushButton {
                background: #e2e8f0; border: 2px solid #cbd5e1;
                border-radius: 6px; color: #94a3b8;
                font-size: 13px; font-weight: 700; padding: 7px 18px;
            }
        """)
        if war_frei and self.bei_aktion:
            self.bei_aktion(f"⚠ V1 gesperrt: {grund}")

    def _v1_freigeben(self):
        btn = self._buttons.get("V1")
        if not btn:
            return
        war_gesperrt = self._v1_gesperrt is True
        self._v1_gesperrt = False
        btn.setEnabled(True)
        btn.setToolTip("")
        an = btn.isChecked()
        btn.setStyleSheet(self._style(an))
        if war_gesperrt and self.bei_aktion:
            sensoren = ", ".join(
                f"{n}: {d['mbar']:.2E} mbar"
                for n, d in self._druck_werte.items()
                if d.get("gueltig") and d.get("mbar") is not None
            )
            self.bei_aktion(f"V1 freigegeben ({sensoren})")

    # ── Normales Schalten ─────────────────────────────────────
    def _schalten(self, name: str, btn: QPushButton):
        if name == "Heater" and btn.isChecked():
            if self._heater_gesperrt:
                btn.setChecked(False)
                if self.bei_aktion:
                    self.bei_aktion("⛔ Heater gesperrt – mind. ein Kryo ist EIN!")
                return
            if self._kryo_an_check and self._kryo_an_check():
                btn.setChecked(False)
                if self.bei_aktion:
                    self.bei_aktion("⛔ Heater kann nicht eingeschaltet werden – Kryos aktiv!")
                return
        if name == "Roots" and self._roots_gesperrt:
            btn.setChecked(False)
            if self.bei_aktion:
                self.bei_aktion("⛔ Roots blockiert – Druck zu hoch!")
            return
        if name == "V1" and self._v1_gesperrt:
            btn.setChecked(False)
            if self.bei_aktion:
                self.bei_aktion("⛔ V1 Schaltversuch blockiert – Druck zu niedrig!")
            return

        an = btn.isChecked()

        # Bestätigungsdialog für V1
        if name == "V1" and an:
            antwort = QMessageBox.question(
                self, "V1 einschalten",
                "V1 wirklich einschalten?\n\nBitte sicherstellen dass der Druck >= 1 mbar ist.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if antwort != QMessageBox.StandardButton.Yes:
                btn.setChecked(False)
                return

        if an:
            self._steckdose.einschalten(name)
        else:
            self._steckdose.ausschalten(name)
        btn.setStyleSheet(self._style(an))
        self._log(f"{name} → {'EIN' if an else 'AUS'}")

    def _style(self, an: bool) -> str:
        if an:
            return """QPushButton {
                background: #2563eb; border: none; border-radius: 6px;
                color: #ffffff; font-size: 13px; font-weight: 700; padding: 7px 18px;
            } QPushButton:hover { background: #1d4ed8; }"""
        else:
            return """QPushButton {
                background: #f1f5f9; border: 2px solid #94a3b8;
                border-radius: 6px; color: #334155;
                font-size: 13px; font-weight: 700; padding: 7px 18px;
            } QPushButton:hover { background: #e2e8f0; border-color: #2563eb; color: #2563eb; }"""

    # ── Kryo-Button ───────────────────────────────────────────
    def _kryo_style(self, an: bool) -> str:
        if an:
            return """QPushButton {
                background: #16a34a; border: none; border-radius: 6px;
                color: white; font-size: 13px; font-weight: 700; padding: 7px 18px;
            } QPushButton:hover { background: #15803d; }"""
        else:
            return """QPushButton {
                background: #f1f5f9; border: 2px solid #94a3b8;
                border-radius: 6px; color: #334155;
                font-size: 13px; font-weight: 700; padding: 7px 18px;
            } QPushButton:hover { border-color: #16a34a; color: #16a34a; }"""

    def _kryo_schalten(self, an: bool):
        self._btn_kryo.setText("Kryo EIN" if an else "Kryo AUS")
        self._btn_kryo.setStyleSheet(self._kryo_style(an))

        def _run():
            erfolg = []
            fehler = []
            # Kryo 1+2 → XSP01R
            xsp_kryos = [k for k in self._aktive_kryos if k in KRYO_XSP]
            if xsp_kryos:
                try:
                    from hardware.geraete import get_xsp01r
                    x = get_xsp01r()
                    for k in xsp_kryos:
                        if k == "Kryo 1":
                            if an: x.kryo1_einschalten()
                            else:  x.kryo1_ausschalten()
                        elif k == "Kryo 2":
                            if an: x.kryo2_einschalten()
                            else:  x.kryo2_ausschalten()
                    erfolg += xsp_kryos
                except Exception as e:
                    fehler += [f"{k}: {e}" for k in xsp_kryos]

            # Kryo 3-8 → Coolpack
            cool_kryos = [k for k in self._aktive_kryos if k in KRYO_COOL]
            if cool_kryos:
                try:
                    from config import COOLPACK_PORTS
                    from hardware.coolpack import Coolpack
                    for name in cool_kryos:
                        port = COOLPACK_PORTS.get(name)
                        if not port:
                            fehler.append(f"{name}: kein Port")
                            continue
                        try:
                            c = Coolpack(port, name=name)
                            if an:
                                c.einschalten()
                            else:
                                c.ausschalten()
                            c.beenden()
                            erfolg.append(name)
                        except Exception as e:
                            fehler.append(f"{name}: {e}")
                except ImportError as e:
                    fehler.append(str(e))

            msg = f"Kryo {'EIN' if an else 'AUS'}: {', '.join(erfolg)}"
            if fehler:
                msg += f"  ⚠ {', '.join(fehler)}"
            if self.bei_aktion:
                self.bei_aktion(msg)

        threading.Thread(target=_run, daemon=True).start()

    def _kryo_kontextmenu(self, pos):
        menu = QMenu(self._btn_kryo)
        act_konfig = QAction("⚙  Konfigurieren...", self)
        act_konfig.triggered.connect(self._kryo_konfigurieren)
        menu.addAction(act_konfig)
        menu.exec(self._btn_kryo.mapToGlobal(pos))

    def _kryo_konfigurieren(self):
        dlg = KryoKonfigDialog(self._aktive_kryos, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._aktive_kryos = dlg.ausgewaehlte_kryos()
            if self.bei_aktion:
                self.bei_aktion(
                    f"Kryo-Konfiguration: {', '.join(self._aktive_kryos) or 'keine'}"
                )

    # ── Hilfsmethoden ─────────────────────────────────────────
    def _log(self, text: str):
        if self.bei_aktion:
            self.bei_aktion(text)

    def _roots_sicherheit_pruefen(self):
        werte = self._druck_werte
        if not werte:
            self._roots_sperren("Druckstatus unbekannt"); return
        gueltig = {n: d for n, d in werte.items()
                   if d.get("gueltig") and d.get("mbar") is not None
                   and d.get("status") not in ("Overrange","Underrange",
                       "Sensor error","Sensor off","No sensor")}
        if not gueltig:
            self._roots_sperren("Keine gültigen Druckwerte"); return
        unter = {n: d for n, d in gueltig.items() if d["mbar"] < ROOTS_DRUCKGRENZE}
        if ROOTS_MODUS == "all":
            if len(unter) < len(gueltig):
                ueber = {n: d for n, d in gueltig.items() if d["mbar"] >= ROOTS_DRUCKGRENZE}
                details = ", ".join(f"{n}: {d['mbar']:.1f} mbar" for n, d in ueber.items())
                self._roots_sperren(f"Druck zu hoch – {details}"); return
        else:
            if not unter:
                details = ", ".join(f"{n}: {d['mbar']:.1f} mbar" for n, d in gueltig.items())
                self._roots_sperren(f"Druck zu hoch – {details}"); return
        self._roots_freigeben()

    def _roots_sperren(self, grund: str):
        btn = self._buttons.get("Roots")
        if not btn: return
        war_frei = self._roots_gesperrt is False
        self._roots_gesperrt = True
        btn.setEnabled(False)
        btn.setToolTip(f"⚠ Roots gesperrt:\n{grund}\n(Grenze: < {ROOTS_DRUCKGRENZE} mbar)")
        btn.setStyleSheet("QPushButton { background: #e2e8f0; border: 2px solid #cbd5e1;"
            " border-radius: 6px; color: #94a3b8; font-size: 13px; font-weight: 700; padding: 7px 18px; }")
        if war_frei and self.bei_aktion:
            self.bei_aktion(f"⚠ Roots gesperrt: {grund}")

    def _roots_freigeben(self):
        btn = self._buttons.get("Roots")
        if not btn: return
        war_gesperrt = self._roots_gesperrt is True
        self._roots_gesperrt = False
        btn.setEnabled(True)
        btn.setToolTip(f"Roots-Pumpe (Grenze: < {ROOTS_DRUCKGRENZE} mbar)")
        btn.setStyleSheet(self._style(btn.isChecked()))
        if war_gesperrt and self.bei_aktion:
            self.bei_aktion("Roots freigegeben – Druck unter Grenzwert")

    def heater_verriegeln(self, grund: str = "Kryos aktiv"):
        self._heater_gesperrt = True
        btn = self._buttons.get("Heater")
        if btn:
            btn.setEnabled(False)
            btn.setToolTip(f"⚠ Heater gesperrt: {grund}")
            btn.setStyleSheet("QPushButton { background: #e2e8f0; border: 2px solid #fbbf24;"
                " border-radius: 6px; color: #94a3b8; font-size: 13px; font-weight: 700; padding: 7px 18px; }")
        if self.bei_aktion:
            self.bei_aktion(f"⚠ Heater gesperrt: {grund}")

    def heater_freigeben(self):
        self._heater_gesperrt = False
        btn = self._buttons.get("Heater")
        if btn:
            btn.setEnabled(True)
            btn.setToolTip("")
            btn.setStyleSheet(self._style(btn.isChecked()))
        if self.bei_aktion:
            self.bei_aktion("Heater freigegeben – alle Kryos AUS")

    def get_druck_werte(self) -> dict:
        """Gibt die zuletzt empfangenen Druckwerte zurück (thread-safe lesbar)."""
        return self._druck_werte

    def ist_heater_an(self) -> bool:
        btn = self._buttons.get("Heater")
        return bool(btn and btn.isChecked())

    def set_kryo_an_check(self, fn):
        self._kryo_an_check = fn

    def _xsp01r_oeffnen(self):
        """Öffnet das XSP01R-Statusfenster."""
        from gui.xsp01r_fenster import Xsp01rFenster
        if self._xsp01r_fenster is None or not self._xsp01r_fenster.isVisible():
            self._xsp01r_fenster = Xsp01rFenster(
                log_callback=self.bei_aktion,
                parent=None
            )
        self._xsp01r_fenster.show()
        self._xsp01r_fenster.raise_()

    def _status_aktualisieren(self):
        """Poll alle 3s – erkennt manuell geschaltete Dosen."""
        import threading
        def _run():
            try:
                status = self._steckdose.status_alle()
                self._status_signal.emit(status)
            except Exception as e:
                print(f"[Poll Fehler] {e}")
        threading.Thread(target=_run, daemon=True).start()

    def _status_anwenden(self, status: dict):
        """Aktualisiert Buttons im GUI-Thread."""
        geaendert = False
        for name, d in status.items():
            if name not in self._buttons or not d["gueltig"]:
                continue
            if name == "V1":
                continue  # V1 durch Drucksicherheit gesteuert
            an  = d["an"]
            btn = self._buttons[name]
            if btn.isChecked() != an:
                btn.blockSignals(True)
                btn.setChecked(an)
                # Gesperrten Style nicht überschreiben
                if name == "Heater" and self._heater_gesperrt:
                    pass  # Style bleibt gesperrt
                elif name == "Roots" and self._roots_gesperrt:
                    pass
                else:
                    btn.setStyleSheet(self._style(an))
                btn.blockSignals(False)
                geaendert = True
                if self.bei_aktion:
                    self.bei_aktion(
                        f"Steckdose {name} extern auf {'EIN' if an else 'AUS'} geschaltet"
                    )
        # Verriegelungen neu prüfen wenn sich etwas geändert hat
        if geaendert:
            self._v1_sicherheit_pruefen()
            self._roots_sicherheit_pruefen()
            # Heater-Zustand hat sich geändert → Kryos neu sperren/freigeben
            heater_an = self._buttons["Heater"].isChecked() if "Heater" in self._buttons else False
            if heater_an and not self._heater_gesperrt:
                # Heater wurde extern eingeschaltet → Kryos sperren
                if hasattr(self, "_kryo_panel_ref") and self._kryo_panel_ref:
                    self._kryo_panel_ref.kryos_verriegeln("Heater extern eingeschaltet")
            elif not heater_an:
                if hasattr(self, "_kryo_panel_ref") and self._kryo_panel_ref:
                    self._kryo_panel_ref.kryos_freigeben()

    def _status_laden(self):
        try:
            status = self._steckdose.status_alle()
            for name, d in status.items():
                if name in self._buttons and d["gueltig"] and name != "V1":
                    an = d["an"]
                    self._buttons[name].setChecked(an)
                    self._buttons[name].setStyleSheet(self._style(an))
        except Exception:
            pass
