"""
hardware/steckdose.py
Modul zur Steuerung der ALLNET ALL4076 IP-Steckdosenleiste.
Protokoll: HTTP GET, XML-Antwort (laut ALL4076 Handbuch Seite 33)

Status alle:    GET /xml/?q=0
Schalten:       GET /xml/?q=1&actor=<nr>&switch=<0|1>
Status einzeln: GET /xml/?q=2&actor=<nr>

Verwendung:
    from hardware.steckdose import Steckdose

    s = Steckdose()
    status = s.status_alle()
    s.einschalten("Rotary")
    s.ausschalten("Rotary")
"""

import urllib.request
import xml.etree.ElementTree as ET
from config import STECKDOSE_IP, STECKDOSE_TIMEOUT
from log_utils import tprint

# ── Dosenzuordnung (Name → Aktornummer) ───────────────────────
# Aktornummern entsprechen der Konfiguration in der ALL4076
DOSEN = {
    "V1":     1,
    "Rotary": 2,
    "Roots":  3,
    "Vu":     4,
    "Heater": 5,
    "Slider": 6,
}

# actor_state: 0 = AUS, 1 = EIN, 2 = FEHLER (laut Handbuch S.34)
AKTOR_STATUS = {
    "0": "AUS",
    "1": "EIN",
    "2": "FEHLER",
}


def _get(url: str, timeout: float) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8")


def _fehler_klasse(exc: Exception) -> str:
    """Klassifiziert Netzwerkfehler für verständlichere Meldungen."""
    text = str(exc)
    if "10061" in text:
        return "Verbindung verweigert (Gerät antwortet nicht auf Port)"
    if "timed out" in text or "timeout" in text.lower():
        return "Zeitüberschreitung (Netzwerk/Gerät reagiert nicht)"
    if "10060" in text:
        return "Verbindung Zeitüberschreitung (Netzwerk nicht erreichbar)"
    if "10065" in text or "No route" in text:
        return "Kein Netzwerkpfad (Gerät nicht erreichbar)"
    return "Netzwerkfehler"


class Steckdose:
    """
    Steuert die ALLNET ALL4076 IP-Steckdosenleiste über HTTP/XML.

    Beispiel:
        s = Steckdose()
        status = s.status_alle()
        # status["Rotary"] = {"dose": 2, "an": True,  "status": "EIN", "gueltig": True}
        # status["Heater"] = {"dose": 5, "an": False, "status": "AUS", "gueltig": True}

        s.einschalten("Rotary")
        s.ausschalten("Heater")
        s.umschalten("V1")
    """

    def __init__(self, ip=STECKDOSE_IP):
        self._basis = f"http://{ip}/xml"
        self._online = True   # Zustandswechsel-Tracking

    def status_alle(self) -> dict:
        """
        Liest Status aller Dosen aus (?q=0).
        Rückgabe: dict mit Dosenname als Schlüssel.
        """
        url      = f"{self._basis}?mode=actor&type=list"
        ergebnis = {name: {"dose": nr, "an": None, "status": "unbekannt", "gueltig": False}
                    for name, nr in DOSEN.items()}
        try:
            body  = _get(url, STECKDOSE_TIMEOUT)
            aktoren = self._parse_alle(body)
            for name, nr in DOSEN.items():
                if nr in aktoren:
                    state = aktoren[nr]
                    ergebnis[name] = {
                        "dose":    nr,
                        "an":      state == "1",
                        "status":  AKTOR_STATUS.get(state, f"unbekannt ({state})"),
                        "gueltig": state in ("0", "1"),
                    }
            if not self._online:
                tprint("Steckdose", "Verbindung wiederhergestellt")
                self._online = True
        except Exception as e:
            if self._online:
                tprint("Steckdose", f"Offline – {_fehler_klasse(e)}: {e}")
                self._online = False
        return ergebnis

    def status(self, name: str) -> dict:
        """Status einer einzelnen Dose (?q=2&actor=<nr>)."""
        nr = DOSEN.get(name)
        if nr is None:
            return {"dose": None, "an": None, "status": "unbekannt", "gueltig": False}
        url = f"{self._basis}?mode=actor&type=list"
        try:
            body  = _get(url, STECKDOSE_TIMEOUT)
            state = self._parse_einzeln(body, nr)
            return {
                "dose":    nr,
                "an":      state == "1",
                "status":  AKTOR_STATUS.get(state, f"unbekannt ({state})"),
                "gueltig": state in ("0", "1"),
            }
        except Exception as e:
            tprint("Steckdose", f"Fehler status {name}: {e}")
            return {"dose": nr, "an": None, "status": "Fehler", "gueltig": False}

    def einschalten(self, name: str) -> bool:
        """Schaltet eine Dose ein."""
        return self._schalten(name, True)

    def ausschalten(self, name: str) -> bool:
        """Schaltet eine Dose aus."""
        return self._schalten(name, False)

    def umschalten(self, name: str) -> bool:
        """Schaltet eine Dose um (Toggle)."""
        aktuell = self.status(name)
        if not aktuell["gueltig"]:
            return False
        return self._schalten(name, not aktuell["an"])

    def _schalten(self, name: str, an: bool) -> bool:
        nr = DOSEN.get(name)
        if nr is None:
            tprint("Steckdose", f"Unbekannte Dose: {name}")
            return False
        wert = 1 if an else 0
        url  = f"{self._basis}?mode=actor&type=switch&id={nr}&action={wert}"
        try:
            body  = _get(url, STECKDOSE_TIMEOUT)
            # actor_setstate: 0=AUS, 1=EIN, 3=Nichts zu tun
            state = self._parse_setstate(body)
            tprint("Steckdose", f"{name} (Dose {nr}) → {'EIN' if an else 'AUS'}  (setstate={state})")
            return True
        except Exception as e:
            tprint("Steckdose", f"Fehler beim Schalten von {name}: {_fehler_klasse(e)}: {e}")
            return False

    def _parse_alle(self, body: str) -> dict:
        """Parst /xml?mode=actor&type=list → {id: state}"""
        zustaende = {}
        try:
            root = ET.fromstring(body)
            for actor in root.iter("actor"):
                aid   = actor.findtext("id")
                state = actor.findtext("state")
                if aid is not None and state is not None:
                    zustaende[int(aid)] = state.strip()
        except ET.ParseError as e:
            tprint("Steckdose", f"XML-Fehler: {e}\nBody: {body[:200]}")
        return zustaende

    def _parse_einzeln(self, body: str, nr: int) -> str:
        """Parst list-XML und gibt state für Aktor nr zurück"""
        alle = self._parse_alle(body)
        return alle.get(nr, "?")

    def _parse_setstate(self, body: str) -> str:
        """Parst Schalt-Antwort → state als String"""
        try:
            root  = ET.fromstring(body)
            state = root.findtext(".//state")
            return state.strip() if state else "?"
        except ET.ParseError:
            return "?"


# ── Direktaufruf zum Testen ────────────────────────────────────
if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    s = Steckdose()
    print(f"\n{'='*45}")
    print(f"  ALLNET ALL4076  |  {STECKDOSE_IP}")
    print(f"{'='*45}")
    status = s.status_alle()
    for name, d in status.items():
        if d["gueltig"]:
            print(f"  Dose {d['dose']}  {name:<8}  {d['status']}")
        else:
            print(f"  Dose {d['dose']}  {name:<8}  Fehler")
    print(f"{'='*45}")
