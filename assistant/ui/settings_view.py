"""
Настройки EVA — единая секция под Hero.

Структура:
  - одна карточка «Настройки»;
  - основные параметры видны всегда;
  - дополнительные — раскрываются по кнопке;
  - одна кнопка «Применить и сохранить»;
  - кнопка «Открыть лог».

Все значения сохраняются в settings.json через SettingsStore.
Mute НЕ сохраняется — управляется отдельным сигналом.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
    QToolButton, QVBoxLayout, QWidget,
)

from assistant import paths
from assistant.events import Event, EventType

from .theme import Palette, Radius, Spacing


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

def _card_frame() -> QFrame:
    frame = QFrame()
    frame.setProperty("role", "card")
    return frame


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "section")
    return label


def _subsection_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "dim")
    f = label.font()
    f.setBold(True)
    label.setFont(f)
    return label


def _make_form() -> QFormLayout:
    form = QFormLayout()
    form.setContentsMargins(0, 0, 0, 0)
    form.setSpacing(Spacing.SM)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    return form


def _list_input_devices_safe():
    try:
        from assistant.audio import list_input_devices
        return list_input_devices()
    except Exception:
        return []


_LLM_MODEL_KEY_BY_PROVIDER = {
    "gemini": "GEMINI_MODEL",
    "groq": "GROQ_MODEL",
    "cerebras": "CEREBRAS_MODEL",
    "openrouter": "OPENROUTER_MODEL",
    "deepseek": "DEEPSEEK_MODEL",
}


# ---------------------------------------------------------------------------
# SettingsPanel
# ---------------------------------------------------------------------------

class SettingsPanel(QWidget):
    save_requested = Signal(dict)
    cancelled = Signal()
    mute_toggled = Signal(bool)
    open_log_requested = Signal()

    def __init__(self, store, parent: Optional[QWidget] = None, bus=None):
        super().__init__(parent)
        self._store = store
        self._bus = bus

        self._inputs: dict[str, QWidget] = {}
        self._dirty = False
        self._extra_expanded = False

        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(Spacing.XXL, Spacing.XL, Spacing.XXL, Spacing.XL)
        outer.setSpacing(Spacing.LG)

        card = _card_frame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(Spacing.XL, Spacing.LG,
                                       Spacing.XL, Spacing.LG)
        card_layout.setSpacing(Spacing.MD)

        card_layout.addWidget(_section_title("НАСТРОЙКИ"))

        # --- Основные параметры ---
        main_form = _make_form()

        name = QLineEdit()
        self._register("ASSISTANT_NAME", name)
        main_form.addRow("Имя ассистента", name)

        aliases = QLineEdit()
        aliases.setPlaceholderText("через запятую; можно оставить пустым")
        self._register("ASSISTANT_ALIASES", aliases)
        main_form.addRow("Алиасы обращения", aliases)

        llm_provider = QComboBox()
        llm_provider.addItems([
            "router", "gemini", "groq", "cerebras",
            "openrouter", "deepseek", "echo",
        ])
        llm_provider.currentTextChanged.connect(self._on_llm_provider_changed)
        self._register("LLM_PROVIDER", llm_provider)
        main_form.addRow("LLM provider", llm_provider)

        self._llm_model_label = QLabel("Модель LLM")
        self._llm_model_edit = QLineEdit()
        self._llm_model_edit.textEdited.connect(self._mark_dirty)
        main_form.addRow(self._llm_model_label, self._llm_model_edit)

        whisper = QComboBox()
        whisper.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self._register("WHISPER_MODEL", whisper)
        main_form.addRow("STT модель", whisper)

        lang = QComboBox()
        lang.addItems(["ru", "en"])
        self._register("WHISPER_LANGUAGE", lang)
        main_form.addRow("STT язык", lang)

        tts = QComboBox()
        tts.addItems(["silero", "edge", "pyttsx3"])
        self._register("TTS_PROVIDER", tts)
        main_form.addRow("TTS provider", tts)

        speaker = QComboBox()
        speaker.addItems(["xenia", "baya", "kseniya", "aidar", "eugene", "random"])
        self._register("SILERO_SPEAKER", speaker)
        main_form.addRow("Голос", speaker)

        volume = QDoubleSpinBox()
        volume.setRange(0.0, 1.0)
        volume.setSingleStep(0.05)
        volume.setDecimals(2)
        self._register("UI_VOLUME", volume)
        main_form.addRow("Громкость", volume)

        rate = QSpinBox()
        rate.setRange(80, 320)
        rate.setSingleStep(10)
        self._register("UI_SPEECH_RATE", rate)
        main_form.addRow("Скорость речи", rate)

        # --- Режим извлечения параметров ---
        param_mode = QComboBox()
        param_mode.addItems(["ml", "кастыли"])
        self._register("PARAMETER_ROUTER_MODE", param_mode)
        main_form.addRow("Режим извлечения параметров", param_mode)

        # --- Папка с презентациями ---
        pres_row = QWidget()
        pres_layout = QHBoxLayout(pres_row)
        pres_layout.setContentsMargins(0, 0, 0, 0)
        pres_layout.setSpacing(Spacing.SM)

        pres_edit = QLineEdit()
        pres_edit.setReadOnly(True)
        self._register("PRESENTATIONS_DIR", pres_edit)

        pres_btn = QPushButton("Выбрать папку…")
        pres_btn.clicked.connect(self._on_pick_presentations_dir)

        pres_layout.addWidget(pres_edit, 1)
        pres_layout.addWidget(pres_btn, 0)

        main_form.addRow("Папка с презентациями", pres_row)

        # --- Файл журнала ---
        gb_row = QWidget()
        gb_layout = QHBoxLayout(gb_row)
        gb_layout.setContentsMargins(0, 0, 0, 0)
        gb_layout.setSpacing(Spacing.SM)

        gb_edit = QLineEdit()
        gb_edit.setReadOnly(True)
        self._register("GRADEBOOK_PATH", gb_edit)

        gb_btn = QPushButton("Выбрать файл…")
        gb_btn.clicked.connect(self._on_pick_gradebook_path)

        gb_layout.addWidget(gb_edit, 1)
        gb_layout.addWidget(gb_btn, 0)

        main_form.addRow("Файл журнала", gb_row)

        # --- Пороги презентаций ---
        pres_threshold = QDoubleSpinBox()
        pres_threshold.setRange(0.0, 1.0)
        pres_threshold.setSingleStep(0.01)
        pres_threshold.setDecimals(2)
        self._register("PRESENTATION_MATCH_THRESHOLD", pres_threshold)
        pres_threshold.valueChanged.connect(self._on_pres_threshold_changed)
        main_form.addRow("Порог совпадения презентаций", pres_threshold)

        pres_margin = QDoubleSpinBox()
        pres_margin.setRange(0.0, 1.0)
        pres_margin.setSingleStep(0.01)
        pres_margin.setDecimals(2)
        self._register("PRESENTATION_AMBIGUITY_MARGIN", pres_margin)
        pres_margin.valueChanged.connect(self._on_pres_margin_changed)
        main_form.addRow("Порог неоднозначности", pres_margin)

        card_layout.addLayout(main_form)

        # Mute — НЕ сохраняется, только сигнал.
        self._mic_cb = QCheckBox("Микрофон включён (снять mute)")
        self._mic_cb.setChecked(False)
        self._mic_cb.toggled.connect(self._on_mic_toggled)
        card_layout.addWidget(self._mic_cb)

        # --- Раскрытие дополнительных параметров ---
        extra_header = QHBoxLayout()
        extra_header.setContentsMargins(0, 0, 0, 0)
        extra_header.setSpacing(Spacing.SM)

        self._extra_btn = QToolButton()
        self._extra_btn.setArrowType(Qt.ArrowType.RightArrow)
        self._extra_btn.setCheckable(True)
        self._extra_btn.setAutoRaise(True)
        self._extra_btn.setStyleSheet(
            f"QToolButton {{ border: none; color: {Palette.TEXT_DIM}; }}"
        )
        self._extra_btn.setText("Дополнительные параметры")
        self._extra_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._extra_btn.clicked.connect(self._on_extra_toggle)
        extra_header.addWidget(self._extra_btn)
        extra_header.addStretch(1)
        card_layout.addLayout(extra_header)

        self._extra_body = QWidget()
        extra_layout = QVBoxLayout(self._extra_body)
        extra_layout.setContentsMargins(0, 0, 0, 0)
        extra_layout.setSpacing(Spacing.LG)

        extra_layout.addWidget(_subsection_label("Модели LLM (по провайдерам)"))
        llm_form = _make_form()
        for key, label in (
            ("GEMINI_MODEL", "Gemini"),
            ("GROQ_MODEL", "Groq"),
            ("CEREBRAS_MODEL", "Cerebras"),
            ("OPENROUTER_MODEL", "OpenRouter"),
            ("DEEPSEEK_MODEL", "DeepSeek"),
        ):
            edit = QLineEdit()
            self._register(key, edit)
            llm_form.addRow(label, edit)
        extra_layout.addLayout(llm_form)

        extra_layout.addWidget(_subsection_label("UI"))
        ui_form = _make_form()

        anim = QCheckBox("Анимации интерфейса")
        self._register("UI_ANIMATIONS_ENABLED", anim)
        ui_form.addRow("", anim)

        extra_layout.addLayout(ui_form)

        extra_layout.addWidget(_subsection_label("Аудио"))
        audio_form = _make_form()

        device = QComboBox()
        device.addItem("Автоматически", None)
        for d in _list_input_devices_safe():
            label = f"#{d.index} {d.name}"
            if getattr(d, "is_default", False):
                label += "  (по умолчанию)"
            if getattr(d, "is_monitor", False):
                label += "  [monitor]"
            device.addItem(label, d.index)
        self._register("INPUT_DEVICE_INDEX", device)
        audio_form.addRow("Микрофон", device)

        note = QLabel(
            "Применяется при следующем запуске приложения "
            "(нужен перезапуск ContinuousListener)."
        )
        note.setProperty("role", "dim")
        note.setWordWrap(True)
        audio_form.addRow("", note)

        extra_layout.addLayout(audio_form)

        extra_layout.addWidget(_subsection_label("Только для справки"))
        ro_form = _make_form()

        from config import Config
        ro_items = (
            ("CONFIDENCE_EXECUTE", getattr(Config, "CONFIDENCE_EXECUTE", "?")),
            ("CONFIDENCE_CLARIFY", getattr(Config, "CONFIDENCE_CLARIFY", "?")),
            ("RECORD_SECONDS", getattr(Config, "RECORD_SECONDS", "?")),
            ("SAMPLE_RATE", getattr(Config, "SAMPLE_RATE", "?")),
            ("LLM_ROUTER_COOLDOWN_SEC",
             getattr(Config, "LLM_ROUTER_COOLDOWN_SEC", "?")),
        )
        for label, value in ro_items:
            v = QLabel(str(value))
            v.setProperty("role", "dim")
            ro_form.addRow(label, v)

        hint = QLabel("Изменяются в .env, требуют перезапуска.")
        hint.setProperty("role", "dim")
        hint.setWordWrap(True)
        ro_form.addRow("", hint)

        extra_layout.addLayout(ro_form)

        extra_layout.addWidget(_subsection_label("Диагностика"))
        paths_label = QLabel(str(paths.describe()))
        paths_label.setProperty("role", "dim")
        paths_label.setWordWrap(True)
        paths_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        extra_layout.addWidget(paths_label)

        card_layout.addWidget(self._extra_body)
        self._extra_body.setVisible(False)

        outer.addWidget(card)

        # --- Footer ---
        footer = QFrame()
        footer.setStyleSheet(f"""
            QFrame {{
                background: {Palette.SURFACE};
                border: 1px solid {Palette.BORDER_SOFT};
                border-radius: {Radius.MD}px;
            }}
        """)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(Spacing.XL, Spacing.MD,
                                         Spacing.XL, Spacing.MD)
        footer_layout.setSpacing(Spacing.MD)

        self._status = QLabel("")
        self._status.setProperty("role", "dim")
        self._status.setWordWrap(True)
        footer_layout.addWidget(self._status, 1)

        self._log_btn = QPushButton("Открыть лог")
        self._log_btn.clicked.connect(self.open_log_requested.emit)
        footer_layout.addWidget(self._log_btn)

        self._reset_btn = QPushButton("Отменить изменения")
        self._reset_btn.clicked.connect(self._on_reset)
        self._reset_btn.setEnabled(False)
        footer_layout.addWidget(self._reset_btn)

        self._save_btn = QPushButton("Применить и сохранить")
        self._save_btn.setProperty("role", "primary")
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setEnabled(False)
        footer_layout.addWidget(self._save_btn)

        outer.addWidget(footer)

    # ------------------------------------------------------------------
    def _on_extra_toggle(self, checked: bool) -> None:
        self._extra_expanded = checked
        self._extra_body.setVisible(checked)
        self._extra_btn.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )

    # ------------------------------------------------------------------
    def _register(self, key: str, widget: QWidget) -> None:
        self._inputs[key] = widget
        if isinstance(widget, QLineEdit):
            widget.textEdited.connect(self._mark_dirty)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self._mark_dirty)
        elif isinstance(widget, QCheckBox):
            widget.stateChanged.connect(self._mark_dirty)
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            widget.valueChanged.connect(self._mark_dirty)

    # ------------------------------------------------------------------
    def _current_llm_model_key(self) -> Optional[str]:
        provider = self._inputs["LLM_PROVIDER"].currentText()
        return _LLM_MODEL_KEY_BY_PROVIDER.get(provider)

    def _on_llm_provider_changed(self, provider: str) -> None:
        model_key = _LLM_MODEL_KEY_BY_PROVIDER.get(provider)
        if model_key is None:
            self._llm_model_edit.setEnabled(False)
            self._llm_model_edit.setPlaceholderText(
                "Для router/echo модель задаётся в дополнительных параметрах"
            )
            self._llm_model_edit.setText("")
            return
        from config import Config
        self._llm_model_edit.setEnabled(True)
        self._llm_model_edit.setPlaceholderText("")
        self._llm_model_edit.setText(str(getattr(Config, model_key, "") or ""))

    def _on_pick_presentations_dir(self) -> None:
        current = self._inputs["PRESENTATIONS_DIR"].text() or str(paths.presentations_dir())
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку с презентациями",
            current,
        )
        if chosen:
            self._inputs["PRESENTATIONS_DIR"].setText(chosen)
            self._mark_dirty()

    def _on_pick_gradebook_path(self) -> None:
        current = self._inputs["GRADEBOOK_PATH"].text() or str(paths.gradebook_path())
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл журнала",
            current,
            "Excel (*.xlsx *.xls *.xlsm)",
        )
        if chosen:
            self._inputs["GRADEBOOK_PATH"].setText(chosen)
            self._mark_dirty()

    def _on_pres_threshold_changed(self, value: float) -> None:
        w = self._inputs.get("PRESENTATION_MATCH_THRESHOLD")
        if w is not None:
            w.setSuffix(f"   ({int(round(value * 100))}%)")

    def _on_pres_margin_changed(self, value: float) -> None:
        w = self._inputs.get("PRESENTATION_AMBIGUITY_MARGIN")
        if w is not None:
            w.setSuffix(f"   ({int(round(value * 100))}%)")

    # ------------------------------------------------------------------
    def _load_values(self) -> None:
        from config import Config

        for key, widget in self._inputs.items():
            value = getattr(Config, key, None)

            if key == "ASSISTANT_ALIASES":
                if isinstance(value, list):
                    widget.setText(", ".join(value))
                else:
                    widget.setText(str(value) if value else "")
                continue

            if key == "INPUT_DEVICE_INDEX":
                idx = widget.findData(value)
                widget.setCurrentIndex(idx if idx >= 0 else 0)
                continue

            if key == "PRESENTATIONS_DIR":
                widget.setText(str(value or paths.presentations_dir()))
                continue

            if key == "GRADEBOOK_PATH":
                widget.setText(str(value or paths.gradebook_path()))
                continue

            if isinstance(widget, QLineEdit):
                widget.setText("" if value is None else str(value))
            elif isinstance(widget, QComboBox):
                idx = widget.findText(str(value)) if value is not None else -1
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value) if value is not None else 0.0)
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value) if value is not None else 0)

        self._on_llm_provider_changed(self._inputs["LLM_PROVIDER"].currentText())
        self._on_pres_threshold_changed(
            self._inputs["PRESENTATION_MATCH_THRESHOLD"].value()
        )
        self._on_pres_margin_changed(
            self._inputs["PRESENTATION_AMBIGUITY_MARGIN"].value()
        )

        self._set_clean()

    def _collect_values(self) -> dict:
        data: dict = {}
        for key, widget in self._inputs.items():
            if key == "INPUT_DEVICE_INDEX":
                idx = widget.currentIndex()
                data[key] = widget.itemData(idx)
            elif key == "ASSISTANT_ALIASES":
                data[key] = widget.text().strip()
            elif isinstance(widget, QLineEdit):
                data[key] = widget.text().strip()
            elif isinstance(widget, QComboBox):
                data[key] = widget.currentText()
            elif isinstance(widget, QCheckBox):
                data[key] = widget.isChecked()
            elif isinstance(widget, QDoubleSpinBox):
                data[key] = widget.value()
            elif isinstance(widget, QSpinBox):
                data[key] = widget.value()

        model_key = self._current_llm_model_key()
        if model_key is not None and self._llm_model_edit.isEnabled():
            data[model_key] = self._llm_model_edit.text().strip()

        return data

    # ------------------------------------------------------------------
    def _mark_dirty(self, *_args) -> None:
        if not self._dirty:
            self._dirty = True
            self._save_btn.setEnabled(True)
            self._reset_btn.setEnabled(True)
            self._status.setText("Есть несохранённые изменения")
            self._status.setStyleSheet(f"color: {Palette.WARN};")

    def _set_clean(self) -> None:
        self._dirty = False
        self._save_btn.setEnabled(False)
        self._reset_btn.setEnabled(False)
        self._status.setText("")
        self._status.setStyleSheet("")

    def has_unsaved_changes(self) -> bool:
        return self._dirty

    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        try:
            data = self._collect_values()
            self._store.save_from(data)
            self._set_clean()
            self.save_requested.emit(data)
            self._status.setText("Сохраняю и применяю…")
            self._status.setStyleSheet(f"color: {Palette.TEXT_DIM};")
        except Exception as e:
            self._status.setText("Не удалось сохранить настройки")
            self._status.setStyleSheet(f"color: {Palette.ERR};")
            print(f"[Settings] save error: {e}", flush=True)

    def _on_reset(self) -> None:
        self._load_values()
        self.cancelled.emit()

    # ------------------------------------------------------------------
    def set_mute_state(self, muted: bool) -> None:
        self._mic_cb.blockSignals(True)
        self._mic_cb.setChecked(not muted)
        self._mic_cb.blockSignals(False)

    def _on_mic_toggled(self, checked: bool) -> None:
        muted = not checked
        if self._bus is not None:
            self._bus.publish(Event(
                type=EventType.MICROPHONE_MUTED_CHANGED,
                payload={"muted": muted},
            ))
        self.mute_toggled.emit(muted)

    def reload_values(self) -> None:
        self._load_values()

    def show_rebuild_result(self, ok: bool, error: str) -> None:
        if ok:
            self._status.setText("Применено и сохранено")
            self._status.setStyleSheet(f"color: {Palette.OK};")
            return

        self._status.setText(
            "Настройки сохранены, но применить их сейчас не удалось.\n"
            "Продолжаю работать с предыдущими компонентами.\n"
            f"Причина: {error or 'неизвестная ошибка'}.\n"
            "При следующем запуске EVA попробует применить сохранённые настройки."
        )
        self._status.setStyleSheet(f"color: {Palette.ERR};")
