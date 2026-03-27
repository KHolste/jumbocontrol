"""
hardware/coolpack.py
Kommunikationsmodul für Sumitomo/Leybold Coolpack 6000.
Protokoll: 4800,8,N,1, kein Handshake
Nachrichtenformat: STX "Befehl" [Parameter] CR

Befehle:
    DAT          → Alle Statusdaten abfragen
    SYS 0/1      → System AUS/EIN
    SC x y       → Cold Head x (1/2) y=0 AUS / y=1 EIN  (nur 4000D/6000D)
    ERR          → Fehlerprotokoll abfragen

Verwendung:
    from hardware.coolpack import Coolpack
    c = Coolpack("COM12", name="Kryo 1")
    status = c.status()
    c.einschalten()
    c.ausschalten()
"""

import serial
import time
from log_utils import tprint

STX = b'\x02'
CR  = b'\x0d'

WARTUNGSINTERVALL_H = 10000

FEHLERCODES = {
    1:  "SYSTEM ERROR",
    2:  "Compressor fail (KLIXON)",
    3:  "Locked rotor",
    4:  "OVERLOAD",
    5:  "Phase/fuse ERROR",
    6:  "Pressure alarm",
    7:  "Helium temp. fail",
    8:  "Oil circuit fail",
    9:  "RAM ERROR",
    10: "ROM ERROR",
    11: "EEPROM ERROR",
    12: "DC Voltage error",
    13: "MAINS LEVEL",
}


def _befehl_bytes(befehl: str) -> bytes:
    return STX + befehl.encode("ascii") + CR


class Coolpack:
    """
    Steuert einen Sumitomo/Leybold Coolpack 6000 Kompressor.

    Beispiel:
        c = Coolpack("COM12", name="Kryo 1")
        st = c.status()
        print(st["betriebsstunden"], st["kompressor_an"])
        c.einschalten()
        c.ausschalten()
    """

    def __init__(self, port: str, name: str = "", timeout: float = 1.5):
        self.port    = port
        self.name    = name or port
        self._timeout = timeout
        self._ser    = None
        self._verbinden()

    def _verbinden(self):
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=4800,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self._timeout,
                rtscts=False,
                dsrdtr=False
            )
            time.sleep(0.3)
        except Exception as e:
            tprint(f"Coolpack {self.name}", f"Verbindungsfehler: {e}")
            self._ser = None

    def _sende(self, befehl: str) -> str:
        """Sendet Befehl und gibt dekodierte Antwort zurück."""
        if not self._ser:
            return ""
        try:
            self._ser.reset_input_buffer()
            self._ser.write(_befehl_bytes(befehl))
            rohdaten = b""
            deadline = time.time() + self._timeout
            while time.time() < deadline:
                chunk = self._ser.read(self._ser.in_waiting or 1)
                rohdaten += chunk
                if rohdaten.endswith(CR):
                    break
            return rohdaten.decode("ascii", errors="replace").strip()
        except Exception as e:
            tprint(f"Coolpack {self.name}", f"Kommunikationsfehler: {e}")
            return ""

    def status(self) -> dict:
        """
        Fragt alle Statusdaten ab (DAT-Befehl).

        Rückgabe:
        {
            "name":              "Kryo 1",
            "port":              "COM12",
            "gueltig":           True,
            "kompressor_an":     False,
            "command_status":    "OFF",
            "betriebsstunden":   4439,
            "software_version":  "4.01",
            "switch_on_timer":   0,
            "cold_head":         "1/0",
            "aktive_fehler":     0,
            "fehlerbits":        "0000000000000000",
            "fehler_liste":      [],
            "wartung_faellig":   False,
            "wartung_in_h":      5561,
        }
        """
        antwort = self._sende("DAT")
        ergebnis = {
            "name":             self.name,
            "port":             self.port,
            "gueltig":          False,
            "kompressor_an":    None,
            "command_status":   None,
            "betriebsstunden":  None,
            "software_version": None,
            "switch_on_timer":  None,
            "cold_head":        None,
            "aktive_fehler":    None,
            "fehlerbits":       None,
            "fehler_liste":     [],
            "wartung_faellig":  False,
            "wartung_in_h":     None,
        }

        if not antwort or "\x02DAT" not in antwort:
            return ergebnis

        try:
            teil  = antwort.replace("\x02", "").replace("\r", "").strip()
            werte = teil[3:].split("/")  # nach "DAT" aufteilen

            def w(i): return werte[i].strip('"') if i < len(werte) else ""

            # [ 0] SW-Version
            # [ 1] Interne Nummer (Leybold only)
            # [ 2] Betriebsstunden (Display-Wert)
            # [ 3] Temperatur 1 (intern)
            # [ 4] Temperatur 2 (intern)
            # [ 5] Switch-ON Timer [sec] (00.x Format)
            # [ 6] Fehler-Code (000 = kein Fehler)
            # [ 7] Command Status (0=OFF, 1=ON, 2=SYSTEM ERROR)
            # [ 8] Kompressor Status (0=OFF, 1=ON)
            # [ 9] Cold Head Status (0=OFF, 1=ON)
            # [10] nicht verwendet
            # [11] Anzahl aktiver Fehler
            # [12] Fehlerbits (16 Stellen)
            # [13] Anzahl gespeicherter Fehler

            ergebnis["software_version"] = w(0)

            stunden_str = w(2).lstrip("0") or "0"
            try:
                ergebnis["betriebsstunden"] = int(stunden_str)
            except ValueError:
                pass

            timer_str = w(5)
            try:
                ergebnis["switch_on_timer"] = float(timer_str)
            except ValueError:
                pass

            cmd = w(7)
            ergebnis["command_status"] = {"0": "OFF", "1": "ON",
                                           "2": "SYSTEM ERROR"}.get(cmd, cmd)

            st = w(8)
            ergebnis["kompressor_an"] = st == "1"

            ergebnis["cold_head"] = w(9)

            fehler_str = w(11)
            try:
                ergebnis["aktive_fehler"] = int(fehler_str)
            except ValueError:
                pass

            bits = w(12)
            ergebnis["fehlerbits"] = bits
            # Aktive Fehler aus Bitmaske dekodieren
            if bits:
                for i, bit in enumerate(reversed(bits)):
                    if bit == "1" and (i + 1) in FEHLERCODES:
                        ergebnis["fehler_liste"].append(
                            f"[{i+1}] {FEHLERCODES[i+1]}"
                        )

            # Wartung
            if ergebnis["betriebsstunden"] is not None:
                verbleibend = WARTUNGSINTERVALL_H - ergebnis["betriebsstunden"]
                ergebnis["wartung_in_h"]   = max(0, verbleibend)
                ergebnis["wartung_faellig"] = verbleibend <= 0

            ergebnis["gueltig"] = True

        except Exception as e:
            tprint(f"Coolpack {self.name}", f"Parse-Fehler: {e}")

        return ergebnis

    def einschalten(self) -> bool:
        """Schaltet Kompressor EIN (SYS 1)."""
        r = self._sende("SYS1")
        an = "SYS1" in r
        tprint(f"Coolpack {self.name}", f"EIN → {r!r}")
        return an

    def ausschalten(self) -> bool:
        """Schaltet Kompressor AUS (SYS 0)."""
        r = self._sende("SYS0")
        aus = "SYS0" in r
        tprint(f"Coolpack {self.name}", f"AUS → {r!r}")
        return aus

    def fehler_abfragen(self) -> list:
        """Fragt gespeicherte Fehler ab (ERR-Befehl)."""
        antwort = self._sende("ERR")
        fehler = []
        if not antwort:
            return fehler
        try:
            teil   = antwort.replace("\x02", "").replace("\r", "").strip()
            einzel = teil[3:].split("\x02")  # mehrere ERR-Blöcke
            for block in einzel:
                teile = block.strip().split("/")
                if len(teile) >= 2:
                    code_str = teile[0].strip('"')
                    stunden  = teile[1].strip('"')
                    if code_str.isdigit():
                        code = int(code_str)
                        name = FEHLERCODES.get(code, f"Fehler {code}")
                        fehler.append({
                            "code":     code,
                            "name":     name,
                            "stunden":  stunden,
                        })
        except Exception as e:
            tprint(f"Coolpack {self.name}", f"ERR Parse-Fehler: {e}")
        return fehler

    def beenden(self):
        if self._ser and self._ser.is_open:
            self._ser.close()


if __name__ == "__main__":
    from config import COOLPACK_PORTS
    for name, port in COOLPACK_PORTS.items():
        print(f"\n{'='*45}")
        c = Coolpack(port, name=name)
        st = c.status()
        if st["gueltig"]:
            print(f"  {name} ({port})")
            print(f"    Status:       {st['command_status']}")
            print(f"    Betriebsstd.: {st['betriebsstunden']} h")
            print(f"    SW-Version:   {st['software_version']}")
            print(f"    Wartung in:   {st['wartung_in_h']} h  "
                  f"{'⚠ FÄLLIG!' if st['wartung_faellig'] else ''}")
            if st["fehler_liste"]:
                print(f"    Fehler:       {', '.join(st['fehler_liste'])}")
        else:
            print(f"  {name} ({port}): keine Antwort")
        c.beenden()
