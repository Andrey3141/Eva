"""
Просмотрщик логов EVA.

Показывает записи из GuiLogHandler в реальном времени.
Кнопки: Копировать, Сохранить как..., Очистить, Обновить.
Окно немодальное, не блокирует основной интерфейс.

Lifecycle подписки:
  - подписка на handler.new_line выполняется в showEvent(),
    если ещё не подписаны;
  - отписка — в closeEvent();
  - при каждом открытии буфер заливается заново,
    поэтому записи, сделанные пока окно было закрыто, попадают в окно.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from assistant.logging_setup import get_gui_handler

from .theme import Palette, Spacing


class LogView(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Лог EVA")
        self.resize(900, 560)
        self.setModal(False)

        self._handler = get_gui_handler()
        self._subscribed = False

        self._build_ui()
        # Подписка и заливка буфера — в showEvent().

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        layout.setSpacing(Spacing.MD)

        header = QLabel("Лог EVA")
        header.setProperty("role", "title")
        layout.addWidget(header)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        f = QFont("Consolas")
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setPointSize(9)
        self._text.setFont(f)
        self._text.setStyleSheet(
            f"QPlainTextEdit {{ background: {Palette.SURFACE_LO}; "
            f"color: {Palette.TEXT}; border: 1px solid {Palette.BORDER}; }}"
        )
        layout.addWidget(self._text, 1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(Spacing.SM)

        self._copy_btn = QPushButton("Копировать")
        self._copy_btn.clicked.connect(self._on_copy)
        buttons.addWidget(self._copy_btn)

        self._save_btn = QPushButton("Сохранить как…")
        self._save_btn.clicked.connect(self._on_save)
        buttons.addWidget(self._save_btn)

        self._clear_btn = QPushButton("Очистить")
        self._clear_btn.clicked.connect(self._on_clear)
        buttons.addWidget(self._clear_btn)

        self._refresh_btn = QPushButton("Обновить")
        self._refresh_btn.clicked.connect(self._on_refresh)
        buttons.addWidget(self._refresh_btn)

        buttons.addStretch(1)

        self._close_btn = QPushButton("Закрыть")
        self._close_btn.clicked.connect(self.close)
        buttons.addWidget(self._close_btn)

        layout.addLayout(buttons)

    # ------------------------------------------------------------------
    def _subscribe(self) -> None:
        if self._subscribed or self._handler is None:
            return
        try:
            self._handler.new_line.connect(self._append)
            self._subscribed = True
        except Exception:
            pass

    def _unsubscribe(self) -> None:
        if not self._subscribed or self._handler is None:
            return
        try:
            self._handler.new_line.disconnect(self._append)
        except Exception:
            pass
        self._subscribed = False

    def _drain_buffer(self) -> None:
        if self._handler is None:
            return
        self._text.clear()
        for line in self._handler.snapshot():
            self._append(line)

    # ------------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        self._subscribe()
        # Заливаем буфер при каждом открытии: записи, сделанные пока окно
        # было закрыто, попадут сюда.
        self._drain_buffer()

    def closeEvent(self, event):
        self._unsubscribe()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    def _append(self, line: str) -> None:
        self._text.appendPlainText(line)

    def _on_copy(self) -> None:
        cursor = self._text.textCursor()
        selected = cursor.selectedText()
        if selected:
            QGuiApplication.clipboard().setText(selected)
            return
        QGuiApplication.clipboard().setText(self._text.toPlainText())

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить лог", "eva_log.txt", "Текстовые файлы (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._text.toPlainText())
        except OSError as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить: {e}")

    def _on_clear(self) -> None:
        self._text.clear()

    def _on_refresh(self) -> None:
        self._drain_buffer()
