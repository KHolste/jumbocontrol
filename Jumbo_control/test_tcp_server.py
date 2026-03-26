"""
test_tcp_server.py
Testet den TCP-Messserver auf Port 5001.
Ausführen während main.py läuft: python test_tcp_server.py
"""
import socket
import sys

HOST = "127.0.0.1"   # lokal testen; für Remote: IP des Jumbo-PCs
PORT = 5001

print(f"Verbinde zu {HOST}:{PORT} ...")
try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(5)
        s.connect((HOST, PORT))
        print("✓ Verbunden")

        # V senden
        s.sendall(b"V\r\n")
        print("→ 'V' gesendet, warte auf Antwort ...")

        # Lesen bis \r\n (Dashboard-konform)
        buf = b""
        while b"\r\n" not in buf:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk

        response = buf.decode("ascii", errors="replace")
        print(f"\n── Rohantwort ({len(response)} Zeichen) ──")
        print(response[:300], "..." if len(response) > 300 else "")

        # Parsen wie das Dashboard
        print("\n── Geparste Werte ──")
        items = response.strip().split(";")
        print(f"  Anzahl Felder: {len(items)}")
        pressures = {}
        temps = {}
        for item in items:
            if "," not in item:
                continue
            key, val = item.strip().split(",", 1)
            key = key.strip()
            val = val.strip()
            if key.lower() in ["p door", "p center", "p ba"]:
                pressures[key] = val
            elif key.lower().startswith("kryo"):
                temps[key] = val

        print(f"\n  Druckwerte ({len(pressures)}):")
        for k, v in pressures.items():
            print(f"    {k}: {v}")

        print(f"\n  Temperaturwerte ({len(temps)}):")
        for k, v in list(temps.items())[:5]:
            print(f"    {k}: {v}")
        if len(temps) > 5:
            print(f"    ... (+{len(temps)-5} weitere)")

        print("\n✓ Test abgeschlossen")

except ConnectionRefusedError:
    print("✗ Verbindung abgelehnt – läuft main.py?")
    sys.exit(1)
except socket.timeout:
    print("✗ Timeout – Server antwortet nicht")
    sys.exit(1)
except Exception as e:
    print(f"✗ Fehler: {e}")
    sys.exit(1)
