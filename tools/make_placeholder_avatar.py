"""
Создаёт placeholder-картинки аватара для всех состояний.
Путь берётся из assistant.paths.avatar_dir().

Запуск: python -m tools.make_placeholder_avatar
"""
import os

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QColor, QPainter, QPixmap, QRadialGradient, QFont, QPen, QBrush,
)
from PySide6.QtWidgets import QApplication

from assistant import paths


STATES = {
    "idle":                 ("#38bdf8", "IDLE"),
    "listening":            ("#22c55e", "LISTENING"),
    "thinking":             ("#a855f7", "THINKING"),
    "speaking_1":           ("#ef4444", "SPEAKING 1"),
    "speaking_2":           ("#ef4444", "SPEAKING 2"),
    "speaking_3":           ("#ef4444", "SPEAKING 3"),
    "confirmation":         ("#f59e0b", "CONFIRM?"),
    "happy":                ("#22c55e", "HAPPY"),
    "error":                ("#dc2626", "ERROR"),
}

SIZE = 480


def _render(path: str, color_hex: str, label: str) -> None:
    pix = QPixmap(SIZE, SIZE)
    pix.fill(QColor("#0f172a"))

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    cx = cy = SIZE / 2
    color = QColor(color_hex)

    outer = SIZE * 0.45
    grad = QRadialGradient(cx, cy, outer)
    c1 = QColor(color); c1.setAlpha(120)
    c2 = QColor(color); c2.setAlpha(0)
    grad.setColorAt(0.0, c1)
    grad.setColorAt(1.0, c2)
    painter.setBrush(QBrush(grad))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(cx - outer, cy - outer, outer * 2, outer * 2))

    inner = SIZE * 0.30
    painter.setBrush(color)
    painter.setPen(QPen(QColor("#0f172a"), 0))
    painter.drawEllipse(QRectF(cx - inner, cy - inner, inner * 2, inner * 2))

    painter.setPen(QColor("#f8fafc"))
    f = QFont("Segoe UI", 22, QFont.Weight.Bold)
    painter.setFont(f)
    painter.drawText(
        QRectF(0, cy + inner + 12, SIZE, 48),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        label,
    )
    painter.end()

    pix.save(path, "PNG")


def main():
    _ = QApplication.instance() or QApplication([])

    out_dir = paths.avatar_dir()
    os.makedirs(out_dir, exist_ok=True)

    for state, (color, label) in STATES.items():
        path = os.path.join(str(out_dir), f"{state}.png")
        _render(path, color, label)
        print(f"[OK] {path}", flush=True)


if __name__ == "__main__":
    main()
