"""
config.py
Zentrale Konfiguration der Jumbo-Weltraumsimulationsanlage.
Alle hardware-spezifischen Parameter werden hier gepflegt.
"""

# ── cDAQ / Temperaturen ────────────────────────────────────────
CDAQ_GERAET     = "cDAQ9188-Jumbo"
CDAQ_IP         = "192.168.1.237"
TEMP_STROM_MA   = 0.001
TEMP_SAMPLERATE = 1000.0
TEMP_SAMPLES    = 2
TEMP_MIN        = -273.15
TEMP_MAX        =  100.0

# ── IP-Steckdosenleiste ───────────────────────────────────────
STECKDOSE_IP      = "192.168.1.215"
STECKDOSE_TIMEOUT = 3.0

# ── Drucksensoren (MaxiGauge) ──────────────────────────────────
MAXIGAUGE_PORT  = "COM5"
DRUCK_SENSOREN  = ["CENT", "DOOR", "MASS", "BA"]

# ── Kryopumpen (COM-Ports) ─────────────────────────────────────
KRYO_PORTS = ["COM10", "COM11", "COM12", "COM15",
              "COM14", "COM13", "COM16", "COM17"]

# ── Datenspeicherung ───────────────────────────────────────────
LOG_PFAD        = "daten/logs/"

# ── Automatischer PDF-Druck ────────────────────────────────────
# Druckername für den automatischen Tagesbericht (Extras-Menü).
# None → Windows-Standarddrucker. Beispiel: "HP LaserJet M404"
DRUCKER_NAME    = None

# ── Grenzwerte (Alarme) ────────────────────────────────────────
TEMP_ALARM_MAX  =  50.0   # °C – Überhitzung
TEMP_ALARM_MIN  = -270.0  # °C – Unterkühlung

# ── XSP01R Digital-I/O ────────────────────────────────────────
XSP01R_PORT    = "COM6"
XSP01R_TIMEOUT = 0.5

# Kryopumpen die standardmäßig über den Cryo-Button gesteuert werden
KRYO_AUSWAHL_DEFAULT = ["Kryo 1", "Kryo 2"]

# Zeitverzögerung zwischen dem Einschalten einzelner Kryopumpen (ms)
KRYO_EINSCHALT_DELAY_MS = 5000

# ── Coolpack 6000 Kompressoren ────────────────────────────────
# Kryo 1+2 werden über XSP01R (COM6) Relais INE3 gesteuert
# Kryo 3-8 sind direkte Coolpack-Verbindungen
COOLPACK_PORTS = {
    "Kryo 3": "COM12",
    "Kryo 4": "COM15",
    "Kryo 5": "COM14",
    "Kryo 6": "COM13",
    "Kryo 7": "COM16",
    "Kryo 8": "COM17",
}
COOLPACK_WARTUNGSINTERVALL_H = 10000

# ── Messintervall ─────────────────────────────────────────────
MESS_INTERVALL_MIN_S     = 2.0   # Untergrenze (Seriell + cDAQ Trägheit)
MESS_INTERVALL_DEFAULT_S = 5.0   # Startwert
# ── PT100-Kalibrierung (Temperatur) ──────────────────────────
# Zuordnung: Sensorname → Kalibrierdatei im Ordner kalibrierung/
# Nur eingetragene Sensoren nutzen die Tabelle; alle anderen → CVD-Formel.
# Kryo 1/2: Dateinamen sind Nummern (1-6) entsprechend der Einbaureihenfolge.
# Kryo 4/7/8: Kalibrierung 2026-11, Rohdaten in kalibrierung/rohdaten/.
# Format: "Temperature,Resistance" / "K,Ohm" / Werte mit Punkt als Dezimalzeichen.
PT100_KALIBRIERUNG = {
    "Kryo 1 In": "Pt100_1.csv",
    "Kryo 1":    "Pt100_2.csv",
    "Kryo 1b":   "Pt100_3.csv",
    "Kryo 2 In": "Pt100_4.csv",
    "Kryo 2":    "Pt100_5.csv",
    "Kryo 2b":   "Pt100_6.csv",
    "Kryo 4 In": "Pt100_Kryo4_In.csv",
    "Kryo 4":    "Pt100_Kryo4.csv",
    "Kryo 4b":   "Pt100_Kryo4b.csv",
    "Kryo 7 In": "Pt100_Kryo7_In.csv",
    "Kryo 7":    "Pt100_Kryo7.csv",
    "Kryo 8 In": "Pt100_Kryo8_In.csv",
    # Achtung: Die Kalibrierung zeigt einen Offset von ~ +2,5..3 Ohm gegenüber
    # "Kryo 8 In", den die Anlage selbst nicht zeigt (bei Raumtemperatur messen beide
    # ~110,5 Ohm). Mit Tabelle liegt "Kryo 8" daher ~8 K unter "Kryo 8 In".
    "Kryo 8":    "Pt100_Kryo8.csv",
}
