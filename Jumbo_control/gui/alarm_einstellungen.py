"""
gui/alarm_einstellungen.py
Einstellungsfenster für Alarm- und Ausreißer-Schwellen.
Persistiert Einstellungen in JSON (daten/logs/alarm_einstellungen.json).
"""

import json
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QDoubleSpinBox, QTabWidget, QWidget,
    QGroupBox, QGridLayout, QPushButton, QDialogButtonBox,
    QLineEdit
)
from PyQt6.QtCore import Qt
from config import LOG_PFAD


# ── Standardwerte ─────────────────────────────────────────────
DEFAULTS = {
    "temp": {
        "sprung_alarm_aktiv":    True,
        "sprung_alarm_grad":     10.0,    # °C pro Zyklus
        "ausreisser_aktiv":      True,
        "ausreisser_grad":       50.0,    # °C pro Zyklus → rausfiltern
    },
    "druck": {
        "sprung_alarm_aktiv":    True,
        "sprung_alarm_dekaden":  1.0,     # Dekaden pro Sekunde
        "ausreisser_aktiv":      True,
        "ausreisser_dekaden":    3.0,     # Dekaden pro Sekunde → rausfiltern
    }
}

_JSON_PFAD = os.path.join(LOG_PFAD, "alarm_einstellungen.json")


def _validiere(daten: dict) -> dict:
    """Validiert geladene Daten gegen DEFAULTS – fehlende/ungültige Keys → Default."""
    ergebnis = {}
    for bereich in ("temp", "druck"):
        ergebnis[bereich] = {}
        defaults = DEFAULTS[bereich]
        section = daten.get(bereich, {})
        if not isinstance(section, dict):
            section = {}
        for key, default in defaults.items():
            val = section.get(key, default)
            # Typprüfung: bool-Keys müssen bool sein, float-Keys positiv
            if isinstance(default, bool):
                ergebnis[bereich][key] = bool(val)
            elif isinstance(default, (int, float)):
                try:
                    val = float(val)
                    ergebnis[bereich][key] = val if val > 0 else default
                except (TypeError, ValueError):
                    ergebnis[bereich][key] = default
    return ergebnis


class AlarmEinstellungen:
    """Hält die aktuellen Alarm- und Filter-Einstellungen. Lädt/speichert JSON."""

    def __init__(self):
        daten = self._laden()
        self.temp  = daten["temp"]
        self.druck = daten["druck"]

    def _laden(self) -> dict:
        """Lädt aus JSON, fällt auf DEFAULTS zurück bei Fehler."""
        try:
            if os.path.exists(_JSON_PFAD):
                with open(_JSON_PFAD, "r", encoding="utf-8") as f:
                    return _validiere(json.load(f))
        except Exception:
            pass
        return _validiere({})

    def speichern(self):
        """Persistiert aktuelle Werte nach JSON."""
        os.makedirs(os.path.dirname(_JSON_PFAD), exist_ok=True)
        daten = {"temp": dict(self.temp), "druck": dict(self.druck)}
        tmp = _JSON_PFAD + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(daten, f, indent=2, ensure_ascii=False)
        os.replace(tmp, _JSON_PFAD)  # Atomar auf Windows/NTFS


class AlarmEinstellungenDialog(QDialog):

    def __init__(self, einstellungen: AlarmEinstellungen, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alarm & Filter – Einstellungen")
        self.setMinimumWidth(380)
        self._e = einstellungen

        layout = QVBoxLayout(self)
        tabs   = QTabWidget()

        tabs.addTab(self._build_temp_tab(),  "Temperatur")
        tabs.addTab(self._build_druck_tab(), "Druck")
        layout.addWidget(tabs)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.RestoreDefaults
        )
        btns.accepted.connect(self._speichern)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self._defaults
        )
        layout.addWidget(btns)

    # ── Temperatur-Tab ────────────────────────────────────────
    def _build_temp_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)

        # Sprung-Alarm
        alarm_box = QGroupBox("Sprung-Alarm")
        al = QGridLayout(alarm_box)

        self._chk_temp_alarm = QCheckBox("Aktiviert")
        self._chk_temp_alarm.setChecked(self._e.temp["sprung_alarm_aktiv"])
        al.addWidget(self._chk_temp_alarm, 0, 0, 1, 2)

        al.addWidget(QLabel("Schwelle:"), 1, 0)
        self._spn_temp_alarm = QDoubleSpinBox()
        self._spn_temp_alarm.setRange(0.1, 500.0)
        self._spn_temp_alarm.setValue(self._e.temp["sprung_alarm_grad"])
        self._spn_temp_alarm.setSuffix(" °C / Zyklus")
        self._spn_temp_alarm.setDecimals(1)
        al.addWidget(self._spn_temp_alarm, 1, 1)

        hinweis = QLabel("Alarm im Log wenn Temperatur um mehr\nals X °C pro Messzyklus springt.")
        hinweis.setStyleSheet("font-size: 9px; color: #666;")
        al.addWidget(hinweis, 2, 0, 1, 2)
        l.addWidget(alarm_box)

        # Ausreißer
        ausreisser_box = QGroupBox("Ausreißer herausfiltern")
        arl = QGridLayout(ausreisser_box)

        self._chk_temp_ausreisser = QCheckBox("Aktiviert")
        self._chk_temp_ausreisser.setChecked(self._e.temp["ausreisser_aktiv"])
        arl.addWidget(self._chk_temp_ausreisser, 0, 0, 1, 2)

        arl.addWidget(QLabel("Schwelle:"), 1, 0)
        self._spn_temp_ausreisser = QDoubleSpinBox()
        self._spn_temp_ausreisser.setRange(1.0, 1000.0)
        self._spn_temp_ausreisser.setValue(self._e.temp["ausreisser_grad"])
        self._spn_temp_ausreisser.setSuffix(" °C / Zyklus")
        self._spn_temp_ausreisser.setDecimals(1)
        arl.addWidget(self._spn_temp_ausreisser, 1, 1)

        hinweis2 = QLabel("Wert wird nicht geplottet/gespeichert\nwenn Sprung größer als X °C.")
        hinweis2.setStyleSheet("font-size: 9px; color: #666;")
        arl.addWidget(hinweis2, 2, 0, 1, 2)
        l.addWidget(ausreisser_box)
        l.addStretch()
        return w

    # ── Druck-Tab ─────────────────────────────────────────────
    def _build_druck_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)

        # Sprung-Alarm
        alarm_box = QGroupBox("Sprung-Alarm")
        al = QGridLayout(alarm_box)

        self._chk_druck_alarm = QCheckBox("Aktiviert")
        self._chk_druck_alarm.setChecked(self._e.druck["sprung_alarm_aktiv"])
        al.addWidget(self._chk_druck_alarm, 0, 0, 1, 2)

        al.addWidget(QLabel("Schwelle:"), 1, 0)
        self._spn_druck_alarm = QDoubleSpinBox()
        self._spn_druck_alarm.setRange(0.1, 10.0)
        self._spn_druck_alarm.setValue(self._e.druck["sprung_alarm_dekaden"])
        self._spn_druck_alarm.setSuffix(" Dekaden / s")
        self._spn_druck_alarm.setDecimals(1)
        al.addWidget(self._spn_druck_alarm, 1, 1)

        hinweis = QLabel("Alarm im Log wenn Druck um mehr als\nX Dekaden pro Sekunde ansteigt.")
        hinweis.setStyleSheet("font-size: 9px; color: #666;")
        al.addWidget(hinweis, 2, 0, 1, 2)
        l.addWidget(alarm_box)

        # Ausreißer
        ausreisser_box = QGroupBox("Ausreißer herausfiltern")
        arl = QGridLayout(ausreisser_box)

        self._chk_druck_ausreisser = QCheckBox("Aktiviert")
        self._chk_druck_ausreisser.setChecked(self._e.druck["ausreisser_aktiv"])
        arl.addWidget(self._chk_druck_ausreisser, 0, 0, 1, 2)

        arl.addWidget(QLabel("Schwelle:"), 1, 0)
        self._spn_druck_ausreisser = QDoubleSpinBox()
        self._spn_druck_ausreisser.setRange(0.5, 10.0)
        self._spn_druck_ausreisser.setValue(self._e.druck["ausreisser_dekaden"])
        self._spn_druck_ausreisser.setSuffix(" Dekaden / s")
        self._spn_druck_ausreisser.setDecimals(1)
        arl.addWidget(self._spn_druck_ausreisser, 1, 1)

        hinweis2 = QLabel("Wert wird nicht geplottet/gespeichert\nwenn Sprung größer als X Dekaden.")
        hinweis2.setStyleSheet("font-size: 9px; color: #666;")
        arl.addWidget(hinweis2, 2, 0, 1, 2)
        l.addWidget(ausreisser_box)
        l.addStretch()
        return w

    def _speichern(self):
        self._e.temp["sprung_alarm_aktiv"]   = self._chk_temp_alarm.isChecked()
        self._e.temp["sprung_alarm_grad"]     = self._spn_temp_alarm.value()
        self._e.temp["ausreisser_aktiv"]      = self._chk_temp_ausreisser.isChecked()
        self._e.temp["ausreisser_grad"]       = self._spn_temp_ausreisser.value()
        self._e.druck["sprung_alarm_aktiv"]   = self._chk_druck_alarm.isChecked()
        self._e.druck["sprung_alarm_dekaden"] = self._spn_druck_alarm.value()
        self._e.druck["ausreisser_aktiv"]     = self._chk_druck_ausreisser.isChecked()
        self._e.druck["ausreisser_dekaden"]   = self._spn_druck_ausreisser.value()
        self._e.speichern()
        self.accept()

    def _defaults(self):
        self._spn_temp_alarm.setValue(DEFAULTS["temp"]["sprung_alarm_grad"])
        self._spn_temp_ausreisser.setValue(DEFAULTS["temp"]["ausreisser_grad"])
        self._spn_druck_alarm.setValue(DEFAULTS["druck"]["sprung_alarm_dekaden"])
        self._spn_druck_ausreisser.setValue(DEFAULTS["druck"]["ausreisser_dekaden"])
        self._chk_temp_alarm.setChecked(True)
        self._chk_temp_ausreisser.setChecked(True)
        self._chk_druck_alarm.setChecked(True)
        self._chk_druck_ausreisser.setChecked(True)
