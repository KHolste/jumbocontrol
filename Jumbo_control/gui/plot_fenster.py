"""
gui/plot_fenster.py
Hilfsklasse: macht einen Plot-Container aus einem Panel herausziehbar.

Verwendung:
    self._detach_helper = DetachHelper(
        panel=self,
        plot_container=plot_container,
        placeholder_layout=plot_placeholder_layout,
        titel="Temperaturplot",
    )
    btn.clicked.connect(self._detach_helper.toggle)
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent


class PlotFenster(QWidget):
    """Eigenständiges Fenster das einen Plot-Container aufnimmt."""

    def __init__(self, titel: str, container: QWidget, rueckruf, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(titel)
        self.resize(900, 500)
        self._container  = container
        self._rueckruf   = rueckruf   # wird beim Schließen aufgerufen

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(container)
        container.show()

    def closeEvent(self, event):
        self._rueckruf()
        event.accept()


class DetachHelper:
    """
    Verwaltet das Herausziehen und Zurückholen eines Plot-Containers.

    Parameters
    ----------
    panel            : das übergeordnete QWidget (z.B. TempPanel)
    plot_container   : der Widget-Block mit Canvas + Toolbar + Steuerleiste
    container_layout : das Layout im panel in das plot_container gehört
    insert_index     : Position im Layout wo container wieder eingefügt wird
    titel            : Fenstertitel des Pop-out-Fensters
    btn              : der Toggle-Button (Text wird aktualisiert)
    """

    def __init__(self, panel: QWidget, plot_container: QWidget,
                 container_layout, insert_index: int,
                 titel: str, btn=None):
        self._panel            = panel
        self._container        = plot_container
        self._layout           = container_layout
        self._insert_index     = insert_index
        self._titel            = titel
        self._btn              = btn
        self._fenster          = None
        self._placeholder      = None

    def is_detached(self) -> bool:
        return self._fenster is not None and self._fenster.isVisible()

    def toggle(self):
        if self.is_detached():
            self.andocken()
        else:
            self.abdocken()

    def abdocken(self):
        if self.is_detached():
            return

        # Laufende Timers im Container pausieren
        self._timer_pause(True)

        # Platzhalter einsetzen
        self._placeholder = QLabel(f"📊  {self._titel}\n(in eigenem Fenster geöffnet)")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(
            "color: #7f8daa; font-size: 13px; font-style: italic; "
            "border: 2px dashed #2c3a57; border-radius: 10px; margin: 8px;"
        )
        self._placeholder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._layout.insertWidget(self._insert_index, self._placeholder, 1)

        # Container in eigenem Fenster anzeigen
        self._fenster = PlotFenster(
            titel=self._titel,
            container=self._container,
            rueckruf=self.andocken,
            parent=None,
        )
        self._fenster.show()

        if self._btn:
            self._btn.setText("⊙ Einbetten")
            self._btn.setToolTip("Plot zurück ins Hauptfenster einbetten")

        self._timer_pause(False)

    def _timer_pause(self, pausieren: bool):
        """Pausiert alle QTimer im Container damit kein draw_idle während Reparent feuert."""
        from PyQt6.QtCore import QTimer as _QT
        for timer in self._container.findChildren(_QT):
            if pausieren:
                timer.stop()
            else:
                # Nur starten wenn Intervall gesetzt (d.h. war aktiv)
                if timer.interval() > 0:
                    timer.start()

    def andocken(self):
        if not self._fenster:
            return

        # Laufende Timers pausieren während Reparent
        self._timer_pause(True)

        # Container zurück ins Panel
        self._container.setParent(self._panel)
        self._layout.insertWidget(self._insert_index, self._container, 1)
        self._container.show()

        # Platzhalter entfernen
        if self._placeholder:
            self._layout.removeWidget(self._placeholder)
            self._placeholder.deleteLater()
            self._placeholder = None

        # Fenster schließen ohne Rekursion
        fenster = self._fenster
        self._fenster = None
        if fenster and not fenster.isHidden():
            fenster.close()

        if self._btn:
            self._btn.setText("⇱ Pop-out")
            self._btn.setToolTip("Plot in eigenem Fenster öffnen")

        self._timer_pause(False)
