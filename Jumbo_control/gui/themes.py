"""
gui/themes.py
Korrigierte Theme-Datei mit vollständigen Keys und dunkler Matplotlib-Toolbar.
"""

from PyQt6.QtCore import QSize

DARK_THEME = {
    "bg":       "#0b1220",
    "panel":    "#121b2b",
    "card":     "#182336",
    "border":   "#2c3a57",
    "border2":  "#415277",
    "accent":   "#7db2ff",
    "accent2":  "#2dd4bf",
    "accent3":  "#fbbf24",
    "danger":   "#fb7185",
    "text":     "#edf2ff",
    "text_sec": "#b3c0dc",
    "text_dim": "#7f8daa",
    "log_info": "#edf2ff",
    "log_ok":   "#34d399",
    "log_warn": "#fbbf24",
    "log_err":  "#fb7185",
    "log_stamp":"#8ec5ff",
}

LIGHT_THEME = {
    "bg":       "#f3f6fb",
    "panel":    "#e9eef8",
    "card":     "#ffffff",
    "border":   "#d9e2f1",
    "border2":  "#c0cee3",
    "accent":   "#2563eb",
    "accent2":  "#0f766e",
    "accent3":  "#c2410c",
    "danger":   "#e11d48",
    "text":     "#111827",
    "text_sec": "#667085",
    "text_dim": "#8a94a6",
    "log_info": "#111827",
    "log_ok":   "#0f766e",
    "log_warn": "#b45309",
    "log_err":  "#be123c",
    "log_stamp":"#475467",
}

def build_stylesheet(t: dict) -> str:
    border2 = t.get("border2", t["border"])
    text_dim = t.get("text_dim", t["text_sec"])
    return f"""
QWidget {{
    background-color: {t['bg']};
    color: {t['text']};
    font-family: "Segoe UI", "Inter", "SF Pro Display", sans-serif;
    font-size: 13px;
}}

QMainWindow, QDialog {{
    background-color: {t['bg']};
}}

QLabel {{
    background: transparent;
    color: {t['text']};
}}

QLabel#date {{
    color: {t['accent2']};
    font-weight: 700;
}}

QLabel#time, QLabel#utc {{
    color: {t['accent']};
    font-weight: 700;
}}

QLabel#kw, QLabel#mjd {{
    color: {t['accent3']};
    font-weight: 700;
}}

QPushButton {{
    background-color: {t['card']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 12px;
    padding: 9px 16px;
    min-height: 24px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {t['panel']};
    border-color: {border2};
}}

QPushButton:pressed, QPushButton:checked {{
    background-color: {t['accent']};
    color: #ffffff;
    border-color: {t['accent']};
}}

QPushButton:disabled {{
    color: {text_dim};
    background-color: {t['panel']};
    border-color: {t['border']};
}}

QPushButton#supportButton,
QPushButton#pdfButton,
QPushButton#fullscreenButton {{
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 0 18px;
    min-height: 34px;
    font-size: 12px;
    font-weight: 700;
}}

QPushButton#supportButton {{ background: {t['accent']}; }}
QPushButton#supportButton:hover {{ background: #6aa7ff; }}

QPushButton#pdfButton {{ background: {t['accent2']}; }}
QPushButton#pdfButton:hover {{ background: #19c2ae; }}
QPushButton#pdfButton:disabled {{
    background: {t['border']};
    color: {t['text_dim']};
}}

QPushButton#fullscreenButton {{ background: #7c3aed; }}
QPushButton#fullscreenButton:hover {{ background: #8b5cf6; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QTextEdit, QPlainTextEdit {{
    background-color: {t['card']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 10px;
    padding: 8px 10px;
    selection-background-color: {t['accent']};
    selection-color: #ffffff;
}}

QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QDateTimeEdit:hover,
QTextEdit:hover, QPlainTextEdit:hover {{
    border-color: {border2};
}}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateTimeEdit:focus,
QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {t['accent']};
}}

QTabWidget::pane {{
    background: transparent;
    border: none;
}}

QTabBar::tab {{
    background: {t['panel']};
    color: {t['text_sec']};
    border: 2px solid {t['border']};
    padding: 6px 12px;
    margin-right: 4px;
    border-radius: 9px;
    font-size: 11px;
    font-weight: 700;
    min-width: 70px;
}}

QTabBar::tab:selected {{
    background: {t['accent']};
    color: #ffffff;
    border: 2px solid {t['accent']};
    margin-bottom: -1px;
}}

QTabBar::tab:hover:!selected {{
    background: {t['card']};
    color: {t['text']};
    border: 2px solid {border2};
}}

QStatusBar {{
    background: {t['panel']};
    color: {t['text_sec']};
    border: none;
    padding: 4px 10px;
    min-height: 32px;
}}

QStatusBar QLabel {{
    color: {t['text_sec']};
    font-size: 12px;
    font-weight: 600;
    padding: 0 6px;
}}

/* ── QCheckBox ──────────────────────────────────────────── */
QCheckBox {{
    spacing: 8px;
    color: {t['text']};
    background: transparent;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {border2};
    border-radius: 4px;
    background: {t['card']};
}}
QCheckBox::indicator:hover {{
    border-color: {t['accent']};
}}
QCheckBox::indicator:checked {{
    background-color: {t['accent']};
    border-color: {t['accent']};
}}
QCheckBox::indicator:checked:hover {{
    background-color: {t['accent']};
    border-color: {t['text']};
}}
QCheckBox::indicator:disabled {{
    background: {t['panel']};
    border-color: {t['border']};
}}

/* ── QRadioButton ───────────────────────────────────────── */
QRadioButton {{
    spacing: 6px;
    color: {t['text']};
    background: transparent;
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {border2};
    border-radius: 9px;
    background: {t['card']};
}}
QRadioButton::indicator:hover {{
    border-color: {t['accent']};
}}
QRadioButton::indicator:checked {{
    background-color: {t['accent']};
    border-color: {t['accent']};
}}

/* ── QSpinBox / QDoubleSpinBox / QDateTimeEdit Buttons ── */
QSpinBox::up-button, QDoubleSpinBox::up-button, QDateTimeEdit::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 24px;
    background: {t['panel']};
    border-left: 1px solid {t['border']};
    border-top-right-radius: 9px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QDateTimeEdit::up-button:hover {{
    background: {border2};
}}
QSpinBox::down-button, QDoubleSpinBox::down-button, QDateTimeEdit::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 24px;
    background: {t['panel']};
    border-left: 1px solid {t['border']};
    border-bottom-right-radius: 9px;
}}
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover, QDateTimeEdit::down-button:hover {{
    background: {border2};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QDateTimeEdit::up-arrow {{
    width: 8px; height: 8px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {t['text_sec']};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QDateTimeEdit::down-arrow {{
    width: 8px; height: 8px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {t['text_sec']};
}}
QSpinBox::up-arrow:hover, QDoubleSpinBox::up-arrow:hover, QDateTimeEdit::up-arrow:hover {{
    border-bottom-color: {t['accent']};
}}
QSpinBox::down-arrow:hover, QDoubleSpinBox::down-arrow:hover, QDateTimeEdit::down-arrow:hover {{
    border-top-color: {t['accent']};
}}

/* ── QComboBox Dropdown ─────────────────────────────────── */
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 24px;
    border-left: 1px solid {t['border']};
    border-top-right-radius: 9px;
    border-bottom-right-radius: 9px;
    background: {t['panel']};
}}
QComboBox::drop-down:hover {{
    background: {border2};
}}
QComboBox::down-arrow {{
    width: 8px; height: 8px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {t['text_sec']};
}}
QComboBox::down-arrow:hover {{
    border-top-color: {t['accent']};
}}
QComboBox QAbstractItemView {{
    background: {t['card']};
    color: {t['text']};
    border: 1px solid {border2};
    selection-background-color: {t['accent']};
    selection-color: #ffffff;
    outline: none;
}}

/* ── QGroupBox ──────────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {t['border']};
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
    background: transparent;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {t['text_sec']};
    font-weight: 700;
    font-size: 11px;
}}

/* ── QScrollBar Vertical ────────────────────────────────── */
QScrollBar:vertical {{
    background: {t['panel']};
    width: 10px;
    border-radius: 5px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {border2};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t['accent']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

/* ── QScrollBar Horizontal ──────────────────────────────── */
QScrollBar:horizontal {{
    background: {t['panel']};
    height: 10px;
    border-radius: 5px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {border2};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t['accent']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* ── QSplitter Handle ───────────────────────────────────── */
QSplitter::handle {{
    background: {t['border']};
}}
QSplitter::handle:hover {{
    background: {t['accent']};
}}
QSplitter::handle:vertical {{
    height: 3px;
    margin: 2px 0;
}}
QSplitter::handle:horizontal {{
    width: 3px;
    margin: 0 2px;
}}

/* ── QToolTip ───────────────────────────────────────────── */
QToolTip {{
    background: {t['card']};
    color: {t['text']};
    border: 1px solid {border2};
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 12px;
}}
"""

def matplotlib_dark_style(fig, *axes):
    bg = DARK_THEME["bg"]
    panel = "#111827"
    text = DARK_THEME["text"]
    grid = "#334155"

    fig.patch.set_facecolor(bg)

    for ax in axes:
        ax.set_facecolor(panel)
        ax.tick_params(colors=text, which="both", labelsize=10)
        ax.xaxis.label.set_color(text)
        ax.yaxis.label.set_color(text)
        ax.title.set_color(text)
        ax.grid(True, color=grid, linewidth=1.0, alpha=0.6)
        for spine in ax.spines.values():
            spine.set_edgecolor(grid)
            spine.set_linewidth(1.2)


def _colorize_toolbar_icons(toolbar, color_hex: str, size: int = 18):
    """Färbt alle Icons der matplotlib-Toolbar in der gewünschten Farbe ein."""
    from PyQt6.QtWidgets import QToolButton
    from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
    from PyQt6.QtCore import Qt
    color = QColor(color_hex)
    q_size = QSize(size, size)
    for btn in toolbar.findChildren(QToolButton):
        icon = btn.icon()
        if icon.isNull():
            continue
        src = icon.pixmap(q_size)
        dst = QPixmap(src.size())
        dst.fill(Qt.GlobalColor.transparent)
        painter = QPainter(dst)
        painter.drawPixmap(0, 0, src)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceIn
        )
        painter.fillRect(dst.rect(), color)
        painter.end()
        btn.setIcon(QIcon(dst))

def matplotlib_toolbar_style(toolbar, dark: bool = True):
    toolbar.setIconSize(QSize(18, 18))
    toolbar.setMinimumHeight(44)

    if dark:
        toolbar.setStyleSheet("""
            QToolBar {
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 10px;
                spacing: 4px;
                padding: 5px 8px;
            }
            QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 5px;
                min-width: 30px;
                min-height: 30px;
                color: #cbd5e1;
            }
            QToolButton:hover {
                background: #1e293b;
                border-color: #334155;
            }
            QToolButton:pressed,
            QToolButton:checked {
                background: #2563eb;
                border-color: #2563eb;
                color: #ffffff;
            }
            QToolBar QLabel {
                color: #94a3b8;
                font-size: 11px;
                font-weight: 600;
                padding-left: 6px;
                min-width: 120px;
            }
        """)
    else:
        toolbar.setStyleSheet("""
            QToolBar {
                background: #f8fafc;
                border: 1px solid #d8dee8;
                border-radius: 10px;
                spacing: 4px;
                padding: 5px 8px;
            }
            QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 5px;
                min-width: 30px;
                min-height: 30px;
                color: #0f172a;
            }
            QToolButton:hover {
                background: #ffffff;
                border-color: #c5d0df;
            }
            QToolButton:pressed,
            QToolButton:checked {
                background: #dbeafe;
                border-color: #93c5fd;
                color: #0f172a;
            }
            QToolBar QLabel {
                color: #334155;
                font-size: 11px;
                font-weight: 700;
                padding-left: 6px;
                min-width: 120px;
            }
        """)

    # Icons einfärben: matplotlib liefert schwarze SVGs → auf dunklem BG unsichtbar.
    # Rot für beide Themes – gut erkennbar, passt zum wissenschaftlichen Look.
    icon_color = "#4ade80" if dark else "#16a34a"
    _colorize_toolbar_icons(toolbar, icon_color, size=18)
