"""
main.py – Jumbo Control
"""
import sys
import os
import platform
from pyfiglet import figlet_format
from colorama import init

# ── Banner sofort anzeigen – vor allen schweren Imports ──────
def clear_console():
    os.system("cls" if platform.system() == "Windows" else "clear")

def print_banner() -> None:
    init()
    GREEN = "\033[92m"
    CYAN  = "\033[96m"
    RESET = "\033[0m"
    banner = figlet_format("Jumbo control", font="slant")
    subtitle = (
        "Version 1.0  (basierend auf historischer LabVIEW-Steuerung (c) HP Jorde)\n"
        "JLU Giessen – IPI"
    )
    print(GREEN + banner + RESET)
    print(CYAN + subtitle + RESET)
    print("-" * 80)

if __name__ == "__main__":
    clear_console()
    print_banner()

# ── Jetzt erst schwere Imports (drucken ihre Meldungen NACH dem Banner) ──
import matplotlib
matplotlib.use("QtAgg")

import fehler_log
fehler_log.installieren()

# Segfaults und harte Abstürze loggen
import faulthandler
import os
os.makedirs("daten/logs", exist_ok=True)
_fault_log = open("daten/logs/crash.log", "a")
faulthandler.enable(file=_fault_log)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from gui import Hauptfenster
from gui.themes import DARK_THEME, build_stylesheet


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(build_stylesheet(DARK_THEME))
    fenster = Hauptfenster()
    fenster.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
