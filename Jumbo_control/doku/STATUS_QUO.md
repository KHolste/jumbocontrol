# Jumbo Control – Status Quo
**Weltraumsimulationsanlage JLU Giessen – IPI**
Stand: 18.03.2026

---

## Projektstruktur

```
jumbo/
├── main.py                        # Einstiegspunkt
├── config.py                      # Zentrale Konfiguration
├── STATUS_QUO.md                  # Diese Datei
│
├── hardware/                      # Direkte Hardwarekommunikation
│   ├── __init__.py                # Exportiert: TemperaturMessung, DruckMessung, Steckdose
│   ├── temperatur.py              # PT100 via NI cDAQ9188-Jumbo (Ethernet)
│   ├── druck.py                   # Pfeiffer TPG 366 MaxiGauge (RS232 → COM5)
│   └── steckdose.py               # ALLNET ALL4076 IP-Steckdosenleiste (HTTP)
│
├── daten/                         # Datenspeicherung
│   ├── __init__.py                # Exportiert: CsvSchreiber, CsvLeser
│   └── csv_schreiber.py           # Tagesweise CSV-Dateien, ISO-Zeitstempel, MJD, UTC
│
├── steuerung/                     # Messlogik und Ablaufsteuerung
│   ├── __init__.py                # Exportiert: Messzyklus
│   └── ablauf.py                  # Messzyklus (Hintergrund-Thread)
│
├── gui/                           # PyQt6 Benutzeroberfläche
│   ├── __init__.py                # Exportiert: Hauptfenster
│   ├── themes.py                  # Hell/Dunkel-Theme (LIGHT_THEME, DARK_THEME)
│   ├── hauptfenster.py            # Hauptfenster, Header, Log, Layout
│   ├── druck_panel.py             # Druckplot + Anzeigen
│   ├── temp_panel.py              # Temperaturplot + Sensor-Checkboxen
│   └── steckdosen_panel.py        # Steckdosen-Buttons + Cryo-Button
│
├── tests/
│   └── __init__.py
│
└── test_*.py                      # Standalone-Tests ohne GUI
    ├── test_temperatur.py
    ├── test_temperatur_timing.py
    ├── test_druck.py
    ├── test_druck_raw.py
    ├── test_steckdose.py
    └── test_steckdose_debug.py
```

---

## Hardware-Module (`hardware/`)

### `temperatur.py` – Klasse `TemperaturMessung`
- **Gerät:** NI cDAQ-9188 „Jumbo" über Ethernet (192.168.1.237)
- **Treiber:** nidaqmx
- **Sensoren:** 26 PT100-Kanäle (4-Leiter), Callendar-Van-Dusen-Umrechnung
- **Messzeit:** ~3.5s pro Zyklus
- **Kanalbelegung:** aus `Jumbo.ini` (LabVIEW-Konfiguration)
  - Mod1: Kryo 1 In/1/1b, Peltier/Peltier b, Kryo 2 In/2/2b
  - Mod2: Kryo 3 In/3/3b, Kryo 4 In/4/4b
  - Mod3: Kryo 5 In/5/5b, Kryo 6 In/6/6b
  - Mod4: Kryo 7 In/7, Kryo 9/9b, Kryo 8 In/8
- **Rückgabe:** `dict` mit Sensorname als Schlüssel:
  ```python
  {"Kryo 3 In": {"celsius": 9.55, "kelvin": 282.70,
                  "ohm": 103.73, "kanal": "...", "gueltig": True}}
  ```

### `druck.py` – Klasse `DruckMessung`
- **Gerät:** Pfeiffer TPG 366 MaxiGauge über RS232 (COM5, 9600 Baud)
- **Protokoll:** ACK/ENQ (laut Handbuch BG 805 186 BE/B)
  - Senden: `PRx<CR>` → Empfang: `<ACK><CR><LF>` → Senden: `<ENQ>` → Empfang: `status,wert<CR><LF>`
- **Kanäle:** 1=DOOR, 2=CENTER, 4=BA
- **Messzeit:** ~0.06s
- **Statuscodes:** 0=OK, 1=Underrange, 2=Overrange, 3=Sensor error, 4=Sensor off, 5=No sensor
- **Rückgabe:** `dict` mit Sensorname als Schlüssel:
  ```python
  {"CENTER": {"mbar": 1.55e-6, "status": "OK", "gueltig": True}}
  ```

### `steckdose.py` – Klasse `Steckdose`
- **Gerät:** ALLNET ALL4076 IP-Steckdosenleiste (192.168.1.215)
- **Protokoll:** HTTP GET, XML-Antwort
  - Status lesen: `GET /xml?mode=actor&type=list`
  - Schalten: `GET /xml?mode=actor&type=switch&id=<n>&action=<0|1>`
- **Dosen:** V1(1), Rotary(2), Roots(3), Vu(4), Heater(5), Slider(6)
- **Methoden:** `einschalten(name)`, `ausschalten(name)`, `umschalten(name)`, `status_alle()`

---

## Datenhaltung (`daten/`)

### `csv_schreiber.py` – Klassen `CsvSchreiber`, `CsvLeser`
- **Format:** Tab-getrennte CSV, Punkt als Dezimaltrennzeichen
- **Zeitstempel:** ISO 8601 lokal + MJD + UTC ISO 8601
- **Dateien:** tagesweise, z.B. `2026-03-18_temperatur.csv` / `2026-03-18_druck.csv`
- **Speicherort:** `daten/logs/` (aus `config.py`)
- **Temperatur:** Kelvin, Spalten laut `Jumbo.ini`
- **Druck:** mbar (immer), Einheitenumrechnung nur in der GUI
- **Rückwärtskompatibel:** `CsvLeser` liest auch alte LabVIEW-Dateien (Komma als Dezimal, DD.MM.YYYY Format)

---

## Steuerung (`steuerung/`)

### `ablauf.py` – Klasse `Messzyklus`
- Läuft in einem **Hintergrund-Thread** (daemon)
- Misst Temperatur (~3.5s) + Druck (~0.06s) pro Zyklus
- Speichert automatisch in CSV
- Callbacks für GUI-Aktualisierung:
  ```python
  zyklus.bei_messung_temp  = fn(werte: dict)
  zyklus.bei_messung_druck = fn(werte: dict)
  zyklus.bei_alarm         = fn(sensor: str, celsius: float)
  ```
- Alarmgrenzen aus `config.py`: `TEMP_ALARM_MAX`, `TEMP_ALARM_MIN`

---

## GUI (`gui/`)

### `themes.py`
- `LIGHT_THEME` und `DARK_THEME` als dicts
- `build_stylesheet(t)` erzeugt komplettes PyQt6-Stylesheet
- Umschaltbar über Menüleiste `Ansicht → Helles/Dunkles Theme`
- Matplotlib-Plots passen sich via `apply_theme(t)` an

### `hauptfenster.py` – Klasse `Hauptfenster`
- Header: Datum, Uhrzeit (Gießen), KW, MJD, UTC, Speicherdatei
- Layout (von oben nach unten):
  - Header-Zeile
  - Druckplot + Anzeigen
  - Temperaturplot + Sensor-Checkboxen
  - Steckdosen-Buttons
- Rechte Spalte (per Splitter verstellbar):
  - Ereignis-Log (obere Hälfte)
  - Timing-Panel mit Regenerate + Kryo Timer (Dummy, noch nicht implementiert)
- Thread-sichere GUI-Updates via `SignalBridge` (pyqtSignal)

### `druck_panel.py`
- Matplotlib-Plot mit NavigationToolbar (Zoom, Pan, Speichern)
- Logarithmische oder lineare Y-Achse umschaltbar
- Einheitenauswahl: mbar, hPa, Pa, Torr (nur Anzeige, nicht CSV)
- Overrange-Anzeige: wählbar „Overrange" oder „1013 mbar"
- Alarmgrenze mit blinkendem Anzeigeelement
- Zeitbereich: Live oder letzten X Minuten

### `temp_panel.py`
- Matplotlib-Plot mit NavigationToolbar
- 26 Sensoren einzeln ein-/ausschaltbar per Checkbox
- Zeitbereich: Live oder letzten X Minuten

### `steckdosen_panel.py`
- 6 Steckdosen-Buttons (V1, Rotary, Roots, Vu, Heater, Slider)
- Cryo ON/OFF Button (Dummy – Kommunikation mit Helium-Kompressor, noch nicht implementiert)
- Aktionen werden im Ereignis-Log protokolliert

---

## Konfiguration (`config.py`)

```python
CDAQ_GERAET      = "cDAQ9188-Jumbo"      # NI cDAQ Hostname
CDAQ_IP          = "192.168.1.237"
TEMP_STROM_MA    = 0.001                  # PT100 Speisestrom
TEMP_SAMPLERATE  = 1000.0                 # Hz
TEMP_SAMPLES     = 2
TEMP_MIN         = -273.15               # Absoluter Nullpunkt
TEMP_MAX         = 100.0

MAXIGAUGE_PORT   = "COM5"               # TPG 366 COM-Port
DRUCK_SENSOREN   = ["CENT", "DOOR", "MASS", "BA"]

KRYO_PORTS       = ["COM10".."COM17"]   # 8 Kryopumpen (noch nicht implementiert)

STECKDOSE_IP     = "192.168.1.215"
STECKDOSE_TIMEOUT = 3.0

LOG_PFAD         = "daten/logs/"

TEMP_ALARM_MAX   = 50.0                  # °C
TEMP_ALARM_MIN   = -270.0               # °C
```

---

## Noch nicht implementiert / geplant

| Feature | Modul | Status |
|---|---|---|
| Druckmessung Kanäle funktionieren | `hardware/druck.py` | In Arbeit |
| Kryopumpen-Steuerung (COM10–17) | `hardware/kryopumpen.py` | Ausstehend |
| Helium-Kompressor Kommunikation | `hardware/kompressor.py` | Ausstehend |
| Cryo ON/OFF Button | `gui/steckdosen_panel.py` | Dummy vorhanden |
| Regenerier-Prozedur | `steuerung/regenerierung.py` | Dummy vorhanden |
| Kryo Timer | `steuerung/kryo_timer.py` | Dummy vorhanden |
| Druckkanäle MASS in GUI | `gui/druck_panel.py` | Ausstehend |
| Vergleichs-Plots (alte CSV-Daten) | `gui/` | Ausstehend |
| Export-Modul | `daten/export.py` | Ausstehend |

---

## Abhängigkeiten

```
pip install nidaqmx PyQt6 pyqtgraph matplotlib numpy pyserial pyvisa colorama pyfiglet
```

Zusätzlich: **NI-DAQmx Treiber** (Windows, von ni.com)

---

## Starten

```bash
cd jumbo/
python main.py
```

## Tests (ohne GUI, aus Hauptordner)

```bash
python test_temperatur.py
python test_druck.py
python test_steckdose.py
```
