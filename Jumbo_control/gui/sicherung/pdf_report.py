# pdf_report.py – JUMBO Tages-PDF-Report
# Erzeugt ein zweiseitiges Matplotlib-PDF mit Druck- und Temperaturplot
# analog zum MJD-Format des bestehenden Archivs.

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # kein GUI-Backend nötig
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# ── Konstanten ────────────────────────────────────────────────────────────────
OVERRANGE_PA = 101_300.0          # 1013 mbar in Pa (Fallback wenn Overrange)
DRUCK_KANAELE = ["door", "center", "ba"]
DRUCK_LABELS  = {"door": "door", "center": "center", "ba": "Bayard-Alpert"}
DRUCK_MARKER  = {"door": ">", "center": "s", "ba": "D"}
DRUCK_FARBE   = {"door": "black", "center": "green", "ba": "royalblue"}

# Farben für Cryo-Kanäle (wird dynamisch erweitert wenn mehr als 3)
CRYO_FARBEN = ["royalblue", "gray", "orange", "red", "purple",
               "brown", "pink", "olive", "cyan", "magenta"]


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _datum_zu_mjd(dt: datetime) -> int:
    """Wandelt datetime in Modified Julian Date (ganzzahlig) um."""
    # MJD = JD - 2400000.5
    # JD für 1858-11-17 00:00 UTC = 2400000.5  → MJD 0
    epoch = datetime(1858, 11, 17, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = dt - epoch
    return int(delta.days)


def _stunden_achse(zeiten_s: list[float], tag_start_s: float) -> np.ndarray:
    """Rechnet absolute Unix-Timestamps in Stunden seit Tagesbeginn um."""
    arr = np.asarray(zeiten_s, dtype=float)
    return (arr - tag_start_s) / 3600.0


def _bereinige_druck(werte: list[Optional[float]]) -> np.ndarray:
    """Ersetzt None / NaN (Overrange) durch OVERRANGE_PA."""
    arr = np.array([OVERRANGE_PA if (v is None or np.isnan(float(v))) else float(v)
                    for v in werte])
    return arr


# ── Haupt-API ─────────────────────────────────────────────────────────────────

def erstelle_tagesbericht(
    druck_daten: dict,
    temp_daten:  dict,
    ausgabe_verzeichnis: str | Path,
    datum: Optional[datetime] = None,
) -> Path:
    """
    Erstellt einen Tages-PDF-Report und speichert ihn im Unterordner PDF/.

    Parameters
    ----------
    druck_daten : dict
        {
          "zeiten": [unix_timestamp, ...],   # float, Sekunden
          "door":   [Pa | None, ...],        # None = Overrange
          "center": [Pa | None, ...],
          "ba":     [Pa | None, ...],
        }

    temp_daten : dict
        {
          "zeiten":  [unix_timestamp, ...],
          "Cryo 3":  [K, ...],              # Schlüssel = Kanalname
          "Cryo 5":  [K, ...],
          ...                               # beliebig viele Kanäle
        }

    ausgabe_verzeichnis : str | Path
        Hauptordner des Projekts; PDF wird in <ausgabe_verzeichnis>/PDF/ abgelegt.

    datum : datetime, optional
        Datum des Berichts; Standard = heute (UTC).

    Returns
    -------
    Path
        Pfad zur erzeugten PDF-Datei.
    """
    if datum is None:
        datum = datetime.now(tz=timezone.utc)

    mjd = _datum_zu_mjd(datum)

    # Tagesbeginn in Unix-Sekunden – lokale Mitternacht,
    # passend zu den ISO_lokal-Timestamps in der CSV
    tag_start = datetime(datum.year, datum.month, datum.day).timestamp()

    # ── Ausgabe-Verzeichnis vorbereiten ──
    pdf_ordner = Path(ausgabe_verzeichnis) / "PDF"
    pdf_ordner.mkdir(parents=True, exist_ok=True)

    dateiname = f"MJD_{mjd}_{datum.strftime('%Y-%m-%d')}.pdf"
    pdf_pfad  = pdf_ordner / dateiname

    # ── Figure aufbauen ──
    fig, (ax_p, ax_t) = plt.subplots(
        2, 1,
        figsize=(8.27, 11.69),   # A4
        dpi=150,
        constrained_layout=True,
    )
    erstellt_um = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    fig.suptitle(
        f"MJD: {mjd}    {datum.strftime('%Y-%m-%d')}    erstellt: {erstellt_um}",
        fontsize=12, fontweight="bold"
    )

    # ── Druckplot ──
    zeiten_d = druck_daten.get("zeiten", [])
    if zeiten_d:
        t_h_d = _stunden_achse(zeiten_d, tag_start)
        for kanal in DRUCK_KANAELE:
            werte = druck_daten.get(kanal)
            if werte is None:
                continue
            pa = _bereinige_druck(werte)
            ax_p.scatter(
                t_h_d, pa,
                s=4,
                marker=DRUCK_MARKER[kanal],
                color=DRUCK_FARBE[kanal],
                label=DRUCK_LABELS[kanal],
                zorder=3,
            )

    ax_p.set_yscale("log")
    ax_p.set_ylim(1e-5, 1e-1)
    ax_p.set_xlim(0, 24)
    ax_p.set_xlabel("$t$ / hour", fontsize=11)
    ax_p.set_ylabel("$p$ / Pa", fontsize=11)
    ax_p.legend(loc="upper right", markerscale=2, fontsize=9)
    ax_p.set_xticks(range(0, 25, 1))          # Hauptticks jede Stunde
    ax_p.set_xticks([h + 0.5 for h in range(24)], minor=True)  # Hilfsticks
    ax_p.grid(True, which="major", linestyle="-",  linewidth=0.5, alpha=0.4)
    ax_p.grid(True, which="minor", linestyle=":",  linewidth=0.3, alpha=0.3)
    ax_p.grid(True, axis="y",      linestyle="--", linewidth=0.4, alpha=0.5)
    ax_p.tick_params(which="both", direction="in")
    ax_p.tick_params(axis="x", which="major", labelsize=7, rotation=45)

    # ── Temperaturplot ──
    zeiten_t = temp_daten.get("zeiten", [])
    cryo_kanaele = [k for k in temp_daten if k != "zeiten"]

    if zeiten_t:
        t_h_t = _stunden_achse(zeiten_t, tag_start)
        for cidx, kanal in enumerate(cryo_kanaele):
            werte = temp_daten.get(kanal)
            if werte is None:
                continue
            T = np.array([float(v) if v is not None else np.nan for v in werte])
            farbe = CRYO_FARBEN[cidx % len(CRYO_FARBEN)]
            valid = np.isfinite(T)
            if not valid.any():
                continue
            ax_t.scatter(
                t_h_t[valid], T[valid],
                s=6, marker="D",
                color=farbe,
                label=kanal,
                zorder=3,
            )

    ax_t.set_xlim(0, 24)
    ax_t.set_xlabel("$t$ / hour", fontsize=11)
    ax_t.set_ylabel("$T$ / K", fontsize=11)
    ax_t.legend(loc="upper right", fontsize=9)
    ax_t.set_xticks(range(0, 25, 1))          # Hauptticks jede Stunde
    ax_t.set_xticks([h + 0.5 for h in range(24)], minor=True)
    ax_t.grid(True, which="major", linestyle="-",  linewidth=0.5, alpha=0.4)
    ax_t.grid(True, which="minor", linestyle=":",  linewidth=0.3, alpha=0.3)
    ax_t.tick_params(which="both", direction="in")
    ax_t.tick_params(axis="x", which="major", labelsize=7, rotation=45)

    # ── Speichern ──
    fig.savefig(str(pdf_pfad), format="pdf", bbox_inches="tight")
    plt.close(fig)

    return pdf_pfad
