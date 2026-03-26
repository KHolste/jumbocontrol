"""
test_xsp01r.py – ZEB XSP01R Kommunikationstest, 9600,8,N,1
"""
import serial
import time

PORT    = "COM6"
BAUD    = 9600
TIMEOUT = 1.0

def char_zu_bits(c: str) -> str:
    val = ord(c) - ord('@')
    return f"{val:04b}"

def befehl(ser, cmd: bytes) -> bytes:
    ser.reset_input_buffer()
    ser.write(cmd)
    time.sleep(0.3)
    return ser.read(ser.in_waiting or 32)

print(f"\n{'='*45}")
print(f"  ZEB XSP01R  |  {PORT}  |  9600,8,N,1")
print(f"{'='*45}")

with serial.Serial(port=PORT, baudrate=BAUD,
                   bytesize=serial.EIGHTBITS,
                   parity=serial.PARITY_NONE,
                   stopbits=serial.STOPBITS_ONE,
                   timeout=TIMEOUT,
                   rtscts=False, dsrdtr=False) as ser:
    ser.rts = True
    ser.dtr = True
    time.sleep(0.5)

    # Eingänge lesen
    r = befehl(ser, b"I\r")
    print(f"\n  Eingänge lesen:  raw={repr(r)}")
    decoded = r.decode("ascii", errors="replace").strip()
    if len(decoded) >= 3 and decoded[0] == 'I':
        h, l = decoded[1], decoded[2]
        bits = char_zu_bits(h) + char_zu_bits(l)
        print(f"  Bit7..0 = {bits}")
    else:
        print(f"  Antwort: '{decoded}'")

    # Ausgänge lesen
    r = befehl(ser, b"O\r")
    print(f"\n  Ausgänge lesen:  raw={repr(r)}")
    decoded = r.decode("ascii", errors="replace").strip()
    if len(decoded) >= 3 and decoded[0] == 'O':
        h, l = decoded[1], decoded[2]
        bits = char_zu_bits(h) + char_zu_bits(l)
        print(f"  Bit7..0 = {bits}")
    else:
        print(f"  Antwort: '{decoded}'")

    # Ausgang 0 einschalten (Bit0=1 → low='A', high='@')
    print(f"\n  Setze Ausgang Bit0 EIN  (O@A)...")
    ser.write(b"O@A\r")
    time.sleep(1.0)

    # Status prüfen
    r = befehl(ser, b"O\r")
    decoded = r.decode("ascii", errors="replace").strip()
    print(f"  Ausgänge nach Schalten: '{decoded}'")

    # Alles aus
    time.sleep(1.0)
    print(f"\n  Alle Ausgänge AUS  (O@@)...")
    ser.write(b"O@@\r")
    time.sleep(0.3)

    r = befehl(ser, b"O\r")
    decoded = r.decode("ascii", errors="replace").strip()
    print(f"  Ausgänge nach AUS: '{decoded}'")

print(f"\n{'='*45}")
