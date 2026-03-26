"""Schnelltest für hardware/temperatur.py – aus dem Hauptordner starten."""
import time
from hardware.temperatur import TemperaturMessung

with TemperaturMessung() as t:
    t0 = time.perf_counter()
    werte = t.messen()
    dauer = time.perf_counter() - t0

    print(f"\n{'='*60}")
    print(f"  PT100 Temperaturen  |  cDAQ9188-Jumbo")
    print(f"{'='*60}")
    print(f"  {'Sensor':<12}  {'°C':>8}  {'K':>8}  {'Ohm':>8}")
    print(f"  {'-'*56}")
    for name, d in werte.items():
        if d["gueltig"]:
            print(f"  {name:<12}  {d['celsius']:>8.2f}  {d['kelvin']:>8.2f}  {d['ohm']:>8.3f}")
        else:
            print(f"  {name:<12}  {'---':>8}  {'---':>8}  {d['ohm']:>8.3f}  (kein Sensor)")

    gueltig = sum(1 for d in werte.values() if d["gueltig"])
    print(f"\n  Gültige Sensoren: {gueltig}/{len(werte)}  |  Messzeit: {dauer:.3f} s")
    print(f"{'='*60}")
