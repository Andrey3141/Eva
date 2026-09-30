"""
Единая визуальная тема EVA.
Единственный источник цветов, радиусов, отступов и шрифтов для UI.
"""
from __future__ import annotations

from PySide6.QtGui import QFont


class Palette:
    # Фон приложения
    BG = "#0b1120"
    SURFACE = "#111827"
    SURFACE_HI = "#172033"
    SURFACE_LO = "#0f172a"

    # Границы
    BORDER = "#1f2937"
    BORDER_SOFT = "#18202e"

    # Текст
    TEXT = "#e5e7eb"
    TEXT_DIM = "#94a3b8"
    TEXT_MUTED = "#64748b"
    TEXT_INVERT = "#0b1120"

    # Акцент
    ACCENT = "#3b82f6"
    ACCENT_HI = "#60a5fa"
    ACCENT_LO = "#1d4ed8"

    # Состояния
    OK = "#22c55e"
    WARN = "#f59e0b"
    ERR = "#ef4444"
    LISTEN = "#38bdf8"
    THINK = "#a855f7"
    SPEAK = "#ef4444"

    # Пузыри чата
    USER_BUBBLE = "#1e3a8a"
    USER_BUBBLE_HI = "#1e40af"
    ASSISTANT_BUBBLE = "#172033"
    ASSISTANT_BUBBLE_HI = "#1e293b"


class Radius:
    XS = 6
    SM = 8
    MD = 12
    LG = 16
    XL = 22
    PILL = 999


class Spacing:
    XS = 4
    SM = 8
    MD = 12
    LG = 18
    XL = 24
    XXL = 32


def default_font() -> QFont:
    f = QFont("Segoe UI", 10)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


# ---------------------------------------------------------------------------
# Готовые QSS-фрагменты
# ---------------------------------------------------------------------------

BASE_QSS = f"""
    QMainWindow, QWidget {{
        background: {Palette.BG};
        color: {Palette.TEXT};
    }}
"""


def app_qss() -> str:
    P = Palette
    R = Radius
    return f"""
    QMainWindow, QWidget {{
        background: {P.BG};
        color: {P.TEXT};
    }}

    QLabel[role="title"] {{
        color: {P.TEXT};
        font-size: 17px;
        font-weight: 700;
        letter-spacing: 0.4px;
    }}
    QLabel[role="subtitle"] {{
        color: {P.TEXT_DIM};
        font-size: 12px;
        letter-spacing: 0.6px;
    }}
    QLabel[role="section"] {{
        color: {P.TEXT_MUTED};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.2px;
    }}
    QLabel[role="body"] {{
        color: {P.TEXT};
        font-size: 13px;
    }}
    QLabel[role="dim"] {{
        color: {P.TEXT_DIM};
        font-size: 12px;
    }}

    QPushButton {{
        background: {P.SURFACE_HI};
        color: {P.TEXT};
        border: 1px solid {P.BORDER};
        border-radius: {R.SM}px;
        padding: 7px 14px;
        font-size: 12px;
    }}
    QPushButton:hover {{
        background: {P.SURFACE_LO};
        border-color: {P.BORDER_SOFT};
    }}
    QPushButton:pressed {{
        background: {P.BG};
    }}
    QPushButton:disabled {{
        color: {P.TEXT_MUTED};
        background: {P.SURFACE};
        border-color: {P.BORDER_SOFT};
    }}

    QPushButton[role="primary"] {{
        background: {P.ACCENT};
        border-color: {P.ACCENT};
        color: white;
        font-weight: 600;
    }}
    QPushButton[role="primary"]:hover {{
        background: {P.ACCENT_HI};
        border-color: {P.ACCENT_HI};
    }}
    QPushButton[role="primary"]:pressed {{
        background: {P.ACCENT_LO};
        border-color: {P.ACCENT_LO};
    }}

    QPushButton[role="ghost"] {{
        background: transparent;
        border: 1px solid transparent;
        color: {P.TEXT_DIM};
    }}
    QPushButton[role="ghost"]:hover {{
        background: {P.SURFACE_HI};
        color: {P.TEXT};
    }}

    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {P.SURFACE};
        color: {P.TEXT};
        border: 1px solid {P.BORDER};
        border-radius: {R.XS}px;
        padding: 6px 10px;
        font-size: 12px;
        selection-background-color: {P.ACCENT};
        selection-color: white;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {P.ACCENT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background: {P.SURFACE_HI};
        color: {P.TEXT};
        border: 1px solid {P.BORDER};
        selection-background-color: {P.ACCENT};
        selection-color: white;
    }}

    QCheckBox {{
        color: {P.TEXT};
        font-size: 12px;
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border-radius: 4px;
        border: 1px solid {P.BORDER};
        background: {P.SURFACE};
    }}
    QCheckBox::indicator:checked {{
        background: {P.ACCENT};
        border-color: {P.ACCENT};
    }}

    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {P.BORDER};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {P.BORDER_SOFT};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QDialog {{
        background: {P.BG};
    }}

    QFrame[role="card"] {{
        background: {P.SURFACE};
        border: 1px solid {P.BORDER_SOFT};
        border-radius: {R.MD}px;
    }}
    QFrame[role="divider"] {{
        background: {P.BORDER_SOFT};
        max-height: 1px;
    }}
"""
