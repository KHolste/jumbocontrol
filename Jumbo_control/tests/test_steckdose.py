"""Schnelltest für hardware/steckdose.py – aus dem Hauptordner starten."""
from hardware.steckdose import Steckdose

s = Steckdose()

# Status vorher
print(f"\n{'='*45}")
print(f"  Status vorher:")
print(f"{'='*45}")
status = s.status_alle()
for name, d in status.items():
    if d["gueltig"]:
        print(f"  Dose {d['dose']}  {name:<8}  {d['status']}")
    else:
        print(f"  Dose {d['dose']}  {name:<8}  Fehler")

# Dose 2 (Rotary) ausschalten
print(f"\nSchalte Rotary (Dose 2) AUS...")
erfolg = s.ausschalten("Rotary")
print(f"  {'OK' if erfolg else 'FEHLER'}")

# Status nachher
print(f"\n{'='*45}")
print(f"  Status nachher:")
print(f"{'='*45}")
status = s.status_alle()
for name, d in status.items():
    if d["gueltig"]:
        print(f"  Dose {d['dose']}  {name:<8}  {d['status']}")
    else:
        print(f"  Dose {d['dose']}  {name:<8}  Fehler")
print(f"{'='*45}")
