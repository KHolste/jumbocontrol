"""
test_coolpack.py – Schnelltest eines einzelnen Coolpack.
"""
import serial
import time

PORT    = "COM12"   # anpassen
BAUD    = 4800
STX     = b'\x02'
CR      = b'\x0d'
TIMEOUT = 2.0

def sende(ser, befehl: str) -> str:
    ser.reset_input_buffer()
    paket = STX + befehl.encode("ascii") + CR
    print(f"  → sende: {repr(paket)}")
    ser.write(paket)
    rohdaten = b""
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        rohdaten += chunk
        if rohdaten.endswith(CR):
            break
    print(f"  ← empfangen: {repr(rohdaten)}")
    return rohdaten.decode("ascii", errors="replace").strip()

print(f"\n{'='*45}")
print(f"  Coolpack Test  |  {PORT}  |  {BAUD} Baud")
print(f"{'='*45}\n")

with serial.Serial(port=PORT, baudrate=BAUD,
                   bytesize=serial.EIGHTBITS,
                   parity=serial.PARITY_NONE,
                   stopbits=serial.STOPBITS_ONE,
                   timeout=TIMEOUT,
                   rtscts=False, dsrdtr=False) as ser:
    time.sleep(0.5)

    print("1. DAT abfragen:")
    r = sende(ser, "DAT")
    print(f"   Antwort: '{r}'\n")

    print("2. SYS1 – EIN:")
    r = sende(ser, "SYS1")
    print(f"   Antwort: '{r}'\n")

    time.sleep(2)

    print("3. DAT – Status nach EIN:")
    r = sende(ser, "DAT")
    print(f"   Antwort: '{r}'\n")

    print("4. SYS0 – AUS:")
    r = sende(ser, "SYS0")
    print(f"   Antwort: '{r}'\n")

print(f"{'='*45}")
