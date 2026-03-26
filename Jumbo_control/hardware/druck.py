"""
hardware/druck.py
Modul zum Auslesen des Pfeiffer TPG 366 MaxiGauge über COM5.

Verwendung:
    from hardware.druck import DruckMessung

    d = DruckMessung()
    werte = d.messen()
    d.beenden()

    Oder als Context Manager:
    with DruckMessung() as d:
        werte = d.messen()
"""

import time
import serial
from config import MAXIGAUGE_PORT

# ── Konfiguration ──────────────────────────────────────────────
BAUDRATE   = 9600
TIMEOUT    = 0.2
ALLE_KANAELE = [1, 2, 4]   # Belegte Kanäle: DOOR, CENTER, BA

# Sensor-Statuscodes laut Pfeiffer-Protokoll
SENSOR_STATUS = {
    "0": "OK",
    "1": "Underrange",
    "2": "Overrange",
    "3": "Sensor error",
    "4": "Sensor off",
    "5": "No sensor",
    "6": "Identification error",
}

# Einheitencodes
EINHEITEN = {
    "0": "mbar",
    "1": "Torr",
    "2": "Pa",
    "3": "Micron",
    "4": "hPa",
    "5": "V",
}

KANAL_NAMEN = {
    1: "DOOR",
    2: "CENTER",
    4: "BA",
}


ACK = b'\x06'
ENQ = b'\x05'

def _befehl(ser, befehl: str):
    """
    Sendet einen Befehl an den TPG 366.
    Protokoll: Befehl senden → ACK empfangen → ENQ senden → Antwort lesen.
    """
    try:
        ser.reset_input_buffer()
        ser.write((befehl + "\r\n").encode("ascii"))
        # ACK + CR + LF lesen
        ack = b""
        deadline_ack = time.time() + TIMEOUT
        while time.time() < deadline_ack and b"\n" not in ack:
            ack += ser.read(ser.in_waiting or 1)
        if ACK not in ack:
            return False, f"Kein ACK: {repr(ack)}"
        # ENQ senden
        ser.write(ENQ)
        # Antwort lesen
        antwort = b""
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            chunk = ser.read(ser.in_waiting or 1)
            antwort += chunk
            if b"\r" in antwort or b"\n" in antwort:
                break
        if not antwort.strip():
            return False, "Keine Antwort nach ENQ"
        return True, antwort.decode("ascii").strip()
    except Exception as e:
        return False, str(e)


def _parse_druck(antwort: str):
    """Zerlegt Antwort 'status,wert' in (statuscode, float oder None)."""
    teile = antwort.split(",")
    if len(teile) == 2:
        code = teile[0].strip()
        try:
            return code, float(teile[1].strip())
        except ValueError:
            return code, None
    return "?", None


class DruckMessung:
    """
    Verwaltet die serielle Verbindung zum TPG 366 MaxiGauge
    und liest alle 6 Druckkanäle aus.

    Beispiel:
        d = DruckMessung()
        werte = d.messen()
        # werte[1] = {
        #     "mbar":    9.95e+0,
        #     "einheit": "mbar",
        #     "status":  "OK",
        #     "gueltig": True
        # }
        # werte[4] = {
        #     "mbar":    None,
        #     "einheit": "mbar",
        #     "status":  "kein Sensor",
        #     "gueltig": False
        # }
        d.beenden()
    """

    def __init__(self, port=MAXIGAUGE_PORT):
        self._port    = port
        self._ser     = None
        self._einheit = "mbar"
        self._verbinden()

    def _verbinden(self):
        self._ser = serial.Serial(
            port=self._port,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=TIMEOUT,
        )
        # Einheit auslesen
        ok, wert = _befehl(self._ser, "UNI")
        if ok:
            self._einheit = EINHEITEN.get(wert.strip(), "mbar")

    def messen(self):
        """
        Liest Kanäle 1, 2, 4 einzeln mit PR<n>.

        Rückgabe: dict mit Kanalnummer als Schlüssel, z.B.:
        {
            1: {"name": "DOOR",   "mbar": 9.95e+0, "einheit": "mbar", "status": "OK", "gueltig": True},
            2: {"name": "CENTER", "mbar": 9.48e+0, "einheit": "mbar", "status": "OK", "gueltig": True},
            4: {"name": "BA",     "mbar": None,    "einheit": "mbar", "status": "Überdruck", "gueltig": False},
        }
        """
        ergebnis = {}
        for kanal in ALLE_KANAELE:
            ok, antwort = _befehl(self._ser, f"PR{kanal}")
            if ok:
                code, wert = _parse_druck(antwort)
                status  = SENSOR_STATUS.get(code, f"Unbekannt ({code})")
                gueltig = code == "0" and wert is not None
            else:
                wert, status, gueltig = None, f"Fehler: {antwort}", False

            name = KANAL_NAMEN.get(kanal, f"Kanal {kanal}")
            ergebnis[name] = {
                "name":    name,
                "mbar":    wert,  # kein round() – zerstört Werte im e-7-Bereich und kleiner
                "einheit": self._einheit,
                "status":  status,
                "gueltig": gueltig,
            }
        return ergebnis

    @property
    def einheit(self):
        return self._einheit

    def beenden(self):
        """Serielle Verbindung schließen."""
        if self._ser and self._ser.is_open:
            self._ser.close()
            self._ser = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.beenden()


# ── Direktaufruf zum Testen ────────────────────────────────────
if __name__ == "__main__":
    with DruckMessung() as d:
        print(f"\n{'='*55}")
        print(f"  TPG 366 MaxiGauge  |  {d.einheit}  |  {MAXIGAUGE_PORT}")
        print(f"{'='*55}")
        werte = d.messen()
        for kanal, w in werte.items():
            name = w["name"]
            if w["gueltig"]:
                print(f"  K{kanal} {name:<8}:  {w['mbar']:.3E} {w['einheit']}  ({w['status']})")
            else:
                print(f"  K{kanal} {name:<8}:  ---  ({w['status']})")
        print(f"{'='*55}")
