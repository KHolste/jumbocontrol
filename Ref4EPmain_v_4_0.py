from __future__ import annotations
import os
import platform
import time
import socket
import html
import math
import numpy as np
from datetime import datetime
import serial
import serial.tools.list_ports
import pyvisa
from pyfiglet import figlet_format
from colorama import init
import sys

import os as _os
_os.environ.setdefault("QT_API", "pyside6")   # matplotlib soll PySide6 verwenden, nicht PyQt6

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QFrame, QComboBox, QCheckBox,
    QDoubleSpinBox, QSpinBox, QStatusBar, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QSplitter, QScrollArea, QTextEdit, QMessageBox,
    QLineEdit, QFileDialog, QLabel, QLCDNumber, QSizePolicy, QDialog, QFormLayout,
    QRadioButton, QButtonGroup, QProgressBar,
)

from PySide6.QtCore import (
    QObject, Signal, Slot, QThread, QFile, QIODevice, Qt, QSettings, QTimer,
)
from PySide6.QtGui import QAction, QColor, QPalette



import re
import threading
import logging
import configparser
from dataclasses import dataclass
from typing import Optional


import matplotlib
matplotlib.use("qtagg")   # QT_API=pyside6 bereits gesetzt → verwendet PySide6

import matplotlib as mpl
mpl.rcParams["font.size"] = 10
mpl.rcParams["axes.labelsize"] = 11
mpl.rcParams["axes.titlesize"] = 12
mpl.rcParams["axes.grid"] = True
mpl.rcParams["lines.linewidth"] = 2.0
mpl.rcParams["figure.dpi"] = 100

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Konfiguration (Ref4EP.ini)
# ---------------------------------------------------------------------------

class AppConfig:
    """
    Lädt und speichert die INI-Konfiguration.
    Die Datei liegt im selben Verzeichnis wie das Skript.
    Fehlende Schlüssel werden mit Defaults aufgefüllt.
    """

    DEFAULTS = {
        "ion_psu":        {"mode": "tcp",    "host": "192.168.1.93", "tcp_port": "2101", "timeout": "2.0", "v_max": "3500.0", "i_max": "0.040"},
        "ppa_up_psu":     {"mode": "visa",   "visa_resource": "GPIB1::9::INSTR",         "timeout": "2.0", "v_max": "2000.0", "i_max": "0.006"},
        "ppa_down_psu":   {"mode": "serial", "port": "COM4",         "baudrate": "9600", "timeout": "2.0", "v_max": "2000.0", "i_max": "0.006"},
        "einzellens_psu": {"mode": "tcp",    "host": "192.168.1.95", "tcp_port": "2101", "timeout": "2.0", "v_max": "6500.0", "i_max": "0.020"},
        "keithley_6485":  {"port": "COM12"},
        "keithley_6517b": {"port": "COM11"},
        "scan":           {"e_start": "40.0", "e_stop": "50.0", "e_step": "1.0", "settle_s": "0.1", "spectrometer_constant": "1.0275", "offset_p2": "0.0"},
        "keithley":       {"nplc": "0.1", "averages": "1", "mode": "Single"},
        "csv":            {"save_dir": "", "auto_save": "false"},
    }

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(os.path.dirname(__file__), "Ref4EP.ini")
        self.cfg = configparser.ConfigParser()
        # Defaults eintragen damit fehlende Schlüssel nie KeyError werfen
        for section, values in self.DEFAULTS.items():
            self.cfg[section] = values
        self.load()

    # Korrekte i_max-Werte in Ampere (seit v3.1).
    # Alte INI-Dateien hatten Phantasiewerte in Ampere (3.0, 14.0).
    _I_MAX_MIGRATION = {
        "ion_psu":        0.040,
        "ppa_up_psu":     0.006,
        "ppa_down_psu":   0.006,
        "einzellens_psu": 0.020,
    }

    def load(self) -> None:
        """Liest die INI-Datei. Existiert sie nicht, werden nur Defaults verwendet.
        Migriert veraltete i_max-Werte (>1 A) automatisch auf korrekte mA-Werte."""
        if os.path.isfile(self.path):
            try:
                self.cfg.read(self.path, encoding="utf-8")
                log.info("Config geladen: %s", self.path)
                # Migration: i_max > 1.0 A ist mit Sicherheit ein alter Phantasiewert
                migrated = False
                for section, correct_val in self._I_MAX_MIGRATION.items():
                    try:
                        val = self.cfg.getfloat(section, "i_max")
                        if val > 1.0:
                            self.cfg.set(section, "i_max", str(correct_val))
                            log.warning(
                                "INI-Migration: [%s] i_max %.3g A -> %.4g A (war veraltet)",
                                section, val, correct_val)
                            migrated = True
                    except Exception:
                        pass
                if migrated:
                    log.warning("i_max-Werte migriert – bitte Config neu speichern (btnSaveConfig).")
            except Exception as e:
                log.warning("Config-Ladefehler (%s): %s – Defaults werden verwendet.", self.path, e)
        else:
            log.info("Keine Config gefunden (%s) – Defaults werden verwendet.", self.path)

    def save(self) -> None:
        """Schreibt die aktuelle Konfiguration in die INI-Datei."""
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write("# Ref4EP Steuerungssoftware – Konfigurationsdatei\n")
                f.write("# JLU Giessen – IPI\n\n")
                self.cfg.write(f)
            log.info("Config gespeichert: %s", self.path)
        except Exception as e:
            log.error("Config-Speicherfehler: %s", e)
            raise

    # --- Bequeme Getter mit Typ-Konvertierung ---

    def get(self, section: str, key: str, fallback: str = "") -> str:
        return self.cfg.get(section, key, fallback=fallback)

    def getfloat(self, section: str, key: str, fallback: float = 0.0) -> float:
        try:
            return self.cfg.getfloat(section, key)
        except Exception:
            return fallback

    def getint(self, section: str, key: str, fallback: int = 0) -> int:
        try:
            return self.cfg.getint(section, key)
        except Exception:
            return fallback

    def getbool(self, section: str, key: str, fallback: bool = False) -> bool:
        try:
            return self.cfg.getboolean(section, key)
        except Exception:
            return fallback

    def set(self, section: str, key: str, value) -> None:
        if not self.cfg.has_section(section):
            self.cfg.add_section(section)
        self.cfg.set(section, key, str(value))


def _find_log_widget(window):
    try:
        return window.findChild(QTextEdit, "txtLog")
    except Exception:
        return None


# Log-Farben – werden von _apply_theme() aktualisiert
_LOG_COLORS = {
    "info":  "#c8ccd8",   # default: hellgrau (Dark-Mode)
    "ok":    "#00e676",
    "warn":  "#ffd166",
    "error": "#ff6b6b",
    "stamp": "#666a80",
}

def append_log(window, text: str, level: str = "info") -> None:
    widget = _find_log_widget(window)
    if widget is None:
        return

    color = _LOG_COLORS.get(level, _LOG_COLORS["info"])
    stamp_color = _LOG_COLORS["stamp"]
    stamp = datetime.now().strftime("%H:%M:%S")
    safe_text = html.escape(str(text))
    line = (
        f'<span style="color:{stamp_color}">[{stamp}]</span> '
        f'<span style="color:{color}">{safe_text}</span>'
    )

    widget.append(line)

    doc = widget.document()
    max_blocks = 500
    while doc.blockCount() > max_blocks:
        cursor = widget.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        cursor.select(cursor.SelectionType.BlockUnderCursor)
        cursor.removeSelectedText()
        cursor.deleteChar()




class SerialInstrumentError(RuntimeError):
    pass



@dataclass
class Rs232Params:
    baudrate: int = 9600
    bytesize: int = serial.EIGHTBITS
    parity: str = serial.PARITY_NONE
    stopbits: int = serial.STOPBITS_ONE
    timeout: float = 0.3
    write_timeout: float = 0.3
    xonxoff: bool = False
    rtscts: bool = False
    dsrdtr: bool = False


class RobustSerialInstrument:
    """
    RS-232 Basis, die nicht von readline()/nur-LF abhängig ist.
    Liest bis \\r, \\n oder \\x00 oder Timeout.
    """
    def __init__(self, port: str, params: Rs232Params = Rs232Params()):
        self.port = port
        self.params = params
        self.ser: Optional[serial.Serial] = None
        self.lock = threading.RLock()

    @property
    def is_connected(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def connect(self, retries: int = 3, settle_s: float = 0.25) -> None:
        if self.is_connected:
            return

        last_err: Optional[Exception] = None
        for _ in range(max(1, retries)):
            try:
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.params.baudrate,
                    bytesize=self.params.bytesize,
                    parity=self.params.parity,
                    stopbits=self.params.stopbits,
                    timeout=self.params.timeout,
                    write_timeout=self.params.write_timeout,
                    xonxoff=self.params.xonxoff,
                    rtscts=self.params.rtscts,
                    dsrdtr=self.params.dsrdtr,
                )

                # Optional: Steuerleitungen definiert setzen (USB-Adapter-Zicken)
                try:
                    self.ser.setDTR(True)
                    self.ser.setRTS(True)
                    time.sleep(0.05)
                    self.ser.setDTR(False)
                    self.ser.setRTS(False)
                except Exception:
                    pass

                # Windows/USB-Serial braucht oft einen Moment nach open()
                time.sleep(settle_s)

                # Buffer leeren
                try:
                    self.ser.reset_input_buffer()
                    self.ser.reset_output_buffer()
                except Exception:
                    pass

                return

            except Exception as e:
                last_err = e
                try:
                    if self.ser:
                        self.ser.close()
                except Exception:
                    pass
                self.ser = None
                time.sleep(0.1)

        raise SerialInstrumentError(f"Could not open {self.port}: {last_err}") from last_err

    def disconnect(self) -> None:
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    def _readline_any_term(self, deadline_s: float = 1.0, maxlen: int = 4096) -> str:
        """
        Byteweise lesen bis \\r, \\n oder \\x00.
        """
        if not self.is_connected:
            raise SerialInstrumentError("Not connected.")

        end = time.time() + deadline_s
        buf = bytearray()

        while time.time() < end and len(buf) < maxlen:
            b = self.ser.read(1)
            if not b:
                continue
            if b in (b"\r", b"\n", b"\x00"):
                if buf:
                    break
                continue
            buf += b

        return buf.decode("ascii", errors="replace").strip()

    def write_raw(self, data: bytes) -> None:
        if not self.is_connected:
            raise SerialInstrumentError("Not connected.")
        with self.lock:
            self.ser.write(data)
            try:
                self.ser.flush()
            except Exception:
                pass

    def write(self, cmd: str, term: str = "\n") -> None:
        self.write_raw((cmd + term).encode("ascii", errors="replace"))

    def query(
        self,
        cmd: str,
        term: str = "\n",
        deadline_s: float = 1.0,
        recover: bool = True,
        recover_retries: int = 1,
    ) -> str:
        """
        Sendet cmd und liest die Antwort.
        Wenn die Antwort leer ist oder die serielle Verbindung zickt:
        -> einmal reconnecten und den Befehl wiederholen.
        """
        if not self.is_connected:
            self.connect()

        def attempt_once() -> str:
            with self.lock:
                try:
                    self.ser.reset_input_buffer()
                except Exception:
                    pass

                self.write(cmd, term=term)

                for _ in range(3):
                    ans = self._readline_any_term(deadline_s=deadline_s)
                    if ans:
                        return ans

            raise SerialInstrumentError(f"Timeout/empty response on query: {cmd!r}")

        try:
            return attempt_once()

        except (SerialInstrumentError, OSError, serial.SerialException) as e:
            if (not recover) or (recover_retries <= 0):
                raise

            log.warning("[RS232] Auto-Recover auf %s bei %r (%s)", self.port, cmd, e)

            try:
                self.disconnect()
            except Exception:
                pass

            time.sleep(0.2)
            self.connect(retries=2, settle_s=0.25)

            return attempt_once()


class Keithley6485(RobustSerialInstrument):
    """
    Keithley 6485 Picoammeter (robust RS-232).
    """
    def __init__(self, port: str = "COM12", params: Rs232Params = Rs232Params()):
        super().__init__(port=port, params=params)
        self._line_freq_hz = 50.0  # DE/EU
        self._nplc = 1.0

    def idn(self) -> str:
        try:
            return self.query("*IDN?", term="\n", deadline_s=1.0)
        except Exception:
            return self.query("*IDN?", term="\r\n", deadline_s=1.0)

    def configure_current(
        self,
        nplc: float = 1.0,
        auto_range: bool = True,
        fixed_range_A: float = 2e-9,
        autozero: bool = True,
        form_read_only: bool = True,
        abort_before_config: bool = False,
        do_reset: bool = True,
    ) -> None:
        self._nplc = float(nplc)

        if abort_before_config:
            try:
                self.write("ABOR")
                time.sleep(0.05)
            except Exception:
                pass

        if do_reset:
            self.write("*RST")
            time.sleep(0.3)

        self.write("*CLS")
        self.write("CONF:CURR")

        if auto_range:
            self.write("CURR:RANG:AUTO ON")
        else:
            self.write(f"CURR:RANG {fixed_range_A:g}")

        self.write(f"CURR:NPLC {nplc:g}")
        self.write(f"SYST:AZER {'ON' if autozero else 'OFF'}")

        if form_read_only:
            self.write("FORM:ELEM READ")

    def set_zero_check(self, enabled: bool) -> None:
        self.write(f"SYST:ZCH {'ON' if enabled else 'OFF'}")

    def read_current_A(self, nplc: float | None = None, **kwargs) -> float:
        # **kwargs nimmt stop_flag u.ä. von ScanWorker entgegen und ignoriert sie –
        # der 6485 hat keinen unterbrechbaren OPC-Wait wie der 6517B.
        if nplc is None:
            nplc = getattr(self, "_nplc", 1.0)

        line_freq = getattr(self, "_line_freq_hz", 50.0)
        integration_s = float(nplc) / float(line_freq)
        deadline_s = max(0.4, integration_s * 3.0 + 0.25)

        last = ""
        for _ in range(3):
            s = self.query("INIT;FETCH?", deadline_s=deadline_s)
            s = s.replace("\x11", "").replace("\x13", "").strip()
            if "," in s:
                s = s.split(",", 1)[0].strip()
            s = s.replace("A", "").replace("a", "").strip()
            last = s
            if s and any(c.isdigit() for c in s):
                try:
                    return float(s)
                except ValueError:
                    pass

        raise SerialInstrumentError(f"Invalid INIT;FETCH? response: {last!r}")


class Keithley6517B(RobustSerialInstrument):
    """
    Keithley 6517B Electrometer (robust RS-232).
    Der 6517B erwartet und sendet CRLF (\\r\\n) als Terminator (laut Manual).
    write() wird daher mit term='\\r\\n' aufgerufen.
    Der 6517B wird vor Strommessungen explizit und recht hart initialisiert,
    inkl. Zero-Check/Zero-Correct-Sequenz.
    """
    # Keithley 6517B: CRLF senden, CRLF empfangen (Manual: RS-232 Interface)
    _TERM = "\r\n"

    def __init__(self, port: str = "COM11", params: Rs232Params = Rs232Params()):
        super().__init__(port=port, params=params)
        self._line_freq_hz = 50.0
        self._nplc = 1.0

    # --- interne Helfer mit korrektem Terminator ---

    def _write6517(self, cmd: str) -> None:
        """Schreibt mit CRLF-Terminator."""
        self.write(cmd, term=self._TERM)

    def _query6517(self, cmd: str, deadline_s: float = 1.0, recover: bool = True) -> str:
        """Query mit CRLF-Terminator und schnellem readline."""
        return self.query(cmd, term=self._TERM, deadline_s=deadline_s, recover=recover)

    def idn(self) -> str:
        # Beim ersten Connect noch unsicher welcher Term akzeptiert wird → beide probieren
        last_err = None
        for term in ("\r\n", "\n", "\r"):
            try:
                return self.query("*IDN?", term=term, deadline_s=1.0, recover=False)
            except Exception as e:
                last_err = e
        raise SerialInstrumentError(f"No valid *IDN? response on {self.port}: {last_err}")

    def system_error(self) -> str:
        try:
            return self._query6517(":SYST:ERR?", deadline_s=1.0)
        except Exception:
            return "<no response>"

    def _wait_opc(self, deadline_s: float = 4.0, stop_flag: list | None = None) -> None:
        """
        Wartet auf *OPC? in kleinen Zeitscheiben.
        stop_flag: eine einelementige Liste [False] – wird von außen auf [True] gesetzt
        um den Wait vorzeitig abzubrechen (z.B. durch ScanWorker._stop).
        """
        chunk_s = 0.2
        end = time.time() + deadline_s
        while time.time() < end:
            if stop_flag is not None and stop_flag[0]:
                return
            remaining = min(chunk_s, end - time.time())
            if remaining <= 0:
                break
            try:
                self.query("*OPC?", term=self._TERM, deadline_s=remaining, recover=False)
                return
            except Exception:
                pass

    @staticmethod
    def _parse_current_response(resp: str) -> float:
        s = (resp or "").replace("\x11", "").replace("\x13", "").replace("\x00", "").strip()
        if not s:
            raise ValueError("empty response")

        first = s.split(",", 1)[0].strip()
        first = first.replace("A", "").replace("a", "").strip()
        value = float(first)

        if (not math.isfinite(value)) or abs(value) >= 1e30:
            raise ValueError(f"invalid/overflow reading: {resp!r}")

        return value

    def configure_current(
        self,
        nplc: float = 1.0,
        auto_range: bool = True,
        fixed_range_A: float = 2e-9,
        autozero: bool = True,
        form_read_only: bool = True,
        abort_before_config: bool = False,
        do_reset: bool = True,
    ) -> None:
        self._nplc = float(nplc)

        if abort_before_config:
            try:
                self._write6517(":ABOR")
                time.sleep(0.05)
            except Exception:
                pass

        if do_reset:
            self._write6517("*RST")
            time.sleep(0.8)

        self._write6517("*CLS")
        self._write6517(":ABOR")
        self._write6517(":INIT:CONT OFF")
        self._write6517(":SYST:ZCH ON")
        time.sleep(0.15)

        self._write6517(":SENS:FUNC 'CURR'")
        self._write6517(f":SENS:CURR:NPLC {nplc:g}")

        if auto_range:
            self._write6517(":SENS:CURR:RANG:AUTO ON")
        else:
            self._write6517(":SENS:CURR:RANG:AUTO OFF")
            self._write6517(f":SENS:CURR:RANG {fixed_range_A:g}")

        self._write6517(":SENS:CURR:DAMP ON")
        self._write6517(f":SYST:AZER {'ON' if autozero else 'OFF'}")
        self._write6517(":FORM:DATA ASC")
        if form_read_only:
            self._write6517(":FORM:ELEM READ")

        # Trigger-Modell: One-Shot per :INIT (laut Manual Section 3)
        self._write6517(":TRIG:SOUR IMM")   # sofort triggern (kein ext. Trigger)
        self._write6517(":TRIG:COUNT 1")    # genau 1 Messung pro :INIT

        # Zero-Correct-Sequenz für den 6517B im Strommodus
        try:
            self._write6517(":SYST:ZCOR:STAT OFF")
        except Exception:
            pass
        time.sleep(0.1)
        self._write6517(":SYST:ZCOR:ACQ")
        self._wait_opc(deadline_s=6.0)
        time.sleep(0.25)
        self._write6517(":SYST:ZCOR:STAT ON")
        time.sleep(0.15)
        self._write6517(":SYST:ZCH OFF")
        self._wait_opc(deadline_s=4.0)
        time.sleep(max(0.4, float(nplc) / self._line_freq_hz * 4.0 + 0.2))

        try:
            func = self._query6517(":SENS:FUNC?", deadline_s=1.2).upper()
            if "CURR" not in func:
                raise SerialInstrumentError(f"6517B not in current mode after config: {func!r}")
            zch = self._query6517(":SYST:ZCH?", deadline_s=1.0).strip()
            if zch not in ("0", "OFF"):
                raise SerialInstrumentError(f"6517B zero-check still enabled after config: {zch!r}")
        except Exception as e:
            err = self.system_error()
            raise SerialInstrumentError(f"6517B current configuration failed: {e}; SYST:ERR={err}") from e

        # Dummy-Messzyklus: Buffer und FRESH?-Pointer auf einen frischen Wert setzen,
        # damit der erste echte read_current_A() keinen Stale-Wert aus configure_current liest.
        try:
            self._write6517(":ABOR")
            self._write6517(":TRIG:COUNT 1")
            self._write6517(":INIT")
            self._wait_opc(deadline_s=max(2.0, float(nplc) / self._line_freq_hz * 10.0 + 1.5))
            self._query6517(":SENS:DATA:FRESH?", deadline_s=2.0)  # Wert lesen und verwerfen
        except Exception:
            pass  # Warmup-Fehler sind nicht kritisch

    def read_current_A(self, nplc: float | None = None, avg_n: int = 1,
                       stop_flag: list | None = None) -> float:
        """
        Messung mit optionalem Hardware-Averaging (avg_n > 1).

        avg_n == 1  →  Single-Shot:
            :TRIG:COUNT 1 → :INIT → *OPC? → :SENS:DATA:FRESH?

        avg_n > 1   →  Hardware-Average in einem einzigen Trigger-Zyklus:
            :TRIG:COUNT N → :INIT → *OPC? → :SENS:DATA? (alle N Samples)
            → Mittelwert im Code; O(1) Kommunikations-Overhead statt O(N).

        stop_flag: einelementige Liste [bool] – wird auf True gesetzt um *OPC?-Wait
                   vorzeitig abzubrechen (z.B. durch ScanWorker beim Stop).
        Fallback bei beiden Modi: :MEAS:CURR?
        """
        if nplc is None:
            nplc = getattr(self, "_nplc", 1.0)
        avg_n = max(1, int(avg_n))

        line_freq = getattr(self, "_line_freq_hz", 50.0)
        integration_s = float(nplc) / float(line_freq)
        # OPC-Deadline: N Integrationen + Autorange-Overhead + Kommunikation
        opc_deadline_s = max(2.0, integration_s * avg_n * 10.0 + 1.5)
        fetch_deadline_s = max(2.0, integration_s * avg_n * 4.0 + 1.0)

        raw_resp = None
        err_before = self.system_error()

        try:
            # Seriellen Eingangspuffer leeren – verhindert Stale-Bytes aus vorherigen Zyklen
            try:
                self.ser.reset_input_buffer()
            except Exception:
                pass

            self._write6517(":ABOR")
            time.sleep(0.05)
            self._write6517(":INIT:CONT OFF")
            self._write6517(f":TRIG:COUNT {avg_n}")
            time.sleep(0.05)

            self._write6517(":INIT")
            self._wait_opc(deadline_s=opc_deadline_s, stop_flag=stop_flag)

            # Stop wurde angefordert während *OPC? lief → sauber abbrechen
            if stop_flag is not None and stop_flag[0]:
                raise SerialInstrumentError("Measurement aborted by stop request.")

            if avg_n == 1:
                raw_resp = self._query6517(":SENS:DATA:FRESH?", deadline_s=fetch_deadline_s)
                return self._parse_current_response(raw_resp)
            else:
                raw_resp = self._query6517(":SENS:DATA?", deadline_s=fetch_deadline_s)
                tokens = [t.strip() for t in raw_resp.split(",") if t.strip()]
                values = []
                for tok in tokens:
                    try:
                        values.append(self._parse_current_response(tok))
                    except Exception:
                        pass
                if not values:
                    raise SerialInstrumentError(
                        f"No valid samples in :SENS:DATA? response: {raw_resp!r}"
                    )
                return sum(values) / len(values)

        except Exception:
            # Fallback: :MEAS:CURR? (ein Sample, keine Averages)
            try:
                raw_resp = self._query6517(":MEAS:CURR?", deadline_s=max(opc_deadline_s, 5.0))
                return self._parse_current_response(raw_resp)
            except Exception as e:
                err_after = self.system_error()
                raise SerialInstrumentError(
                    "Invalid 6517B current response. "
                    f"DATA={raw_resp!r}, "
                    f"SYST:ERR(before)={err_before!r}, SYST:ERR(after)={err_after!r}, err={e}"
                ) from e


WRITE_TERMINATORS = ["\n", "\r\n", "\r"]
SCAN_BAUDRATES = [9600, 19200, 38400, 57600, 115200]


def query_idn_on_port(
    port: str,
    *,
    baudrate: int = 9600,
    timeout: float = 0.6,
    xonxoff: bool = False,
    rtscts: bool = False,
) -> str | None:
    """
    Öffnet einen COM-Port kurz und versucht *IDN? mit mehreren Terminierungen.
    Gibt die IDN-Antwort zurück oder None.
    """
    for term in WRITE_TERMINATORS:
        ser = None
        try:
            ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout,
                write_timeout=timeout,
                xonxoff=xonxoff,
                rtscts=rtscts,
                dsrdtr=False,
            )

            time.sleep(0.2)

            try:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
            except Exception:
                pass

            ser.write(("*IDN?" + term).encode("ascii", errors="replace"))
            ser.flush()
            time.sleep(0.2)

            raw = bytearray()
            t_end = time.time() + timeout
            while time.time() < t_end:
                b = ser.read(1)
                if not b:
                    continue
                if b in (b"\r", b"\n", b"\x00"):
                    if raw:
                        break
                    continue
                raw += b

            text = raw.decode("ascii", errors="replace").strip()
            if text:
                return text

        except Exception:
            pass

        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

    return None


class KeithleyScanWorker(QObject):
    ok = Signal(list, object, dict)   # ports, best_port, idn_map
    fail = Signal(str)
    finished = Signal()
    progress = Signal(str)            # log-Zeile für aktuellen Port

    def __init__(self, model_hint: str, display_name: str | None = None):
        super().__init__()
        self.model_hint = model_hint.upper().strip()
        self.display_name = display_name or model_hint

    @Slot()
    def run(self):
        t_start = time.perf_counter()
        try:
            ports = []
            try:
                portinfos = serial.tools.list_ports.comports()
                # Numerisch sortieren: COM1, COM4, COM10, COM11 statt COM1, COM10, COM11, COM4
                ports = [p.device for p in sorted(
                    portinfos,
                    key=lambda x: int(''.join(filter(str.isdigit, x.device)) or 0)
                )]
            except Exception:
                ports = []

            best = None
            idn_map = {}

            self.progress.emit(f"Scanne {len(ports)} COM-Port(s): {', '.join(ports) or '–'}")

            for port in ports:
                self.progress.emit(f"  → teste {port} …")
                idn = None

                for baudrate in SCAN_BAUDRATES:
                    idn = query_idn_on_port(
                        port,
                        baudrate=baudrate,
                        timeout=0.3,          # verkürzt von 0.6 → 0.3 s
                        xonxoff=False,
                        rtscts=False,
                    )
                    if idn:
                        break

                    idn = query_idn_on_port(
                        port,
                        baudrate=baudrate,
                        timeout=0.3,
                        xonxoff=True,
                        rtscts=False,
                    )
                    if idn:
                        break

                if not idn:
                    self.progress.emit(f"  ✗ {port}: kein Gerät")
                    continue

                idn_map[port] = idn
                u = idn.upper()
                is_match = "KEITHLEY" in u and self.model_hint in u

                if is_match and best is None:
                    best = port
                    self.progress.emit(f"  ✓ {port}: {idn}  ← {self.display_name} gefunden!")
                    break   # sofort stoppen nach Fund
                else:
                    self.progress.emit(f"  ~ {port}: {idn}  (anderes Gerät)")

            elapsed = time.perf_counter() - t_start
            if best is None:
                self.progress.emit(f"Scan abgeschlossen – {self.display_name} nicht gefunden. ({elapsed:.1f} s)")
            else:
                self.progress.emit(f"Scan abgeschlossen. ({elapsed:.1f} s)")

            self.ok.emit(ports, best, idn_map)

        except Exception as e:
            self.fail.emit(str(e))
        finally:
            self.finished.emit()


class ConnectWorker(QObject):
    ok = Signal(object, str)   # psu_obj, idn
    fail = Signal(str)
    finished = Signal()

    def __init__(self, psu_kwargs: dict):
        super().__init__()
        self.psu_kwargs = psu_kwargs

    @Slot()
    def run(self):
        try:
            psu = FugPSU(**self.psu_kwargs)
            psu.connect()
            idn = psu.idn()
            self.ok.emit(psu, idn)
        except Exception as e:
            self.fail.emit(str(e))
        finally:
            self.finished.emit()


class DeviceController(QObject):
    def __init__(self, window, *, btn_name: str, led_name: str, psu_kwargs: dict, status_prefix: str):
        super().__init__(window)
        self.w = window
        self.psu_kwargs = psu_kwargs
        self.status_prefix = status_prefix

        self.btn = self.w.findChild(QPushButton, btn_name)
        self.led = self.w.findChild(QFrame, led_name)

        if self.btn is None:
            raise RuntimeError(f"Button '{btn_name}' nicht gefunden.")
        if self.led is None:
            raise RuntimeError(f"LED '{led_name}' nicht gefunden.")

        # Button muss checkable sein (du setzt das im Designer; hier nur als Safety)
        self.btn.setCheckable(True)
        self.btn.setChecked(False)

        set_led(self.led, "gray")

        self.psu = None
        self.thread = None
        self.worker = None

        # Wichtig: toggled, nicht clicked (passt zur checked-Logik)
        self.btn.toggled.connect(self.on_toggled)






    @Slot(bool)
    def on_toggled(self, want_connect: bool):
        # Wenn gerade ein Connect-Thread läuft: ignorieren
        if self.thread is not None and self.thread.isRunning():
            # Button-Zustand wieder zurück (damit UI konsistent bleibt)
            self.btn.blockSignals(True)
            self.btn.setChecked(not want_connect)
            self.btn.blockSignals(False)
            return

        if not want_connect:
            # -------- DISCONNECT --------
            if self.psu is not None:
                try:
                    self.psu.close()
                except Exception:
                    pass
                self.psu = None

            set_led(self.led, "gray")
            if hasattr(self.w, "statusbar") and self.w.statusbar:
                self.w.statusbar.showMessage(f"{self.status_prefix}: disconnected", 3000)
            append_log(self.w, f"{self.status_prefix} getrennt.", "warn")
            return

        # -------- CONNECT --------
        set_led(self.led, "orange")
        self.btn.setEnabled(False) 

        self.thread = QThread(self.w)
        self.worker = ConnectWorker(self.psu_kwargs)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)

        self.worker.ok.connect(self.on_ok, Qt.QueuedConnection)
        self.worker.fail.connect(self.on_fail, Qt.QueuedConnection)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.on_thread_finished, Qt.QueuedConnection)

        self.thread.start()

    @Slot(object, str)
    def on_ok(self, psu_obj, idn: str):
        self.psu = psu_obj
        set_led(self.led, "green")
        # Button bleibt textlich wie im Designer, nur checked bleibt True
        self.btn.setChecked(True)
        if hasattr(self.w, "statusbar") and self.w.statusbar:
            self.w.statusbar.showMessage(f"{self.status_prefix}: {idn}", 5000)
        append_log(self.w, f"{self.status_prefix} verbunden ({idn}).", "ok")

    @Slot(str)
    def on_fail(self, msg: str):
        self.psu = None
        set_led(self.led, "red")
        # Connect fehlgeschlagen -> zurück auf disconnected
        self.btn.blockSignals(True)
        self.btn.setChecked(False)
        self.btn.blockSignals(False)
        if hasattr(self.w, "statusbar") and self.w.statusbar:
            self.w.statusbar.showMessage(f"{self.status_prefix}: connect failed: {msg}", 8000)
        append_log(self.w, f"Fehler {self.status_prefix}: {msg}", "error")
    @Slot()
    def on_thread_finished(self):
        self.btn.setEnabled(True)
        self.thread = None
        self.worker = None



class KeithleyScanControllerBase(QObject):
    def __init__(self, window, *, model_hint: str, display_name: str,
                 btn_scan_name: str | None = None,
                 port_combo_name: str | None = None,
                 led_name: str | None = None):
        super().__init__(window)
        self.w = window
        self.model_hint = model_hint
        self.display_name = display_name

        self.btn_scan = self.w.findChild(QPushButton, btn_scan_name) if btn_scan_name else None
        self.cmb_port = self.w.findChild(QComboBox, port_combo_name) if port_combo_name else None
        self.led = self.w.findChild(QFrame, led_name) if led_name else None

        if self.led is not None:
            set_led(self.led, "gray")

        self.scan_thread = None
        self.scan_worker = None

        if self.btn_scan is not None:
            self.btn_scan.clicked.connect(self.start_scan)

    def _set_led(self, color: str):
        if self.led is not None:
            set_led(self.led, color)

    @Slot()
    def start_scan(self):
        if self.scan_thread is not None and self.scan_thread.isRunning():
            return

        self._set_led("orange")
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("Scanning...")

        if hasattr(self.w, "statusbar") and self.w.statusbar:
            self.w.statusbar.showMessage(f"Scanning COM ports for {self.display_name}...", 0)

        self.scan_thread = QThread(self.w)
        self.scan_worker = KeithleyScanWorker(self.model_hint, self.display_name)
        self.scan_worker.moveToThread(self.scan_thread)

        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.progress.connect(
            self._on_scan_progress, Qt.QueuedConnection)
        self.scan_worker.ok.connect(self.on_scan_ok, Qt.QueuedConnection)
        self.scan_worker.fail.connect(self.on_scan_fail, Qt.QueuedConnection)

        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_worker.finished.connect(self.scan_worker.deleteLater)
        self.scan_thread.finished.connect(self.scan_thread.deleteLater)
        self.scan_thread.finished.connect(self.on_scan_thread_finished, Qt.QueuedConnection)

        self.scan_thread.start()

    @Slot(str)
    def _on_scan_progress(self, msg: str):
        append_log(self.w, msg, "info")
        QApplication.processEvents()   # sofort in GUI rendern

    @Slot(list, object, dict)
    def on_scan_ok(self, ports: list, best_port, idn_map: dict):
        prev = self.cmb_port.currentText().strip()

        self.cmb_port.clear()
        for p in ports:
            self.cmb_port.addItem(p)

        if prev and self.cmb_port.findText(prev) < 0:
            self.cmb_port.addItem(prev)

        if best_port is not None:
            i = self.cmb_port.findText(best_port)
            if i >= 0:
                self.cmb_port.setCurrentIndex(i)
            else:
                self.cmb_port.setCurrentText(best_port)

            # Gefunden aber noch NICHT verbunden → orange (bereit zum Connect)
            self._set_led("orange")
            idn = idn_map.get(best_port, "")
            if hasattr(self.w, "statusbar") and self.w.statusbar:
                self.w.statusbar.showMessage(
                    f"{self.display_name} gefunden auf {best_port} – bitte 'Connect' drücken.", 6000)
        else:
            if prev:
                try:
                    self.cmb_port.setCurrentText(prev)
                except Exception:
                    pass
            self._set_led("gray")
            if hasattr(self.w, "statusbar") and self.w.statusbar:
                self.w.statusbar.showMessage(f"Kein {self.display_name} gefunden (Ports wurden aktualisiert).", 6000)
            append_log(self.w, f"Kein {self.display_name} gefunden.", "warn")

    @Slot(str)
    def on_scan_fail(self, msg: str):
        self._set_led("red")
        if hasattr(self.w, "statusbar") and self.w.statusbar:
            self.w.statusbar.showMessage(f"{self.display_name}-Scan fehlgeschlagen: {msg}", 8000)
        append_log(self.w, f"Fehler beim Scan von {self.display_name}: {msg}", "error")

    @Slot()
    def on_scan_thread_finished(self):
        self.btn_scan.setText("Scan COM")
        self.btn_scan.setEnabled(True)
        self.scan_thread = None
        self.scan_worker = None


class K6485ConnectWorker(QObject):
    ok = Signal(object, str)
    fail = Signal(str)
    finished = Signal()

    def __init__(self, port: str):
        super().__init__()
        self.port = port

    @Slot()
    def run(self):
        meter = None
        try:
            meter = Keithley6485(port=self.port)
            meter.connect(retries=2, settle_s=0.25)
    
            # "Wake"-Query (best-effort), danach kurze Pause
            try:
                meter.query("*IDN?", term="\n", deadline_s=0.6, recover=False)
                time.sleep(0.1)
            except Exception:
                pass
    
            # echte IDN-Abfrage: schnell scheitern, kein Auto-Recover
            idn = meter.query("*IDN?", term="\n", deadline_s=0.8, recover=False)
    
            self.ok.emit(meter, idn)
    
        except Exception as e:
            if meter is not None:
                try:
                    meter.disconnect()
                except Exception:
                    pass
            self.fail.emit(f"COM-Port falsch oder Gerät antwortet nicht ({self.port}): {e}")
    
        finally:
            self.finished.emit()
        


class K6485Controller(KeithleyScanControllerBase):
    PORT = "COM12"   # hardcoded

    def __init__(self, window, *, btn_name: str, led_name: str):
        super().__init__(
            window,
            model_hint="6485",
            display_name="Keithley 6485",
            led_name=led_name,
        )
        self.w = window

        self.btn = self.w.findChild(QPushButton, btn_name)
        if self.btn is None:
            raise RuntimeError(f"Button '{btn_name}' nicht gefunden.")

        self.btn.setCheckable(True)
        self.btn.setChecked(False)
        self.meter = None
        self.thread = None
        self.worker = None
        self._connected = False

        self.btn.toggled.connect(self.on_toggled)

    @Slot(bool)
    def on_toggled(self, want_connect: bool):
        if self.thread is not None and self.thread.isRunning():
            self.btn.blockSignals(True)
            self.btn.setChecked(not want_connect)
            self.btn.blockSignals(False)
            return

        if not want_connect:
            if self.meter is not None:
                try:
                    self.meter.disconnect()
                except Exception:
                    pass
                self.meter = None
            self._connected = False

            self._set_led("gray")
            if hasattr(self.w, "statusbar") and self.w.statusbar:
                self.w.statusbar.showMessage("Keithley 6485: disconnected", 3000)
            append_log(self.w, "Keithley 6485 getrennt.", "warn")
            return

        port = self.PORT
        self._set_led("orange")
        self.btn.setEnabled(False)

        self.thread = QThread(self.w)
        self.worker = K6485ConnectWorker(port=port)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.ok.connect(self.on_ok, Qt.QueuedConnection)
        self.worker.fail.connect(self.on_fail, Qt.QueuedConnection)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.on_thread_finished, Qt.QueuedConnection)

        self.thread.start()

    @Slot(object, str)
    def on_ok(self, meter_obj, idn: str):
        self.meter = meter_obj
        self._connected = True
        self._set_led("green")
        self.btn.setChecked(True)
        if hasattr(self.w, "statusbar") and self.w.statusbar:
            self.w.statusbar.showMessage(f"Keithley 6485: {idn}", 5000)
        append_log(self.w, f"Keithley 6485 verbunden auf {self.PORT} ({idn}).", "ok")

    @Slot(str)
    def on_fail(self, msg: str):
        self.meter = None
        self._connected = False
        self._set_led("red")
        self.btn.blockSignals(True)
        self.btn.setChecked(False)
        self.btn.blockSignals(False)
        if hasattr(self.w, "statusbar") and self.w.statusbar:
            self.w.statusbar.showMessage(f"Keithley 6485: connect failed: {msg}", 8000)
        append_log(self.w, f"Fehler Keithley 6485: {msg}", "error")

    @Slot()
    def on_thread_finished(self):
        self.btn.setEnabled(True)
        self.thread = None
        self.worker = None


class K6517BConnectWorker(QObject):
    ok = Signal(object, str)
    fail = Signal(str)
    finished = Signal()

    def __init__(self, port: str):
        super().__init__()
        self.port = port

    @Slot()
    def run(self):
        meter = None
        try:
            meter = Keithley6517B(port=self.port)
            meter.connect(retries=2, settle_s=0.25)

            try:
                meter.query("*IDN?", term="\n", deadline_s=0.6, recover=False)
                time.sleep(0.1)
            except Exception:
                pass

            idn = meter.idn()
            if "6517" not in idn.upper():
                raise SerialInstrumentError(f"Falsches Gerät auf {self.port}: {idn}")
            self.ok.emit(meter, idn)

        except Exception as e:
            if meter is not None:
                try:
                    meter.disconnect()
                except Exception:
                    pass
            self.fail.emit(f"COM-Port falsch oder Gerät antwortet nicht ({self.port}): {e}")

        finally:
            self.finished.emit()


class K6517BController(KeithleyScanControllerBase):

    PORT = "COM11"   # hardcoded

    def __init__(self, window, *, btn_name: str, led_name: str | None = None):
        super().__init__(
            window,
            model_hint="6517",
            display_name="Keithley 6517B",
            led_name=led_name,
        )
        self.w = window

        self.btn = self.w.findChild(QPushButton, btn_name)
        if self.btn is None:
            raise RuntimeError(f"Button '{btn_name}' nicht gefunden.")

        self.btn.setCheckable(True)
        self.btn.setChecked(False)
        self.meter = None
        self.thread = None
        self.worker = None
        self._connected = False

        self.btn.toggled.connect(self.on_toggled)

    @Slot(bool)
    def on_toggled(self, want_connect: bool):
        if self.thread is not None and self.thread.isRunning():
            self.btn.blockSignals(True)
            self.btn.setChecked(not want_connect)
            self.btn.blockSignals(False)
            return

        if not want_connect:
            if self.meter is not None:
                try:
                    self.meter.disconnect()
                except Exception:
                    pass
                self.meter = None
            self._connected = False
            self._set_led("gray")
            if hasattr(self.w, "statusbar") and self.w.statusbar:
                self.w.statusbar.showMessage("Keithley 6517B: disconnected", 3000)
            append_log(self.w, "Keithley 6517B getrennt.", "warn")
            return

        self._set_led("orange")
        self.btn.setEnabled(False)

        self.thread = QThread(self.w)
        self.worker = K6517BConnectWorker(port=self.PORT)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.ok.connect(self.on_ok, Qt.QueuedConnection)
        self.worker.fail.connect(self.on_fail, Qt.QueuedConnection)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.on_thread_finished, Qt.QueuedConnection)

        self.thread.start()

    @Slot(object, str)
    def on_ok(self, meter_obj, idn: str):
        self.meter = meter_obj
        self._connected = True
        self._set_led("green")
        self.btn.setChecked(True)
        if hasattr(self.w, "statusbar") and self.w.statusbar:
            self.w.statusbar.showMessage(f"Keithley 6517B: {idn}", 5000)
        append_log(self.w, f"Keithley 6517B verbunden auf {self.PORT} ({idn}).", "ok")

    @Slot(str)
    def on_fail(self, msg: str):
        self.meter = None
        self._connected = False
        self._set_led("red")
        self.btn.blockSignals(True)
        self.btn.setChecked(False)
        self.btn.blockSignals(False)
        if hasattr(self.w, "statusbar") and self.w.statusbar:
            self.w.statusbar.showMessage(f"Keithley 6517B: connect failed: {msg}", 8000)
        append_log(self.w, f"Fehler Keithley 6517B: {msg}", "error")

    @Slot()
    def on_thread_finished(self):
        self.btn.setEnabled(True)
        self.thread = None
        self.worker = None


class MeasurementSettingsController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.w = window

        self.cmbDetector = self.w.findChild(QComboBox, "cmbDetector")
        self.cmbRange = self.w.findChild(QComboBox, "cmbRange")
        self.chkAutoRange = self.w.findChild(QCheckBox, "chkAutoRange")

        if self.cmbDetector is None:
            raise RuntimeError("cmbDetector nicht gefunden.")
        if self.cmbRange is None:
            raise RuntimeError("cmbRange nicht gefunden.")
        if self.chkAutoRange is None:
            raise RuntimeError("chkAutoRange nicht gefunden.")

        self.cmbDetector.currentIndexChanged.connect(self.on_detector_changed)
        self.chkAutoRange.toggled.connect(self.on_autorange_toggled)

        # einmal initial anwenden
        self.on_detector_changed(self.cmbDetector.currentIndex())

    @Slot(int)
    def on_detector_changed(self, _idx: int):
        det = self.cmbDetector.currentText().strip()

        self.cmbRange.blockSignals(True)
        self.cmbRange.clear()

        if det == "Keithley 6485":
            self.cmbRange.addItems(["2 nA", "20 nA", "200 nA", "2 µA", "20 µA", "200 µA", "2 mA", "20 mA"])
            self.cmbRange.setCurrentIndex(2)  # Default 200 nA
            self.cmbRange.setEnabled(not self.chkAutoRange.isChecked())

        elif det == "Keithley 6517B":
            self.cmbRange.addItems([
                "20 pA", "200 pA",
                "2 nA", "20 nA", "200 nA",
                "2 µA", "20 µA", "200 µA",
                "2 mA", "20 mA"])
            self.cmbRange.setCurrentIndex(4)  # Default 200 nA
            self.cmbRange.setEnabled(not self.chkAutoRange.isChecked())

        elif det == "CEM":
            self.cmbRange.addItem("n/a (CEM)")
            self.cmbRange.setEnabled(False)

        else:
            self.cmbRange.addItem("unknown detector")
            self.cmbRange.setEnabled(False)

        self.cmbRange.blockSignals(False)

    @Slot(bool)
    def on_autorange_toggled(self, enabled: bool):
        # Range-Auswahl nur aktiv, wenn AutoRange AUS
        self.cmbRange.setEnabled(not enabled)


def _range_str_to_A(range_str: str) -> float:
    """Wandelt einen Range-String wie '200 nA' oder '2 µA' in Ampere um."""
    s = range_str.strip().lower().replace("µ", "u").replace(" ", "")
    try:
        if s.endswith("pa"): return float(s[:-2]) * 1e-12
        if s.endswith("na"): return float(s[:-2]) * 1e-9
        if s.endswith("ua"): return float(s[:-2]) * 1e-6
        if s.endswith("ma"): return float(s[:-2]) * 1e-3
        if s.endswith("a"):  return float(s[:-1])
    except ValueError:
        pass
    return 2e-9  # fallback


class ScanWorker(QObject):

    progress = Signal(int, int, float)        # i, n, energy_eV
    finished = Signal(float)                  # elapsed_s
    stopped = Signal(str)
    failed = Signal(str)
    # i, n, E_soll_eV, V_up_V, V_down_V, I_mean_A, I_std_A, vals_json
    # vals_json: JSON-String der Einzelmesswerte (fuer Roh-CSV)
    point = Signal(int, int, float, float, float, float, float, str)


    def __init__(self,
                 energies: list[float],
                 settle_s: float,
                 psu_ion,
                 psu_up,
                 psu_down,
                 meter,
                 mode_text: str,
                 avg_n: int,
                 k: float = 1.0,
                 e_decel: float = 0.0,
                 p2: float = 0.0,
                 settle_tol_v: float = 1.0,
                 settle_timeout_s: float = 10.0,
                 buffer_n: int = 1,
                 dwell_s: float = 0.0):
        super().__init__()

        self.energies = energies
        self.settle_s = settle_s

        self.psu_ion = psu_ion
        self.psu_up = psu_up
        self.psu_down = psu_down

        self.meter = meter
        self.mode_text = mode_text
        self.avg_n = avg_n
        self.k = max(k, 1e-6)        # Spektrometerkonstante
        self.e_decel = e_decel        # Abbremsspannung [eV]
        self.p2 = p2                  # Offset P2 [V] (Gl. 4.27)
        self.settle_tol_v = float(settle_tol_v)       # Toleranz Soll/Ist [V]
        self.settle_timeout_s = float(settle_timeout_s)  # max. Wartezeit [s]
        self.buffer_n = max(1, int(buffer_n))
        self.dwell_s  = max(0.0, float(dwell_s))

        self._stop = False
        self._paused = False
        # Einelementige Liste als shared stop-flag – wird an read_current_A()
        # übergeben damit *OPC?-Waits im 6517B vorzeitig abgebrochen werden können
        self._stop_flag: list[bool] = [False]

    @Slot()
    def stop(self):
        self._stop = True
        self._stop_flag[0] = True
        self._paused = False   # unblock if paused

    @Slot()
    def pause(self):
        self._paused = True

    @Slot()
    def resume(self):
        self._paused = False

    def _interruptible_sleep(self, duration_s: float, chunk_s: float = 0.05) -> bool:
        """Schläft in kleinen Stücken und prüft dazwischen auf Stop/Pause.
        Gibt True zurück, wenn ein Stop angefordert wurde.
        """
        end = time.time() + max(0.0, float(duration_s))
        while time.time() < end:
            if self._stop:
                return True
            while self._paused and not self._stop:
                time.sleep(0.1)
            time.sleep(min(chunk_s, max(0.0, end - time.time())))
        return self._stop

    @Slot()
    def run(self):
        t_start = time.perf_counter()
        try:
            n = len(self.energies)
    
            for i, e in enumerate(self.energies, start=1):

                if self._stop:
                    self.stopped.emit("Scan stopped by user.")
                    return
                # Pause zwischen zwei Messpunkten
                while self._paused and not self._stop:
                    time.sleep(0.1)
                if self._stop:
                    self.stopped.emit("Scan stopped by user.")
                    return
    
                # -------------------------------------------------
                # 1) Spannung setzen  –  Gl. 4.27 (konstantes ICS-Potential)
                #    U_PPA_oben  = k·(E − E_decel) + P2 + E_decel
                #    PPA_unten = E_decel
                # -------------------------------------------------
                u_up   = self.k * (e - self.e_decel) + self.p2 + self.e_decel
                u_down = self.e_decel

                if self.psu_up is not None:
                    self.psu_up.set_voltage(u_up)
                if self.psu_down is not None:
                    self.psu_down.set_voltage(u_down)

                # ---- aktive Stabilitaetspruefung (Soll/Ist-Vergleich) ----
                # Prueft psu_up (PPA oben) und psu_down mit konfigurierbarer
                # Toleranz und Timeout. Bei Timeout: Warnung im Log, Scan laeuft weiter.
                V_up_read   = float("nan")
                V_down_read = float("nan")

                def _wait_settle(psu, u_soll, label):
                    """Wartet bis |U_ist - u_soll| < settle_tol_v oder Timeout.
                    Gibt den zuletzt gelesenen Istwert zurueck (nan wenn kein Readback)."""
                    try:
                        v = psu.read_voltage()
                    except Exception:
                        return float("nan")   # kein Readback verfügbar

                    if not math.isfinite(v):
                        return float("nan")

                    t0 = time.time()
                    while abs(v - u_soll) > self.settle_tol_v:
                        if self._stop:
                            return v
                        if time.time() - t0 > self.settle_timeout_s:
                            log.warning(
                                "Settle-Timeout %s: Soll=%.3f V, Ist=%.3f V "
                                "(Toleranz=%.2f V, Timeout=%.1f s)",
                                label, u_soll, v,
                                self.settle_tol_v, self.settle_timeout_s
                            )
                            break
                        time.sleep(0.05)
                        try:
                            v = psu.read_voltage()
                        except Exception:
                            break
                    return v

                if self.psu_up is not None:
                    V_up_read = _wait_settle(self.psu_up, u_up, "PPA_up")
                    if self._stop:
                        self.stopped.emit("Scan stopped by user.")
                        return

                if self.psu_down is not None:
                    V_down_read = _wait_settle(self.psu_down, u_down, "PPA_down")
                    if self._stop:
                        self.stopped.emit("Scan stopped by user.")
                        return

                # -------------------------------------------------
                # 2) optional zusätzliche settle-Zeit
                # -------------------------------------------------
                if self.settle_s > 0:
                    if self._interruptible_sleep(self.settle_s):
                        self.stopped.emit("Scan stopped by user.")
                        return

                # -------------------------------------------------
                # 3) Keithley messen
                # -------------------------------------------------
                I_mean = float("nan")
                I_std  = float("nan")
                vals   = []

                if self.meter is not None:

                    def _read_one() -> float:
                        return self.meter.read_current_A(
                            stop_flag=self._stop_flag if hasattr(self.meter, "_TERM") else None
                        )

                    def _collect(n_readings: int) -> list[float]:
                        buf = []
                        for k in range(n_readings):
                            if self._stop:
                                return buf
                            v = _read_one()
                            if not np.isnan(v):
                                buf.append(v)
                            if k < n_readings - 1 and self.dwell_s > 0:
                                if self._interruptible_sleep(self.dwell_s):
                                    return buf
                        return buf

                    if self.mode_text.startswith("Single"):
                        vals = _collect(self.buffer_n)
                    elif self.mode_text.startswith("Average"):
                        vals = _collect(self.avg_n * self.buffer_n)
                    else:
                        vals = _collect(self.buffer_n)

                    if vals:
                        I_mean = float(np.mean(vals))
                        I_std  = float(np.std(vals, ddof=1)) if len(vals) > 1 else float("nan")

                # -------------------------------------------------
                # 4) Signale an GUI
                # -------------------------------------------------
                self.progress.emit(i, n, e)
                import json as _json
                _vals_json = _json.dumps(vals if "vals" in dir() and vals else [])
                self.point.emit(i, n, e, V_up_read, V_down_read, I_mean, I_std, _vals_json)
    
            self.finished.emit(time.perf_counter() - t_start)
    
        except Exception as ex:
            self.failed.emit(str(ex))


class ScanPlotController(QObject):
    """
    Verantwortlich für: matplotlib Figure, Canvas, NavigationToolbar,
    Datenpuffer (xdata/ydata/vdata) und automatische Y-Achsen-Skalierung.
    """

    # Skalierungsstufen: (Schwellwert in A, Skalierungsfaktor, Einheitenlabel)
    _CURRENT_UNITS = [
        (1e-12, 1e15, "fA"),
        (1e-9,  1e12, "pA"),
        (1e-6,  1e9,  "nA"),
        (1e-3,  1e6,  "µA"),
        (1.0,   1e3,  "mA"),
    ]

    def __init__(self, window):
        super().__init__(window)
        self.w = window

        self.xdata: list[float] = []   # akkumulierter Mittelwert (alle Loops, alle Richtungen)
        self.ydata: list[float] = []
        self.vdata: list[float] = []   # mittlerer Istwert pro Bin
        self.vsdata: list[float] = []  # Stdabw der Istwerte pro Bin
        self.edata: list[float] = []   # Stdabw Strom über Loops

        # Separate Puffer für Vorwärts / Rückwärts (für Plot)
        self._fwd: dict[float, list[float]] = {}   # key=round(e,6) → [i_mean pro Loop]
        self._bwd: dict[float, list[float]] = {}
        self._fwd_v: dict[float, float] = {}   # key → v_read (letzter Wert)
        self._bwd_v: dict[float, float] = {}
        self._v_all: dict[float, list[float]] = {}  # key → alle Istwerte (alle Loops/Richtungen)
        self._current_loop_keys: set[float] = {}   # Punkte die im laufenden Loop schon gemessen wurden

        # ── Stop-Leiste (oben im Plot-Bereich) ───────────────────────────────
        self._btn_plot_stop      = QPushButton("⏹ Stop Scan")
        self._btn_plot_loop_stop = QPushButton("⏭ Stop after Loop")
        self._btn_plot_pause     = QPushButton("⏸ Pause")
        self._btn_plot_stop.setCheckable(False)
        self._btn_plot_loop_stop.setCheckable(False)
        self._btn_plot_pause.setCheckable(True)
        self._btn_plot_stop.setEnabled(False)
        self._btn_plot_loop_stop.setEnabled(False)
        self._btn_plot_pause.setEnabled(False)

        _stop_style = (
            "QPushButton { background-color: #c0392b; color: white; "
            "font-weight: bold; padding: 4px 12px; border-radius: 3px; }"
            "QPushButton:disabled { background-color: #888; color: #ccc; }"
            "QPushButton:hover:!disabled { background-color: #e74c3c; }"
        )
        _pause_style = (
            "QPushButton { background-color: #2980b9; color: white; "
            "font-weight: bold; padding: 4px 12px; border-radius: 3px; }"
            "QPushButton:checked { background-color: #e67e22; }"
            "QPushButton:disabled { background-color: #888; color: #ccc; }"
            "QPushButton:hover:!disabled { background-color: #3498db; }"
        )
        self._btn_plot_stop.setStyleSheet(_stop_style)
        self._btn_plot_loop_stop.setStyleSheet(_stop_style)
        self._btn_plot_pause.setStyleSheet(_pause_style)
        self._btn_plot_stop.setToolTip("Scan sofort abbrechen.")
        self._btn_plot_loop_stop.setToolTip("Aktuellen Loop zu Ende laufen, dann stoppen.")
        self._btn_plot_pause.setToolTip("Scan zwischen zwei Messpunkten einfrieren / fortsetzen.")

        self._btn_export = QPushButton("💾 Export Plot")
        self._btn_export.setToolTip("Plot als PNG, PDF oder SVG exportieren.")
        self._btn_export.setStyleSheet(
            "QPushButton { padding: 4px 10px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #2ecc71; color: white; }")
        self._btn_export.clicked.connect(self._on_export_plot)

        stop_bar = QWidget()
        stop_lay = QHBoxLayout(stop_bar)
        stop_lay.setContentsMargins(6, 4, 6, 4); stop_lay.setSpacing(8)
        stop_lay.addWidget(self._btn_plot_stop)
        stop_lay.addWidget(self._btn_plot_loop_stop)
        stop_lay.addWidget(self._btn_plot_pause)
        stop_lay.addWidget(_vsep())
        stop_lay.addWidget(self._btn_export)
        stop_lay.addStretch()

        # ── Figure & Canvas ───────────────────────────────────────────────────
        self.figure = Figure(figsize=(5, 4))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.figure.set_constrained_layout(True)

        self.ax.set_xlabel("Energy (eV)")
        self.ax.set_ylabel("Current (A)")
        self.ax.grid(True, which="major", linestyle="--", linewidth=0.8, alpha=0.4)
        self.ax.grid(True, which="minor", linestyle=":",  linewidth=0.6, alpha=0.25)
        self.ax.minorticks_on()
        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)

        # Inject into _plot_container/_plot_layout set by MainWindow
        _plot_parent = getattr(self.w, "_plot_container", None)
        _plot_layout = getattr(self.w, "_plot_layout", None)
        if _plot_layout is not None:
            _plot_layout.addWidget(stop_bar)
            _plot_layout.addWidget(self.canvas)
            _plot_layout.setStretch(_plot_layout.count() - 1, 1)
            _plot_layout.addWidget(NavigationToolbar(self.canvas, _plot_parent or self.w))
        else:
            # Fallback: embed in plotWidget (old path)
            plot_container = self.w.findChild(QWidget, "plotWidget")
            if plot_container is None:
                raise RuntimeError("plotWidget nicht gefunden.")
            layout = QVBoxLayout(plot_container)
            layout.addWidget(stop_bar)
            layout.addWidget(self.canvas)
            layout.setStretch(layout.count() - 1, 1)
            layout.addWidget(NavigationToolbar(self.canvas, plot_container))

        # Einzige Kurve – wird in _redraw_plot aufgeteilt in "bereits gemessen" + "noch ausstehend"
        # Wir nutzen zwei errorbar-Segmente auf derselben sortierten Achse:
        # _eb_done  = gemessener Teil (Vorlauf: blau, Rücklauf: orange)
        # _eb_ahead = noch nicht gemessener Teil im Rücklauf (blau, gedimmt)
        self._eb_done  = self.ax.errorbar([], [], fmt="o-", linewidth=2.0, markersize=5,
                                          capsize=4, capthick=1.2, elinewidth=1.2, color="C0")
        self._eb_ahead = self.ax.errorbar([], [], fmt="o-", linewidth=2.0, markersize=5,
                                          capsize=4, capthick=1.2, elinewidth=1.2,
                                          color="C0", alpha=0.25)
        self.cursor_pt = self.ax.scatter([], [], s=80, color="C0", zorder=6)

        # Theme initial anwenden
        if hasattr(self.w, "_theme"):
            self.apply_theme(self.w._theme)

    # ------------------------------------------------------------------

    def apply_theme(self, t: dict) -> None:
        """Passt matplotlib-Farben an das aktive Qt-Theme an."""
        is_dark = t.get("bg", "#fff") < "#888888"   # einfache Heuristik

        bg      = t["bg"]
        panel   = t["card"]
        text    = t["text"]
        grid_c  = t["border"]
        spine_c = t["border"]

        self.figure.patch.set_facecolor(bg)
        self.ax.set_facecolor(panel)
        self.ax.tick_params(colors=text, which="both")
        self.ax.xaxis.label.set_color(text)
        self.ax.yaxis.label.set_color(text)
        for spine in self.ax.spines.values():
            spine.set_edgecolor(spine_c)
        self.ax.grid(True, which="major", linestyle="--",
                     linewidth=0.8, alpha=0.5, color=grid_c)
        self.ax.grid(True, which="minor", linestyle=":",
                     linewidth=0.5, alpha=0.3, color=grid_c)
        self.canvas.draw_idle()

    def reset(self) -> None:
        """Löscht Datenpuffer und setzt Plot auf Ausgangszustand zurück."""
        self.xdata.clear()
        self.ydata.clear()
        self.vdata.clear()
        self.vsdata.clear()
        self.edata.clear()
        self._fwd.clear()
        self._bwd.clear()
        self._fwd_v.clear()
        self._bwd_v.clear()
        self._v_all.clear()
        self._current_loop_keys = set()

        self._eb_done.remove()
        self._eb_ahead.remove()
        self._eb_done  = self.ax.errorbar([], [], fmt="o-", linewidth=2.0, markersize=5,
                                          capsize=4, capthick=1.2, elinewidth=1.2, color="C0")
        self._eb_ahead = self.ax.errorbar([], [], fmt="o-", linewidth=2.0, markersize=5,
                                          capsize=4, capthick=1.2, elinewidth=1.2,
                                          color="C0", alpha=0.25)
        self.cursor_pt.set_offsets(np.empty((0, 2)))
        self.cursor_pt.set_color("C0")
        self.ax.set_ylabel("Current (A)")
        if self.ax.get_legend():
            self.ax.get_legend().remove()
        from matplotlib.ticker import FuncFormatter
        self.ax.yaxis.set_major_formatter(FuncFormatter(lambda val, _: f"{val:.3g}"))
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw_idle()

    def reset_loop_keys(self) -> None:
        """Leert den Satz der im aktuellen Loop gemessenen Punkte (beim Loop-Start aufrufen)."""
        self._current_loop_keys = set()

    def set_scan_ctrl(self, scan_ctrl) -> None:
        """Verbindet die Stop-Leiste mit dem ScanController."""
        self._scan_ctrl = scan_ctrl
        self._btn_plot_stop.clicked.connect(scan_ctrl.stop_scan)
        self._btn_plot_loop_stop.clicked.connect(scan_ctrl.stop_after_loop)
        self._btn_plot_pause.toggled.connect(self._on_pause_toggled)

    def set_stop_buttons_enabled(self, stop: bool, loop_stop: bool, pause: bool = False) -> None:
        self._btn_plot_stop.setEnabled(stop)
        self._btn_plot_loop_stop.setEnabled(loop_stop)
        self._btn_plot_pause.setEnabled(pause)
        if not pause:
            self._btn_plot_pause.blockSignals(True)
            self._btn_plot_pause.setChecked(False)
            self._btn_plot_pause.setText("⏸ Pause")
            self._btn_plot_pause.blockSignals(False)

    @Slot(bool)
    def _on_pause_toggled(self, paused: bool):
        ctrl = getattr(self, "_scan_ctrl", None)
        if ctrl is None or ctrl.worker is None:
            return
        ctrl._on_pause_toggled(paused)

    def _on_export_plot(self):
        if not self.xdata:
            QMessageBox.information(self.w, "Keine Daten",
                                    "Noch keine Messdaten vorhanden.")
            return
        try:
            ctrl = getattr(self, "_scan_ctrl", None)
            save_dir = (ctrl.params.txtSaveDir.text().strip()
                        if ctrl is not None else os.path.expanduser("~"))
            save_dir = save_dir or os.path.expanduser("~")
            suggested = os.path.join(save_dir, "ref4ep_scan.png")
        except Exception:
            suggested = os.path.join(os.path.expanduser("~"), "ref4ep_scan.png")

        filepath, sel_filter = QFileDialog.getSaveFileName(
            self.w, "Plot exportieren", suggested,
            "PNG Image (*.png);;PDF Document (*.pdf);;SVG Vector (*.svg)")
        if not filepath:
            return
        ext_map = {"PNG Image (*.png)": ".png",
                   "PDF Document (*.pdf)": ".pdf",
                   "SVG Vector (*.svg)": ".svg"}
        if not os.path.splitext(filepath)[1]:
            filepath += ext_map.get(sel_filter, ".png")
        try:
            dpi = 200 if filepath.endswith(".png") else None
            self.figure.savefig(filepath, dpi=dpi, bbox_inches="tight")
            append_log(self.w, f"Plot exportiert: {filepath}", "ok")
        except Exception as ex:
            QMessageBox.critical(self.w, "Export fehlgeschlagen", str(ex))

    def set_bin_params(self, e_start: float, e_step: float) -> None:
        """Setzt Bin-Zentren und Bin-Halbbreite fuer Istwert-basiertes Binning.

        Bin-Zentren: e_start, e_start+e_step, e_start+2*e_step, ...
        Ein Istwert v_read faellt in Bin i wenn:
            |v_read - (e_start + i*e_step)| <= e_step/2

        Punkte die in keinen Bin fallen werden mit key=None verworfen und geloggt.
        """
        self._bin_e_start  = float(e_start)
        self._bin_e_step   = max(float(e_step), 1e-9)
        self._bin_half     = self._bin_e_step / 2.0

    def bin_width_str(self) -> str:
        """Gibt die Bin-Breite als lesbaren String zurueck (fuer Widget-Anzeige)."""
        bw = getattr(self, "_bin_e_step", None)
        if bw is None:
            return ""
        return f"±{bw/2:.3g} eV"

    def _bin_key(self, v_read: float) -> float | None:
        """Ordnet einen Istwert v_read dem naechsten Bin-Zentrum zu.

        Gibt das Bin-Zentrum (float) zurueck, oder None wenn v_read
        ausserhalb aller Bins liegt (Abweichung > e_step/2).
        """
        e0   = getattr(self, "_bin_e_start", 0.0)
        step = getattr(self, "_bin_e_step",  1e-3)
        half = getattr(self, "_bin_half",    5e-4)

        if not math.isfinite(v_read):
            return None
        # Naechstes Bin-Zentrum
        n = round((v_read - e0) / step)
        centre = e0 + n * step
        if abs(v_read - centre) <= half:
            return round(centre, 9)
        return None   # Istwert ausserhalb aller Bins

    def add_point(self, e_soll: float, v_read: float, i_mean: float,
                  i_std: float = float("nan"),
                  direction: str = "forward") -> None:
        """Fuegt Messpunkt hinzu, akkumuliert ueber Loops, aktualisiert Plot.

        Binning erfolgt auf dem PSU-Istwert v_read:
          - v_read wird dem naechsten Bin-Zentrum zugeordnet (±e_step/2)
          - Punkte ausserhalb aller Bins werden verworfen und geloggt
          - Als Plot-X-Wert wird das Bin-Zentrum verwendet (nicht der Sollwert)
          - Im CSV steht: Bin-Zentrum, I_mean, I_std, mittlerer Istwert
        """
        key = self._bin_key(v_read)
        if key is None:
            log.warning(
                "Binning: Istwert %.4g V passt in keinen Bin "
                "(e_start=%.4g, e_step=%.4g, Toleranz=±%.4g eV) – Punkt verworfen.",
                v_read,
                getattr(self, "_bin_e_start", float("nan")),
                getattr(self, "_bin_e_step",  float("nan")),
                getattr(self, "_bin_half",    float("nan")),
            )
            return
        buf  = self._fwd  if direction == "forward" else self._bwd
        vbuf = self._fwd_v if direction == "forward" else self._bwd_v

        if key not in buf:
            buf[key] = []
        if math.isfinite(i_mean):
            buf[key].append(i_mean)
        vbuf[key] = v_read
        self._current_loop_keys.add(key)

        # Gesamtmittelwert über beide Richtungen und alle Loops
        all_vals = self._fwd.get(key, []) + self._bwd.get(key, [])
        acc_mean = float(np.mean(all_vals)) if all_vals else i_mean
        if len(all_vals) > 1:
            # Mehrere Loops → Loop-zu-Loop-Stdabw
            acc_std = float(np.std(all_vals, ddof=1))
        elif math.isfinite(i_std):
            # Erster Loop, N>1 → Stdabw aus Einzelmessungen des Workers
            acc_std = i_std
        else:
            acc_std = float("nan")

        # Alle Istwerte für diesen Bin akkumulieren
        if key not in self._v_all:
            self._v_all[key] = []
        if math.isfinite(v_read):
            self._v_all[key].append(v_read)

        # Mittlerer Istwert und Stdabw über alle akkumulierten Werte
        all_v = self._v_all[key]
        v_mean = float(np.mean(all_v)) if all_v else v_read
        v_std  = float(np.std(all_v, ddof=1)) if len(all_v) > 1 else float("nan")

        # CSV-Puffer aktualisieren
        existing_keys = [round(x, 9) for x in self.xdata]
        if key not in existing_keys:
            self.xdata.append(key)
            self.ydata.append(acc_mean)
            self.edata.append(acc_std)
            self.vdata.append(v_mean)
            self.vsdata.append(v_std)
        else:
            idx = existing_keys.index(key)
            self.ydata[idx]  = acc_mean
            self.edata[idx]  = acc_std
            self.vdata[idx]  = v_mean
            self.vsdata[idx] = v_std

        self._redraw_plot(last_e=key, last_y=acc_mean, direction=direction)
        self.canvas.draw_idle()

    # ------------------------------------------------------------------

    def _best_current_unit(self, values: list[float]):
        if not values:
            return 1.0, "A"
        finite_vals = [v for v in values if math.isfinite(v)]
        if not finite_vals:
            return 1.0, "A"
        max_abs = max(abs(v) for v in finite_vals)
        if max_abs == 0:
            return 1.0, "A"
        for threshold, scale, label in self._CURRENT_UNITS:
            if max_abs < threshold * 1000:
                return scale, label
        return 1e3, "mA"

    def _redraw_plot(self, last_e: float = None, last_y: float = None,
                     direction: str = "forward") -> None:
        """
        Zeichnet eine einzige akkumulierte Kurve.
        Beim Rücklauf: gemessener Teil orange, noch ausstehender Teil blau+gedimmt.
        Beim Vorlauf: alles blau.
        """
        # Alle bekannten Energiepunkte sortiert
        all_keys = sorted(set(list(self._fwd.keys()) + list(self._bwd.keys())))
        if not all_keys:
            return

        all_y_raw = []
        for k in all_keys:
            vals = self._fwd.get(k, []) + self._bwd.get(k, [])
            all_y_raw.append(float(np.mean(vals)) if vals else float("nan"))

        scale, unit = self._best_current_unit(
            [v for v in all_y_raw if math.isfinite(v)])

        def _point_stats(key):
            vals = self._fwd.get(key, []) + self._bwd.get(key, [])
            y = float(np.mean(vals)) * scale if vals else float("nan")
            if len(vals) > 1:
                # Mehrere Loops → Loop-zu-Loop-Stdabw
                e = float(np.std(vals, ddof=1)) * scale
            else:
                # Erster Loop → Stdabw aus edata (N Einzelmessungen), falls vorhanden
                try:
                    idx = [round(x, 6) for x in self.xdata].index(key)
                    e_raw = self.edata[idx]
                    e = (e_raw * scale) if math.isfinite(e_raw) else 0.0
                except (ValueError, IndexError):
                    e = 0.0
            return y, e

        xs_all = all_keys
        ys_all = [_point_stats(k)[0] for k in xs_all]
        es_all = [_point_stats(k)[1] for k in xs_all]

        def _replace_eb(old_eb, xs, ys, es, color, alpha, **kw):
            old_eb.remove()
            has_err = any(e > 0 for e in es) if es else False
            return self.ax.errorbar(
                xs, ys, yerr=es if has_err else None,
                fmt="o-", linewidth=2.0, markersize=5,
                capsize=4, capthick=1.2, elinewidth=1.2,
                color=color, alpha=alpha, **kw)

        # Punkte aufteilen: im aktuellen Loop bereits gemessen (blau, neu)
        # vs. noch nicht gemessen (orange, alt)
        new_keys = self._current_loop_keys
        new_idx  = [i for i, k in enumerate(xs_all) if k in new_keys]
        old_idx  = [i for i, k in enumerate(xs_all) if k not in new_keys]

        xs_new = [xs_all[i] for i in new_idx]
        ys_new = [ys_all[i] for i in new_idx]
        es_new = [es_all[i] for i in new_idx]
        xs_old = [xs_all[i] for i in old_idx]
        ys_old = [ys_all[i] for i in old_idx]
        es_old = [es_all[i] for i in old_idx]

        self._eb_done  = _replace_eb(self._eb_done,  xs_new, ys_new, es_new, "C0", 1.0)   # blau = neu
        self._eb_ahead = _replace_eb(self._eb_ahead, xs_old, ys_old, es_old, "C1", 0.7)   # orange = alt
        self.cursor_pt.set_color("C0")

        if last_e is not None and last_y is not None and math.isfinite(last_y):
            self.cursor_pt.set_offsets([[last_e, last_y * scale]])

        if self.ax.get_legend():
            self.ax.get_legend().remove()

        self.ax.set_ylabel(f"Current ({unit})")
        from matplotlib.ticker import FuncFormatter
        self.ax.yaxis.set_major_formatter(FuncFormatter(lambda val, _: f"{val:.3g}"))
        self.ax.relim()
        self.ax.autoscale_view()


# ---------------------------------------------------------------------------

class ScanParameterController(QObject):
    """
    Verantwortlich für: Energie-SpinBoxen, Messparameter-Widgets,
    Detektor-Auswahl, CSV-Export.
    """

    def __init__(self, window, k6485_ctrl, k6517b_ctrl, plot_ctrl: ScanPlotController):
        super().__init__(window)
        self.w = window
        self.k6485_ctrl = k6485_ctrl
        self.k6517b_ctrl = k6517b_ctrl
        self.plot = plot_ctrl

        # --- Energieparameter ---
        self.spEStart    = self.w.findChild(QDoubleSpinBox, "spEStart_eV")
        self.spEStop     = self.w.findChild(QDoubleSpinBox, "spEStop_eV")
        self.spEStep     = self.w.findChild(QDoubleSpinBox, "spEStep_eV")
        self.spEDecel    = self.w.findChild(QDoubleSpinBox, "spEDecel_eV")
        if self.spEStart is None: raise RuntimeError("spEStart_eV nicht gefunden.")
        if self.spEStop  is None: raise RuntimeError("spEStop_eV nicht gefunden.")
        if self.spEStep  is None: raise RuntimeError("spEStep_eV nicht gefunden.")

        # --- Messparameter ---
        self.spSettle    = self.w.findChild(QDoubleSpinBox, "spSettleTime_s")
        self.spK         = self.w.findChild(QDoubleSpinBox, "spSpectrometerConstant")
        self.spP2        = self.w.findChild(QDoubleSpinBox, "spOffsetP2")
        self.spNPLC      = self.w.findChild(QDoubleSpinBox, "spNPLC")
        self.spAvg       = self.w.findChild(QDoubleSpinBox, "spAvg")
        self.spDwell     = self.w.findChild(QDoubleSpinBox, "spDwell")
        self.spBufferN   = self.w.findChild(QSpinBox,       "spBufferN")
        self.rbAvg       = self.w.findChild(QRadioButton,   "rbAvg")
        self.rbBufferN   = self.w.findChild(QRadioButton,   "rbBufferN")
        self.cmbMode     = self.w.findChild(QComboBox,      "cmbMeasMode")
        self.cmbDetector = self.w.findChild(QComboBox,      "cmbDetector")
        self.cmbPPAMode  = self.w.findChild(QComboBox,      "cmbPPAMode")
        if self.spSettle    is None: raise RuntimeError("spSettleTime_s nicht gefunden.")
        if self.spK         is None: raise RuntimeError("spSpectrometerConstant nicht gefunden.")
        if self.spP2        is None: raise RuntimeError("spOffsetP2 nicht gefunden.")
        if self.spNPLC      is None: raise RuntimeError("spNPLC nicht gefunden.")
        if self.spAvg       is None: raise RuntimeError("spAvg nicht gefunden.")
        if self.cmbMode     is None: raise RuntimeError("cmbMeasMode nicht gefunden.")
        if self.cmbDetector is None: raise RuntimeError("cmbDetector nicht gefunden.")
        if self.cmbPPAMode  is None: raise RuntimeError("cmbPPAMode nicht gefunden.")
        # spDwell / spBufferN / rbAvg / rbBufferN: optional

        # Radio button logic
        self._sync_avg_buffer()
        if self.rbAvg     is not None: self.rbAvg.toggled.connect(self._sync_avg_buffer)
        if self.rbBufferN is not None: self.rbBufferN.toggled.connect(self._sync_avg_buffer)
        # Ensure spAvg starts enabled (rbAvg is checked by default)
        if self.spAvg is not None: self.spAvg.setEnabled(True)

        # --- CSV-Export Widgets ---
        self.btnSaveCSV    = self.w.findChild(QPushButton, "btnSaveCSV")
        self.btnBrowseSave = self.w.findChild(QPushButton, "btnBrowseSave")
        self.txtSaveDir    = self.w.findChild(QLineEdit,   "txtSaveDir")
        self.chkAutoSave   = self.w.findChild(QCheckBox,   "chkAutoSave")
        if self.btnSaveCSV    is None: raise RuntimeError("btnSaveCSV nicht gefunden.")
        if self.btnBrowseSave is None: raise RuntimeError("btnBrowseSave nicht gefunden.")
        if self.txtSaveDir    is None: raise RuntimeError("txtSaveDir nicht gefunden.")
        # chkAutoSave: optional, wird nicht mehr für Auto-Export benötigt

        # Gespeicherten CSV-Ordner laden
        self._settings = QSettings("JLU-IPI", "Ref4EP")
        saved_dir = self._settings.value("csv/save_dir", "")
        self.txtSaveDir.setText(saved_dir if saved_dir and os.path.isdir(saved_dir)
                                else os.path.expanduser("~"))

        self.btnSaveCSV.setEnabled(False)
        self.btnBrowseSave.clicked.connect(self.on_browse_save_dir)
        self.btnSaveCSV.clicked.connect(self.on_save_csv)

    # ------------------------------------------------------------------

    def _sync_avg_buffer(self):
        use_avg = (self.rbAvg is None or self.rbAvg.isChecked())
        if self.spAvg     is not None: self.spAvg.setEnabled(use_avg)
        if self.spBufferN is not None: self.spBufferN.setEnabled(not use_avg)
        if self.spDwell   is not None: self.spDwell.setEnabled(True)
        # Averages spinbox: always enabled when mode is Average
        mode = self.cmbMode.currentText().strip() if self.cmbMode else "Single"
        if self.spAvg is not None and mode.startswith("Average"):
            self.spAvg.setEnabled(True)

    def selected_detector_name(self) -> str:
        try:
            return self.cmbDetector.currentText().strip()
        except Exception:
            return ""

    def selected_meter_controller(self):
        det = self.selected_detector_name().upper()
        if "6517" in det:
            return self.k6517b_ctrl, "Keithley 6517B"
        if "6485" in det:
            return self.k6485_ctrl, "Keithley 6485"
        return None, det or "Unbekannter Detektor"

    def read_scan_params(self) -> dict:
        """Liest alle aktuellen Scan-Parameter aus den Widgets aus."""
        ppa_mode_text = self.cmbPPAMode.currentText() if self.cmbPPAMode is not None else ""
        ppa_mode = 1 if "Mode 1" in ppa_mode_text else (2 if "Mode 2" in ppa_mode_text else 3)

        # Mode 1: E_decel wird auf 0 erzwungen (U_PPA_down = 0 V)
        # Mode 2: E_decel aus Eingabefeld
        if ppa_mode == 1:
            e_decel = 0.0
        else:
            e_decel = float(self.spEDecel.value()) if self.spEDecel is not None else 0.0

        # Loop-Parameter (optional – Widgets können noch fehlen wenn UI noch nicht angepasst)
        sp_loop = self.w.findChild(QSpinBox, "spLoopCount")
        chk_bidir = self.w.findChild(QCheckBox, "chkBidirectional")
        loop_count   = int(sp_loop.value())    if sp_loop   is not None else 1
        bidirectional = chk_bidir.isChecked() if chk_bidir is not None else False

        # Settle-Toleranz und -Timeout (optionale Widgets)
        sp_tol     = self.w.findChild(QDoubleSpinBox, "spSettleTol")
        sp_timeout = self.w.findChild(QDoubleSpinBox, "spSettleTimeout")
        settle_tol_v      = float(sp_tol.value())     if sp_tol     is not None else 1.0
        settle_timeout_s  = float(sp_timeout.value()) if sp_timeout is not None else 10.0

        use_avg  = (self.rbAvg is None or self.rbAvg.isChecked())
        buffer_n = int(self.spBufferN.value()) if (not use_avg and self.spBufferN is not None) else 1
        dwell_s  = float(self.spDwell.value()) if (self.spDwell is not None) else 0.0

        return {
            "e_start":          float(self.spEStart.value()),
            "e_stop":           float(self.spEStop.value()),
            "e_step":           float(self.spEStep.value()),
            "e_decel":          e_decel,
            "ppa_mode":         ppa_mode,
            "ppa_mode_text":    ppa_mode_text,
            "settle_s":         float(self.spSettle.value()),
            "settle_tol_v":     settle_tol_v,
            "settle_timeout_s": settle_timeout_s,
            "nplc":             float(self.spNPLC.value()),
            "avg_n":            int(round(self.spAvg.value())),
            "mode":             self.cmbMode.currentText().strip(),
            "buffer_n":         buffer_n,
            "dwell_s":          dwell_s,
            "use_avg":          use_avg,
            "k":                float(self.spK.value()),
            "p2":               float(self.spP2.value()),
            "loop_count":       loop_count,      # 0 = unendlich
            "bidirectional":    bidirectional,
        }

    # ------------------------------------------------------------------

    @Slot()
    def on_browse_save_dir(self):
        start = self.txtSaveDir.text().strip() or os.path.expanduser("~")
        chosen = QFileDialog.getExistingDirectory(self.w, "Speicherordner wählen", start)
        if chosen:
            self.txtSaveDir.setText(chosen)
            self._settings.setValue("csv/save_dir", chosen)

    def _build_csv_filename(self, loop_num: int | None = None) -> str:
        ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        try:
            e_start = self.spEStart.value()
            e_stop  = self.spEStop.value()
            e_step  = self.spEStep.value()
        except Exception:
            e_start = e_stop = e_step = 0.0
        det = self.selected_detector_name().replace(" ", "").replace("/", "")
        loop_suffix = f"_loop{loop_num:03d}" if loop_num is not None else ""
        return (f"{ts}_scan_{e_start:g}eV-{e_stop:g}eV_step{e_step:g}eV_{det}{loop_suffix}.csv")

    def on_save_csv(self, auto: bool = False, loop_num: int | None = None):
        if not self.plot.xdata:
            QMessageBox.information(self.w, "Keine Daten", "Es liegen keine Messdaten vor.")
            return

        save_dir = self.txtSaveDir.text().strip() or os.path.expanduser("~")
        suggested = os.path.join(save_dir, self._build_csv_filename(loop_num))

        if auto:
            filepath = suggested
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        else:
            filepath, _ = QFileDialog.getSaveFileName(
                self.w, "CSV speichern", suggested,
                "CSV Files (*.csv);;All Files (*)",
            )
            if not filepath:
                return

        try:
            p = self.read_scan_params()
            det = self.selected_detector_name()
            ts_human = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            loop_info = f"\n# Loop:       {loop_num}" if loop_num is not None else ""
            header = [
                "# Ref4EP Scan Export",
                f"# Date:       {ts_human}",
                f"# Detector:   {det}",
                f"# E_start:    {p['e_start']} eV",
                f"# E_stop:     {p['e_stop']} eV",
                f"# Step:       {p['e_step']} eV",
                f"# k:          {p['k']}",
                f"# P2:         {p['p2']} V",
                f"# PPA Mode:   {p['ppa_mode']}",
                f"# E_decel:    {p['e_decel']} eV",
                f"# NPLC:       {p['nplc']}",
                f"# Averages:   {p['avg_n']}",
                f"# Mode:       {p['mode']}",
                f"# Settle_s:   {p['settle_s']} s",
                f"# SettleTol:  {p['settle_tol_v']} V",
                f"# SettleTimeout: {p['settle_timeout_s']} s",
                f"# BinWidth:   ±{p['e_step']/2:.4g} eV (= e_step/2)",
                f"# Loops:      {p['loop_count']} (0=∞)",
                f"# Bidir:      {p['bidirectional']}",
                f"# Points:     {len(self.plot.xdata)}{loop_info}",
                "#",
                "# Spalten:\n"
                "#   E_bin_eV : Bin-Zentrum (Istwert-Binning, Breite = e_step/2)\n"
                "#   I_mean_A : Gemittelter Strom ueber alle Loops und Richtungen [A]\n"
                "#   I_std_A  : Standardabweichung (Loop-zu-Loop oder Einzelmessung)\n"
                "#   U_ist_V  : Mittlerer PSU-Istwert im Bin (Mittelwert Fwd+Bwd) [V]\n"
                "# E_bin_eV, I_mean_A, I_std_A, U_ist_V",
            ]
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(header) + "\n")
                for e, i, s, v, vs in zip(
                    self.plot.xdata, self.plot.ydata,
                    self.plot.edata, self.plot.vdata,
                    self.plot.vsdata,
                ):
                    std_str  = f"{s:.6e}"  if math.isfinite(s)  else "NaN"
                    vstd_str = f"{vs:.6g}" if math.isfinite(vs) else "NaN"
                    f.write(f"{e:.6g},{i:.6e},{std_str},{v:.6g},{vstd_str}\n")

            self._settings.setValue("csv/save_dir", os.path.dirname(filepath))
            self.txtSaveDir.setText(os.path.dirname(filepath))
            append_log(self.w, f"CSV gespeichert: {filepath}", "ok")

        except Exception as ex:
            append_log(self.w, f"Fehler beim CSV-Speichern: {ex}", "error")
            QMessageBox.critical(self.w, "Speicherfehler", str(ex))

    # ------------------------------------------------------------------
    # Rohdaten-CSV (ein Loop, ungefiltert)
    # ------------------------------------------------------------------

    def _build_raw_csv_filename(self, loop_num: int, direction: str) -> str:
        ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        try:
            p = self.read_scan_params()
            tag = (f"{p['e_start']:.0f}eV-{p['e_stop']:.0f}eV"
                   f"_step{p['e_step']:.3g}eV")
        except Exception:
            tag = "scan"
        dir_tag = "fwd" if direction == "forward" else "bwd"
        return f"{ts}_{tag}_loop{loop_num:03d}_{dir_tag}_raw.csv"

    def save_raw_csv(self, raw_buffer: list, loop_num: int,
                     direction: str, avg_n: int) -> None:
        """Speichert Rohdaten eines Loops (ungefiltert, ungebinnt).

        Spalten:
          E_soll_eV   – Sollspannung (was an PSU geschickt wurde)
          U_ist_V     – PSU-Istwert (>M0? zum Messzeitpunkt)
          U_down_V    – PPA_down Istwert
          I_mean_A    – Mittelwert der Einzelmessungen dieses Punktes
          I_std_A     – Standardabweichung der Einzelmessungen
          I_1_A .. I_n_A – alle Einzelmesswerte
        """
        if not raw_buffer:
            return
        save_dir = self.txtSaveDir.text().strip() or os.path.expanduser("~")
        filepath = os.path.join(save_dir,
                                self._build_raw_csv_filename(loop_num, direction))
        try:
            p = self.read_scan_params()
            det = self.selected_detector_name()
            ts_human = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Maximale Anzahl Einzelmesswerte in diesem Loop
            max_vals = max((len(r[5]) for r in raw_buffer), default=0)
            i_cols = ",".join(f"I_{k+1}_A" for k in range(max_vals))
            header = [
                "# Ref4EP Rohdaten-Export (ein Loop, ungebinnt)",
                f"# Date:       {ts_human}",
                f"# Detector:   {det}",
                f"# Loop:       {loop_num}  Richtung: {direction}",
                f"# E_start:    {p['e_start']} eV",
                f"# E_stop:     {p['e_stop']} eV",
                f"# E_step:     {p['e_step']} eV",
                f"# Averages:   {avg_n}",
                f"# NPLC:       {p['nplc']}",
                f"# k:          {p['k']}",
                f"# P2:         {p['p2']} V",
                f"# E_decel:    {p['e_decel']} eV",
                "#",
                "# Spalten:",
                "#   E_soll_eV : Sollwert (an PSU gesendet)",
                "#   U_ist_V   : PSU-Istwert zum Messzeitpunkt (>M0?)",
                "#   U_down_V  : PPA_down Istwert",
                "#   I_mean_A  : Mittelwert Einzelmessungen",
                "#   I_std_A   : Stdabw Einzelmessungen (NaN bei avg_n=1)",
                f"#   I_1_A..I_{max_vals}_A : alle Einzelmesswerte",
                "#",
                f"E_soll_eV,U_ist_V,U_down_V,I_mean_A,I_std_A"
                + (f",{i_cols}" if i_cols else ""),
            ]
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(header) + "\n")
                for e_soll, v_up, v_down, i_mean, i_std, vals in raw_buffer:
                    std_str  = f"{i_std:.6e}"  if math.isfinite(i_std)  else "NaN"
                    mean_str = f"{i_mean:.6e}" if math.isfinite(i_mean) else "NaN"
                    vup_str  = f"{v_up:.6g}"   if math.isfinite(v_up)   else "NaN"
                    vdn_str  = f"{v_down:.6g}" if math.isfinite(v_down) else "NaN"
                    row = f"{e_soll:.6g},{vup_str},{vdn_str},{mean_str},{std_str}"
                    # Einzelwerte auf max_vals aufgefüllt
                    padded = vals + [float("nan")] * (max_vals - len(vals))
                    row += "," + ",".join(
                        f"{v:.6e}" if math.isfinite(v) else "NaN"
                        for v in padded
                    )
                    f.write(row + "\n")
            append_log(self.w, f"Roh-CSV gespeichert: {filepath}", "ok")
        except Exception as ex:
            append_log(self.w, f"Fehler Roh-CSV: {ex}", "error")

    # ------------------------------------------------------------------
    # Akkumulierte CSV (alle Loops, gebinnt, gemittelt)
    # ------------------------------------------------------------------

    def save_accumulated_csv(self, loop_num: int) -> None:
        """Speichert den aktuellen akkumulierten Stand (alle Loops bis jetzt).

        Überschreibt dieselbe Datei nach jedem Loop (kein Zeitstempel im Namen).
        Spalten:
          E_bin_eV  – Bin-Zentrum (Istwert-Binning)
          I_mean_A  – Mittelwert über alle Loops und Richtungen
          I_std_A   – Standardabweichung Loop-zu-Loop
          U_ist_V   – Mittlerer Istwert im Bin (Fwd+Bwd gemittelt)
        """
        if not self.plot.xdata:
            return
        save_dir = self.txtSaveDir.text().strip() or os.path.expanduser("~")
        try:
            p = self.read_scan_params()
        except Exception:
            p = {}
        # Fester Dateiname ohne Zeitstempel – wird nach jedem Loop überschrieben
        try:
            tag = (f"{p['e_start']:.0f}eV-{p['e_stop']:.0f}eV"
                   f"_step{p['e_step']:.3g}eV")
        except Exception:
            tag = "scan"
        filepath = os.path.join(save_dir, f"{tag}_accumulated.csv")
        try:
            ts_human = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            bw = self.plot.bin_width_str()
            header = [
                "# Ref4EP Akkumulierte Daten (gebinnt, über alle Loops gemittelt)",
                f"# Date:       {ts_human}",
                f"# Loops:      {loop_num}",
                f"# BinWidth:   {bw}",
                f"# E_start:    {p.get('e_start', '?')} eV",
                f"# E_stop:     {p.get('e_stop', '?')} eV",
                f"# E_step:     {p.get('e_step', '?')} eV",
                "#",
                "# Spalten:",
                "#   E_bin_eV    : Bin-Zentrum (Istwert-Binning, Breite = e_step/2)",
                "#   I_mean_A    : Mittelwert Strom über alle Loops und Richtungen [A]",
                "#   I_std_A     : Standardabweichung Strom Loop-zu-Loop",
                "#   U_ist_V     : Mittlerer PSU-Istwert im Bin [V]",
                "#   U_ist_std_V : Standardabweichung der Istwerte im Bin [V]",
                "#",
                "E_bin_eV,I_mean_A,I_std_A,U_ist_V,U_ist_std_V",
            ]
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(header) + "\n")
                for e, i, s, v in zip(
                    self.plot.xdata, self.plot.ydata,
                    self.plot.edata, self.plot.vdata
                ):
                    std_str = f"{s:.6e}" if math.isfinite(s) else "NaN"
                    f.write(f"{e:.6g},{i:.6e},{std_str},{v:.6g}\n")
            append_log(self.w,
                f"Akkumulierte CSV aktualisiert (Loop {loop_num}): {filepath}", "ok")
        except Exception as ex:
            append_log(self.w, f"Fehler akkumulierte CSV: {ex}", "error")


# ---------------------------------------------------------------------------

class ScanController(QObject):
    """
    Verantwortlich für: Thread-Verwaltung, Start/Stop-Logik, Watchdog,
    Cleanup nach Scan-Ende.
    Delegiert Plot-Updates an ScanPlotController und
    Parameter-Lesen an ScanParameterController.
    """

    def __init__(self, window, ion_ctrl, ppa_up_ctrl, ppa_down_ctrl, k6485_ctrl, k6517b_ctrl):
        super().__init__(window)
        self.w = window

        self.ion_ctrl      = ion_ctrl
        self.ppa_up_ctrl   = ppa_up_ctrl
        self.ppa_down_ctrl = ppa_down_ctrl
        self.k6485_ctrl    = k6485_ctrl
        self.k6517b_ctrl   = k6517b_ctrl

        # --- Buttons & Statusbar ---
        self.btnStart     = self.w.findChild(QPushButton, "btnScanStart")
        self.btnStop      = self.w.findChild(QPushButton, "btnScanStop")
        self.btnLoopStop  = self.w.findChild(QPushButton, "btnLoopStop")
        self.statusbar    = self.w.findChild(QStatusBar,  "statusbar")
        self.txtLog       = self.w.findChild(QTextEdit,   "txtLog")
        if self.btnStart is None: raise RuntimeError("btnScanStart nicht gefunden.")
        if self.btnStop  is None: raise RuntimeError("btnScanStop nicht gefunden.")

        self.btnStart.clicked.connect(self.start_scan)
        self.btnStop.clicked.connect(self.stop_scan)
        self.btnStop.setEnabled(False)
        if self.btnLoopStop is not None:
            self.btnLoopStop.clicked.connect(self.stop_after_loop)
            self.btnLoopStop.setEnabled(False)

        # --- Fortschrittsbalken in Statusbar ---
        if self.statusbar is not None:
            self._progress = QProgressBar()
            self._progress.setRange(0, 100)
            self._progress.setValue(0)
            self._progress.setMaximumWidth(220)
            self._progress.setMinimumHeight(16)
            self._progress.setStyleSheet(
                "QProgressBar { border: 1px solid #2e3247; border-radius: 4px; "
                "background: #1a1d27; height: 16px; text-align: center; "
                "font-size: 11px; color: #e8eaf0; }"
                "QProgressBar::chunk { background: #4f8ef7; border-radius: 3px; }")
            self._progress.setTextVisible(True)
            self._progress.setFormat("%v/%m pts")
            self._progress.setVisible(False)
            self.statusbar.setMinimumHeight(22)
            self.statusbar.addPermanentWidget(self._progress)
        else:
            self._progress = None

        # --- Sub-Controller ---
        self.plot   = ScanPlotController(window)
        self.params = ScanParameterController(window, k6485_ctrl, k6517b_ctrl, self.plot)
        self.plot.set_scan_ctrl(self)

        # --- Thread-Zustand ---
        self.thread: QThread | None = None
        self.worker: ScanWorker | None = None
        self._scan_stop_requested = False

        # --- Loop-Zustand ---
        self._loop_current    = 0       # aktueller Loop (1-basiert)
        self._loop_total      = 1       # 0 = unendlich
        self._loop_bidir      = False
        self._loop_direction  = "forward"
        self._loop_energies_fwd: list[float] = []
        self._loop_params: dict = {}
        self._loop_meter_ctrl = None
        self._stop_after_loop = False   # sanfter Stop nach aktuellem Loop
        self._t_scan_start: float = 0.0 # Gesamtzeit über alle Loops
        # Rohdaten-Puffer für den aktuellen Loop
        # Einträge: (e_soll, v_up, v_down, i_mean, i_std, [i1, i2, ...])
        self._raw_buffer: list[tuple] = []

    # ------------------------------------------------------------------

    def _show_connection_warning(self, device_name: str):
        QMessageBox.warning(
            self.w, "Gerät nicht verbunden",
            f"{device_name} ist nicht verbunden. Bitte zuerst verbinden.",
        )

    # ------------------------------------------------------------------

    @Slot()
    def start_scan(self):
        # Plot zurücksetzen
        self.plot.reset()
        self.params.btnSaveCSV.setEnabled(False)

        # Doppelstart verhindern
        if self.thread is not None and self.thread.isRunning():
            return

        self._scan_stop_requested = False
        self._stop_after_loop = False

        # Geräte prüfen
        if self.ion_ctrl.psu is None:
            append_log(self.w, "Fehler: Ion PSU nicht verbunden.", "error")
            return
        if self.ppa_down_ctrl.psu is None:
            append_log(self.w, "Fehler: PPA down PSU nicht verbunden.", "error")
            return

        # PPA_up aktivieren: Strom → Spannung 0 V → Output on
        # (Spannung wird im ScanWorker pro Schritt gesetzt)
        if self.ppa_up_ctrl.psu is not None:
            try:
                psu = self.ppa_up_ctrl.psu
                psu.set_current_limit(psu.i_max)
                psu.set_voltage(0.0)
                psu.output(True)
                append_log(self.w, f"PPA upper: Stromlimit {psu.i_max*1000:.0f} mA, Ausgang ein.", "info")
            except Exception as e:
                append_log(self.w, f"Fehler: PPA_up Aktivierung fehlgeschlagen: {e}", "error")
                return
        else:
            append_log(self.w, "Warnung: PPA upper PSU nicht verbunden.", "warn")

        # PPA_down aktivieren: Strom → Spannung 0 V → Output on
        try:
            psu = self.ppa_down_ctrl.psu
            psu.set_current_limit(psu.i_max)
            psu.set_voltage(0.0)
            psu.output(True)
            append_log(self.w, f"PPA lower: Stromlimit {psu.i_max*1000:.0f} mA, Ausgang ein.", "info")
        except Exception as e:
            append_log(self.w, f"Fehler: PPA_down Aktivierung fehlgeschlagen: {e}", "error")
            return

        # Ion PSU: Stromlimit setzen (best-effort – Gerät evtl. nicht im Remote-Modus)
        if self.ion_ctrl.psu is not None:
            try:
                self.ion_ctrl.psu.set_current_limit(self.ion_ctrl.psu.i_max)
                append_log(self.w, f"Ion PSU: Stromlimit {self.ion_ctrl.psu.i_max*1000:.0f} mA gesetzt.", "info")
            except Exception as e:
                append_log(self.w, f"Hinweis: Ion PSU Stromlimit nicht setzbar (manuell?): {e}", "warn")
        else:
            append_log(self.w, "Hinweis: Ion PSU nicht verbunden – Scan läuft ohne Remote-Ion.", "warn")

        # Detektor wählen
        meter_ctrl, meter_name = self.params.selected_meter_controller()
        if meter_ctrl is None:
            append_log(self.w, f"Fehler: Nicht unterstützter Detektor ({meter_name}).", "error")
            return
        if meter_ctrl.meter is None:
            append_log(self.w, f"Fehler: {meter_name} nicht verbunden.", "error")
            self._show_connection_warning(meter_name)
            return

        # Scan-Parameter lesen und Energieliste aufbauen
        p = self.params.read_scan_params()
        e_start, e_stop, e_step = p["e_start"], p["e_stop"], p["e_step"]

        if e_step <= 0:
            append_log(self.w, "Fehler: Scan-Step muss > 0 sein.", "error")
            return

        direction = 1.0 if e_stop >= e_start else -1.0
        step = direction * e_step
        energies_fwd: list[float] = []
        e = e_start
        for _ in range(200_000):
            energies_fwd.append(round(e, 6))
            if (direction > 0 and e + 1e-12 >= e_stop) or \
               (direction < 0 and e - 1e-12 <= e_stop):
                break
            e += step
        else:
            append_log(self.w, "Fehler: Scan abgebrochen, zu viele Punkte.", "error")
            return

        # ── Vorschau-Dialog ───────────────────────────────────────────────────
        save_dir = self.params.txtSaveDir.text().strip() if self.params.txtSaveDir else ""
        autosave = self.params.chkAutoSave.isChecked() if self.params.chkAutoSave else False
        dlg = ScanPreviewDialog(
            self.w, p,
            n_pts        = len(energies_fwd),
            ion_ctrl     = self.ion_ctrl,
            ppa_up_ctrl  = self.ppa_up_ctrl,
            ppa_down_ctrl= self.ppa_down_ctrl,
            meter_ctrl   = meter_ctrl,
            meter_name   = meter_name,
            save_dir     = save_dir,
            autosave     = autosave,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Loop-Zustand initialisieren
        self._loop_current       = 0
        self._loop_total         = p["loop_count"]   # 0 = ∞
        self._loop_bidir         = p["bidirectional"]
        self._loop_direction     = "forward"
        self._raw_buffer         = []   # Rohdaten-Puffer zurücksetzen
        self._loop_energies_fwd  = energies_fwd
        self._loop_params        = p
        self._loop_meter_ctrl    = meter_ctrl

        # Bin-Parameter setzen (Istwert-Binning)
        self.plot.set_bin_params(p["e_start"], p["e_step"])
        # Bin-Breite in read-only QLineEdit anzeigen
        le_bin = self.w.findChild(QLineEdit, "leBinWidth")
        if le_bin is not None:
            le_bin.setReadOnly(True)
            le_bin.setText(self.plot.bin_width_str())

        # Keithley konfigurieren (einmalig)
        meas_ctrl   = self.w.findChild(QObject.__class__, "") or None  # fallback
        _chk_auto   = self.w.findChild(QCheckBox, "chkAutoRange")
        _cmb_range  = self.w.findChild(QComboBox, "cmbRange")
        _auto_range = _chk_auto.isChecked() if _chk_auto else True
        _range_str  = _cmb_range.currentText() if _cmb_range else "200 nA"
        _range_A    = _range_str_to_A(_range_str)
        meter_ctrl.meter.configure_current(
            nplc=p["nplc"],
            auto_range=_auto_range,
            fixed_range_A=_range_A,
            autozero=True,
        )

        # Startlog
        loop_str = "∞" if p["loop_count"] == 0 else str(p["loop_count"])
        bidir_str = ", bidirektional" if p["bidirectional"] else ""
        if p["ppa_mode"] == 1:
            mode_str = "Mode 1: E_decel = 0 V"
        elif p["ppa_mode"] == 2:
            mode_str = f"Mode 2: E_decel = {p['e_decel']:.2f} V"
        else:
            mode_str = "Mode 3: Pass energy"
        meas_mode_str = (
            f"Single (N=1)" if p["mode"].startswith("Single")
            else f"Average (N={p['avg_n']})"
        )
        append_log(
            self.w,
            f"Messung gestartet: {len(energies_fwd)} Punkte von {e_start:.2f} eV "
            f"bis {e_stop:.2f} eV, Schrittweite {abs(e_step):.2f} eV. "
            f"Loops: {loop_str}{bidir_str}. "
            f"Detektor: {meter_name}. {mode_str}, k = {p['k']:.4f}, P2 = {p['p2']:.4f} V. "
            f"Messmodus: {meas_mode_str}.",
            "ok",
        )

        # UI sperren
        self.btnStart.setEnabled(False)
        self.btnStop.setEnabled(True)
        if self.btnLoopStop is not None:
            self.btnLoopStop.setEnabled(True)
        self.plot.set_stop_buttons_enabled(stop=True, loop_stop=True, pause=True)
        self.plot._btn_plot_pause.blockSignals(True)
        self.plot._btn_plot_pause.setChecked(False)
        self.plot._btn_plot_pause.setText("⏸ Pause")
        self.plot._btn_plot_pause.blockSignals(False)

        # Ersten Loop starten
        self._t_scan_start = time.perf_counter()
        self._start_one_loop()

    def _start_one_loop(self):
        """Startet einen einzelnen Scan-Durchlauf (Vorwärts oder Rückwärts)."""
        self._loop_current += 1
        self.plot.reset_loop_keys()   # Farbsplit für neuen Loop zurücksetzen
        p = self._loop_params

        # Energieliste für diese Richtung
        if self._loop_direction == "forward":
            energies = self._loop_energies_fwd
        else:
            energies = list(reversed(self._loop_energies_fwd))

        loop_str = "∞" if self._loop_total == 0 else str(self._loop_total)
        dir_str  = "vorwärts" if self._loop_direction == "forward" else "rückwärts"
        # Halb-Loop-Zähler: bei bidir zählt jedes Hin+Rück als ein Loop
        half = self._loop_current
        full_loop = (half + 1) // 2 if self._loop_bidir else half
        append_log(self.w,
            f"Loop {full_loop}/{loop_str} gestartet ({dir_str}, "
            f"{len(energies)} Punkte).", "info")

        if self.statusbar:
            self.statusbar.showMessage(
                f"Loop {full_loop}/{loop_str} – {dir_str}: 0/{len(energies)}", 0)

        self.thread = QThread(self.w)
        self.worker = ScanWorker(
            energies=energies,
            settle_s=p["settle_s"],
            psu_ion=self.ion_ctrl.psu,
            psu_up=self.ppa_up_ctrl.psu,
            psu_down=self.ppa_down_ctrl.psu,
            meter=self._loop_meter_ctrl.meter,
            mode_text=p["mode"],
            avg_n=p["avg_n"],
            k=p["k"],
            e_decel=p["e_decel"],
            p2=p["p2"],
            settle_tol_v=p.get("settle_tol_v", 1.0),
            settle_timeout_s=p.get("settle_timeout_s", 10.0),
            buffer_n=p.get("buffer_n", 1),
            dwell_s=p.get("dwell_s", 0.0),
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)

        self.worker.progress.connect(self.on_scan_progress,  Qt.QueuedConnection)
        self.worker.point.connect(   self.on_scan_point,     Qt.QueuedConnection)
        self.worker.finished.connect(self.on_scan_finished,  Qt.QueuedConnection)
        self.worker.stopped.connect( self.on_scan_stopped,   Qt.QueuedConnection)
        self.worker.failed.connect(  self.on_scan_failed,    Qt.QueuedConnection)

        self.worker.finished.connect(self.thread.quit)
        self.worker.stopped.connect( self.thread.quit)
        self.worker.failed.connect(  self.thread.quit)

        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.on_scan_thread_finished, Qt.QueuedConnection)

        self.thread.start()
        log.info("Loop %d START: %d Punkte (%s)",
                 self._loop_current, len(energies), self._loop_direction)

    def _reset_pause_button(self):
        # Only reset visual state – setEnabled is handled exclusively by
        # set_stop_buttons_enabled, never here.
        self.plot._btn_plot_pause.blockSignals(True)
        self.plot._btn_plot_pause.setChecked(False)
        self.plot._btn_plot_pause.setText("⏸ Pause")
        self.plot._btn_plot_pause.blockSignals(False)

    def _on_pause_toggled(self, paused: bool):
        if self.worker is None:
            return
        if paused:
            self.worker.pause()
            self.plot._btn_plot_pause.blockSignals(True)
            self.plot._btn_plot_pause.setChecked(True)
            self.plot._btn_plot_pause.setText("▶ Resume")
            self.plot._btn_plot_pause.blockSignals(False)
            append_log(self.w, "Scan pausiert.", "warn")
            if self.statusbar:
                self.statusbar.showMessage("Scan paused – Resume zum Fortsetzen.", 0)
        else:
            self.worker.resume()
            self.plot._btn_plot_pause.blockSignals(True)
            self.plot._btn_plot_pause.setChecked(False)
            self.plot._btn_plot_pause.setText("⏸ Pause")
            self.plot._btn_plot_pause.blockSignals(False)
            append_log(self.w, "Scan fortgesetzt.", "info")
            if self.statusbar:
                self.statusbar.showMessage("Scan running.", 3000)

    @Slot()
    def stop_after_loop(self):
        """Sanfter Stop: aktuellen Loop zu Ende laufen, dann aufhören."""
        self._stop_after_loop = True
        append_log(self.w, "Stop nach aktuellem Loop angefordert.", "warn")
        if self.btnLoopStop is not None:
            self.btnLoopStop.setEnabled(False)
        self.plot.set_stop_buttons_enabled(stop=True, loop_stop=False, pause=True)

    @Slot()
    def stop_scan(self):
        log.info("Scan STOP gedrückt")
        if self.worker is None or self.thread is None or not self.thread.isRunning():
            return

        self._scan_stop_requested = True
        self._reset_pause_button()
        try:
            self.worker.stop()   # sets _stop=True, _paused=False
        except Exception:
            pass

        self.btnStart.setEnabled(False)
        self.btnStop.setEnabled(False)
        if self.statusbar:
            self.statusbar.showMessage("Stopping scan...", 0)
        append_log(self.w, "Stop Scan angefordert.", "warn")

        STOP_SOFT_MS = 5_000
        STOP_HARD_MS = 3_000

        def _watchdog_quit():
            if self.thread is not None and self.thread.isRunning():
                log.warning("Watchdog: Thread reagiert nicht – sende quit()")
                append_log(self.w, "Warnung: Scan-Thread reagiert nicht – erzwinge Stopp.", "warn")
                self.thread.quit()
                QTimer.singleShot(STOP_HARD_MS, _watchdog_terminate)

        def _watchdog_terminate():
            if self.thread is not None and self.thread.isRunning():
                log.error("Watchdog: Thread antwortet nicht auf quit() – terminate()")
                append_log(self.w, "Fehler: Thread wurde hart beendet (terminate).", "error")
                self.thread.terminate()
                self.thread.wait(1000)
                self.thread = None
                self.worker = None
                self._scan_stop_requested = False
                self._pending_next_loop = False   # never restart after hard kill
                self._reset_pause_button()
                self.plot.set_stop_buttons_enabled(stop=False, loop_stop=False)
                self.btnStart.setEnabled(True)
                self.btnStop.setEnabled(False)

        QTimer.singleShot(STOP_SOFT_MS, _watchdog_quit)

    # ------------------------------------------------------------------

    @Slot(int, int, float)
    def on_scan_progress(self, i: int, n: int, e: float):
        if self._progress is not None:
            self._progress.setVisible(True)
            self._progress.setRange(0, n)
            self._progress.setValue(i)
            elapsed = time.perf_counter() - self._t_scan_start
            self._progress.setFormat(f"%v/%m pts  ({elapsed:.0f}s)")
        loop_str = "∞" if self._loop_total == 0 else str(self._loop_total)
        full_loop = (self._loop_current + 1) // 2 if self._loop_bidir else self._loop_current
        self.w.setWindowTitle(
            f"Ref4EP – Scan  {i}/{n}  (Loop {full_loop}/{loop_str})  E={e:.2f} eV")
        if self.statusbar:
            self.statusbar.showMessage(f"Scan: {i}/{n}  E = {e:.2f} eV", 0)

    @Slot(int, int, float, float, float, float, float, str)
    def on_scan_point(self, i, n, e, v_up, v_down, i_mean, i_std, vals_json):
        import json as _json
        vals = _json.loads(vals_json)
        self._raw_buffer.append((e, v_up, v_down, i_mean, i_std, vals))

        # Sollwerte berechnen
        p = self._loop_params
        k      = p.get("k", 1.0)
        e_dec  = p.get("e_decel", 0.0)
        p2     = p.get("p2", 0.0)
        u_up_soll   = k * (e - e_dec) + p2 + e_dec
        u_down_soll = e_dec

        # Wenn kein Readback verfügbar (nan), Sollwert fürs Binning verwenden
        v_up_for_bin = v_up if math.isfinite(v_up) else u_up_soll
        self.plot.add_point(e, v_up_for_bin, i_mean, i_std, direction=self._loop_direction)

        def _fv(v):
            return f"{v:.3f}" if math.isfinite(v) else "n/a"

        def _dv(ist, soll):
            if math.isfinite(ist) and math.isfinite(soll):
                return f"Δ={ist-soll:+.3f}"
            return "(no readback)"

        if np.isnan(i_std):
            i_str = f"{i_mean:.3e} A"
        else:
            i_str = f"{i_mean:.3e} ± {i_std:.2e} A"

        append_log(self.w,
            f"[{i}/{n}] E={e:.2f} eV | "
            f"U_up: soll={u_up_soll:.3f} ist={_fv(v_up)} {_dv(v_up, u_up_soll)} V | "
            f"U_dn: soll={u_down_soll:.3f} ist={_fv(v_down)} {_dv(v_down, u_down_soll)} V | "
            f"I={i_str}", "info")

    @Slot(float)
    def on_scan_finished(self, elapsed_s: float):
        mins, secs = divmod(elapsed_s, 60)
        time_str = f"{int(mins)}m {secs:.1f}s" if mins >= 1 else f"{elapsed_s:.1f}s"
        loop_str = "∞" if self._loop_total == 0 else str(self._loop_total)
        full_loop = (self._loop_current + 1) // 2 if self._loop_bidir else self._loop_current
        append_log(self.w,
            f"Loop {full_loop}/{loop_str} ({self._loop_direction}) beendet. "
            f"Dauer: {time_str}", "ok")

        # CSV speichern nur wenn Auto-save aktiviert
        auto_save = (self.params.chkAutoSave is not None
                     and self.params.chkAutoSave.isChecked())
        if auto_save:
            self.params.save_raw_csv(
                raw_buffer=self._raw_buffer,
                loop_num=full_loop,
                direction=self._loop_direction,
                avg_n=self._loop_params.get("avg_n", 1),
            )
        self._raw_buffer = []   # Puffer immer leeren

        # Akkumulierte CSV: nur bei aktiviertem Auto-save
        is_full_loop_done = (not self._loop_bidir or
                             self._loop_direction == "backward")
        if auto_save and self.plot.xdata and is_full_loop_done:
            self.params.save_accumulated_csv(loop_num=full_loop)

        # Manuelles Speichern über btnSaveCSV bleibt möglich
        # (kein automatischer Loop-Summary-Export mehr)

        # Nächste Richtung / nächsten Loop bestimmen
        if self._stop_after_loop or self._scan_stop_requested:
            self._finish_all_loops()
            return

        next_direction = None

        if self._loop_bidir and self._loop_direction == "forward":
            # Rückwärts-Halbloop folgt
            next_direction = "backward"
        else:
            # Vollständigen Loop abgeschlossen – prüfen ob weitere folgen
            completed_full_loops = (self._loop_current + 1) // 2 if self._loop_bidir \
                                   else self._loop_current
            if self._loop_total == 0 or completed_full_loops < self._loop_total:
                next_direction = "forward"
            else:
                self._finish_all_loops()
                return

        self._loop_direction = next_direction
        # Thread ist noch am Aufräumen – kurz warten bis on_scan_thread_finished
        # den Thread auf None setzt, dann nächsten Loop starten
        self._pending_next_loop = True   # Flag für on_scan_thread_finished

    def _finish_all_loops(self):
        """Wird nach dem letzten Loop aufgerufen."""
        total_s = time.perf_counter() - self._t_scan_start
        mins, secs = divmod(total_s, 60)
        time_str = f"{int(mins)}m {secs:.1f}s" if mins >= 1 else f"{total_s:.1f}s"
        append_log(self.w, f"Alle Loops abgeschlossen. Gesamtdauer: {time_str}", "ok")
        self._scan_cleanup("Scan finished.")
        if self.plot.xdata:
            self.params.btnSaveCSV.setEnabled(True)

    @Slot(str)
    def on_scan_stopped(self, msg: str):
        append_log(self.w, msg, "warn")
        self._pending_next_loop = False
        self._finish_all_loops()

    @Slot(str)
    def on_scan_failed(self, msg: str):
        append_log(self.w, f"Fehler: {msg}", "error")
        self._pending_next_loop = False
        self._scan_cleanup(f"Scan failed: {msg}")

    def _scan_cleanup(self, msg: str):
        self._pending_next_loop = False
        if self._progress is not None:
            self._progress.setVisible(False)
            self._progress.setValue(0)
        self.w.setWindowTitle("Ref4EP  v4.0  |  JLU Giessen – IPI")
        if self.statusbar:
            self.statusbar.showMessage(msg, 5000)
        self.btnStop.setEnabled(False)
        if self.btnLoopStop is not None:
            self.btnLoopStop.setEnabled(False)

    @Slot()
    def on_scan_thread_finished(self):
        self.thread = None
        self.worker = None
        was_stop_requested = self._scan_stop_requested
        self._scan_stop_requested = False

        if getattr(self, "_pending_next_loop", False) and not was_stop_requested:
            self._pending_next_loop = False
            self._start_one_loop()   # buttons stay as-is, like BuehlerRPA
        else:
            self._pending_next_loop = False
            self._reset_pause_button()
            self.plot.set_stop_buttons_enabled(stop=False, loop_stop=False)
            self.btnStart.setEnabled(True)
            self.btnStop.setEnabled(False)
            if self.btnLoopStop is not None:
                self.btnLoopStop.setEnabled(False)


class CloseEventFilter(QObject):
    """
    Event-Filter der das Hauptfenster-CloseEvent abfängt.
    Ist ein Scan aktiv: Rückfrage → sauberer Stop → dann schließen.
    Läuft kein Scan: direkt schließen.
    """
    def __init__(self, window, scan_ctrl):
        super().__init__(window)
        self.w = window
        self.scan_ctrl = scan_ctrl
        self._closing = False   # verhindert Doppel-Close während Thread stoppt

    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent
        if obj is self.w and event.type() == QEvent.Type.Close:
            if self._closing:
                # Zweiter Close-Versuch nach Thread-Stop → durchlassen
                return False

            scan_running = (
                self.scan_ctrl.thread is not None
                and self.scan_ctrl.thread.isRunning()
            )

            if scan_running:
                reply = QMessageBox.question(
                    self.w,
                    "Scan läuft",
                    "Ein Scan ist noch aktiv.\n"
                    "Scan abbrechen und Programm beenden?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return True  # Event konsumieren – Fenster bleibt offen

                # Scan stoppen und auf Thread-Ende warten
                self._closing = True
                self.scan_ctrl.stop_scan()

                thread = self.scan_ctrl.thread
                if thread is not None:
                    # Blockierend warten (max. 8s) – wir sind im GUI-Thread,
                    # daher kurz aber ausreichend für sauberes Ende
                    if not thread.wait(8000):
                        thread.terminate()
                        thread.wait(1000)

                # Fenster schließen erlauben – Spannungen werden nicht verändert
                return False

        return False   # alle anderen Events normal weiterleiten


class EmergencyController(QObject):
    """
    Zufälliges Bild aus pics/ anzeigen wenn btnEmergency gedrückt wird.
    Name der Person wird links unten ins Bild gerendert.
    Fenster schließt sich nach 5 Sekunden automatisch.
    """

    PERSONS = [
        ("davar.jpg",        "Davar"),
        ("hans.jpg",         "hans"),
        ("udo.jpg",          "Udo"),
        ("versuchsleiter.jpg", "Versuchsleiter"),
    ]

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        btn = self.w.findChild(QPushButton, "btnEmergency")
        if btn is not None:
            btn.clicked.connect(self.show_emergency)
        else:
            log.warning("btnEmergency nicht gefunden – Spaßfunktion deaktiviert.")

    @Slot()
    def show_emergency(self):
        import random
        from pathlib import Path
        from PySide6.QtGui import QPixmap, QPainter, QFont, QColor, QPen
        from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout
        from PySide6.QtCore import QTimer, Qt

        filename, name = random.choice(self.PERSONS)
        img_path = Path(__file__).parent / "pics" / filename

        pixmap = QPixmap()
        if img_path.exists():
            pixmap.load(str(img_path))
        else:
            # Fallback: graues Platzhalterbild
            pixmap = QPixmap(400, 300)
            pixmap.fill(QColor("#555555"))
            log.warning(f"Emergency-Bild nicht gefunden: {img_path}")

        # Name links unten ins Bild rendern
        painter = QPainter(pixmap)
        font = QFont("Arial", max(18, pixmap.height() // 18))
        font.setBold(True)
        painter.setFont(font)

        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(name)
        text_h = fm.height()
        margin = 14
        x = margin
        y = pixmap.height() - margin

        # Schatten für Lesbarkeit
        painter.setPen(QPen(QColor(0, 0, 0, 180)))
        for dx, dy in [(-2,-2),(2,-2),(-2,2),(2,2),(0,2),(0,-2),(-2,0),(2,0)]:
            painter.drawText(x + dx, y + dy, name)

        painter.setPen(QPen(Qt.white))
        painter.drawText(x, y, name)
        painter.end()

        # Dialog ohne Rahmen, zentriert über Hauptfenster
        dlg = QDialog(self.w, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.setWindowTitle("!")

        lbl = QLabel()
        # Bild auf max. 600px Breite skalieren, Seitenverhältnis behalten
        if pixmap.width() > 600:
            pixmap = pixmap.scaledToWidth(600, Qt.SmoothTransformation)
        lbl.setPixmap(pixmap)
        lbl.setCursor(Qt.PointingHandCursor)
        lbl.mousePressEvent = lambda _: dlg.close()

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(lbl)

        # Zentriert über Hauptfenster positionieren
        geo = self.w.geometry()
        dlg.adjustSize()
        dlg.move(
            geo.center().x() - dlg.width() // 2,
            geo.center().y() - dlg.height() // 2,
        )

        # Automatisch nach 5 s schließen
        QTimer.singleShot(5000, dlg.close)

        dlg.exec()


class ConfigController(QObject):
    """
    Verbindet AppConfig mit der GUI:
    - Beim Start: Config → Widgets (apply_to_ui)
    - Auf Knopfdruck: Widgets → Config → INI speichern (save_from_ui)
    """

    def __init__(self, window, cfg: AppConfig, scan_ctrl, controllers: list):
        super().__init__(window)
        self.w = window
        self.cfg = cfg
        self.scan_ctrl = scan_ctrl
        self.controllers = controllers   # [ion, ppa_up, ppa_down, einzellens]

        self.btn_save = self.w.findChild(QPushButton, "btnSaveConfig")
        if self.btn_save is None:
            log.warning("btnSaveConfig nicht gefunden – Config-Speichern deaktiviert.")
        else:
            self.btn_save.clicked.connect(self.save_from_ui)

        self.apply_to_ui()

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _set_spinbox(self, name: str, value: float) -> None:
        w = self.w.findChild(QDoubleSpinBox, name)
        if w is not None:
            w.setValue(value)

    def _set_spinbox_int(self, name: str, value: int) -> None:
        w = self.w.findChild(QSpinBox, name)
        if w is None:
            w = self.w.findChild(QDoubleSpinBox, name)
        if w is not None:
            w.setValue(value)

    def _set_combo(self, name: str, text: str) -> None:
        w = self.w.findChild(QComboBox, name)
        if w is not None:
            idx = w.findText(text)
            if idx >= 0:
                w.setCurrentIndex(idx)
            else:
                w.setCurrentText(text)

    def _set_lineedit(self, name: str, text: str) -> None:
        w = self.w.findChild(QLineEdit, name)
        if w is not None:
            w.setText(text)

    def _set_checkbox(self, name: str, value: bool) -> None:
        w = self.w.findChild(QCheckBox, name)
        if w is not None:
            w.setChecked(value)

    def _get_spinbox(self, name: str, fallback: float = 0.0) -> float:
        w = self.w.findChild(QDoubleSpinBox, name)
        if w is None:
            w = self.w.findChild(QSpinBox, name)
        return float(w.value()) if w is not None else fallback

    def _get_combo(self, name: str, fallback: str = "") -> str:
        w = self.w.findChild(QComboBox, name)
        return w.currentText().strip() if w is not None else fallback

    def _get_lineedit(self, name: str, fallback: str = "") -> str:
        w = self.w.findChild(QLineEdit, name)
        return w.text().strip() if w is not None else fallback

    def _get_checkbox(self, name: str, fallback: bool = False) -> bool:
        w = self.w.findChild(QCheckBox, name)
        return w.isChecked() if w is not None else fallback

    # ------------------------------------------------------------------
    # Config → UI (beim Start)
    # ------------------------------------------------------------------

    def apply_to_ui(self) -> None:
        """Überträgt alle Config-Werte in die GUI-Widgets."""

        # Keithley COM-Ports
        # COM ports are hardcoded in K6485Controller.PORT and K6517BController.PORT

        # Scan-Parameter
        self._set_spinbox("spEStart_eV",   self.cfg.getfloat("scan", "e_start",  40.0))
        self._set_spinbox("spEStop_eV",    self.cfg.getfloat("scan", "e_stop",   50.0))
        self._set_spinbox("spEStep_eV",    self.cfg.getfloat("scan", "e_step",    1.0))
        self._set_spinbox("spSettleTime_s",  self.cfg.getfloat("scan", "settle_s",         0.5))
        self._set_spinbox("spSettleTol",     self.cfg.getfloat("scan", "settle_tol_v", 1.0))
        self._set_spinbox("spSettleTimeout", self.cfg.getfloat("scan", "settle_timeout_s", 10.0))
        self._set_spinbox("spSpectrometerConstant", self.cfg.getfloat("scan", "spectrometer_constant", 1.0275))
        self._set_spinbox("spOffsetP2",             self.cfg.getfloat("scan", "offset_p2",             0.0))

        # Keithley-Messparameter
        self._set_spinbox("spNPLC",  self.cfg.getfloat("keithley", "nplc",     0.1))
        self._set_spinbox("spAvg",   self.cfg.getfloat("keithley", "averages", 1.0))
        self._set_combo("cmbMeasMode", self.cfg.get("keithley", "mode", "Single"))

        # CSV
        save_dir = self.cfg.get("csv", "save_dir", "")
        if save_dir and os.path.isdir(save_dir):
            self._set_lineedit("txtSaveDir", save_dir)
        self._set_checkbox("chkAutoSave", self.cfg.getbool("csv", "auto_save", False))

        log.info("Config auf UI angewendet.")

    # ------------------------------------------------------------------
    # UI → Config → INI speichern (auf Knopfdruck)
    # ------------------------------------------------------------------

    def save_from_ui(self) -> None:
        """Liest aktuelle Widget-Werte aus und speichert sie in der INI."""

        # Keithley COM-Ports
        # COM ports are hardcoded – not saved to config

        # Scan-Parameter
        self.cfg.set("scan", "e_start",  self._get_spinbox("spEStart_eV",    40.0))
        self.cfg.set("scan", "e_stop",   self._get_spinbox("spEStop_eV",     50.0))
        self.cfg.set("scan", "e_step",   self._get_spinbox("spEStep_eV",      1.0))
        self.cfg.set("scan", "settle_s",         self._get_spinbox("spSettleTime_s",  0.5))
        self.cfg.set("scan", "settle_tol_v",     self._get_spinbox("spSettleTol",     1.0))
        self.cfg.set("scan", "settle_timeout_s", self._get_spinbox("spSettleTimeout", 10.0))
        self.cfg.set("scan", "spectrometer_constant", self._get_spinbox("spSpectrometerConstant", 1.0275))
        self.cfg.set("scan", "offset_p2",             self._get_spinbox("spOffsetP2",             0.0))

        # Keithley-Messparameter
        self.cfg.set("keithley", "nplc",     self._get_spinbox("spNPLC",    0.1))
        self.cfg.set("keithley", "averages", self._get_spinbox("spAvg",     1.0))
        self.cfg.set("keithley", "mode",     self._get_combo("cmbMeasMode", "Single"))

        # CSV
        self.cfg.set("csv", "save_dir",  self._get_lineedit("txtSaveDir", ""))
        self.cfg.set("csv", "auto_save", self._get_checkbox("chkAutoSave", False))

        # Netzgeräte aus den psu_kwargs der Controller
        psu_sections = ["ion_psu", "ppa_up_psu", "ppa_down_psu", "einzellens_psu"]
        for ctrl, section in zip(self.controllers, psu_sections):
            if ctrl.psu_kwargs:
                for key, val in ctrl.psu_kwargs.items():
                    self.cfg.set(section, key, val)

        try:
            self.cfg.save()
            append_log(self.w, f"Konfiguration gespeichert: {self.cfg.path}", "ok")
            if hasattr(self.w, "statusbar") and self.w.statusbar:
                self.w.statusbar.showMessage(f"Config gespeichert: {self.cfg.path}", 5000)
        except Exception as e:
            QMessageBox.critical(self.w, "Config-Fehler", f"Speichern fehlgeschlagen:\n{e}")


# ---------------------------------------------------------------------------
# IonEinzellensController
# ---------------------------------------------------------------------------

class MonitorWindow(QObject):
    """
    Monitor-Fenster mit:
      - Wertetabelle: U ist, I ist, U soll, I limit für Ion-PSU und Einzellens
      - 2×2 Zeitverlaufs-Plots: Spannung und Strom beider PSUs
    """

    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self._win    = None
        self._canvas = None
        self._fig    = None
        self._ax_ion_v = self._ax_ion_i = self._ax_el_v = self._ax_el_i = None

        self._t_ion:  list[float] = []
        self._v_ion:  list[float] = []
        self._i_ion:  list[float] = []   # mA
        self._t_el:   list[float] = []
        self._v_el:   list[float] = []
        self._i_el:   list[float] = []   # mA
        self._t0: float = time.time()
        self._last: dict = {}
        self._tbl_labels: dict = {}

    def _build(self):
        from PySide6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout,
                                       QLabel, QFrame)
        self._win = QWidget()
        self._win.setWindowTitle("Monitor – Ion & Einzellens")
        self._win.resize(820, 600)
        root = QVBoxLayout(self._win)
        root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)

        # ── Wertetabelle ──────────────────────────────────────────────────────
        tbl = QFrame(); tbl.setFrameShape(QFrame.Shape.StyledPanel)
        tg = QGridLayout(tbl); tg.setSpacing(6); tg.setContentsMargins(10, 6, 10, 6)

        def _th(text):
            l = QLabel(text)
            l.setStyleSheet("font-weight: 600; font-size: 11px; color: #8b8fa8;")
            return l

        def _val(key):
            l = QLabel("—")
            l.setStyleSheet("font-size: 12px; font-family: Consolas; min-width: 80px;")
            self._tbl_labels[key] = l
            return l

        for col, txt in enumerate(["", "U ist (V)", "I ist (mA)", "U soll (V)", "I limit (mA)"]):
            tg.addWidget(_th(txt), 0, col)
        tg.addWidget(_th("Ion PSU"),    1, 0)
        tg.addWidget(_val("ion_v"),     1, 1); tg.addWidget(_val("ion_i"),     1, 2)
        tg.addWidget(_val("ion_v_set"), 1, 3); tg.addWidget(_val("ion_i_lim"), 1, 4)
        tg.addWidget(_th("Einzellens"), 2, 0)
        tg.addWidget(_val("el_v"),      2, 1); tg.addWidget(_val("el_i"),      2, 2)
        tg.addWidget(_val("el_v_set"),  2, 3); tg.addWidget(_val("el_i_lim"),  2, 4)
        root.addWidget(tbl)

        # ── 2×2 Plots ─────────────────────────────────────────────────────────
        self._fig = Figure(tight_layout=True)
        self._fig.subplots_adjust(hspace=0.45, left=0.10, right=0.97, top=0.93, bottom=0.08)
        self._ax_ion_v = self._fig.add_subplot(221)
        self._ax_ion_i = self._fig.add_subplot(222)
        self._ax_el_v  = self._fig.add_subplot(223)
        self._ax_el_i  = self._fig.add_subplot(224)
        for ax, title, ylabel in [
            (self._ax_ion_v, "Ion – Spannung",         "U (V)"),
            (self._ax_ion_i, "Ion – Strom",             "I (mA)"),
            (self._ax_el_v,  "Einzellens – Spannung",  "U (V)"),
            (self._ax_el_i,  "Einzellens – Strom",     "I (mA)"),
        ]:
            ax.set_title(title, fontsize=9, pad=3)
            ax.set_ylabel(ylabel, fontsize=8)
            ax.set_xlabel("Zeit (s)", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.grid(True, linestyle="--", alpha=0.4)
        self._canvas = FigureCanvas(self._fig)
        root.addWidget(self._canvas)
        root.setStretch(root.count() - 1, 1)
        root.addWidget(NavigationToolbar(self._canvas, self._win))

    def show(self):
        if self._win is None:
            self._build()
        self._win.show(); self._win.raise_(); self._win.activateWindow()

    def reset(self):
        for lst in (self._t_ion, self._v_ion, self._i_ion,
                    self._t_el,  self._v_el,  self._i_el):
            lst.clear()
        self._t0 = time.time()

    # Hauptschnittstelle: wird von _poll_actuals aufgerufen
    def update(self, *, ion_v, ion_i, ion_v_set, ion_i_lim,
                       el_v,  el_i,  el_v_set,  el_i_lim):
        t = time.time() - self._t0
        if math.isfinite(ion_v): self._t_ion.append(t); self._v_ion.append(ion_v)
        if math.isfinite(ion_i): self._i_ion.append(ion_i * 1e3)
        if math.isfinite(el_v):  self._t_el.append(t);  self._v_el.append(el_v)
        if math.isfinite(el_i):  self._i_el.append(el_i * 1e3)
        self._last = dict(
            ion_v=ion_v,      ion_i=ion_i*1e3,
            ion_v_set=ion_v_set, ion_i_lim=ion_i_lim*1e3,
            el_v=el_v,        el_i=el_i*1e3,
            el_v_set=el_v_set,   el_i_lim=el_i_lim*1e3,
        )
        self._refresh_table()
        self._redraw()

    # Rückwärtskompatibilität (alte Aufrufer)
    def add_ion(self, v: float): pass
    def add_el(self,  v: float): pass

    def _refresh_table(self):
        if not self._tbl_labels:
            return
        d = self._last
        def fv(k):  v = d.get(k, float("nan")); return f"{v:.1f}"  if math.isfinite(v) else "—"
        def fma(k): v = d.get(k, float("nan")); return f"{v:.3f}" if math.isfinite(v) else "—"
        for k, fn in [("ion_v",fv),("ion_i",fma),("ion_v_set",fv),("ion_i_lim",fma),
                      ("el_v", fv),("el_i", fma),("el_v_set", fv),("el_i_lim", fma)]:
            lbl = self._tbl_labels.get(k)
            if lbl: lbl.setText(fn(k))

    def _redraw(self):
        if self._win is None or not self._win.isVisible() or self._ax_ion_v is None:
            return
        for ax, xs, ys, col, title, ylabel in [
            (self._ax_ion_v, self._t_ion, self._v_ion, "#4f8ef7", "Ion – Spannung",        "U (V)"),
            (self._ax_ion_i, self._t_ion, self._i_ion, "#f7a14f", "Ion – Strom",            "I (mA)"),
            (self._ax_el_v,  self._t_el,  self._v_el,  "#00d4aa", "Einzellens – Spannung", "U (V)"),
            (self._ax_el_i,  self._t_el,  self._i_el,  "#c77dff", "Einzellens – Strom",    "I (mA)"),
        ]:
            ax.clear()
            ax.set_title(title, fontsize=9, pad=3); ax.set_ylabel(ylabel, fontsize=8)
            ax.set_xlabel("Zeit (s)", fontsize=8);  ax.tick_params(labelsize=7)
            ax.grid(True, linestyle="--", alpha=0.4)
            if xs and ys and len(xs) == len(ys):
                ax.plot(xs, ys, "-o", color=col, markersize=2, linewidth=1.2)
        try:
            self._canvas.draw_idle()
        except Exception:
            pass


class IonEinzellensController(QObject):
    """
    Steuert Ion-PSU und Einzellens-PSU:
    - Spannungsvorgabe per SpinBox + Set-Button
    - Istwert-Anzeige per Label (polling via QTimer)
    - Zeitverlaufs-Plot (separates Fenster)
    - Alle Aktionen sind best-effort: wenn PSU nicht verbunden → Warnung im Log
    """

    def __init__(self, window, ion_ctrl: "DeviceController",
                 einzellens_ctrl: "DeviceController"):
        super().__init__(window)
        self.w = window
        self.ion_ctrl = ion_ctrl
        self.einzellens_ctrl = einzellens_ctrl

        # --- Ion Widgets ---
        self.spIonVoltage   = self.w.findChild(QDoubleSpinBox, "spIonVoltage")
        self.btnIonSetV     = self.w.findChild(QPushButton,    "btnIonSetV")
        self.lcdIonVActual  = self.w.findChild(QLCDNumber,     "lcdIonVActual")

        # --- Einzellens Widgets ---
        self.spElVoltage    = self.w.findChild(QDoubleSpinBox, "spElVoltage")
        self.btnElSetV      = self.w.findChild(QPushButton,    "btnElSetV")
        self.lcdElVActual   = self.w.findChild(QLCDNumber,     "lcdElVActual")

        # --- Monitor-Fenster Button ---
        self.btnMonitor     = self.w.findChild(QPushButton,    "btnShowMonitor")

        # --- Monitor-Fenster ---
        self.monitor = MonitorWindow(window)

        # LCD-Konfiguration: schwarzer Hintergrund, gruene Segmente
        # QPalette ist der zuverlaessigste Weg fuer QLCDNumber-Farben.
        from PySide6.QtGui import QPalette, QColor
        for lcd in (self.lcdIonVActual, self.lcdElVActual):
            if lcd is not None:
                lcd.setDigitCount(7)
                lcd.setSmallDecimalPoint(True)
                lcd.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
                # Hintergrund schwarz, Segmentfarbe gruen
                pal = lcd.palette()
                pal.setColor(QPalette.ColorRole.Window,     QColor("#0d0d0d"))
                pal.setColor(QPalette.ColorRole.WindowText, QColor("#00e040"))
                pal.setColor(QPalette.ColorRole.Light,      QColor("#001a00"))  # inaktive Segmente
                lcd.setPalette(pal)
                lcd.setAutoFillBackground(True)
                # Mindestgroesse damit die Anzeige gut lesbar ist
                lcd.setMinimumHeight(30)
                lcd.display(0)

        # SpinBox-Limits
        if self.spIonVoltage is not None:
            self.spIonVoltage.setRange(0.0, 3500.0)
            self.spIonVoltage.setDecimals(1)
            self.spIonVoltage.setSuffix(" V")
        if self.spElVoltage is not None:
            self.spElVoltage.setRange(0.0, 6500.0)
            self.spElVoltage.setDecimals(1)
            self.spElVoltage.setSuffix(" V")

        # Signals
        if self.btnIonSetV is not None:
            self.btnIonSetV.clicked.connect(self.on_set_ion_voltage)
        if self.btnElSetV is not None:
            self.btnElSetV.clicked.connect(self.on_set_el_voltage)
        # Connect spinbox Enter directly – btn.click() is blocked on hidden buttons
        if self.spIonVoltage is not None:
            self.spIonVoltage.editingFinished.connect(self.on_set_ion_voltage)
        if self.spElVoltage is not None:
            self.spElVoltage.editingFinished.connect(self.on_set_el_voltage)
        if self.btnMonitor is not None:
            self.btnMonitor.clicked.connect(self.monitor.show)

        # Polling-Timer (Istwerte lesen alle 2 s)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2000)
        self._poll_timer.timeout.connect(self._poll_actuals)
        self._poll_timer.start()

        if self.spIonVoltage is None:
            log.warning("spIonVoltage nicht gefunden – Ion-Steuerung eingeschränkt.")
        if self.spElVoltage is None:
            log.warning("spElVoltage nicht gefunden – Einzellens-Steuerung eingeschränkt.")

    @Slot()
    def on_set_ion_voltage(self):
        psu = self.ion_ctrl.psu
        if psu is None:
            append_log(self.w, "Ion PSU nicht verbunden – Spannungsvorgabe ignoriert.", "warn")
            return
        if self.spIonVoltage is None:
            return
        v = self.spIonVoltage.value()
        try:
            # Reihenfolge laut FuG Probus Manual:
            # 1) Stromlimit setzen  2) Sollspannung setzen  3) Ausgang freigeben (>BON 1)
            psu.set_current_limit(psu.i_max)
            psu.set_voltage(v)
            psu.output(True)
            append_log(self.w,
                f"Ion PSU: Stromlimit {psu.i_max*1000:.0f} mA, "
                f"Spannung auf {v:.1f} V gesetzt, Ausgang freigegeben.", "ok")
        except Exception as e:
            append_log(self.w, f"Ion PSU Fehler beim Setzen: {e}", "error")

    @Slot()
    def on_set_el_voltage(self):
        psu = self.einzellens_ctrl.psu
        if psu is None:
            append_log(self.w, "Einzellens PSU nicht verbunden – Spannungsvorgabe ignoriert.", "warn")
            return
        if self.spElVoltage is None:
            return
        v = self.spElVoltage.value()
        try:
            # Reihenfolge laut FuG Probus Manual:
            # 1) Stromlimit setzen  2) Sollspannung setzen  3) Ausgang freigeben (>BON 1)
            psu.set_current_limit(psu.i_max)
            psu.set_voltage(v)
            psu.output(True)
            append_log(self.w,
                f"Einzellens PSU: Stromlimit {psu.i_max*1000:.0f} mA, "
                f"Spannung auf {v:.1f} V gesetzt, Ausgang freigegeben.", "ok")
        except Exception as e:
            append_log(self.w, f"Einzellens PSU Fehler beim Setzen: {e}", "error")

    @Slot()
    def _poll_actuals(self):
        nan = float("nan")

        # ── Ion PSU ───────────────────────────────────────────────────────────
        psu_ion = self.ion_ctrl.psu
        ion_v = ion_i = nan
        ion_v_set = float(self.spIonVoltage.value()) if self.spIonVoltage else nan
        ion_i_lim = psu_ion.i_max if psu_ion is not None else nan

        if psu_ion is not None:
            try:
                ion_v = psu_ion.read_voltage()
                if self.lcdIonVActual is not None:
                    self.lcdIonVActual.display(round(ion_v, 1))
            except Exception:
                if self.lcdIonVActual is not None:
                    self.lcdIonVActual.display(0)
            try:
                ion_i = psu_ion.read_current()
            except Exception:
                pass
        else:
            if self.lcdIonVActual is not None:
                self.lcdIonVActual.display(0)

        # ── Einzellens PSU ────────────────────────────────────────────────────
        psu_el = self.einzellens_ctrl.psu
        el_v = el_i = nan
        el_v_set = float(self.spElVoltage.value()) if self.spElVoltage else nan
        el_i_lim = psu_el.i_max if psu_el is not None else nan

        if psu_el is not None:
            try:
                el_v = psu_el.read_voltage()
                if self.lcdElVActual is not None:
                    self.lcdElVActual.display(round(el_v, 1))
            except Exception:
                if self.lcdElVActual is not None:
                    self.lcdElVActual.display(0)
            try:
                el_i = psu_el.read_current()
            except Exception:
                pass
        else:
            if self.lcdElVActual is not None:
                self.lcdElVActual.display(0)

        # ── Monitor-Fenster aktualisieren (Tabelle + Plots) ───────────────────
        self.monitor.update(
            ion_v=ion_v, ion_i=ion_i,
            ion_v_set=ion_v_set, ion_i_lim=ion_i_lim,
            el_v=el_v,   el_i=el_i,
            el_v_set=el_v_set,   el_i_lim=el_i_lim,
        )


# ---------------------------------------------------------------------------
# SafetyController – Alle Spannungen abschalten (best-effort)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# TooltipController – setzt Hover-Tooltips auf alle relevanten Widgets
# ---------------------------------------------------------------------------

class TooltipController(QObject):
    """
    Setzt beim Start setToolTip() auf alle bekannten Widgets.
    Widgets die nicht gefunden werden, werden still uebersprungen.
    Kein Qt-Designer-Eingriff noetig.
    """

    # (widget_name, tooltip_text)
    _TIPS = [
        # --- Scan-Parameter ---
        ("spEStart_eV",          "Startenergie des Scans in eV.\nDer Scan laeuft von E_start bis E_stop in Schritten von E_step."),
        ("spEStop_eV",           "Stoppenergie des Scans in eV.\nKann kleiner als E_start sein (Rueckwaertsscan)."),
        ("spEStep_eV",           "Schrittweite des Energiescans in eV.\nMuss > 0 sein. Kleinere Schritte = mehr Punkte, laengerer Scan."),
        ("spEDecel_eV",          "Abbremsspannung E_decel in eV (nur PPA-Modus 2/3).\nWird direkt an PPA_unten angelegt.\nIm Modus 1 wird dieser Wert ignoriert (fest 0 V)."),
        ("spSettleTime_s",       "Zusaetzliche Wartezeit in Sekunden nach dem Setzen der Spannung,\nbevor die Strommessung startet.\nErhoehen wenn das Signal nach dem Spannungssprung noch schwingt."),
        ("spSettleTol",          "Toleranz fuer den Soll/Ist-Vergleich der PSU-Spannung in Volt.\nDer Scan wartet bis |U_ist - U_soll| < Toleranz.\nTypisch: 0.5-2 V je nach PSU-Ansprechgeschwindigkeit."),
        ("spSettleTimeout",      "Maximale Wartezeit in Sekunden fuer den Soll/Ist-Vergleich.\nNach Ablauf: Warnung im Log, Scan laeuft trotzdem weiter."),
        ("spSpectrometerConstant","Spektrometerkonstante k (dimensionslos).\nU_PPA_oben = k * (E - E_decel) + P2 + E_decel.\nTypischer Wert: ~1.0275 (aus Geraetekalibrierung)."),
        ("spOffsetP2",           "Spannungsoffset P2 in Volt (Gleichung 4.27).\nKorrekturfaktor fuer das konstante ICS-Potential.\nNormalerweise 0 V."),
        ("spNPLC",               "Number of Power Line Cycles fuer die Keithley-Messung.\nt = NPLC / 50 Hz. 0.01 = schnell (0.2 ms), 10 = rauscharm (200 ms)."),
        ("spAvg",                "Anzahl der Einzelmessungen pro Energiepunkt fuer Mittelwertbildung.\n1 = Single-Shot. >1 = Mittelwert + Standardabweichung."),
        ("cmbMeasMode",          "Messmodus:\nSingle: eine Messung pro Energiepunkt.\nAverage: N Messungen, Mittelwert und Stdabw werden berechnet."),
        ("cmbDetector",          "Auswahl des Detektors.\nKeithley 6485: Picoammeter.\nKeithley 6517B: Elektrometer (hoehere Empfindlichkeit)."),
        ("cmbRange",             "Messbereich des Keithley. Nur aktiv wenn Auto-Range deaktiviert.\nKleinerer Bereich = hoehere Aufloesung, aber Uebersteuerungsgefahr."),
        ("chkAutoRange",         "Auto-Range: Messgeraet waehlt optimalen Messbereich automatisch.\nEmpfohlen fuer unbekannte Signalstaerken."),
        ("cmbPPAMode",           "PPA-Betriebsmodus:\nModus 1: E_decel = 0 V.\nModus 2: E_decel aus Eingabefeld.\nModus 3: Pass-Energy-Modus."),
        ("spLoopCount",          "Anzahl der Scan-Loops (Wiederholungen).\n0 = unendlich, bis manuell gestoppt.\nMesswerte werden ueber Loops gemittelt."),
        ("chkBidirectional",     "Bidirektionaler Scan: Vorwaerts- und Rueckwaerts-Scan abwechselnd.\nErkennt Hysterese-Effekte."),
        # --- Ion PSU ---
        ("spIonVoltage",         "Sollspannung fuer die Ionenenergie-PSU in Volt.\nMax: 3500 V, Stromlimit: 40 mA."),
        ("btnIonSetV",           "Setzt Stromlimit (40 mA) und Sollspannung, gibt Ausgang frei.\nSequenz: >S1 0.04  >S0 {U}  >BON 1"),
        ("lcdIonVActual",        "Aktueller Istwert der Ionenenergie-PSU (>M0?).\nWird alle 2 Sekunden automatisch abgefragt."),
        # --- Einzellens PSU ---
        ("spElVoltage",          "Sollspannung fuer die Einzellens-PSU in Volt.\nMax: 6500 V, Stromlimit: 20 mA."),
        ("btnElSetV",            "Setzt Stromlimit (20 mA) und Sollspannung, gibt Ausgang frei.\nSequenz: >S1 0.02  >S0 {U}  >BON 1"),
        ("lcdElVActual",         "Aktueller Istwert der Einzellens-PSU (>M0?).\nWird alle 2 Sekunden automatisch abgefragt."),
        # --- Monitor / Safety ---
        ("btnShowMonitor",       "Oeffnet das Zeitverlaufs-Fenster mit Istwerten\nvon Ionenenergie-PSU und Einzellens-PSU."),
        ("btnAllOff",            "SICHERHEITSABSCHALTUNG: Alle verbundenen PSUs werden sofort\nauf 0 V gesetzt und Ausgang abgeschaltet (>BON 0)."),
        # --- CSV / Speichern ---
        ("btnSaveCSV",           "Manuell akkumulierte Daten als CSV speichern.\nAlternative zur automatischen akkumulierten CSV."),
        ("chkAutoSave",          "Nicht mehr verwendet – Rohdaten und akkumulierte CSV\nwerden automatisch nach jedem Loop gespeichert."),
        ("txtSaveDir",           "Zielverzeichnis fuer CSV-Dateien."),
        ("btnBrowseSave",        "Ordner-Dialog oeffnen fuer CSV-Speicherverzeichnis."),
        ("btnSaveConfig",        "Aktuelle Einstellungen in Ref4EP.ini speichern.\nWerden beim naechsten Start automatisch geladen."),
        # --- Scan-Steuerung ---
        ("leBinWidth",
         "Aktuelle Bin-Breite fuer das Istwert-Binning.\n""Jeder PSU-Istwert wird dem naechsten Bin-Zentrum zugeordnet\n""wenn |Istwert - Bin-Zentrum| <= e_step/2.\n""Punkte ausserhalb werden verworfen und im Log gemeldet."),
        ("btnScanStart",         "Scan starten: PSUs aktivieren, Keithley konfigurieren,\nEnergiepunkte abfahren und Strom messen."),
        ("btnScanStop",          "Scan sofort abbrechen. Spannungen bleiben unveraendert."),
        ("btnLoopStop",          "Aktuellen Loop zu Ende laufen, dann sauber stoppen.\nNaechster Loop wird nicht gestartet."),
    ]

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self._apply()

    def _apply(self) -> None:
        from PySide6.QtWidgets import (QWidget, QDoubleSpinBox, QSpinBox,
            QPushButton, QLabel, QLineEdit, QCheckBox, QComboBox, QFrame)
        # findChild(QWidget) findet in PySide6 keine Subklassen – daher alle
        # relevanten Typen explizit durchprobieren.
        _types = (QDoubleSpinBox, QSpinBox, QPushButton, QLabel,
                  QLineEdit, QCheckBox, QComboBox, QFrame, QWidget)
        applied = 0
        for name, tip in self._TIPS:
            widget = None
            for wtype in _types:
                widget = self.w.findChild(wtype, name)
                if widget is not None:
                    break
            if widget is not None:
                widget.setToolTip(tip)
                applied += 1
            else:
                log.debug("Tooltip: Widget '%s' nicht gefunden.", name)
        log.info("Tooltips gesetzt: %d von %d Widgets gefunden.", applied, len(self._TIPS))


class SafetyController(QObject):
    """
    Drücken von btnAllOff → alle verbundenen PSUs: set_voltage(0) + output(False).
    Fehler werden geloggt, aber nie propagiert (best-effort).
    """

    def __init__(self, window, controllers: list, einzellens_ctrl: "DeviceController"):
        super().__init__(window)
        self.w = window
        self.controllers = controllers        # [ion, ppa_up, ppa_down]
        self.einzellens_ctrl = einzellens_ctrl

        self.btn = self.w.findChild(QPushButton, "btnAllOff")
        if self.btn is not None:
            self.btn.clicked.connect(self.all_off)
            # Auffällige Buttonfarbe
            self.btn.setStyleSheet(
                "QPushButton { background-color: #c0392b; color: white; "
                "font-weight: bold; border-radius: 4px; padding: 4px 10px; }"
                "QPushButton:hover { background-color: #e74c3c; }"
                "QPushButton:pressed { background-color: #922b21; }"
            )
        else:
            log.warning("btnAllOff nicht gefunden – Safety-Abschaltung deaktiviert.")

    @Slot()
    def all_off(self):
        reply = QMessageBox.warning(
            self.w, "Alle Spannungen abschalten",
            "Sollen ALLE verbundenen PSUs sofort auf 0 V gesetzt und abgeschaltet werden?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        all_ctrls = list(self.controllers) + [self.einzellens_ctrl]
        errors = []
        for ctrl in all_ctrls:
            psu = getattr(ctrl, "psu", None)
            name = getattr(ctrl, "status_prefix", str(ctrl))
            if psu is None:
                continue
            try:
                psu.set_voltage(0.0)
            except Exception as e:
                errors.append(f"{name}: set_voltage(0) → {e}")
            try:
                psu.output(False)
            except Exception as e:
                errors.append(f"{name}: output(False) → {e}")
            append_log(self.w, f"Safety: {name} → 0 V, Ausgang aus.", "warn")

        if errors:
            for err in errors:
                append_log(self.w, f"Safety-Fehler: {err}", "error")
            append_log(self.w, "Safety abgeschlossen (mit Fehlern – s. Log).", "warn")
        else:
            append_log(self.w, "Safety: Alle PSUs abgeschaltet.", "ok")



class FugPSU:
    def __init__(
        self,
        *,
        mode: str,                  # "serial" | "tcp" | "visa"
        port: str | None = None,    # serial: "COM12"
        baudrate: int = 115200,
        host: str | None = None,    # tcp: "192.168.1.93"
        tcp_port: int = 2101,
        visa_resource: str | None = None,  # visa: "GPIB0::9::INSTR"
        timeout: float = 0.5,
        addr: int | None = None,
        term: str = "\r",           # MCP14 uses CR only
        v_max: float = 6500.0,      # voltage limit (from INI per device)
        i_max: float = 0.040,       # current limit (from INI per device)
    ):
        if mode not in ("serial", "tcp", "visa"):
            raise ValueError("mode must be 'serial', 'tcp', or 'visa'")

        self.mode = mode
        self.port = port
        self.baudrate = baudrate
        self.host = host
        self.tcp_port = tcp_port
        self.visa_resource = visa_resource
        self.timeout = timeout
        self.addr = addr
        self.term = term
        self.v_max = float(v_max)
        self.i_max = float(i_max)

        self.ser = None
        self.sock = None
        self.rm = None
        self.inst = None
        self._rxbuf = b""
        self._proto: str = "mcp14"   # detected in connect(): "mcp14" | "probus"
        self.read_only: bool = False  # True if PSU only supports readback (no set/output)

    def connect(self):
        if self.mode == "serial":
            if not self.port:
                raise ValueError("port is required for mode='serial'")
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            try:
                self.ser.reset_input_buffer()
            except Exception:
                pass

        elif self.mode == "tcp":
            if not self.host:
                raise ValueError("host is required for mode='tcp'")

            last_exc = None
            for attempt in range(5):
                try:
                    self.sock = socket.create_connection((self.host, self.tcp_port), timeout=self.timeout)
                    self.sock.settimeout(self.timeout)
                    self._rxbuf = b""
                    break
                except (TimeoutError, OSError) as e:
                    last_exc = e
                    time.sleep(0.2 * (attempt + 1))
            else:
                raise last_exc

        else:  # visa
            if not self.visa_resource:
                raise ValueError("visa_resource is required for mode='visa'")
            self.rm = pyvisa.ResourceManager()
            self.inst = self.rm.open_resource(self.visa_resource)
            self.inst.timeout = int(self.timeout * 1000)

        self._detect_protocol()

    def _detect_protocol(self):
        """Auto-detect protocol (MCP14 or Probus-V) and write capability.
        Sets self._proto ('mcp14' | 'probus') and self.read_only (bool)."""

        # --- try MCP14: N0\r ---
        try:
            self._flush_rx()
            self._write_raw_term("N0", "\r")
            ans = self._readline()
            self._parse_fug_value(ans)
            self._proto = "mcp14"
            log.info("FugPSU protocol detected: MCP14 (N0/U/I/F). Response: %r", ans)
            self.read_only = False
            return
        except Exception as e:
            log.debug("FugPSU MCP14 probe failed: %s", e)

        # --- try Probus-V with \r ---
        probus_term = None
        for term in ("\r", "\r\n"):
            try:
                self._flush_rx()
                self._write_raw_term(">M0?", term)
                ans = self._readline()
                self._parse_fug_value(ans)
                probus_term = term
                log.info("FugPSU protocol detected: Probus-V (term=%r). Response: %r", term, ans)
                break
            except Exception as e:
                log.debug("FugPSU Probus-V probe (term=%r) failed: %s", term, e)

        if probus_term is not None:
            self._proto = "probus"
            self.term   = probus_term
            self.read_only = False
            log.info("FugPSU Probus-V detected (term=%r) – write commands available.", probus_term)
            return

        # --- neither worked ---
        log.warning(
            "FugPSU: could not auto-detect protocol – defaulting to MCP14. "
            "read_voltage() may return NaN."
        )
        self._proto = "mcp14"
        self.read_only = True

    def _write_raw_term(self, cmd: str, term: str):
        """Send cmd with an explicit terminator, bypassing self.term."""
        msg = (cmd + term).encode("ascii", errors="replace")
        if self.mode == "serial":
            self.ser.write(msg); self.ser.flush()
        elif self.mode == "tcp":
            self.sock.sendall(msg)
        else:
            self.inst.write_raw(msg)

    def close(self):
        if self.ser:
            try: self.ser.close()
            finally: self.ser = None
        if self.sock:
            try: self.sock.close()
            finally: self.sock = None
        if self.inst:
            try: self.inst.close()
            finally: self.inst = None
        if self.rm:
            try: self.rm.close()
            finally: self.rm = None

    def _prefix(self) -> str:
        return f"#{self.addr}" if self.addr is not None else ""

    def _write(self, cmd: str):
        msg = (self._prefix() + cmd + self.term)

        if self.mode == "serial":
            self.ser.write(msg.encode("ascii", errors="replace"))
            self.ser.flush()

        elif self.mode == "tcp":
            self.sock.sendall(msg.encode("ascii", errors="replace"))

        else:  # visa (GPIB)
            # For VISA, do not blindly append terminator if write_termination is already set.
            # Wir senden hier exakt msg, inkl. term. (funktioniert i.d.R. stabil)
            self.inst.write_raw(msg.encode("ascii", errors="replace"))

    def _readline(self) -> str:
        if self.mode == "serial":
            return self.ser.readline().decode("ascii", errors="ignore").strip()

        if self.mode == "tcp":
            end = time.time() + self.timeout
            while time.time() < end:
                if b"\n" in self._rxbuf:
                    line, self._rxbuf = self._rxbuf.split(b"\n", 1)
                    return line.decode("ascii", errors="ignore").strip()
                try:
                    chunk = self.sock.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    return ""
                self._rxbuf += chunk
            return ""

        # visa (GPIB): read_raw ist am robustesten, dann bis Terminator splitten
        try:
            raw = self.inst.read_raw()
        except Exception:
            return ""
        return raw.decode("ascii", errors="ignore").strip()

    def _flush_rx(self):
        """Discard any bytes already in the receive buffer (stale echoes)."""
        if self.mode == "serial" and self.ser:
            self.ser.reset_input_buffer()
        elif self.mode == "tcp":
            self._rxbuf = b""
        # VISA: no equivalent flush needed – read_raw blocks until new data

    def _query(self, cmd: str, timeout_s: float = 0.8) -> str:
        self._flush_rx()
        self._write(cmd)

        end = time.time() + timeout_s
        last = ""
        while time.time() < end:
            line = self._readline()
            if not line:
                continue
            last = line
            return line

        if last:
            return last
        raise TimeoutError(cmd)

    def idn(self) -> str:
        """Return device identification string.
        All FuG devices (Probus-V and MCP14) respond to *IDN?.
        Falls back to connection info + limits if no response."""
        try:
            resp = self._query("*IDN?")
            if resp and resp.strip():
                return f"{resp.strip()} – {self.v_max:.4g} V / {self.i_max*1000:.4g} mA"
        except Exception:
            pass
        # Fallback
        if self.mode == "tcp":
            conn = f"{self.host}:{self.tcp_port}"
        elif self.mode == "serial":
            conn = self.port
        else:
            conn = self.visa_resource
        return f"FuG @ {conn} – {self.v_max:.4g} V / {self.i_max*1000:.4g} mA"

    @staticmethod
    def _parse_fug_value(ans: str) -> float:
        """Parse both MCP14 ('+3.58E-02VN') and Probus-V ('#1 >M0:1.0E+1') responses."""
        s = ans.strip()
        if ":" in s:
            # Probus-V: value is after last ':'
            s = s.split(":")[-1].strip()
        # Strip trailing non-numeric chars (MCP14 unit suffix e.g. 'VN', 'AN')
        i = len(s)
        while i > 0 and not (s[i-1].isdigit() or s[i-1] in '+-'):
            i -= 1
        return float(s[:i])

    def _cmd_write(self, mcp14: str, probus: str):
        """Send a fire-and-forget command, read and discard the response (E0 = ACK)."""
        if self._proto == "mcp14":
            cmd, term = mcp14, "\r"
        else:
            cmd, term = probus, self.term
        self._write_raw_term(cmd, term)
        self._readline()   # discard E0 ACK or echo

    def _cmd_query(self, mcp14: str, probus: str) -> str:
        """Send a query command and return the response string."""
        if self._proto == "mcp14":
            cmd, term = mcp14, "\r"
        else:
            cmd, term = probus, self.term
        self._flush_rx()
        self._write_raw_term(cmd, term)
        end = time.time() + self.timeout
        while time.time() < end:
            line = self._readline()
            if line:
                return line
        raise TimeoutError(f"No response to '{cmd}'")

    def set_voltage(self, value: float):
        if not (0.0 <= value <= self.v_max):
            raise ValueError(
                f"Voltage {value:.4g} V outside safe range "
                f"[0, {self.v_max:.4g} V] – command aborted."
            )
        if self._proto == "mcp14":
            self._cmd_write(f"U{value:.4f}", "")
        else:
            self._cmd_write("", f">S0 {value:.6g}")

    def set_current_limit(self, value: float):
        if not (0.0 <= value <= self.i_max):
            raise ValueError(
                f"Current limit {value:.4g} A outside safe range "
                f"[0, {self.i_max:.4g} A] – command aborted."
            )
        if self._proto == "mcp14":
            self._cmd_write(f"I{value:.4f}", "")
        else:
            self._cmd_write("", f">S1 {value:.6g}")

    def output(self, enable: bool):
        if self._proto == "mcp14":
            self._cmd_write("F1" if enable else "F0", "")
        else:
            self._cmd_write("", ">BON 1" if enable else ">BON 0")

    def read_voltage(self) -> float:
        ans = self._cmd_query("N0", ">M0?")
        return self._parse_fug_value(ans)

    def read_current(self) -> float:
        ans = self._cmd_query("N1", ">M1?")
        return self._parse_fug_value(ans)



###############################################################################
###############################################################################
    
def scan_fug_devices(baudrates=(115200, 230400), timeout=0.5):
    results = []
    ports = serial.tools.list_ports.comports()
    for portinfo in ports:
        port = portinfo.device

        for br in baudrates:
            try:
                with serial.Serial(port, baudrate=br, timeout=timeout) as ser:
                    ser.reset_input_buffer()

                    # Terminator sicherstellen
                    ser.write(b"Y0\r\n")
                    time.sleep(0.05)
                    ser.reset_input_buffer()

                    # IDN Anfrage
                    ser.write(b"*IDN?\r\n")
                    ser.flush()

                    time.sleep(0.1)
                    reply = ser.readline().decode(errors="ignore").strip()

                    if reply:
                        results.append({
                            "port": port,
                            "baudrate": br,
                            "reply": reply
                        })
            except Exception:
                pass
    return results

def ramp_voltage(psu, v_start=30.0, v_stop=40.0, v_step=1.0, wait_s=0.5, i_max_A=0.006):
    # Stromlimit auf Maximum setzen
    psu.set_current_limit(i_max_A)

    # (optional, aber sinnvoll) Ausgang an
    psu.output(True)

    # Rampe fahren
    v = v_start
    # inkl. Endwert
    n_steps = int(round((v_stop - v_start) / v_step))
    for k in range(n_steps + 1):
        v = v_start + k * v_step
        psu.set_voltage(v)
        time.sleep(wait_s)

def print_banner() -> None:
    init()

    GREEN = "\033[92m"
    CYAN = "\033[96m"
    RESET = "\033[0m"

    banner = figlet_format("Ref4EP control", font="slant")

    subtitle = """
Version 4.0
JLU Giessen – IPI
"""

    print(GREEN + banner + RESET)
    print(CYAN + subtitle + RESET)
    print("-" * 80)

def clear_console():
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")
        
def clear_console2():
    # Robust: cls/clear
    os.system("cls" if platform.system() == "Windows" else "clear")

def probe_port(port="COM16", baud=115200, term="\r\n"):
    with serial.Serial(port, baudrate=baud, timeout=0.3) as ser:
        try:
            ser.reset_input_buffer()
        except Exception:
            pass

        def tx(cmd):
            ser.write((cmd + term).encode("ascii", errors="replace"))
            ser.flush()

        def rx_window(t=0.8):
            t0 = time.time()
            lines = []
            while time.time() - t0 < t:
                raw = ser.readline()
                if raw:
                    lines.append(raw)
            return lines

        # 1) Terminator setzen (FuG Probus)
        tx("Y0")
        time.sleep(0.05)
        try:
            ser.reset_input_buffer()
        except Exception:
            pass

        # 2) IDN?
        tx("*IDN?")
        lines = rx_window(1.0)

        print(f"--- {port} @ {baud} ---")
        if not lines:
            print("NO RESPONSE")
        else:
            for r in lines:
                print(repr(r), "->", r.decode(errors="ignore").strip())

def set_led(frame: QFrame, color: str, size_px: int = 16):
    r = size_px // 2
    frame.setStyleSheet(f"""
        background-color: {color};
        border-radius: {r}px;
        border: 1px solid black;
    """)
 
def myjob():
    ion = ppa_up = ppa_low = einzel = None
    try:
        ion = FugPSU(mode="tcp", host="192.168.1.93", tcp_port=2101, timeout=2.0)
        ion.connect()
        print("ion energy: ", ion.idn())

        ppa_up = FugPSU(mode="visa", visa_resource="GPIB0::9::INSTR", timeout=2.0)
        ppa_up.connect()
        print("PPA upper plate: ", ppa_up.idn())

        ppa_low = FugPSU(mode="serial", port="COM16", baudrate=9600, timeout=1.0)
        ppa_low.connect()
        print("PPA lower plate: ", ppa_low.idn())

        time.sleep(0.2)  # kleine Pause hilft manchen Controllern

        einzel = FugPSU(mode="tcp", host="192.168.1.91", tcp_port=2101, timeout=2.0)
        einzel.connect()
        print("einzel lens: ", einzel.idn())
        
        #ramp_voltage(ppa_up)
        #ppa_up.close()
        

    finally:
        for dev in (einzel, ppa_low, ppa_up, ion):
            if dev:
                dev.close()
   


    







# =============================================================================
# ScanProfileManager – benannte Scan-Profile speichern/laden
# =============================================================================

class ScanProfileManager(QObject):
    """
    Speichert und lädt benannte Scan-Profile (Energiebereich + Messparameter)
    über QSettings. Widgets: cmbScanProfiles, btnProfileLoad,
    btnProfileSave, btnProfileDelete.
    """
    _KEY_PREFIX = "scan_profiles"

    def __init__(self, window, params_ctrl):
        super().__init__(window)
        self.w      = window
        self.params = params_ctrl
        self._settings = QSettings("JLU-IPI", "Ref4EP")

        self._cmb      = self.w.findChild(QComboBox,   "cmbScanProfiles")
        self._btn_load = self.w.findChild(QPushButton,  "btnProfileLoad")
        self._btn_save = self.w.findChild(QPushButton,  "btnProfileSave")
        self._btn_del  = self.w.findChild(QPushButton,  "btnProfileDelete")

        if self._cmb is None:
            log.warning("cmbScanProfiles nicht gefunden – Profile deaktiviert.")
            return

        self._btn_load.clicked.connect(self._load_profile)
        self._btn_save.clicked.connect(self._save_profile)
        self._btn_del.clicked.connect(self._delete_profile)
        self._refresh_combo()

    def _profile_names(self) -> list[str]:
        self._settings.beginGroup(self._KEY_PREFIX)
        names = self._settings.childGroups()
        self._settings.endGroup()
        return sorted(names)

    def _refresh_combo(self):
        self._cmb.blockSignals(True)
        cur = self._cmb.currentText()
        self._cmb.clear()
        for n in self._profile_names():
            self._cmb.addItem(n)
        idx = self._cmb.findText(cur)
        if idx >= 0:
            self._cmb.setCurrentIndex(idx)
        has = self._cmb.count() > 0
        self._btn_load.setEnabled(has)
        self._btn_del.setEnabled(has)
        self._cmb.blockSignals(False)

    def _save_profile(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self.w, "Profil speichern", "Profilname:")
        if not ok or not name.strip():
            return
        name = name.strip()
        p = self.params.read_scan_params()
        self._settings.beginGroup(f"{self._KEY_PREFIX}/{name}")
        for k, v in p.items():
            self._settings.setValue(k, v)
        self._settings.endGroup()
        self._refresh_combo()
        idx = self._cmb.findText(name)
        if idx >= 0:
            self._cmb.setCurrentIndex(idx)
        append_log(self.w, f"Scan-Profil gespeichert: '{name}'.", "ok")

    def _load_profile(self):
        name = self._cmb.currentText()
        if not name:
            return
        self._settings.beginGroup(f"{self._KEY_PREFIX}/{name}")
        p = {k: self._settings.value(k) for k in self._settings.childKeys()}
        self._settings.endGroup()
        self._apply_to_ui(p)
        append_log(self.w, f"Scan-Profil geladen: '{name}'.", "info")

    def _delete_profile(self):
        name = self._cmb.currentText()
        if not name:
            return
        reply = QMessageBox.question(
            self.w, "Profil löschen",
            f"Profil '{name}' löschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._settings.remove(f"{self._KEY_PREFIX}/{name}")
        self._refresh_combo()
        append_log(self.w, f"Scan-Profil gelöscht: '{name}'.", "warn")

    def _apply_to_ui(self, p: dict):
        def _dsb(name, key):
            w = self.w.findChild(QDoubleSpinBox, name)
            if w and key in p:
                try: w.setValue(float(p[key]))
                except Exception: pass

        def _sb(name, key):
            w = self.w.findChild(QSpinBox, name)
            if w and key in p:
                try: w.setValue(int(float(p[key])))
                except Exception: pass

        def _chk(name, key):
            w = self.w.findChild(QCheckBox, name)
            if w and key in p:
                try: w.setChecked(str(p[key]).lower() in ("true", "1"))
                except Exception: pass

        def _cmb_txt(name, key):
            w = self.w.findChild(QComboBox, name)
            if w and key in p:
                idx = w.findText(str(p[key]))
                if idx >= 0: w.setCurrentIndex(idx)
                else:
                    try: w.setCurrentText(str(p[key]))
                    except Exception: pass

        _dsb("spEStart_eV",            "e_start")
        _dsb("spEStop_eV",             "e_stop")
        _dsb("spEStep_eV",             "e_step")
        _dsb("spEDecel_eV",            "e_decel")
        _dsb("spSpectrometerConstant", "k")
        _dsb("spOffsetP2",             "p2")
        _dsb("spSettleTime_s",         "settle_s")
        _dsb("spSettleTol",            "settle_tol_v")
        _dsb("spSettleTimeout",        "settle_timeout_s")
        _dsb("spNPLC",                 "nplc")
        _dsb("spAvg",                  "avg_n")
        _sb ("spLoopCount",            "loop_count")
        _chk("chkBidirectional",       "bidirectional")
        _cmb_txt("cmbMeasMode",        "mode")
        _cmb_txt("cmbPPAMode",         "ppa_mode_text")


# =============================================================================
# ScanPreviewDialog – Vorschau vor dem Scan-Start
# =============================================================================

class ScanPreviewDialog(QDialog):
    """
    Modaler Dialog der vor dem Scan-Start alle Parameter zusammenfasst,
    die geschätzte Dauer anzeigt und Warnungen bei fehlenden Geräten gibt.
    """
    _OVERHEAD_S = 0.15   # empirischer Overhead pro Punkt (Serial + PSU-Latenz)

    def __init__(self, parent, params: dict, n_pts: int,
                 ion_ctrl, ppa_up_ctrl, ppa_down_ctrl,
                 meter_ctrl, meter_name: str,
                 save_dir: str, autosave: bool):
        super().__init__(parent)
        self.setWindowTitle("Ref4EP – Scan Vorschau")
        self.setModal(True)
        self.setMinimumWidth(440)
        self._warnings = []

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        p = params

        # ── Zeitschätzung ─────────────────────────────────────────────────────
        nplc_s    = p["nplc"] / 50.0
        avg_n     = p["avg_n"] if p["mode"].startswith("Average") else 1
        t_point_s = nplc_s * avg_n + p["settle_s"] + self._OVERHEAD_S
        t_sweep_s = n_pts * t_point_s
        n_sweeps  = max(1, p["loop_count"]) * (2 if p["bidirectional"] else 1)
        t_total_s = n_sweeps * t_sweep_s

        def _fmt_t(s: float) -> str:
            if s < 60:   return f"~{s:.0f} s"
            h, r = divmod(int(s), 3600)
            m, sc = divmod(r, 60)
            if h:        return f"~{h}h {m:02d}m {sc:02d}s"
            return f"~{m}m {sc:02d}s"

        from PySide6.QtWidgets import QFormLayout, QDialogButtonBox
        from PySide6.QtCore import Qt

        def _section(title):
            gb = QGroupBox(title)
            fl = QFormLayout(gb); fl.setSpacing(4)
            layout.addWidget(gb)
            return gb

        def _row(gb, label, value, color=""):
            v = QLabel(str(value))
            if color:
                v.setStyleSheet(f"color: {color}; font-weight: bold;")
            gb.layout().addRow(QLabel(label), v)

        # ── Energieparameter ──────────────────────────────────────────────────
        gb_e = _section("Energieparameter")
        _row(gb_e, "Bereich:",      f"{p['e_start']:.2f} – {p['e_stop']:.2f} eV")
        _row(gb_e, "Schrittweite:", f"{p['e_step']:.3f} eV")
        _row(gb_e, "Punkte/Sweep:", str(n_pts))
        loop_str  = "∞" if p["loop_count"] == 0 else str(p["loop_count"])
        bidir_str = "  (bidirektional)" if p["bidirectional"] else ""
        _row(gb_e, "Loops:",        f"{loop_str}{bidir_str}")
        _row(gb_e, "E_decel:",      f"{p['e_decel']:.2f} eV  (PPA-Modus {p['ppa_mode']})")
        _row(gb_e, "Spektr. k:",    f"{p['k']:.4f}")
        if p["p2"] != 0.0:
            _row(gb_e, "Offset P2:", f"{p['p2']:.3f} V")

        # ── Messung ───────────────────────────────────────────────────────────
        gb_m = _section("Messung")
        mode_str = (f"Average  N={avg_n}" if avg_n > 1 else "Single")
        _row(gb_m, "Messmodus:",  mode_str)
        _row(gb_m, "NPLC:",       f"{p['nplc']:.2f}  (→ {nplc_s*1000:.0f} ms/Messung)")
        _row(gb_m, "Settle:",     f"{p['settle_s']*1000:.0f} ms  (Tol. {p['settle_tol_v']:.2f} V)")

        # ── Geräte ────────────────────────────────────────────────────────────
        gb_d = _section("Geräte")

        def _dev_row(label, ctrl_or_meter, name=""):
            connected = ctrl_or_meter is not None
            txt   = f"{name}  ✓ verbunden" if connected else f"{name}  ✗ nicht verbunden"
            color = "#27ae60" if connected else "#c0392b"
            _row(gb_d, label, txt, color)
            return connected

        det_ok  = _dev_row("Detektor:", meter_ctrl.meter if meter_ctrl else None, meter_name)
        if not det_ok:
            self._warnings.append("detector")
        _dev_row("Ion PSU:",    ion_ctrl.psu,     "Ion PSU")
        ppa_up_ok = _dev_row("PPA upper:", ppa_up_ctrl.psu,  "PPA upper")
        ppa_dn_ok = _dev_row("PPA lower:", ppa_down_ctrl.psu,"PPA lower")
        if not ppa_dn_ok:
            self._warnings.append("ppa_down")

        # ── Zeitschätzung ─────────────────────────────────────────────────────
        gb_t = _section("Zeitschätzung")
        _row(gb_t, "Pro Punkt:",  f"~{t_point_s*1000:.0f} ms")
        _row(gb_t, "Pro Sweep:",  _fmt_t(t_sweep_s))
        inf_hint   = "  (für 1 Loop)" if p["loop_count"] == 0 else ""
        dur_color  = "#c0392b" if t_total_s > 3600 else ("#e67e22" if t_total_s > 600 else "")
        _row(gb_t, "Gesamt:",     _fmt_t(t_total_s) + inf_hint, dur_color)
        if t_total_s > 3600:
            self._warnings.append("long")

        # ── Speichern ─────────────────────────────────────────────────────────
        gb_s = _section("Speichern")
        if autosave:
            save_ok    = os.path.isdir(save_dir) if save_dir else False
            save_color = "#27ae60" if save_ok else "#e67e22"
            save_txt   = save_dir if save_dir else "(kein Ordner gewählt)"
            if not save_ok:
                self._warnings.append("savedir")
            _row(gb_s, "Auto-Save:", f"Ein  →  {save_txt}", save_color)
        else:
            _row(gb_s, "Auto-Save:", "Aus")

        # ── Warnungen ─────────────────────────────────────────────────────────
        if self._warnings:
            lines = []
            if "detector"  in self._warnings: lines.append("⚠  Kein Detektor verbunden – Scan nicht möglich.")
            if "ppa_down"  in self._warnings: lines.append("⚠  PPA lower PSU nicht verbunden – Scan nicht möglich.")
            if "long"      in self._warnings: lines.append("ℹ  Sehr langer Scan (>1h) – Auto-Save empfohlen.")
            if "savedir"   in self._warnings: lines.append("⚠  Auto-Save Ordner nicht erreichbar.")
            warn_lbl = QLabel("\n".join(lines))
            warn_lbl.setWordWrap(True)
            warn_lbl.setStyleSheet(
                "background: #fef9e7; border: 1px solid #f39c12; "
                "border-radius: 4px; padding: 6px; color: #7d6608;")
            layout.addWidget(warn_lbl)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Abbrechen")
        btn_start  = QPushButton("▶  Scan starten")
        btn_start.setDefault(True)
        btn_start.setStyleSheet(
            "QPushButton { background: #27ae60; color: white; font-weight: bold; "
            "padding: 6px 24px; border-radius: 4px; }"
            "QPushButton:hover { background: #2ecc71; }"
            "QPushButton:disabled { background: #888; color: #ccc; }")
        fatal = any(w in self._warnings for w in ("detector", "ppa_down"))
        btn_start.setEnabled(not fatal)
        btn_cancel.clicked.connect(self.reject)
        btn_start.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_start)
        layout.addLayout(btn_row)


# =============================================================================
# Theme system
# =============================================================================

DARK_THEME = {
    "bg": "#0f1117", "panel": "#1a1d27", "card": "#20232e",
    "border": "#2e3247", "accent": "#4f8ef7", "accent2": "#00d4aa",
    "accent3": "#f7a14f", "danger": "#f74f6e",
    "text": "#e8eaf0", "text_sec": "#9096b0",
    "led_red": "#ff1744", "led_green": "#00e676", "led_grey": "#37404f",
    "lcd_bg": "#0d0d0d", "lcd_fg": "#00e040",
    # log colors
    "log_info": "#c8ccd8", "log_ok": "#00e676",
    "log_warn": "#ffd166", "log_error": "#ff6b6b", "log_stamp": "#666a80",
}
LIGHT_THEME = {
    "bg": "#e8eaed", "panel": "#f5f6f8", "card": "#ffffff",
    "border": "#c0c5d4", "accent": "#1a6fd4", "accent2": "#007755",
    "accent3": "#c45f00", "danger": "#cc1133",
    "text": "#12151f", "text_sec": "#485070",
    "led_red": "#e00020", "led_green": "#00aa44", "led_grey": "#999999",
    "lcd_bg": "#111111", "lcd_fg": "#00cc44",
    # log colors – dunkel genug für weißen Hintergrund
    "log_info": "#1a1d27", "log_ok": "#007733",
    "log_warn": "#8a5500", "log_error": "#cc1133", "log_stamp": "#5a6080",
}


def _build_stylesheet(t: dict) -> str:
    return f"""
QWidget {{ background-color: {t['bg']}; color: {t['text']};
    font-family: "Segoe UI", "SF Pro Display", sans-serif; font-size: 12px; }}
QMainWindow, QDialog {{ background-color: {t['bg']}; }}
/* Ensure plain container widgets don't get a dark bg that bleeds through */
QGroupBox > QWidget, QScrollArea > QWidget > QWidget {{ background-color: {t['card']}; }}
QGroupBox {{ background-color: {t['card']}; border: none;
    border-top: 2px solid {t['border']}; border-radius: 0px;
    margin-top: 14px; padding: 8px 6px 6px 6px;
    font-weight: 600; font-size: 10px; color: {t['text_sec']}; letter-spacing: 0.8px; text-transform: uppercase; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left;
    left: 6px; padding: 0 4px; background-color: {t['card']}; }}
QPushButton {{ background-color: {t['panel']}; border: 1px solid {t['border']};
    border-radius: 5px; padding: 5px 12px; color: {t['text']}; }}
QPushButton:hover {{ background-color: {t['card']}; border-color: {t['accent']}; }}
QPushButton:pressed {{ border-color: {t['accent']}; }}
QPushButton:disabled {{ color: {t['text_sec']}; border-color: {t['border']}; }}
QPushButton:checked {{ background-color: {t['accent']}; color: #ffffff; font-weight: 600; border-color: {t['accent']}; }}
QLabel {{ background: transparent; color: {t['text']}; }}
QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox {{
    background-color: {t['panel']}; border: 1px solid {t['border']};
    border-radius: 4px; padding: 3px 7px; color: {t['text']}; selection-background-color: {t['accent']}; }}
QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus, QComboBox:focus {{ border-color: {t['accent']}; }}
QDoubleSpinBox:read-only, QLineEdit:read-only {{ background-color: {t['bg']}; color: {t['text_sec']}; border-color: transparent; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{ background-color: {t['panel']}; border: 1px solid {t['border']};
    selection-background-color: {t['accent']}; color: {t['text']}; }}
QCheckBox {{ background: transparent; spacing: 5px; color: {t['text']}; }}
QCheckBox::indicator {{ width: 13px; height: 13px; border-radius: 3px;
    border: 1px solid {t['border']}; background: {t['panel']}; }}
QCheckBox::indicator:checked {{ background-color: {t['accent']}; border-color: {t['accent']}; }}
QRadioButton {{ background: transparent; spacing: 5px; color: {t['text']}; }}
QRadioButton::indicator {{ width: 13px; height: 13px; border-radius: 7px;
    border: 1px solid {t['border']}; background: {t['panel']}; }}
QRadioButton::indicator:checked {{ background-color: {t['accent']}; border-color: {t['accent']}; }}
QTextEdit {{ background-color: {t['panel']}; border: 1px solid {t['border']};
    border-radius: 4px; padding: 4px; color: {t['text']};
    font-family: "Consolas", "Courier New", monospace; font-size: 11px; }}
QStatusBar {{ background-color: {t['panel']}; border-top: 1px solid {t['border']};
    color: {t['text_sec']}; font-size: 11px; }}
QSplitter::handle {{ background-color: {t['border']}; }}
QScrollBar:vertical {{ background: {t['bg']}; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 4px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{ color: {t['border']}; }}
QMenuBar {{ background: {t['panel']}; color: {t['text']}; border-bottom: 1px solid {t['border']}; padding: 2px 4px; }}
QMenuBar::item:selected {{ background: {t['accent']}; color: #fff; border-radius: 3px; }}
QMenu {{ background: {t['panel']}; color: {t['text']}; border: 1px solid {t['border']}; }}
QMenu::item:selected {{ background: {t['accent']}; color: #fff; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 3px 6px; }}
QToolTip {{ background: {t['card']}; color: {t['text']}; border: 1px solid {t['accent']}; border-radius: 4px; padding: 4px 7px; }}
"""


def _make_led_w() -> QFrame:
    f = QFrame(); f.setFixedSize(16, 16); f.setFrameShape(QFrame.Shape.NoFrame); return f

def _set_led_w(led: QFrame, color: str) -> None:
    led.setStyleSheet(f"background-color: {color}; border-radius: 8px; border: 1px solid #333;")

def _btn_w(text: str, checkable: bool = False) -> QPushButton:
    b = QPushButton(text); b.setCheckable(checkable); return b

def _spi_w(lo, hi, val) -> QSpinBox:
    w = QSpinBox(); w.setRange(lo, hi); w.setValue(val); return w

def _spd_w(lo, hi, val, dec=2, step=None) -> QDoubleSpinBox:
    w = QDoubleSpinBox(); w.setRange(lo, hi); w.setValue(val); w.setDecimals(dec)
    if step is not None: w.setSingleStep(step)
    return w

def _vsep() -> QFrame:
    """Thin vertical separator for toolbars."""
    f = QFrame(); f.setFrameShape(QFrame.Shape.VLine); f.setFrameShadow(QFrame.Shadow.Sunken)
    return f


# =============================================================================
# MainWindow
# =============================================================================

class MainWindow(QMainWindow):
    theme_changed = Signal(dict)

    def __init__(self, cfg: "AppConfig"):
        super().__init__()
        self.setWindowTitle("Ref4EP  v4.0  |  JLU Giessen – IPI")
        self.resize(1400, 860); self.setMinimumSize(1100, 700)
        self._cfg = cfg
        self._settings_qt = QSettings("JLU-IPI", "Ref4EP")
        self._theme = DARK_THEME
        self._build_ui()
        self._build_menubar()

    def _build_ui(self):
        from PySide6.QtWidgets import QHBoxLayout, QGridLayout, QGroupBox, QSplitter, QScrollArea, QSizePolicy, QRadioButton, QButtonGroup
        C = 6   # inner margin for groups
        S = 3   # spacing

        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QWidget(); hdr.setObjectName("header")
        hh = QHBoxLayout(hdr); hh.setContentsMargins(16,8,16,8)
        lbl_title = QLabel("REF4EP MEASUREMENT STUDIO"); lbl_title.setObjectName("header_title")
        lbl_sub   = QLabel("Ion Energy Scan  ·  JLU Giessen – IPI"); lbl_sub.setObjectName("header_sub")
        lhdr = QVBoxLayout(); lhdr.setSpacing(1)
        lhdr.addWidget(lbl_title); lhdr.addWidget(lbl_sub)
        hh.addLayout(lhdr); hh.addStretch()
        self.lblClock = QLabel("00:00:00"); self.lblClock.setObjectName("lblClock")
        hh.addWidget(self.lblClock)
        root.addWidget(hdr)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)
        root.setStretch(root.count() - 1, 1)
        left_inner = QWidget(); left_inner.setObjectName("left_panel")
        lv = QVBoxLayout(left_inner); lv.setContentsMargins(6,6,6,6); lv.setSpacing(4)
        left_scroll = QScrollArea()
        left_scroll.setWidget(left_inner); left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setMinimumWidth(620)
        # no maximum – user can drag as wide as they like

        def _grp(title):
            g = QGroupBox(title)
            gl = QGridLayout(g); gl.setSpacing(S); gl.setContentsMargins(C,C+8,C,C)
            return g, gl

        def _lbl(t): return QLabel(t)

        # ── Connections ───────────────────────────────────────────────────────
        grp_conn, gc = _grp("Connections")
        gc.setColumnStretch(0,1); gc.setColumnStretch(1,1)
        gc.setSpacing(4)

        def _conn_cell(row, col, label, btn_name, led_name):
            b = _btn_w(label, checkable=True); b.setObjectName(btn_name)
            led = _make_led_w(); led.setObjectName(led_name); led.setFixedSize(14, 14)
            # wrap in a plain QWidget with no stylesheet override
            cell = QWidget()
            ch = QHBoxLayout(cell); ch.setContentsMargins(0,0,0,0); ch.setSpacing(4)
            ch.addWidget(b); ch.setStretch(ch.count() - 1, 1)
            ch.addWidget(led); ch.setStretch(ch.count() - 1, 0)
            gc.addWidget(cell, row, col)

        _conn_cell(0, 0, "Ion PSU",    "btnIonConnect",       "ledIon")
        _conn_cell(0, 1, "PPA upper",  "btnPPAupConnect",     "ledPPAup")
        _conn_cell(1, 0, "PPA lower",  "btnPPAdownConnect",   "ledPPAdown")
        _conn_cell(1, 1, "Einzellens", "btnEinzellensConnect","ledeinzellens")
        _conn_cell(2, 0, "K6485",      "btnK6485Connect",     "ledK6485")
        _conn_cell(2, 1, "K6517B",     "btnK6517BConnect",    "ledK6517B")
        lv.addWidget(grp_conn)

        # ── Voltage Control ───────────────────────────────────────────────────
        grp_volt, gv = _grp("Voltage Control")
        self.spIonVoltage = _spd_w(0,3500,0,dec=1); self.spIonVoltage.setObjectName("spIonVoltage"); self.spIonVoltage.setSuffix(" V")
        self.spIonVoltage.setToolTip("Sollspannung Ion-PSU. Enter drücken zum Setzen.")
        self.btnIonSetV = _btn_w("Set V"); self.btnIonSetV.setObjectName("btnIonSetV"); self.btnIonSetV.setVisible(False)
        self.lcdIonVActual = QLCDNumber(6); self.lcdIonVActual.setObjectName("lcdIonVActual")
        self.lcdIonVActual.setSegmentStyle(QLCDNumber.SegmentStyle.Flat); self.lcdIonVActual.setMinimumHeight(28)
        self.spElVoltage = _spd_w(0,6500,0,dec=1); self.spElVoltage.setObjectName("spElVoltage"); self.spElVoltage.setSuffix(" V")
        self.spElVoltage.setToolTip("Sollspannung Einzellens-PSU. Enter drücken zum Setzen.")
        self.btnElSetV = _btn_w("Set V"); self.btnElSetV.setObjectName("btnElSetV"); self.btnElSetV.setVisible(False)
        self.lcdElVActual = QLCDNumber(6); self.lcdElVActual.setObjectName("lcdElVActual")
        self.lcdElVActual.setSegmentStyle(QLCDNumber.SegmentStyle.Flat); self.lcdElVActual.setMinimumHeight(28)
        # row: label | spinbox | "V act:" | lcd
        gv.addWidget(_lbl("Ion energy:"), 0,0); gv.addWidget(self.spIonVoltage, 0,1)
        gv.addWidget(_lbl("V act:"),      0,2); gv.addWidget(self.lcdIonVActual,0,3)
        gv.addWidget(_lbl("Einzellens:"), 1,0); gv.addWidget(self.spElVoltage,  1,1)
        gv.addWidget(_lbl("V act:"),      1,2); gv.addWidget(self.lcdElVActual, 1,3)
        gv.setColumnStretch(1,1); gv.setColumnStretch(3,1)
        btn_monitor = _btn_w("📈 Monitor"); btn_monitor.setObjectName("btnShowMonitor")
        gv.addWidget(btn_monitor, 2,0,1,4)
        lv.addWidget(grp_volt)

        # ── Scan Parameters ───────────────────────────────────────────────────
        grp_scan, gs = _grp("Scan Parameters")
        self.spEStart_eV = _spd_w(-5000,5000,40.0,dec=2); self.spEStart_eV.setObjectName("spEStart_eV")
        self.spEStop_eV  = _spd_w(-5000,5000,50.0,dec=2); self.spEStop_eV.setObjectName("spEStop_eV")
        self.spEStep_eV  = _spd_w(0.001,1000,1.0,dec=3);  self.spEStep_eV.setObjectName("spEStep_eV")
        # Start / Stop / Step on one row
        r0 = QHBoxLayout()
        for lbl,w in [("Start:",self.spEStart_eV),("Stop:",self.spEStop_eV),("Step:",self.spEStep_eV)]:
            r0.addWidget(_lbl(lbl)); r0.addWidget(w)
        gs.addLayout(r0, 0,0,1,4)

        self.spEDecel_eV = _spd_w(-5000,5000,0.0,dec=2);  self.spEDecel_eV.setObjectName("spEDecel_eV")
        self.spSpectrometerConstant = _spd_w(0.5,2.0,1.0275,dec=6,step=0.0001); self.spSpectrometerConstant.setObjectName("spSpectrometerConstant")
        self.spOffsetP2  = _spd_w(-500,500,0.0,dec=3);    self.spOffsetP2.setObjectName("spOffsetP2")
        self.cmbPPAMode  = QComboBox(); self.cmbPPAMode.setObjectName("cmbPPAMode")
        self.cmbPPAMode.addItems(["Modus 1 (E_decel=0)","Modus 2","Modus 3"])
        gs.addWidget(_lbl("E decel (eV):"),     1,0); gs.addWidget(self.spEDecel_eV,            1,1)
        gs.addWidget(_lbl("PPA mode:"),          1,2); gs.addWidget(self.cmbPPAMode,             1,3)
        gs.addWidget(_lbl("Spectr. k:"),         2,0); gs.addWidget(self.spSpectrometerConstant, 2,1)
        gs.addWidget(_lbl("Offset P2 (V):"),     2,2); gs.addWidget(self.spOffsetP2,             2,3)
        gs.setColumnStretch(1,1); gs.setColumnStretch(3,1)

        # Loops / Bidirectional / BinWidth
        self.spLoopCount = _spi_w(0,9999,0); self.spLoopCount.setObjectName("spLoopCount")
        self.chkBidirectional = QCheckBox("Bidirectional"); self.chkBidirectional.setObjectName("chkBidirectional"); self.chkBidirectional.setChecked(True)
        self.leBinWidth = QLineEdit(); self.leBinWidth.setObjectName("leBinWidth"); self.leBinWidth.setReadOnly(True); self.leBinWidth.setPlaceholderText("Bin width")
        self.leBinWidth.setFixedWidth(70)
        r2 = QHBoxLayout()
        r2.addWidget(_lbl("Loops:")); r2.addWidget(self.spLoopCount)
        r2.addWidget(self.chkBidirectional)
        r2.addStretch()
        r2.addWidget(_lbl("Bin:")); r2.addWidget(self.leBinWidth)
        gs.addLayout(r2, 3,0,1,4)

        # Profiles
        cmb_prof = QComboBox(); cmb_prof.setObjectName("cmbScanProfiles"); cmb_prof.setPlaceholderText("Profile…")
        cmb_prof.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_prof_load = _btn_w("Load");   btn_prof_load.setObjectName("btnProfileLoad");  btn_prof_load.setFixedWidth(60)
        btn_prof_save = _btn_w("Save…");  btn_prof_save.setObjectName("btnProfileSave");  btn_prof_save.setFixedWidth(60)
        btn_prof_del  = _btn_w("Delete"); btn_prof_del.setObjectName("btnProfileDelete"); btn_prof_del.setFixedWidth(60)
        r3 = QHBoxLayout()
        r3.addWidget(cmb_prof); r3.addWidget(btn_prof_load); r3.addWidget(btn_prof_save); r3.addWidget(btn_prof_del)
        gs.addLayout(r3, 4,0,1,4)
        lv.addWidget(grp_scan)

        # ── Measurement Settings ──────────────────────────────────────────────
        grp_meas, gm = _grp("Measurement Settings")
        self.cmbDetector  = QComboBox(); self.cmbDetector.setObjectName("cmbDetector")
        self.cmbDetector.addItems(["Keithley 6485","Keithley 6517B","CEM"])
        self.cmbMeasMode  = QComboBox(); self.cmbMeasMode.setObjectName("cmbMeasMode")
        self.cmbMeasMode.addItems(["Single","Average"])
        self.cmbRange     = QComboBox(); self.cmbRange.setObjectName("cmbRange")
        self.chkAutoRange = QCheckBox("Auto-range"); self.chkAutoRange.setObjectName("chkAutoRange"); self.chkAutoRange.setChecked(True)
        self.spNPLC       = _spd_w(0.01,10.0,0.1,dec=2); self.spNPLC.setObjectName("spNPLC")
        self.spAvg        = _spd_w(1,9999,1,dec=0);       self.spAvg.setObjectName("spAvg")

        # Averages vs Buffer N radio buttons
        self.rbAvg     = QRadioButton("Averages"); self.rbAvg.setObjectName("rbAvg"); self.rbAvg.setChecked(True)
        self.rbBufferN = QRadioButton("Buffer N"); self.rbBufferN.setObjectName("rbBufferN")
        _rb_grp = QButtonGroup(self); _rb_grp.addButton(self.rbAvg); _rb_grp.addButton(self.rbBufferN)
        self.spBufferN = _spi_w(1, 9999, 10); self.spBufferN.setObjectName("spBufferN"); self.spBufferN.setEnabled(False)
        self.spDwell   = _spd_w(0, 60, 0.0, dec=3); self.spDwell.setObjectName("spDwell"); self.spDwell.setSuffix(" s")

        gm.addWidget(_lbl("Detector:"),  0,0); gm.addWidget(self.cmbDetector, 0,1)
        gm.addWidget(_lbl("Mode:"),      0,2); gm.addWidget(self.cmbMeasMode, 0,3)
        gm.addWidget(_lbl("Range:"),     1,0); gm.addWidget(self.cmbRange,    1,1)
        gm.addWidget(self.chkAutoRange,  1,2,1,2)
        gm.addWidget(_lbl("NPLC:"),      2,0); gm.addWidget(self.spNPLC,      2,1)
        # Row 3: Averages radio + spinbox | Buffer N radio + spinbox
        gm.addWidget(self.rbAvg,         3,0); gm.addWidget(self.spAvg,       3,1)
        gm.addWidget(self.rbBufferN,     3,2); gm.addWidget(self.spBufferN,   3,3)
        # Row 4: Dwell
        gm.addWidget(_lbl("Dwell:"),     4,0); gm.addWidget(self.spDwell,     4,1)
        gm.setColumnStretch(1,1); gm.setColumnStretch(3,1)
        lv.addWidget(grp_meas)

        # ── Settle ────────────────────────────────────────────────────────────
        grp_settle, gst = _grp("Settle")
        self.spSettleTime_s  = _spd_w(0,60,0.5,dec=2);   self.spSettleTime_s.setObjectName("spSettleTime_s")
        self.spSettleTol     = _spd_w(0.01,100,1.0,dec=2); self.spSettleTol.setObjectName("spSettleTol")
        self.spSettleTimeout = _spd_w(1,300,10.0,dec=1); self.spSettleTimeout.setObjectName("spSettleTimeout")
        gst.addWidget(_lbl("Settle (s):"),  0,0); gst.addWidget(self.spSettleTime_s,  0,1)
        gst.addWidget(_lbl("Tol. (V):"),    0,2); gst.addWidget(self.spSettleTol,     0,3)
        gst.addWidget(_lbl("Timeout (s):"), 1,0); gst.addWidget(self.spSettleTimeout, 1,1)
        gst.setColumnStretch(1,1); gst.setColumnStretch(3,1)
        lv.addWidget(grp_settle)

        # ── Scan Actions ──────────────────────────────────────────────────────
        grp_ctrl, gctrl = _grp("Scan Actions")
        self.btnScanStart = _btn_w("▶  Start Scan"); self.btnScanStart.setObjectName("btnScanStart")
        self.btnScanStart.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: white; font-weight: bold; "
            "border-radius: 5px; padding: 5px 12px; }"
            "QPushButton:hover { background-color: #2ecc71; }"
            "QPushButton:disabled { background-color: #555; color: #999; }")
        self.btnScanStop  = _btn_w("■ Stop");           self.btnScanStop.setObjectName("btnScanStop");  self.btnScanStop.setEnabled(False)
        self.btnLoopStop  = _btn_w("⏭ Finish Loop");   self.btnLoopStop.setObjectName("btnLoopStop");  self.btnLoopStop.setEnabled(False)
        gctrl.addWidget(self.btnScanStart, 0,0)
        gctrl.addWidget(self.btnScanStop,  0,1)
        gctrl.addWidget(self.btnLoopStop,  0,2)
        gctrl.setColumnStretch(0,1); gctrl.setColumnStretch(1,1); gctrl.setColumnStretch(2,1)
        lv.addWidget(grp_ctrl)

        # ── Data Saving ───────────────────────────────────────────────────────
        grp_csv, gcsv = _grp("Data Saving")
        self.txtSaveDir    = QLineEdit(); self.txtSaveDir.setObjectName("txtSaveDir"); self.txtSaveDir.setPlaceholderText("Save folder…")
        self.btnBrowseSave = _btn_w("📁 Browse"); self.btnBrowseSave.setObjectName("btnBrowseSave"); self.btnBrowseSave.setFixedWidth(80)
        self.btnSaveCSV    = _btn_w("💾 Save CSV"); self.btnSaveCSV.setObjectName("btnSaveCSV")
        self.chkAutoSave   = QCheckBox("Auto-save after each loop"); self.chkAutoSave.setObjectName("chkAutoSave")
        r_dir = QHBoxLayout()
        r_dir.addWidget(self.txtSaveDir); r_dir.addWidget(self.btnBrowseSave)
        gcsv.addLayout(r_dir, 0,0,1,2)
        gcsv.addWidget(self.btnSaveCSV,  1,0)
        gcsv.addWidget(self.chkAutoSave, 1,1)
        gcsv.setColumnStretch(1,1)
        lv.addWidget(grp_csv)

        # ── Safety / Config ───────────────────────────────────────────────────
        grp_safe, gsf = _grp("Safety / Config")
        self.btnAllOff     = _btn_w("⚠ ALL OFF");  self.btnAllOff.setObjectName("btnAllOff")
        btn_monitor2       = _btn_w("📈 Monitor");  btn_monitor2.setObjectName("btnShowMonitor")   # alias – same objectName
        self.btnSaveConfig = _btn_w("💾 Save Config"); self.btnSaveConfig.setObjectName("btnSaveConfig")
        self.btnEmergency  = _btn_w("🚨");          self.btnEmergency.setObjectName("btnEmergency"); self.btnEmergency.setFixedWidth(32)
        gsf.addWidget(self.btnAllOff,     0,0)
        gsf.addWidget(btn_monitor2,        0,1)
        gsf.addWidget(self.btnSaveConfig,  0,2)
        gsf.addWidget(self.btnEmergency,   0,3)
        lv.addWidget(grp_safe)

        lv.addStretch()

        # ── RIGHT: vertical splitter ─────────────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right); rv.setContentsMargins(4,4,4,4); rv.setSpacing(0)
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setChildrenCollapsible(False); right_splitter.setHandleWidth(5)

        # _plot_container: ScanPlotController injects stop_bar + canvas + toolbar here
        self._plot_container = QWidget(); self._plot_container.setObjectName("plotWidget")
        self._plot_layout    = QVBoxLayout(self._plot_container)
        self._plot_layout.setContentsMargins(6,6,6,2)
        self._plot_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.txtLog = QTextEdit(); self.txtLog.setObjectName("txtLog")
        self.txtLog.setReadOnly(True); self.txtLog.setMinimumHeight(80)

        right_splitter.addWidget(self._plot_container); right_splitter.addWidget(self.txtLog)
        right_splitter.setSizes([600, 200]); right_splitter.setStretchFactor(0,3); right_splitter.setStretchFactor(1,1)
        rv.addWidget(right_splitter)
        rv.setStretch(rv.count() - 1, 1)

        splitter.addWidget(left_scroll); splitter.addWidget(right)
        # Restore saved splitter position, else default
        saved = self._settings_qt.value("splitter_h")
        if saved:
            try:
                splitter.restoreState(saved)
            except Exception:
                splitter.setSizes([420, 980])
        else:
            splitter.setSizes([420, 980])
        self._splitter_h = splitter   # keep ref for closeEvent save

        saved_v = self._settings_qt.value("splitter_v")
        if saved_v:
            try:
                right_splitter.restoreState(saved_v)
            except Exception:
                right_splitter.setSizes([600, 200])
        self._splitter_v = right_splitter

        self.statusbar = QStatusBar(); self.statusbar.setObjectName("statusbar"); self.setStatusBar(self.statusbar)

    def _build_menubar(self):
        mb = self.menuBar()
        view_menu = mb.addMenu("View")
        self._act_dark  = view_menu.addAction("Dark Theme")
        self._act_light = view_menu.addAction("Light Theme")
        self._act_dark.setCheckable(True); self._act_light.setCheckable(True)
        self._act_dark.triggered.connect(lambda: self._apply_theme(DARK_THEME))
        self._act_light.triggered.connect(lambda: self._apply_theme(LIGHT_THEME))
        help_menu = mb.addMenu("Help")
        help_menu.addAction("About").triggered.connect(
            lambda: QMessageBox.about(self,"About","<b>Ref4EP v3.1</b><br>I. Physikalisches Institut · JLU Giessen"))
        if self._settings_qt.value("theme","dark") == "light":
            self._apply_theme(LIGHT_THEME)
        else:
            self._apply_theme(DARK_THEME)

    def _apply_theme(self, t: dict):
        global _LOG_COLORS
        self._theme = t
        self.setStyleSheet(_build_stylesheet(t))
        is_dark = (t is DARK_THEME)
        self._settings_qt.setValue("theme","dark" if is_dark else "light")
        if hasattr(self,"_act_dark"):
            self._act_dark.setChecked(is_dark); self._act_light.setChecked(not is_dark)
        hdr = self.findChild(QWidget,"header")
        if hdr: hdr.setStyleSheet(f"#header {{ background: {t['panel']}; border-bottom: 1px solid {t['border']}; }}")
        for name, style in [
            ("header_title", f"font-size: 20px; font-weight: 700; color: {t['accent']}; letter-spacing: 1px; background: transparent;"),
            ("header_sub",   f"font-size: 11px; color: {t['text_sec']}; background: transparent;"),
            ("lblClock",     f"font-size: 11pt; font-family: Consolas; color: {t['accent']}; background: transparent;"),
        ]:
            w = self.findChild(QLabel, name)
            if w: w.setStyleSheet(style)
        if hasattr(self,"btnAllOff"):
            self.btnAllOff.setStyleSheet(
                f"QPushButton {{ background-color: {t['danger']}; color: white; font-weight: bold; border-radius: 5px; padding: 5px 12px; }}"
                f"QPushButton:hover {{ background-color: {t['danger']}; }}")
        from PySide6.QtGui import QPalette, QColor
        for lcd in (self.lcdIonVActual, self.lcdElVActual):
            pal = lcd.palette()
            pal.setColor(QPalette.ColorRole.Window,     QColor(t["lcd_bg"]))
            pal.setColor(QPalette.ColorRole.WindowText, QColor(t["lcd_fg"]))
            lcd.setPalette(pal); lcd.setAutoFillBackground(True)
        app = QApplication.instance()
        if app:
            pal = QPalette()
            pal.setColor(QPalette.Window,          QColor(t["bg"]))
            pal.setColor(QPalette.WindowText,      QColor(t["text"]))
            pal.setColor(QPalette.Base,            QColor(t["panel"]))
            pal.setColor(QPalette.AlternateBase,   QColor(t["card"]))
            pal.setColor(QPalette.Text,            QColor(t["text"]))
            pal.setColor(QPalette.Button,          QColor(t["panel"]))
            pal.setColor(QPalette.ButtonText,      QColor(t["text"]))
            pal.setColor(QPalette.Highlight,       QColor(t["accent"]))
            pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
            app.setPalette(pal)
        # Log-Farben aktualisieren
        _LOG_COLORS["info"]  = t.get("log_info",  "#c8ccd8")
        _LOG_COLORS["ok"]    = t.get("log_ok",    "#00e676")
        _LOG_COLORS["warn"]  = t.get("log_warn",  "#ffd166")
        _LOG_COLORS["error"] = t.get("log_error", "#ff6b6b")
        _LOG_COLORS["stamp"] = t.get("log_stamp", "#666a80")
        self.theme_changed.emit(t)

    def _show_about(self):
        QMessageBox.about(self,"About Ref4EP",
            "<b>Ref4EP Measurement Studio  v3.1</b><br>Ion Energy Scan Controller<br><br>"
            "I. Physikalisches Institut · JLU Giessen")


if __name__ == "__main__":
    clear_console()
    print_banner()

    # Logging einrichten: INFO+ auf Konsole, WARNING+ in Logdatei neben dem Skript
    _log_path = os.path.join(os.path.dirname(__file__), "Ref4EP.log")
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),                         # Konsole: alles ab DEBUG
            logging.FileHandler(_log_path, encoding="utf-8", mode="a"), # Datei: alles ab DEBUG
        ],
    )
    # Third-party-Logger nicht zu gesprächig werden lassen
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("pyvisa").setLevel(logging.WARNING)

    log.info("Ref4EP gestartet – Logdatei: %s", _log_path)

    # Config laden (Ref4EP.ini neben dem Skript)
    cfg = AppConfig()

    app = QApplication(sys.argv)

    window = MainWindow(cfg)

    controllers = [
        DeviceController(
            window,
            btn_name="btnIonConnect",
            led_name="ledIon",
            psu_kwargs=dict(
                mode=cfg.get("ion_psu", "mode", "tcp"),
                host=cfg.get("ion_psu", "host", "192.168.1.93"),
                tcp_port=cfg.getint("ion_psu", "tcp_port", 2101),
                timeout=cfg.getfloat("ion_psu", "timeout", 2.0),
                v_max=cfg.getfloat("ion_psu", "v_max", 3500.0),
                i_max=cfg.getfloat("ion_psu", "i_max", 0.040),
            ),
            status_prefix="Ion energy",
        ),
        DeviceController(
            window,
            btn_name="btnPPAupConnect",
            led_name="ledPPAup",
            psu_kwargs=dict(
                mode=cfg.get("ppa_up_psu", "mode", "visa"),
                visa_resource=cfg.get("ppa_up_psu", "visa_resource", "GPIB1::9::INSTR"),
                timeout=cfg.getfloat("ppa_up_psu", "timeout", 2.0),
                v_max=cfg.getfloat("ppa_up_psu", "v_max", 2000.0),
                i_max=cfg.getfloat("ppa_up_psu", "i_max", 0.006),
            ),
            status_prefix="PPA upper",
        ),
        DeviceController(
            window,
            btn_name="btnPPAdownConnect",
            led_name="ledPPAdown",
            psu_kwargs=dict(
                mode=cfg.get("ppa_down_psu", "mode", "serial"),
                port=cfg.get("ppa_down_psu", "port", "COM4"),
                baudrate=cfg.getint("ppa_down_psu", "baudrate", 9600),
                timeout=cfg.getfloat("ppa_down_psu", "timeout", 2.0),
                v_max=cfg.getfloat("ppa_down_psu", "v_max", 2000.0),
                i_max=cfg.getfloat("ppa_down_psu", "i_max", 0.006),
            ),
            status_prefix="PPA lower",
        ),
        DeviceController(
            window,
            btn_name="btnEinzellensConnect",
            led_name="ledeinzellens",
            psu_kwargs=dict(
                mode=cfg.get("einzellens_psu", "mode", "tcp"),
                host=cfg.get("einzellens_psu", "host", "192.168.1.95"),
                tcp_port=cfg.getint("einzellens_psu", "tcp_port", 2101),
                timeout=cfg.getfloat("einzellens_psu", "timeout", 2.0),
                v_max=cfg.getfloat("einzellens_psu", "v_max", 6500.0),
                i_max=cfg.getfloat("einzellens_psu", "i_max", 0.020),
            ),
            status_prefix="Einzellens",
        ),
    ]

    k6485_ctrl = K6485Controller(
        window,
        btn_name="btnK6485Connect",
        led_name="ledK6485",
    )

    k6517b_ctrl = K6517BController(
        window,
        btn_name="btnK6517BConnect",
        led_name="ledK6517B",
    )

    meas_ctrl = MeasurementSettingsController(window)

    scan_ctrl = ScanController(
        window,
        ion_ctrl=controllers[0],
        ppa_up_ctrl=controllers[1],
        ppa_down_ctrl=controllers[2],
        k6485_ctrl=k6485_ctrl,
        k6517b_ctrl=k6517b_ctrl,
    )

    # Spaßfunktion: zufälliges Personenbild bei btnEmergency
    emergency_ctrl = EmergencyController(window)

    # Ion + Einzellens Steuerung (Spannungsvorgabe, Istwert, Zeitplot)
    ion_el_ctrl = IonEinzellensController(window, controllers[0], controllers[3])

    # Safety-Button: alle PSUs sofort auf 0 V / output off
    safety_ctrl = SafetyController(window, controllers[:3], controllers[3])

    # Scan-Profile Manager
    profile_mgr = ScanProfileManager(window, scan_ctrl.params)

    # Plot-Theme mit Qt-Theme synchronisieren
    window.theme_changed.connect(scan_ctrl.plot.apply_theme)

    # Tooltips auf alle bekannten Widgets setzen
    tooltip_ctrl = TooltipController(window)

    # Config-Controller: wendet Config auf UI an, speichert auf Knopfdruck
    cfg_ctrl = ConfigController(window, cfg, scan_ctrl, controllers)

    # CloseEvent-Schutz: fragt nach wenn Scan läuft, stoppt sauber vor dem Schließen
    close_filter = CloseEventFilter(window, scan_ctrl)
    window.installEventFilter(close_filter)

    # Uhr: lblClock wird jede Sekunde aktualisiert
    lbl_clock = window.lblClock

    WEEKDAYS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

    def _calc_mjd(now: datetime) -> float:
        Y, M, D = now.year, now.month, now.day
        H, Min, S = now.hour, now.minute, now.second
        if M <= 2:
            Y -= 1; M += 12
        frac = D + H/24 + Min/1440 + S/86400
        JD = (math.floor(365.25*(Y + 4716)) + math.floor(30.6001*(M+1))
              + frac + 2 - math.floor(Y/100) + math.floor(Y/400) - 1524.5)
        return JD - 2400000.5

    def _update_clock():
        now = datetime.now()
        wd   = WEEKDAYS_DE[now.weekday()]
        kw   = now.isocalendar()[1]
        mjd  = _calc_mjd(now)
        line1 = f"{wd}  {now.strftime('%d.%m.%Y')}  {now.strftime('%H:%M:%S')}"
        line2 = f"KW {kw:02d}   MJD {mjd:.5f}"
        lbl_clock.setText(f"{line1}\n{line2}")

    _clock_timer = QTimer(window)
    _clock_timer.timeout.connect(_update_clock)
    _clock_timer.start(1000)
    _update_clock()

    window.show()
    sys.exit(app.exec())
