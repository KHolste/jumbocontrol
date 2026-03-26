"""
gui/tcp_server.py
TCP-Server auf Port 5001 – kompatibel zum LabVIEW-VI der Jumbo-Anlage.

Protokoll:
  Client sendet "V" (oder "V\r\n") → Server antwortet mit allen Messwerten
  Format: Tab-getrennte Zeile, analog zum alten LogDataString

Verwendung in hauptfenster.py:
    from gui.tcp_server import TcpMessServer
    self._tcp_server = TcpMessServer(port=5001)
    self._tcp_server.start()
    # Messwerte aktuell halten:
    self._tcp_server.update_druck(werte_dict)
    self._tcp_server.update_temp(werte_dict)
    # Beim Beenden:
    self._tcp_server.stop()
"""

import socket
import threading
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TcpMessServer:
    """
    Winsocket-Server analog zum LabVIEW-VI:
    - Horcht auf Port 5001
    - Akzeptiert beliebig viele gleichzeitige Verbindungen
    - Wartet auf "V" → sendet LogDataString aller aktuellen Messwerte
    - Läuft komplett im Hintergrund (Daemon-Threads)
    """

    PORT = 5001

    def __init__(self, port: int = 5001):
        self._port      = port
        self._lock      = threading.Lock()
        self._druck     = {}   # aktuellste Druckwerte
        self._temp      = {}   # aktuellste Temperaturwerte
        self._running   = False
        self._server_sock = None
        self._connections = []   # offene Client-Sockets

    # ── Öffentliche API ────────────────────────────────────────

    def update_druck(self, werte: dict):
        """Aktualisiert den Druck-Snapshot (aus Messzyklus-Callback)."""
        with self._lock:
            self._druck = dict(werte)

    def update_temp(self, werte: dict):
        """Aktualisiert den Temperatur-Snapshot (aus Messzyklus-Callback)."""
        with self._lock:
            self._temp = dict(werte)

    def start(self):
        """Startet den Server-Thread."""
        if self._running:
            return
        self._running = True
        t = threading.Thread(target=self._listen_loop, daemon=True,
                             name="TcpMessServer-Listen")
        t.start()
        logger.info(f"[TcpServer] Gestartet auf Port {self._port}")

    def stop(self):
        """Beendet Server und schließt alle offenen Verbindungen."""
        self._running = False
        # Alle Client-Verbindungen schließen
        with self._lock:
            for conn in self._connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections.clear()
        # Server-Socket schließen → blockierendes accept() wird unterbrochen
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        logger.info("[TcpServer] Gestoppt")

    @property
    def num_connections(self) -> int:
        with self._lock:
            return len(self._connections)

    # ── Interner Server-Loop (analog LabVIEW unten-Loop) ──────

    def _listen_loop(self):
        """Nimmt neue Verbindungen an und startet je einen Handler-Thread."""
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind(("", self._port))
            self._server_sock.listen(5)
            self._server_sock.settimeout(1.0)   # damit stop() schnell reagiert
        except OSError as e:
            logger.error(f"[TcpServer] Bind auf Port {self._port} fehlgeschlagen: {e}")
            return

        while self._running:
            try:
                conn, addr = self._server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break   # Server-Socket wurde geschlossen

            with self._lock:
                self._connections.append(conn)
            logger.info(f"[TcpServer] Neue Verbindung von {addr[0]}:{addr[1]}")

            t = threading.Thread(
                target=self._handle_client,
                args=(conn, addr),
                daemon=True,
                name=f"TcpMessServer-Client-{addr[0]}"
            )
            t.start()

    # ── Client-Handler (analog LabVIEW oberer Loop) ───────────

    def _handle_client(self, conn: socket.socket, addr: tuple):
        """Wartet auf 'V', antwortet mit LogDataString, bleibt verbunden.
        Liest zeilenweise bis \n; verarbeitet jede Zeile einzeln.
        """
        try:
            conn.settimeout(1.0)
            buf = ""
            while self._running:
                # ── Daten lesen ──────────────────────────────────
                try:
                    chunk = conn.recv(1024)
                except socket.timeout:
                    continue
                except OSError:
                    break

                if not chunk:
                    break   # Client hat Verbindung geschlossen

                buf += chunk.decode("ascii", errors="ignore")

                # ── Zeilen verarbeiten ────────────────────────────
                while "\n" in buf:
                    zeile, buf = buf.split("\n", 1)
                    zeile = zeile.strip().upper()

                    if not zeile:
                        continue   # Leerzeile überspringen

                    if zeile == "V":
                        antwort = self._build_log_string() + "\r\n"
                        try:
                            conn.sendall(antwort.encode("ascii"))
                            logger.debug(f"[TcpServer] V-Antwort → {addr[0]}")
                        except OSError:
                            return
                    else:
                        try:
                            conn.sendall(b"ERR: unknown command\r\n")
                        except OSError:
                            return

        except Exception as e:
            logger.warning(f"[TcpServer] Client {addr[0]}: {e}")
        finally:
            with self._lock:
                if conn in self._connections:
                    self._connections.remove(conn)
            try:
                conn.close()
            except Exception:
                pass
            logger.info(f"[TcpServer] Verbindung getrennt: {addr[0]}:{addr[1]}")

    # ── LogDataString aufbauen ────────────────────────────────

    def _build_log_string(self) -> str:
        """
        Erzeugt den LogDataString im Format des jumbo_dashboard.py:
            Name1,Wert1;Name2,Wert2;...
        Druckkanäle als "P Door", "P Center", "P BA" in mbar,
        Temperaturkanäle als "Kryo X In" / "Kryo X" in Kelvin.
        """
        with self._lock:
            druck = dict(self._druck)
            temp  = dict(self._temp)

        eintraege = []

        # Druckkanäle – Dashboard erwartet "P Door", "P Center", "P BA"
        druck_map = [
            ("DOOR", "P Door"),
            ("CENT", "P Center"),
            ("BA",   "P BA"),
        ]
        for csv_key, dash_name in druck_map:
            d = druck.get(csv_key)
            if d and d.get("gueltig") and d.get("mbar") is not None:
                eintraege.append(f"{dash_name},{d['mbar']:.3E}")
            else:
                eintraege.append(f"{dash_name},NaN")

        # Temperaturkanäle in Kelvin
        SENSOREN = [
            "Kryo 1 In", "Kryo 1", "Kryo 1b",
            "Peltier", "Peltier b",
            "Kryo 2 In", "Kryo 2", "Kryo 2b",
            "Kryo 3 In", "Kryo 3", "Kryo 3b",
            "Kryo 4 In", "Kryo 4", "Kryo 4b",
            "Kryo 5 In", "Kryo 5", "Kryo 5b",
            "Kryo 6 In", "Kryo 6", "Kryo 6b",
            "Kryo 7 In", "Kryo 7",
            "Kryo 9", "Kryo 9b",
            "Kryo 8 In", "Kryo 8",
        ]
        for name in SENSOREN:
            d = temp.get(name)
            if d and d.get("gueltig") and d.get("kelvin") is not None:
                eintraege.append(f"{name},{d['kelvin']:.2f}")
            else:
                eintraege.append(f"{name},NaN")

        return ";".join(eintraege)
