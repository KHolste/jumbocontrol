"""Schnelltest für hardware/steckdose.py – aus dem Hauptordner starten."""
from hardware.steckdose import Steckdose

s = Steckdose()
print(f"\n{'='*45}")
print(f"  IP-Steckdosenleiste  |  Status")
print(f"{'='*45}")

status = s.status_alle()
for name, d in status.items():
    if d["gueltig"]:
        zustand = "AN " if d["an"] else "AUS"
        print(f"  Dose {d['dose']}  {name:<8}  {zustand}")
    else:
        print(f"  Dose {d['dose']}  {name:<8}  Fehler")
print(f"{'='*45}")
