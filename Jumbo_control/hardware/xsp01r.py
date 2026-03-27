"""
hardware/xsp01r.py
Steuerung des ZEB XSP01R über RS232 (COM6, 9600,8,N,1).

Relaisbelegung Jumbo:
    Bit 0 (Relais 1) → Kryo 1  System EIN/AUS
    Bit 1 (Relais 2) → Kryo 1  Remote EIN/AUS
    Bit 2 (Relais 3) → Kryo 2  System EIN/AUS
    Bit 3 (Relais 4) → Kryo 2  Remote EIN/AUS

Protokoll:
    Ausgänge lesen:  O<CR>           → O<high><low><CR>
    Ausgänge setzen: O<high><low><CR> → keine Antwort
    Eingänge lesen:  I<CR>           → I<high><low><CR>

Kodierung: '@'=0000, 'A'=0001, 'B'=0010 ... 'O'=1111
           high = Bit7..4, low = Bit3..0
"""

import serial
import time
from config import XSP01R_PORT, XSP01R_TIMEOUT
from log_utils import tprint

# Bit-Zuordnung
BIT_KRYO1_SYSTEM = 0   # Relais 1
BIT_KRYO1_REMOTE = 1   # Relais 2
BIT_KRYO2_SYSTEM = 2   # Relais 3
BIT_KRYO2_REMOTE = 3   # Relais 4


def _bits_zu_zeichen(bits: int) -> str:
    high = chr(ord('@') + ((bits >> 4) & 0x0F))
    low  = chr(ord('@') + (bits & 0x0F))
    return high + low

def _zeichen_zu_bits(high: str, low: str) -> int:
    h = ord(high) - ord('@')
    l = ord(low)  - ord('@')
    return ((h & 0x0F) << 4) | (l & 0x0F)


class XSP01R:

    def __init__(self, port=None, timeout=None):
        self._port    = port    or XSP01R_PORT
        self._timeout = timeout or XSP01R_TIMEOUT
        self._ser     = None
        self._verbinden()

    def _verbinden(self):
        try:
            self._ser = serial.Serial(
                port=self._port, baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self._timeout,
                rtscts=False, dsrdtr=False
            )
            self._ser.rts = True
            self._ser.dtr = True
            time.sleep(0.3)
            tprint("XSP01R", f"Verbunden auf {self._port}")
        except Exception as e:
            tprint("XSP01R", f"Verbindungsfehler: {e}")
            self._ser = None

    def _befehl(self, cmd: bytes) -> bytes:
        if not self._ser:
            return b""
        try:
            self._ser.reset_input_buffer()
            self._ser.write(cmd)
            time.sleep(0.15)
            return self._ser.read(self._ser.in_waiting or 16)
        except Exception as e:
            tprint("XSP01R", f"Kommunikationsfehler: {e}")
            return b""

    def _ausgaenge_lesen(self) -> int:
        r = self._befehl(b"O\r")
        try:
            d = r.decode("ascii").strip()
            if len(d) >= 3 and d[0] == 'O':
                return _zeichen_zu_bits(d[1], d[2])
        except Exception:
            pass
        return 0

    def _ausgaenge_setzen(self, bits: int):
        hoch, niedrig = _bits_zu_zeichen(bits)
        self._befehl(f"O{hoch}{niedrig}\r".encode("ascii"))

    def _bit_setzen(self, bit: int, an: bool):
        aktuell = self._ausgaenge_lesen()
        neu = (aktuell | (1 << bit)) if an else (aktuell & ~(1 << bit))
        self._ausgaenge_setzen(neu)

    # ── Kryo 1 ────────────────────────────────────────────────
    def kryo1_system_ein(self):
        self._bit_setzen(BIT_KRYO1_SYSTEM, True)
        print("[XSP01R] Kryo 1 System EIN")

    def kryo1_system_aus(self):
        self._bit_setzen(BIT_KRYO1_SYSTEM, False)
        print("[XSP01R] Kryo 1 System AUS")

    def kryo1_remote_ein(self):
        self._bit_setzen(BIT_KRYO1_REMOTE, True)
        print("[XSP01R] Kryo 1 Remote EIN")

    def kryo1_remote_aus(self):
        self._bit_setzen(BIT_KRYO1_REMOTE, False)
        print("[XSP01R] Kryo 1 Remote AUS")

    # ── Kryo 2 ────────────────────────────────────────────────
    def kryo2_system_ein(self):
        self._bit_setzen(BIT_KRYO2_SYSTEM, True)
        print("[XSP01R] Kryo 2 System EIN")

    def kryo2_system_aus(self):
        self._bit_setzen(BIT_KRYO2_SYSTEM, False)
        print("[XSP01R] Kryo 2 System AUS")

    def kryo2_remote_ein(self):
        self._bit_setzen(BIT_KRYO2_REMOTE, True)
        print("[XSP01R] Kryo 2 Remote EIN")

    def kryo2_remote_aus(self):
        self._bit_setzen(BIT_KRYO2_REMOTE, False)
        print("[XSP01R] Kryo 2 Remote AUS")



    # ── Kombiniert: System + Remote ───────────────────────────
    def kryo1_einschalten(self):
        """Schaltet Kryo 1 ein: erst System, dann Remote."""
        self.kryo1_system_ein()
        time.sleep(0.8)
        self.kryo1_remote_ein()
        print("[XSP01R] Kryo 1 EIN (System -> Remote)")
    
    def kryo1_ausschalten(self):
        """Schaltet Kryo 1 aus: erst System aus, dann Remote aus."""
        self.kryo1_system_aus()
        time.sleep(0.8)
        self.kryo1_remote_aus()
        print("[XSP01R] Kryo 1 AUS (System AUS -> Remote AUS)")
    
    def kryo2_einschalten(self):
        """Schaltet Kryo 2 ein: erst System, dann Remote."""
        self.kryo2_system_ein()
        time.sleep(0.8)
        self.kryo2_remote_ein()
        print("[XSP01R] Kryo 2 EIN (System -> Remote)")
    
    def kryo2_ausschalten(self):
        """Schaltet Kryo 2 aus: erst System aus, dann Remote aus."""
        self.kryo2_system_aus()
        time.sleep(0.8)
        self.kryo2_remote_aus()
        print("[XSP01R] Kryo 2 AUS (System AUS -> Remote AUS)")





    # ── Status ────────────────────────────────────────────────
    def status(self) -> dict:
        bits = self._ausgaenge_lesen()
        return {
            "kryo1_system": bool(bits & (1 << BIT_KRYO1_SYSTEM)),
            "kryo1_remote": bool(bits & (1 << BIT_KRYO1_REMOTE)),
            "kryo2_system": bool(bits & (1 << BIT_KRYO2_SYSTEM)),
            "kryo2_remote": bool(bits & (1 << BIT_KRYO2_REMOTE)),
            "bits_roh":     bits,
        }


    def xsp_status_als_kryo(self, kryo: int = 1) -> dict:
        """Gibt XSP01R-Status im Coolpack-Format zurück (für KryoZeile)."""
        try:
            st = self.status()
            an = st[f"kryo{kryo}_system"] and st[f"kryo{kryo}_remote"]
            return {
                "gueltig": True,
                "kompressor_an": an,
                "command_status": "ON" if an else "OFF",
                "betriebsstunden": None,
                "wartung_in_h": None,
                "wartung_faellig": False,
                "fehler_liste": [],
            }
        except Exception:
            return {"gueltig": False}
    

    def eingaenge_lesen(self) -> int:
        r = self._befehl(b"I\r")
        try:
            d = r.decode("ascii").strip()
            if len(d) >= 3 and d[0] == 'I':
                return _zeichen_zu_bits(d[1], d[2])
        except Exception:
            pass
        return 0

    def beenden(self):
        if self._ser and self._ser.is_open:
            self._ser.close()
            tprint("XSP01R", "Verbindung geschlossen")
