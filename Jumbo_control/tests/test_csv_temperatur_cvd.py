"""
Tests: _cvd-Spalten (unkalibrierte Temperatur nach CVD) in der Temperatur-CSV.

- neue Datei: _cvd-Spalten am ENDE, alte Spaltenpositionen unverändert
- bestehende Datei mit altem Kopf: wird im alten Format weitergeschrieben
"""
import csv

import pytest

from daten.csv_schreiber import CsvSchreiber, TEMP_SPALTEN
from daten.kalibrierung import cvd_kelvin


def _werte():
    # Kryo 4: kalibrierter Wert weicht von CVD ab; Kryo 3: ohne Tabelle; Peltier offen
    return {
        "Kryo 4":  {"kelvin": 297.99, "ohm": 110.481, "gueltig": True},
        "Kryo 3":  {"kelvin": 292.16, "ohm": 107.410, "gueltig": True},
        "Peltier": {"kelvin": None,   "ohm": 500.0,   "gueltig": False},
    }


def _lese(tmp_path):
    datei = next(tmp_path.glob("*_temperatur.csv"))
    with open(datei, encoding="utf-8") as f:
        return list(csv.reader(f, delimiter="\t"))


def _alter_kopf():
    kopf = ["ISO_lokal", "MJD", "UTC"]
    for n in TEMP_SPALTEN:
        kopf += [n, f"{n}_ohm"]
    return kopf


def test_neue_datei_hat_cvd_spalten_am_ende(tmp_path):
    CsvSchreiber(pfad=str(tmp_path)).speichere_temperaturen(_werte())
    kopf, zeile = _lese(tmp_path)
    alt = _alter_kopf()
    assert kopf[:len(alt)] == alt                       # alte Positionen unverändert
    assert kopf[len(alt):] == [f"{n}_cvd" for n in TEMP_SPALTEN]
    assert len(zeile) == len(kopf)


def test_cvd_werte_korrekt(tmp_path):
    CsvSchreiber(pfad=str(tmp_path)).speichere_temperaturen(_werte())
    kopf, zeile = _lese(tmp_path)
    w = dict(zip(kopf, zeile))
    assert float(w["Kryo 4"]) == pytest.approx(297.99)              # kalibriert
    assert float(w["Kryo 4_cvd"]) == pytest.approx(cvd_kelvin(110.481), abs=1e-3)
    assert float(w["Kryo 4_cvd"]) == pytest.approx(300.07, abs=0.05)
    assert float(w["Kryo 3_cvd"]) == pytest.approx(float(w["Kryo 3"]), abs=0.01)
    assert w["Peltier_cvd"] == "NaN"                                # offener Kanal
    assert w["Kryo 1_cvd"] == "NaN"                                 # nicht gemessen


def test_bestehende_datei_mit_altem_kopf_bleibt_im_alten_format(tmp_path):
    s = CsvSchreiber(pfad=str(tmp_path))
    datei = s._dateiname("temperatur")
    with open(datei, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter="\t").writerow(_alter_kopf())
    s.speichere_temperaturen(_werte())
    s.speichere_temperaturen(_werte())
    zeilen = _lese(tmp_path)
    assert zeilen[0] == _alter_kopf()
    assert all(len(z) == len(_alter_kopf()) for z in zeilen)


def test_mehrere_zeilen_konsistent(tmp_path):
    s = CsvSchreiber(pfad=str(tmp_path))
    for _ in range(3):
        s.speichere_temperaturen(_werte())
    zeilen = _lese(tmp_path)
    assert len(zeilen) == 4
    assert len({len(z) for z in zeilen}) == 1
