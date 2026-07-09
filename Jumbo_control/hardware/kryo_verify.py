"""
hardware/kryo_verify.py
Verify-Pass nach einer Bulk-Schaltaktion über alle Kryopumpen.

Liest nach einer kurzen Settle-Phase den Ist-Zustand jedes betroffenen Kryos und
schaltet diejenigen nach, die nicht im Soll-Zustand sind.

Strenge Auslegung:
    XSP01R-Kryos (1+2) gelten nur dann als "EIN", wenn BEIDE Relais
    (System + Remote) gesetzt sind. Sie gelten nur dann als "AUS", wenn beide
    Relais aus sind. Mischzustände werden als unbekannt geführt und ausgelöst
    eine Nachschaltung.
    Coolpack-Kryos (3-8) werden über command_status (ON/OFF) bewertet –
    nicht über kompressor_an, da letzteres erst nach dem Switch-ON-Timer
    True wird.

Verwendung:
    from hardware.kryo_verify import pruefe_und_korrigiere

    eintraege = [
        {"name": "Kryo 1", "ist_xsp": True,  "kryo_nr": 1,        "soll_an": True},
        {"name": "Kryo 3", "ist_xsp": False, "port":    "COM12",  "soll_an": True},
    ]
    pruefe_und_korrigiere(eintraege, log=mein_log)
"""

import time
from log_utils import tprint


def _lies_ist_an(eintrag: dict):
    """Liefert (ist_an: bool|None, fehler: str|None) für einen Kryo-Eintrag."""
    name = eintrag.get("name", "?")
    try:
        if eintrag.get("ist_xsp"):
            from hardware.geraete import get_xsp01r
            nr = eintrag.get("kryo_nr")
            if nr not in (1, 2):
                return None, f"ungültige kryo_nr {nr}"
            st = get_xsp01r().status()
            sys_an = bool(st.get(f"kryo{nr}_system"))
            rem_an = bool(st.get(f"kryo{nr}_remote"))
            if sys_an and rem_an:
                return True, None
            if not sys_an and not rem_an:
                return False, None
            return None, f"Mischzustand (system={sys_an}, remote={rem_an})"

        from hardware.coolpack import Coolpack
        port = eintrag.get("port")
        if not port:
            return None, "kein Port"
        c = None
        try:
            c = Coolpack(port, name=name)
            st = c.status()
            if not st.get("gueltig"):
                return None, "keine gültige Antwort"
            cmd = st.get("command_status")
            if cmd == "ON":
                return True, None
            if cmd == "OFF":
                return False, None
            return None, f"command_status={cmd!r}"
        finally:
            if c is not None:
                try: c.beenden()
                except Exception: pass
    except Exception as e:
        return None, str(e)


def _schalte(eintrag: dict, an: bool):
    """Schaltet einen einzelnen Kryo. Liefert (erfolg: bool, fehler: str|None)."""
    name = eintrag.get("name", "?")
    try:
        if eintrag.get("ist_xsp"):
            from hardware.geraete import get_xsp01r
            nr = eintrag.get("kryo_nr")
            x = get_xsp01r()
            if nr == 1:
                x.kryo1_einschalten() if an else x.kryo1_ausschalten()
            elif nr == 2:
                x.kryo2_einschalten() if an else x.kryo2_ausschalten()
            else:
                return False, f"ungültige kryo_nr {nr}"
            return True, None

        from hardware.coolpack import Coolpack
        port = eintrag.get("port")
        if not port:
            return False, "kein Port"
        c = None
        try:
            c = Coolpack(port, name=name)
            if an:
                c.einschalten()
            else:
                c.ausschalten()
            return True, None
        finally:
            if c is not None:
                try: c.beenden()
                except Exception: pass
    except Exception as e:
        return False, str(e)


def pruefe_und_korrigiere(
    eintraege: list,
    settle_sec: float = 3.0,
    max_retries: int = 1,
    log=None,
) -> dict:
    """
    Wartet `settle_sec`, prüft jeden Eintrag gegen `soll_an` und schaltet
    abweichende Kryos nach – bis zu `max_retries` Korrekturrunden.

    eintraege: Liste dicts mit Schlüsseln
        name (str), ist_xsp (bool), soll_an (bool),
        kryo_nr (int, falls XSP), port (str, falls Coolpack)

    Liefert {"ok": [...], "korrigiert": [...], "fehler": [(name, grund), ...]}.
    """
    def _log(msg):
        if callable(log):
            try: log(msg)
            except Exception: pass
        tprint("KryoVerify", msg)

    if not eintraege:
        return {"ok": [], "korrigiert": [], "fehler": []}

    _log(f"Kryo-Zustand wird in {settle_sec:.0f}s geprüft ...")
    time.sleep(settle_sec)

    korrigiert = set()
    fehler = {}
    ok_namen = []

    for runde in range(max_retries + 1):
        abweichend = []
        ok_namen = []
        for e in eintraege:
            name = e.get("name", "?")
            ist_an, grund = _lies_ist_an(e)
            soll = bool(e.get("soll_an"))
            if ist_an is None:
                fehler[name] = grund or "unbekannt"
                continue
            if ist_an == soll:
                ok_namen.append(name)
                fehler.pop(name, None)
            else:
                abweichend.append(e)

        if not abweichend:
            break

        if runde >= max_retries:
            for e in abweichend:
                fehler.setdefault(e["name"], "weiterhin abweichend")
            break

        soll_text = ", ".join(
            f"{e['name']}→{'EIN' if e.get('soll_an') else 'AUS'}"
            for e in abweichend
        )
        _log(f"Nachschaltung Runde {runde + 1}: {soll_text}")
        for e in abweichend:
            erfolg, grund = _schalte(e, bool(e.get("soll_an")))
            korrigiert.add(e["name"])
            if not erfolg:
                fehler[e["name"]] = grund or "Schaltfehler"

        time.sleep(settle_sec)

    ergebnis = {
        "ok":         ok_namen,
        "korrigiert": sorted(korrigiert),
        "fehler":     [(n, g) for n, g in sorted(fehler.items())],
    }

    if ergebnis["fehler"]:
        details = ", ".join(f"{n} ({g})" for n, g in ergebnis["fehler"])
        _log(f"⚠ Endprüfung – nicht im Soll: {details}")
    elif ergebnis["korrigiert"]:
        _log(f"Endprüfung OK – nachgeschaltet: {', '.join(ergebnis['korrigiert'])}")
    else:
        _log("Endprüfung OK – alle im Soll-Zustand")

    return ergebnis
