"""Schnelltest für hardware/druck.py – aus dem Hauptordner starten."""
import time
from hardware.druck import DruckMessung

with DruckMessung() as d:
    t0 = time.perf_counter()
    werte = d.messen()
    dauer = time.perf_counter() - t0

    print(f"\n{'='*50}")
    print(f"  TPG 366  |  {d.einheit}  |  COM5")
    print(f"{'='*50}")
    for kanal, w in werte.items():
        if w["gueltig"]:
            print(f"  K{kanal} {w['name']:<8}: {w['mbar']:.3E} {w['einheit']}  ({w['status']})")
        else:
            print(f"  K{kanal} {w['name']:<8}: ---  ({w['status']})")
    print(f"\n  Messzeit: {dauer:.3f} s")
    print(f"{'='*50}")
