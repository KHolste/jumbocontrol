"""
pc_diagnose.py – System Health Monitor mit GUI
Standalone-Skript fuer Windows. Liest Sensordaten via LibreHardwareMonitor (WMI),
Systemmetriken via psutil, Windows Event Log via PowerShell.
Keine Projektabhaengigkeiten.
"""

import sys
import os
import csv
import time
import ctypes
import logging
import subprocess
import threading
from queue import Queue, Empty
from datetime import datetime, timezone
from pathlib import Path

import tkinter as tk

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

# ═══════════════════════════════════════════════════════════════
# KONFIGURATION
# ═══════════════════════════════════════════════════════════════

INTERVALL_S = 5
BASE_DIR = Path(__file__).parent
ALERT_LOG = BASE_DIR / "temperature_alert.log"
MAX_LOG_ZEILEN = 800

SCHWELLEN = {
    "temp": {"cpu": (75.0, 85.0), "gpu": (80.0, 90.0),
             "mb": (50.0, 60.0), "disk": (55.0, 65.0),
             "default": (75.0, 85.0)},
    "volt": {"+12v": (11.4, 12.6), "+5v": (4.75, 5.25),
             "+3.3v": (3.13, 3.47)},
    "vbat": {"warn": 2.8, "crit": 2.7},
    "fan_min_rpm": 1,
    "cpu_pct": (90.0, 98.0),
    "ram_pct": (85.0, 95.0),
    "disk_pct": (90.0, 98.0),
}

# Farben
_BG = "#111827"; _CARD = "#1e293b"; _BORDER = "#334155"
_TEXT = "#e2e8f0"; _DIM = "#94a3b8"
_GREEN = "#22c55e"; _YELLOW = "#f59e0b"; _RED = "#ef4444"
_BLUE = "#60a5fa"

# ═══════════════════════════════════════════════════════════════
# ALERT-LOGGER (Datei)
# ═══════════════════════════════════════════════════════════════

_alert_logger = logging.getLogger("pc_diagnose_alert")
_alert_logger.setLevel(logging.WARNING)
_fh = logging.FileHandler(ALERT_LOG, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(message)s"))
_alert_logger.addHandler(_fh)
_alert_logger.propagate = False

# ═══════════════════════════════════════════════════════════════
# HILFSFUNKTIONEN
# ═══════════════════════════════════════════════════════════════

def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _ist_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def _csv_pfad() -> Path:
    return BASE_DIR / f"system_metrics_{datetime.now():%Y-%m-%d}.csv"

# ═══════════════════════════════════════════════════════════════
# POWERSHELL-HELFER
# ═══════════════════════════════════════════════════════════════

def _ps_run(cmd: str, timeout: int = 15) -> str:
    """Fuehrt PowerShell-Befehl aus und gibt stdout zurueck."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""

# ═══════════════════════════════════════════════════════════════
# SENSOR-DATEN (LibreHardwareMonitor via WMI)
# ═══════════════════════════════════════════════════════════════

_PS_SENSOREN = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$s=Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Sensor;"
    "if(-not $s){$s=Get-CimInstance -Namespace root/OpenHardwareMonitor -ClassName Sensor};"
    "if($s){$s|ForEach-Object{"
    "\"$($_.SensorType)\t$($_.Name)\t$($_.Value)\t$($_.Identifier)\""
    "}};"
    "Write-Output '---DISKS---';"
    "Get-PhysicalDisk|ForEach-Object{"
    "\"$($_.FriendlyName)\t$($_.MediaType)\t$($_.HealthStatus)\"}"
)

def _temp_kat(name: str, ident: str) -> str:
    """Ordnet einen Temperatursensor einer Kategorie zu."""
    n, i = name.lower(), ident.lower()
    if "cpu" in i and any(k in n for k in ("package", "tctl", "tdie", "total")):
        return "cpu"
    if "cpu" in i and "core" in n:
        return "cpu"
    if "gpu" in i:
        return "gpu"
    if any(k in i for k in ("nvme", "hdd", "ssd", "/disk")):
        return "disk"
    if any(k in i for k in ("lpc", "motherboard", "superio", "ec/")):
        return "mb"
    return "default"

def _volt_kat(name: str) -> str:
    """Ordnet einen Spannungssensor einer Kategorie zu."""
    n = name.lower()
    if "vbat" in n or "battery" in n or "cmos" in n:
        return "vbat"
    if "vcore" in n or "core" in n:
        return "vcore"
    if "12v" in n or "+12" in n:
        return "+12v"
    if "3.3" in n or "3v3" in n or "+3.3" in n:
        return "+3.3v"
    if "5v" in n and "5vsb" not in n:
        return "+5v"
    return name

def lese_sensoren() -> dict:
    """Liest alle LHM-Sensoren + Disk-Health in einem PS-Aufruf."""
    raw = _ps_run(_PS_SENSOREN)
    temps, fans, volts, disks = {}, {}, {}, []
    modus = "sensoren"

    for zeile in raw.splitlines():
        if zeile.strip() == "---DISKS---":
            modus = "disks"
            continue
        teile = zeile.split("\t")

        if modus == "sensoren" and len(teile) >= 4:
            typ, name, val_str, ident = teile[0], teile[1], teile[2], teile[3]
            try:
                val = float(val_str.replace(",", "."))
            except (ValueError, TypeError):
                continue
            if typ == "Temperature" and 0 < val < 200:
                kat = _temp_kat(name, ident)
                # CPU Package bevorzugen, Cores nur als Fallback
                if kat == "cpu" and "cpu" in temps:
                    if "package" in name.lower() or "tctl" in name.lower():
                        temps["cpu"] = (name, val)
                else:
                    temps.setdefault(kat, (name, val))
            elif typ == "Fan":
                fans[name] = val
            elif typ == "Voltage":
                kat = _volt_kat(name)
                volts[kat] = (name, val)

        elif modus == "disks" and len(teile) >= 3:
            disks.append({"name": teile[0], "typ": teile[1], "health": teile[2]})

    return {"temps": temps, "fans": fans, "volts": volts, "disks": disks}

# ═══════════════════════════════════════════════════════════════
# SYSTEM-METRIKEN (psutil)
# ═══════════════════════════════════════════════════════════════

def lese_system() -> dict:
    if not _HAS_PSUTIL:
        return {}
    try:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/") if sys.platform != "win32" else psutil.disk_usage("C:\\")
        return {
            "cpu_pct": psutil.cpu_percent(interval=None),
            "ram_pct": mem.percent,
            "ram_used_gb": round(mem.used / 1073741824, 1),
            "ram_total_gb": round(mem.total / 1073741824, 1),
            "disk_pct": disk.percent,
        }
    except Exception:
        return {}

# ═══════════════════════════════════════════════════════════════
# WINDOWS EVENT LOG (einmalig beim Start)
# ═══════════════════════════════════════════════════════════════

_PS_EVENTS = (
    "$ErrorActionPreference='SilentlyContinue';"
    "Get-WinEvent -FilterHashtable @{"
    "LogName='System';"
    "ProviderName='Microsoft-Windows-Kernel-Power',"
    "'Microsoft-Windows-WER-SystemErrorReporting',"
    "'Microsoft-Windows-WHEA-Logger','disk','Ntfs','volmgr';"
    "Level=1,2,3} -MaxEvents 10 | ForEach-Object {"
    "$m=if($_.Message){($_.Message -replace '\\s+',' ')}else{''};"
    "if($m.Length -gt 120){$m=$m.Substring(0,120)+'...'};"
    "\"$($_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'))\t$($_.Id)\t$($_.ProviderName)\t$($_.LevelDisplayName)\t$m\"}"
)

def lese_events() -> list[dict]:
    raw = _ps_run(_PS_EVENTS, timeout=20)
    events = []
    for zeile in raw.splitlines():
        teile = zeile.split("\t", 4)
        if len(teile) >= 5:
            events.append({
                "zeit": teile[0], "id": teile[1],
                "quelle": teile[2], "level": teile[3],
                "msg": teile[4][:150],
            })
    return events

# ═══════════════════════════════════════════════════════════════
# ALERT-PRUEFUNG
# ═══════════════════════════════════════════════════════════════

def pruefe_alerts(sens: dict, sys_m: dict, events: list) -> tuple[dict, list]:
    """Gibt (status_dict, alert_list) zurueck.
    status: Kategorie -> 'ok'|'warn'|'crit'|'na'
    alerts: [(level, text), ...]
    """
    status = {"temp": "na", "volt": "na", "fan": "na",
              "system": "na", "disk": "na", "events": "ok"}
    alerts = []

    def _upgrade(kat, level):
        rang = {"na": 0, "ok": 1, "warn": 2, "crit": 3}
        if rang.get(level, 0) > rang.get(status[kat], 0):
            status[kat] = level

    # ── Temperaturen ──
    for kat, (name, val) in sens.get("temps", {}).items():
        _upgrade("temp", "ok")
        s = SCHWELLEN["temp"].get(kat, SCHWELLEN["temp"]["default"])
        if val >= s[1]:
            alerts.append(("KRITISCH", f"{name}: {val:.1f}\u00b0C"))
            _upgrade("temp", "crit")
        elif val >= s[0]:
            alerts.append(("WARNUNG", f"{name}: {val:.1f}\u00b0C"))
            _upgrade("temp", "warn")

    # ── Spannungen ──
    for kat, (name, val) in sens.get("volts", {}).items():
        _upgrade("volt", "ok")
        if kat == "vbat":
            if val < SCHWELLEN["vbat"]["crit"]:
                alerts.append(("KRITISCH", f"VBAT: {val:.3f}V (< {SCHWELLEN['vbat']['crit']}V)"))
                _upgrade("volt", "crit")
            elif val < SCHWELLEN["vbat"]["warn"]:
                alerts.append(("WARNUNG", f"VBAT: {val:.3f}V (< {SCHWELLEN['vbat']['warn']}V)"))
                _upgrade("volt", "warn")
        elif kat in SCHWELLEN["volt"]:
            lo, hi = SCHWELLEN["volt"][kat]
            if val < lo or val > hi:
                alerts.append(("WARNUNG", f"{name}: {val:.3f}V (Bereich {lo}-{hi}V)"))
                _upgrade("volt", "warn")

    # ── Luefter ──
    fan_data = sens.get("fans", {})
    if fan_data:
        _upgrade("fan", "ok")
        for name, rpm in fan_data.items():
            if rpm < SCHWELLEN["fan_min_rpm"]:
                alerts.append(("KRITISCH", f"{name}: 0 RPM – Luefterausfall?"))
                _upgrade("fan", "crit")

    # ── Systemlast ──
    if sys_m:
        _upgrade("system", "ok")
        for key, label in [("cpu_pct", "CPU"), ("ram_pct", "RAM"), ("disk_pct", "Disk")]:
            val = sys_m.get(key)
            if val is None:
                continue
            s = SCHWELLEN.get(key, (90, 98))
            if val >= s[1]:
                alerts.append(("KRITISCH", f"{label}-Auslastung: {val:.0f}%"))
                _upgrade("system", "crit")
            elif val >= s[0]:
                alerts.append(("WARNUNG", f"{label}-Auslastung: {val:.0f}%"))
                _upgrade("system", "warn")

    # ── Disks ──
    disk_data = sens.get("disks", [])
    if disk_data:
        _upgrade("disk", "ok")
        for d in disk_data:
            h = d.get("health", "").lower()
            if h and h != "healthy":
                alerts.append(("KRITISCH", f"Disk {d['name']}: {d['health']}"))
                _upgrade("disk", "crit")

    # ── Events ──
    kritische_ids = {"41", "1001"}
    for ev in events:
        if ev["id"] in kritische_ids:
            _upgrade("events", "crit")
            break
        if ev.get("level", "").lower() in ("fehler", "error", "kritisch", "critical"):
            _upgrade("events", "warn")

    # Gesamt
    stati = [v for v in status.values()]
    if "crit" in stati:
        status["gesamt"] = "crit"
    elif "warn" in stati:
        status["gesamt"] = "warn"
    elif all(s in ("ok", "na") for s in stati):
        status["gesamt"] = "ok"
    else:
        status["gesamt"] = "na"

    return status, alerts

# ═══════════════════════════════════════════════════════════════
# CSV-LOGGING
# ═══════════════════════════════════════════════════════════════

_CSV_SPALTEN = [
    "Zeitstempel", "CPU_Temp", "GPU_Temp", "MB_Temp", "SSD_Temp",
    "CPU_Fan", "Vcore", "V12", "V5", "V3_3", "VBAT",
    "CPU_Pct", "RAM_Pct", "RAM_GB", "Disk_Pct", "Disk_Health", "Alerts",
]

def _schreibe_csv(sens: dict, sys_m: dict, alerts: list):
    pfad = _csv_pfad()
    neu = not pfad.exists()
    try:
        with open(pfad, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_CSV_SPALTEN, delimiter="\t",
                               extrasaction="ignore")
            if neu:
                w.writeheader()
            def _tv(kat):
                e = sens.get("temps", {}).get(kat)
                return f"{e[1]:.1f}" if e else ""
            def _vv(kat):
                e = sens.get("volts", {}).get(kat)
                return f"{e[1]:.3f}" if e else ""
            fans = sens.get("fans", {})
            cpu_fan = ""
            for n, v in fans.items():
                if "cpu" in n.lower():
                    cpu_fan = f"{v:.0f}"
                    break
            dh = "; ".join(d["health"] for d in sens.get("disks", []))
            al = "; ".join(f"{l}: {t}" for l, t in alerts) if alerts else ""
            w.writerow({
                "Zeitstempel": _ts(),
                "CPU_Temp": _tv("cpu"), "GPU_Temp": _tv("gpu"),
                "MB_Temp": _tv("mb"), "SSD_Temp": _tv("disk"),
                "CPU_Fan": cpu_fan,
                "Vcore": _vv("vcore"), "V12": _vv("+12v"),
                "V5": _vv("+5v"), "V3_3": _vv("+3.3v"), "VBAT": _vv("vbat"),
                "CPU_Pct": f"{sys_m['cpu_pct']:.1f}" if sys_m.get("cpu_pct") is not None else "",
                "RAM_Pct": f"{sys_m['ram_pct']:.1f}" if sys_m.get("ram_pct") is not None else "",
                "RAM_GB": f"{sys_m['ram_used_gb']:.1f}" if sys_m.get("ram_used_gb") is not None else "",
                "Disk_Pct": f"{sys_m['disk_pct']:.1f}" if sys_m.get("disk_pct") is not None else "",
                "Disk_Health": dh, "Alerts": al,
            })
            f.flush()
    except Exception as e:
        _alert_logger.warning(f"{_iso()} | FEHLER | CSV-Schreiben: {e}")

def _logge_alerts(alerts: list):
    for level, text in alerts:
        _alert_logger.warning(f"{_iso()} | {level} | {text}")

# ═══════════════════════════════════════════════════════════════
# DATENSAMMLUNG (ein Zyklus)
# ═══════════════════════════════════════════════════════════════

def sammle_daten(events: list) -> dict:
    sens = lese_sensoren()
    sys_m = lese_system()
    status, alerts = pruefe_alerts(sens, sys_m, events)
    _schreibe_csv(sens, sys_m, alerts)
    if alerts:
        _logge_alerts(alerts)
    return {
        "zeit": _ts(), "sens": sens, "sys": sys_m,
        "status": status, "alerts": alerts,
    }

# ═══════════════════════════════════════════════════════════════
# GUI
# ═══════════════════════════════════════════════════════════════

_STATUS_FARBE = {"ok": _GREEN, "warn": _YELLOW, "crit": _RED, "na": _DIM}
_STATUS_LABELS = [
    ("temp", "Temp"), ("volt", "Spannung"), ("fan", "Luefter"),
    ("system", "System"), ("disk", "Disk"), ("events", "Events"),
]

class DiagnoseApp:
    """tkinter-GUI fuer System Health Monitor."""

    def __init__(self, events: list, admin: bool):
        self._events = events
        self._admin = admin
        self._queue: Queue = Queue()
        self._running = True
        self._vorherige_sensoren: set = set()

        self._root = tk.Tk()
        self._root.title("PC Diagnose \u2013 System Health Monitor")
        self._root.configure(bg=_BG)
        self._root.minsize(760, 620)
        self._root.protocol("WM_DELETE_WINDOW", self._beenden)
        self._root.bind("<Escape>", lambda _: self._beenden())

        self._baue_gui()
        self._zeige_start_events()

        # psutil vorwaermen
        if _HAS_PSUTIL:
            psutil.cpu_percent(interval=None)

        # Worker-Thread starten
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        self._root.after(800, self._update_gui)

    # ── GUI-Aufbau ──────────────────────────────────────────

    def _baue_gui(self):
        r = self._root
        mono = ("Consolas", 10)
        mono_s = ("Consolas", 9)

        # Header
        hf = tk.Frame(r, bg=_CARD, padx=10, pady=6)
        hf.pack(fill="x")
        tk.Label(hf, text="PC Diagnose \u2013 System Health Monitor",
                 font=("Consolas", 13, "bold"), fg=_TEXT, bg=_CARD).pack(side="left")
        admin_txt = "\u2714 Admin" if self._admin else "\u26a0 Kein Admin"
        admin_fg = _GREEN if self._admin else _YELLOW
        tk.Label(hf, text=admin_txt, font=mono_s, fg=admin_fg, bg=_CARD).pack(side="right")

        # Status-LEDs
        sf = tk.Frame(r, bg=_BG, pady=4)
        sf.pack(fill="x")
        self._leds: dict[str, tk.Label] = {}
        inner = tk.Frame(sf, bg=_BG)
        inner.pack()
        for kat, label in _STATUS_LABELS:
            frm = tk.Frame(inner, bg=_BG, padx=8)
            frm.pack(side="left")
            led = tk.Label(frm, text="\u25cf", font=("", 16), fg=_DIM, bg=_BG)
            led.pack()
            tk.Label(frm, text=label, font=mono_s, fg=_DIM, bg=_BG).pack()
            self._leds[kat] = led
        # Gesamt
        frm_g = tk.Frame(inner, bg=_BG, padx=16)
        frm_g.pack(side="left")
        self._led_gesamt = tk.Label(frm_g, text="\u25cf", font=("", 20), fg=_DIM, bg=_BG)
        self._led_gesamt.pack()
        tk.Label(frm_g, text="GESAMT", font=("Consolas", 9, "bold"), fg=_TEXT, bg=_BG).pack()

        # Trennlinie
        tk.Frame(r, bg=_BORDER, height=1).pack(fill="x")

        # Hauptbereich (zwei Spalten)
        main = tk.Frame(r, bg=_BG)
        main.pack(fill="both", expand=True, padx=6, pady=4)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        def _box(parent, title, row, col):
            f = tk.LabelFrame(parent, text=f"  {title}  ", font=mono_s,
                              fg=_BLUE, bg=_CARD, bd=1, relief="solid",
                              labelanchor="nw", padx=6, pady=4)
            f.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)
            t = tk.Text(f, font=mono, fg=_TEXT, bg=_CARD, bd=0,
                        highlightthickness=0, wrap="none", height=6, width=32)
            t.pack(fill="both", expand=True)
            for tag, color in [("ok", _GREEN), ("warn", _YELLOW),
                               ("crit", _RED), ("dim", _DIM), ("lbl", _DIM)]:
                t.tag_configure(tag, foreground=color)
            t.configure(state="disabled")
            return t

        self._txt_temp = _box(main, "Temperaturen", 0, 0)
        self._txt_volt = _box(main, "Spannungen", 0, 1)
        self._txt_fan  = _box(main, "Luefter", 1, 0)
        self._txt_sys  = _box(main, "Systemlast / Disk", 1, 1)

        tk.Frame(r, bg=_BORDER, height=1).pack(fill="x")

        # Events-Bereich
        ef = tk.LabelFrame(r, text="  Windows Events (letzte kritische)  ",
                           font=mono_s, fg=_BLUE, bg=_CARD, bd=1,
                           relief="solid", padx=6, pady=2)
        ef.pack(fill="x", padx=6, pady=2)
        self._txt_events = tk.Text(ef, font=mono_s, fg=_TEXT, bg=_CARD, bd=0,
                                   highlightthickness=0, wrap="word", height=4)
        self._txt_events.pack(fill="x")
        for tag, color in [("warn", _YELLOW), ("crit", _RED), ("dim", _DIM)]:
            self._txt_events.tag_configure(tag, foreground=color)
        self._txt_events.configure(state="disabled")

        tk.Frame(r, bg=_BORDER, height=1).pack(fill="x")

        # Log-Bereich
        lf = tk.LabelFrame(r, text="  Log  ", font=mono_s, fg=_BLUE,
                           bg=_CARD, bd=1, relief="solid", padx=6, pady=2)
        lf.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        self._txt_log = tk.Text(lf, font=mono_s, fg=_TEXT, bg=_CARD, bd=0,
                                highlightthickness=0, wrap="word", height=6)
        sb = tk.Scrollbar(lf, command=self._txt_log.yview)
        self._txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._txt_log.pack(side="left", fill="both", expand=True)
        for tag, color in [("ok", _GREEN), ("warn", _YELLOW),
                           ("crit", _RED), ("dim", _DIM), ("info", _BLUE)]:
            self._txt_log.tag_configure(tag, foreground=color)
        self._txt_log.configure(state="disabled")

    # ── Text-Helfer ─────────────────────────────────────────

    def _text_set(self, widget: tk.Text, content: list[tuple[str, str]]):
        """Ersetzt Inhalt eines Text-Widgets. content = [(text, tag), ...]"""
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        for text, tag in content:
            widget.insert("end", text, tag)
        widget.configure(state="disabled")

    def _log(self, text: str, tag: str = "dim"):
        w = self._txt_log
        w.configure(state="normal")
        w.insert("end", f"[{_ts()}] {text}\n", tag)
        # Zeilen begrenzen
        zeilen = int(w.index("end-1c").split(".")[0])
        if zeilen > MAX_LOG_ZEILEN:
            w.delete("1.0", f"{zeilen - MAX_LOG_ZEILEN}.0")
        w.see("end")
        w.configure(state="disabled")

    # ── Start-Events ────────────────────────────────────────

    def _zeige_start_events(self):
        self._log("System Health Monitor gestartet", "info")
        if not self._admin:
            self._log("Nicht als Administrator gestartet – einige Sensoren "
                      "oder Events sind moeglicherweise nicht verfuegbar", "warn")
        if not _HAS_PSUTIL:
            self._log("psutil nicht installiert – Systemmetriken nicht verfuegbar", "warn")

        lines: list[tuple[str, str]] = []
        if not self._events:
            lines.append(("  Keine kritischen Ereignisse gefunden.\n", "dim"))
        for ev in self._events:
            tag = "crit" if ev["id"] in ("41", "1001") else "warn"
            lines.append((f"  {ev['zeit']}  ID {ev['id']}  {ev['quelle']}\n", tag))
            lines.append((f"    {ev['msg']}\n", "dim"))
        self._text_set(self._txt_events, lines)

        if self._events:
            kp = sum(1 for e in self._events if e["id"] == "41")
            bc = sum(1 for e in self._events if e["id"] == "1001")
            if kp:
                self._log(f"Kernel-Power 41 (unerwartete Abschaltung): {kp}x gefunden", "crit")
            if bc:
                self._log(f"BugCheck (BSOD): {bc}x gefunden", "crit")
            andere = len(self._events) - kp - bc
            if andere:
                self._log(f"Weitere kritische System-Events: {andere}", "warn")
        else:
            self._log("Keine kritischen Windows-Events gefunden", "ok")

        self._log(f"Messintervall: {INTERVALL_S}s | CSV: system_metrics_*.csv", "info")
        self._log(f"Alert-Log: {ALERT_LOG.name}", "info")

    # ── Daten-Anzeige ──────────────────────────────────────

    def _zeige_daten(self, daten: dict):
        sens = daten["sens"]
        sys_m = daten["sys"]
        status = daten["status"]
        alerts = daten["alerts"]

        # Status-LEDs aktualisieren
        for kat, _ in _STATUS_LABELS:
            farbe = _STATUS_FARBE.get(status.get(kat, "na"), _DIM)
            self._leds[kat].configure(fg=farbe)
        self._led_gesamt.configure(fg=_STATUS_FARBE.get(status.get("gesamt", "na"), _DIM))
        # Fenstertitel
        gs = status.get("gesamt", "na")
        sym = {"ok": "\u2714", "warn": "\u26a0", "crit": "\u2716", "na": "\u2013"}
        self._root.title(f"PC Diagnose {sym.get(gs, '')} [{gs.upper()}]")

        # ── Temperaturen ──
        lines: list[tuple[str, str]] = []
        for kat, (name, val) in sorted(sens.get("temps", {}).items()):
            s = SCHWELLEN["temp"].get(kat, SCHWELLEN["temp"]["default"])
            tag = "crit" if val >= s[1] else ("warn" if val >= s[0] else "ok")
            lines.append((f"  {name:<22s}", "lbl"))
            lines.append((f"{val:>6.1f}\u00b0C\n", tag))
        if not lines:
            lines.append(("  Keine Sensoren verfuegbar\n", "dim"))
        self._text_set(self._txt_temp, lines)

        # ── Spannungen ──
        lines = []
        for kat, (name, val) in sorted(sens.get("volts", {}).items()):
            tag = "ok"
            if kat == "vbat":
                if val < SCHWELLEN["vbat"]["crit"]:
                    tag = "crit"
                elif val < SCHWELLEN["vbat"]["warn"]:
                    tag = "warn"
            elif kat in SCHWELLEN["volt"]:
                lo, hi = SCHWELLEN["volt"][kat]
                if val < lo or val > hi:
                    tag = "warn"
            lines.append((f"  {name:<22s}", "lbl"))
            lines.append((f"{val:>8.3f} V\n", tag))
        if not lines:
            lines.append(("  Keine Sensoren verfuegbar\n", "dim"))
        self._text_set(self._txt_volt, lines)

        # ── Luefter ──
        lines = []
        for name, rpm in sorted(sens.get("fans", {}).items()):
            tag = "crit" if rpm < SCHWELLEN["fan_min_rpm"] else "ok"
            lines.append((f"  {name:<22s}", "lbl"))
            lines.append((f"{rpm:>6.0f} RPM\n", tag))
        if not lines:
            lines.append(("  Keine Sensoren verfuegbar\n", "dim"))
        self._text_set(self._txt_fan, lines)

        # ── Systemlast + Disk ──
        lines = []
        if sys_m:
            cpu_p = sys_m.get("cpu_pct")
            ram_p = sys_m.get("ram_pct")
            disk_p = sys_m.get("disk_pct")
            if cpu_p is not None:
                s = SCHWELLEN["cpu_pct"]
                tag = "crit" if cpu_p >= s[1] else ("warn" if cpu_p >= s[0] else "ok")
                lines.append((f"  {'CPU:':<14s}", "lbl"))
                lines.append((f"{cpu_p:>5.1f}%\n", tag))
            if ram_p is not None:
                s = SCHWELLEN["ram_pct"]
                tag = "crit" if ram_p >= s[1] else ("warn" if ram_p >= s[0] else "ok")
                used = sys_m.get("ram_used_gb", 0)
                total = sys_m.get("ram_total_gb", 0)
                lines.append((f"  {'RAM:':<14s}", "lbl"))
                lines.append((f"{ram_p:>5.1f}%  ({used:.1f}/{total:.1f} GB)\n", tag))
            if disk_p is not None:
                s = SCHWELLEN["disk_pct"]
                tag = "crit" if disk_p >= s[1] else ("warn" if disk_p >= s[0] else "ok")
                lines.append((f"  {'Disk C:\\:':<14s}", "lbl"))
                lines.append((f"{disk_p:>5.1f}%\n", tag))
        else:
            lines.append(("  psutil nicht verfuegbar\n", "dim"))

        # Disk Health
        for d in sens.get("disks", []):
            h = d.get("health", "")
            tag = "ok" if h.lower() == "healthy" else "crit"
            lines.append((f"  {d['name'][:20]:<22s}", "lbl"))
            lines.append((f"{h}\n", tag))
        self._text_set(self._txt_sys, lines)

        # ── Sensor-Verfuegbarkeit pruefen ──
        aktuelle = set()
        for gruppe in ("temps", "fans", "volts"):
            for k in sens.get(gruppe, {}):
                aktuelle.add(f"{gruppe}:{k}")
        if self._vorherige_sensoren and self._vorherige_sensoren != aktuelle:
            verschwunden = self._vorherige_sensoren - aktuelle
            for s in verschwunden:
                self._log(f"Sensor nicht mehr verfuegbar: {s}", "warn")
                _alert_logger.warning(f"{_iso()} | WARNUNG | Sensor verschwunden: {s}")
        self._vorherige_sensoren = aktuelle

        # ── Alerts loggen ──
        for level, text in alerts:
            tag = "crit" if level == "KRITISCH" else "warn"
            self._log(f"{level}: {text}", tag)

        if not alerts and status.get("gesamt") == "ok":
            self._log("Alle Werte im Normalbereich", "ok")

    # ── Worker-Thread ──────────────────────────────────────

    def _worker_loop(self):
        while self._running:
            t0 = time.monotonic()
            try:
                daten = sammle_daten(self._events)
                self._queue.put(daten)
            except Exception as e:
                self._queue.put({"fehler": str(e)})
                _alert_logger.warning(f"{_iso()} | FEHLER | Worker: {e}")
            dt = time.monotonic() - t0
            warten = max(0, INTERVALL_S - dt)
            ende = time.monotonic() + warten
            while self._running and time.monotonic() < ende:
                time.sleep(0.1)

    def _update_gui(self):
        try:
            while True:
                daten = self._queue.get_nowait()
                if "fehler" in daten:
                    self._log(f"Messfehler: {daten['fehler']}", "crit")
                else:
                    self._zeige_daten(daten)
        except Empty:
            pass
        if self._running:
            self._root.after(500, self._update_gui)

    # ── Steuerung ──────────────────────────────────────────

    def _beenden(self):
        self._running = False
        self._root.destroy()

    def starten(self):
        self._root.mainloop()

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    admin = _ist_admin()

    # psutil CPU-Zaehler vorwaermen (erster Aufruf liefert 0)
    if _HAS_PSUTIL:
        psutil.cpu_percent(interval=None)

    # Events einmalig beim Start lesen
    events = []
    try:
        events = lese_events()
    except Exception:
        pass

    app = DiagnoseApp(events=events, admin=admin)
    app.starten()


if __name__ == "__main__":
    main()
