"""Zeigt rohe Antworten vom TPG 366."""
import serial
import time

COM_PORT = "COM5"
BAUDRATE = 9600
TIMEOUT  = 0.2

with serial.Serial(port=COM_PORT, baudrate=BAUDRATE,
                   bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                   stopbits=serial.STOPBITS_ONE, timeout=TIMEOUT) as ser:

    for befehl in ["PR1", "PR2", "PR4"]:
        ser.reset_input_buffer()
        ser.write((befehl + "\r\n").encode("ascii"))
        antwort = b""
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            chunk = ser.read(ser.in_waiting or 1)
            antwort += chunk
            if b"\r" in antwort or b"\n" in antwort:
                break
        print(f"{befehl}: {repr(antwort)}")
