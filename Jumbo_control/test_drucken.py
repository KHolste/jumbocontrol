"""
test_drucken.py
Testet den automatischen PDF-Druck.
Ausführen aus dem jumbo/-Ordner: python test_drucken.py
"""

import os, sys, subprocess, glob
from pathlib import Path

# ── 1. config.py ─────────────────────────────────────────────
try:
    from config import DRUCKER_NAME
    print(f"✓ DRUCKER_NAME = '{DRUCKER_NAME}'")
except ImportError as e:
    print(f"✗ config.py Fehler: {e}"); sys.exit(1)

# ── 2. Neuestes PDF ──────────────────────────────────────────
pdfs = sorted(Path("PDF").glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
if not pdfs:
    print("✗ Keine PDFs im PDF/-Ordner"); sys.exit(1)
test_pdf = pdfs[0].resolve()
print(f"✓ Test-PDF: {test_pdf.name}")

# ── 3. SumatraPDF suchen (inkl. wo() und AppData) ────────────
def find_sumatra():
    # Bekannte Pfade
    kandidaten = [
        r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
        r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
    ]
    # AppData aller User
    for base in [os.environ.get("LOCALAPPDATA",""), os.environ.get("APPDATA",""),
                 r"C:\Users"]:
        kandidaten += glob.glob(os.path.join(base, "**", "SumatraPDF.exe"), recursive=True)
    # PATH
    try:
        r = subprocess.run(["where", "SumatraPDF"], capture_output=True, text=True)
        if r.returncode == 0:
            kandidaten += r.stdout.strip().splitlines()
    except Exception:
        pass
    for p in kandidaten:
        if p and os.path.exists(p):
            return p
    return None

sumatra = find_sumatra()
if sumatra:
    print(f"✓ SumatraPDF: {sumatra}")
else:
    print("✗ SumatraPDF nicht gefunden – bitte Pfad prüfen")
    sys.exit(1)

# ── 4. Drucken ───────────────────────────────────────────────
print(f"\n→ Drucker: {DRUCKER_NAME}")
if input("Wirklich drucken? [j/N] ").strip().lower() != "j":
    print("Abgebrochen."); sys.exit(0)

try:
    proc = subprocess.Popen([
        sumatra,
        "-print-to", DRUCKER_NAME,
        "-print-settings", "fit",
        "-silent",
        str(test_pdf)
    ])
    proc.wait(timeout=30)
    if proc.returncode == 0:
        print("✓ Druckauftrag gesendet")
    else:
        print(f"⚠ Rückgabecode {proc.returncode} – Druckername korrekt?")
except subprocess.TimeoutExpired:
    print("⚠ Timeout nach 30s")
except Exception as e:
    print(f"✗ Fehler: {e}")
