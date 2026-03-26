"""
test_coolpack_discovery.py
Sucht Coolpack 6000 Kompressoren auf allen verfügbaren COM-Ports.
Protokoll: 4800,8,N,1, kein Handshake
Nachricht:  STX "DAT" CR  →  STX "DAT" ... CR

Ergebnis wird in config_coolpack_vorschlag.py gespeichert.
"""

import serial
import serial.tools.list_ports
import time

STX     = b'\x02'
CR      = b'\x0d'
TIMEOUT = 1.5
BAUD    = 4800

def baue_befehl(befehl: str) -> bytes:
    return STX + befehl.encode("ascii") + CR

def sende_dat(port: str) -> dict | None:
    """
    Sendet DAT-Befehl an einen Port.
    Gibt dict mit Statusdaten zurück oder None wenn kein Coolpack.
    """
    try:
        with serial.Serial(
            port=port, baudrate=BAUD,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=TIMEOUT,
            rtscts=False, dsrdtr=False
        ) as ser:
            time.sleep(0.3)
            ser.reset_input_buffer()
            ser.write(baue_befehl("DAT"))
            time.sleep(TIMEOUT)
            
            rohdaten = b""
            deadline = time.time() + TIMEOUT
            while time.time() < deadline:
                chunk = ser.read(ser.in_waiting or 1)
                rohdaten += chunk
                if rohdaten.endswith(CR):
                    break

            if not rohdaten:
                return None

            # Prüfen ob Antwort mit STX "DAT" beginnt
            decoded = rohdaten.decode("ascii", errors="replace")
            if "\x02DAT" not in decoded:
                return None

            # Antwort parsen
            return _parse_dat(decoded)

    except serial.SerialException:
        return None
    except Exception as e:
        return {"fehler": str(e)}


def _parse_dat(raw: str) -> dict:
    """
    Parst die DAT-Antwort des Coolpack.
    Format: STX "DAT" "version"/"internal"/"stunden"/"datum"/"timer"/"cmd_status"/"status"/"coldhead"/"fehler"/"fehlerbits"/"anzahl" CR
    """
    try:
        # STX und CR entfernen, dann nach DAT suchen
        teil = raw.replace("\x02", "").replace("\r", "").strip()
        if not teil.startswith("DAT"):
            return {"roh": raw}
        
        werte = teil[3:].split("/")  # nach "DAT" aufteilen

        result = {"roh": teil}

        if len(werte) > 0:  result["software_version"]   = werte[0].strip('"')
        if len(werte) > 1:  result["intern"]              = werte[1].strip('"')
        if len(werte) > 2:  result["betriebsstunden"]     = werte[2].strip('"')
        if len(werte) > 3:  result["datum_intern"]        = werte[3].strip('"')
        if len(werte) > 4:  result["switch_on_timer"]     = werte[4].strip('"')
        if len(werte) > 5:
            cs = werte[5].strip('"')
            result["command_status"] = {"0": "OFF", "1": "ON", "2": "SYSTEM ERROR"}.get(cs, cs)
        if len(werte) > 6:
            st = werte[6].strip('"')
            result["kompressor_status"] = {"0": "OFF", "1": "ON"}.get(st, st)
        if len(werte) > 7:  result["cold_head"]           = werte[7].strip('"')
        if len(werte) > 8:  result["aktive_fehler"]       = werte[8].strip('"')
        if len(werte) > 9:  result["fehlerbits"]          = werte[9].strip('"')
        if len(werte) > 10: result["fehler_anzahl"]       = werte[10].strip('"')

        return result
    except Exception as e:
        return {"roh": raw, "parse_fehler": str(e)}


# ── Hauptprogramm ──────────────────────────────────────────────
print("\n" + "="*55)
print("  Coolpack 6000 Discovery")
print("  Protokoll: 4800,8,N,1  |  Befehl: STX DAT CR")
print("="*55)

# Alle verfügbaren Ports auflisten
alle_ports = [p.device for p in serial.tools.list_ports.comports()]
print(f"\n  Verfügbare Ports: {', '.join(alle_ports)}")

# Kandidaten: bevorzugt KRYO_PORTS aus config, sonst alle
try:
    from config import KRYO_PORTS
    kandidaten = KRYO_PORTS
    print(f"  Teste KRYO_PORTS aus config.py: {', '.join(kandidaten)}")
except ImportError:
    kandidaten = alle_ports
    print(f"  Keine config.py gefunden, teste alle Ports")

print(f"\n{'─'*55}")

gefunden = {}

for port in kandidaten:
    if port not in alle_ports:
        print(f"  {port:<8}  nicht verfügbar")
        continue

    print(f"  {port:<8}  sende DAT...", end="", flush=True)
    ergebnis = sende_dat(port)

    if ergebnis is None:
        print("  keine Antwort")
    elif "fehler" in ergebnis:
        print(f"  Fehler: {ergebnis['fehler']}")
    else:
        st  = ergebnis.get("kompressor_status", "?")
        std = ergebnis.get("betriebsstunden",   "?")
        ver = ergebnis.get("software_version",  "?")
        print(f"  ✓ COOLPACK GEFUNDEN!")
        print(f"            Status:        {st}")
        print(f"            Betriebsstd.:  {std} h")
        print(f"            SW-Version:    {ver}")
        if "command_status" in ergebnis:
            print(f"            CMD-Status:    {ergebnis['command_status']}")
        if "aktive_fehler" in ergebnis:
            print(f"            Aktive Fehler: {ergebnis['aktive_fehler']}")
        gefunden[port] = ergebnis

print(f"{'─'*55}")
print(f"\n  Ergebnis: {len(gefunden)} Coolpack(s) gefunden")

if gefunden:
    print("\n  Vorschlag für config.py:")
    print(f"  COOLPACK_PORTS = {list(gefunden.keys())}")

    # Vorschlag-Datei speichern
    with open("config_coolpack_vorschlag.py", "w") as f:
        f.write("# Automatisch ermittelt von test_coolpack_discovery.py\n")
        f.write("# Bitte manuell in config.py übernehmen und Kryos benennen\n\n")
        f.write("COOLPACK_PORTS = {\n")
        for i, port in enumerate(gefunden.keys(), 1):
            f.write(f'    "Kryo {i}": "{port}",\n')
        f.write("}\n")
    print("  Gespeichert in: config_coolpack_vorschlag.py")

print("="*55 + "\n")
