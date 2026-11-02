"""Lumo's native desktop application: background voice pipeline and companion widget."""

from __future__ import annotations

import math
import sys
import tempfile
import time
from importlib.resources import files
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from voice_control_pc.asr import FasterWhisperTranscriber
from voice_control_pc.audio import list_input_devices, record_microphone_to_wav
from voice_control_pc.config import load_config_bundle, resolved_asr_settings, save_preferences
from voice_control_pc.history import HistoryStore
from voice_control_pc.models import ResolvedConfig
from voice_control_pc.service import VoiceControlService
from voice_control_pc.ui.pet import DesktopPet, LumoFace
from voice_control_pc.ui.settings import SettingsDialog
from voice_control_pc.ui.theme import apply_theme

ACTIONS = {
    "open_app": "Открыть приложение",
    "open_folder": "Открыть папку",
    "take_screenshot": "Сохранить снимок экрана",
    "close_window": "Закрыть активное окно",
    "show_desktop": "Показать рабочий стол",
    "open_task_manager": "Открыть диспетчер задач",
    "open_settings": "Открыть настройки Windows",
    "open_terminal": "Открыть терминал",
    "lock_pc": "Заблокировать компьютер",
    "shutdown_pc": "Выключить компьютер",
    "restart_pc": "Перезагрузить компьютер",
}


def describe_match(match: dict) -> str:
    if not match.get("action"):
        return "Не удалось определить действие"
    label = ACTIONS.get(match["action"], "Неизвестное действие")
    target = match.get("slots", {}).get("app_name") or match.get("slots", {}).get("folder_name")
    return f"{label}: {target.replace('_', ' ')}" if target else label


class RecordingStop(Event):
    cancelled = False

    def cancel(self):
        self.cancelled = True
        self.set()


class Task(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function
        self.stop = RecordingStop()

    def run(self):
        try:
            self.done.emit(self.function(self.progress.emit, self.stop))
        except Exception as error:
            self.failed.emit(str(error))


class LumoWindow(QMainWindow):
    hotkey_requested = Signal()

    def __init__(self, config: ResolvedConfig):
        super().__init__()
        apply_theme(QApplication.instance())
        self.config = config
        self.service = None
        self.transcriber = None
        self.job = None
        self.operation = ""
        self.pending_token = ""
        self.pending_text = ""
        self.deadline = 0.0
        self.keyboard_hook = None
        self.shortcut = None
        self.is_recording = False
        self.history_store = HistoryStore(config.project_root / "history.jsonl")
        self.setWindowTitle("Лумо · голосовой помощник")
        self.resize(1060, 780)
        self.setMinimumSize(900, 720)
        self._build()
        self.pet = DesktopPet(config.settings.pet)
        self.pet.open_requested.connect(self.reveal)
        self.pet.listen_requested.connect(self.start_voice)
        self.pet.moved.connect(self._pet_moved)
        self.pet.preferences_changed.connect(self._save_pet)
        self.pet.quit_requested.connect(self.close)
        self.hotkey_requested.connect(self.start_voice)
        self._bind_hotkey()
        self.confirm_timer = QTimer(self)
        self.confirm_timer.setInterval(200)
        self.confirm_timer.timeout.connect(self._tick_confirmation)
        self.reset_timer = QTimer(self)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(lambda: self.set_state("idle"))
        for row in reversed(self.history_store.read()):
            self._history_item(row)
        self._mode_label()

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(20, 20, 24, 20)
        outer.setSpacing(24)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(214)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(20, 26, 20, 22)
        left.setSpacing(15)
        brand = QLabel("LUMO")
        brand.setObjectName("brand")
        left.addWidget(brand)
        caption = QLabel("ГОЛОСОВОЙ ПОМОЩНИК")
        caption.setObjectName("eyebrow")
        left.addWidget(caption)
        left.addStretch()
        self.portrait = LumoFace()
        self.portrait.setFixedSize(170, 148)
        left.addWidget(self.portrait)
        name = QLabel("Рядом, когда нужен.")
        name.setWordWrap(True)
        name.setStyleSheet("font-size:20px; font-weight:500;")
        left.addWidget(name)
        text = QLabel("Скажи, что нужно сделать.\nОстальное — вместе.")
        text.setWordWrap(True)
        text.setStyleSheet("color:#a4a5ad;")
        left.addWidget(text)
        left.addStretch()
        settings = QPushButton("Настроить Лумо")
        settings.clicked.connect(self.open_settings)
        self.settings_button = settings
        left.addWidget(settings)
        pet_only = QPushButton("Только питомец")
        pet_only.clicked.connect(self.minimize_to_pet)
        left.addWidget(pet_only)
        self.pet_button = QPushButton("Скрыть питомца")
        self.pet_button.clicked.connect(self.toggle_pet)
        left.addWidget(self.pet_button)
        foot = QLabel("Локально. Под твоим контролем.")
        foot.setStyleSheet("font-size:10px; color:#94959e;")
        left.addWidget(foot)
        outer.addWidget(sidebar)
        content = QVBoxLayout()
        content.setSpacing(18)
        outer.addLayout(content, 1)
        head = QHBoxLayout()
        eyebrow = QLabel("ЛУМО / ГЛАВНАЯ")
        eyebrow.setObjectName("eyebrow")
        head.addWidget(eyebrow)
        head.addStretch()
        self.mode = QLabel()
        self.mode.setObjectName("status")
        head.addWidget(self.mode)
        content.addLayout(head)
        heading = QLabel("Что сделаем сегодня?")
        heading.setObjectName("heading")
        content.addWidget(heading)
        subtitle = QLabel("Открыть приложение, найти папку или освободить рабочий стол.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        content.addWidget(subtitle)
        voice, voice_box = self._card()
        voice_head = QHBoxLayout()
        section = QLabel("Чем помочь?")
        section.setObjectName("section")
        voice_head.addWidget(section)
        voice_head.addStretch()
        self.status = QLabel("Готов к команде")
        self.status.setObjectName("subtitle")
        voice_head.addWidget(self.status)
        voice_box.addLayout(voice_head)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Например: открой папку загрузки")
        self.input.setAccessibleName("Текст команды")
        self.input.returnPressed.connect(self.start_text)
        voice_box.addWidget(self.input)
        buttons = QHBoxLayout()
        self.record = QPushButton("Слушать команду")
        self.record.setObjectName("primary")
        self.record.clicked.connect(self.start_voice)
        buttons.addWidget(self.record)
        self.run_button = QPushButton("Выполнить текст")
        self.run_button.clicked.connect(self.start_text)
        buttons.addWidget(self.run_button)
        self.hotkey_label = QLabel()
        self.hotkey_label.setObjectName("subtitle")
        buttons.addWidget(self.hotkey_label)
        buttons.addStretch()
        voice_box.addLayout(buttons)
        examples = QHBoxLayout()
        for phrase in ("Открой браузер", "Покажи рабочий стол", "Сделай скриншот"):
            button = QPushButton(phrase)
            button.setStyleSheet("font-size:11px; padding:7px 9px;")
            button.clicked.connect(lambda checked=False, p=phrase: self.input.setText(p))
            examples.addWidget(button)
        voice_box.addLayout(examples)
        content.addWidget(voice)
        result, result_box = self._card()
        result_box.addWidget(self._label("КАК Я ПОНЯЛ", "eyebrow"))
        self.heard = QLabel("Здесь появится услышанная команда")
        self.heard.setObjectName("subtitle")
        self.heard.setWordWrap(True)
        self.heard.setTextFormat(Qt.TextFormat.PlainText)
        result_box.addWidget(self.heard)
        self.interpretation = QLabel("Жду твою первую команду")
        self.interpretation.setObjectName("result")
        self.interpretation.setWordWrap(True)
        self.interpretation.setTextFormat(Qt.TextFormat.PlainText)
        result_box.addWidget(self.interpretation)
        self.feedback = QLabel("Можно начать с текста или нажать «Слушать команду».")
        self.feedback.setWordWrap(True)
        self.feedback.setObjectName("subtitle")
        self.feedback.setTextFormat(Qt.TextFormat.PlainText)
        result_box.addWidget(self.feedback)
        self.confirm_box = QFrame()
        self.confirm_box.setObjectName("confirmation")
        confirm_layout = QHBoxLayout(self.confirm_box)
        self.confirm_label = QLabel()
        self.confirm_label.setWordWrap(True)
        confirm_layout.addWidget(self.confirm_label, 1)
        self.yes_button = QPushButton("Подтвердить")
        self.yes_button.clicked.connect(self.confirm)
        no = QPushButton("Отмена")
        no.clicked.connect(self.cancel_confirmation)
        confirm_layout.addWidget(self.yes_button)
        confirm_layout.addWidget(no)
        self.confirm_box.hide()
        result_box.addWidget(self.confirm_box)
        content.addWidget(result)
        history, history_box = self._card()
        hist_head = QHBoxLayout()
        hist_head.addWidget(self._label("Последние команды", "section"))
        hist_head.addStretch()
        clear = QPushButton("Очистить")
        clear.setStyleSheet("padding:5px 10px; font-size:11px;")
        clear.clicked.connect(self.clear_history)
        hist_head.addWidget(clear)
        history_box.addLayout(hist_head)
        self.history = QListWidget()
        self.history.setMinimumHeight(80)
        history_box.addWidget(self.history)
        content.addWidget(history, 1)
        self.footer = QLabel("Голос обрабатывается на этом компьютере. Записи не сохраняются.")
        self.footer.setWordWrap(True)
        self.footer.setObjectName("subtitle")
        content.addWidget(self.footer)

    def _label(self, text, name):
        label = QLabel(text)
        label.setObjectName(name)
        return label

    def _card(self):
        card = QFrame()
        card.setObjectName("card")
        box = QVBoxLayout(card)
        box.setContentsMargins(22, 18, 22, 18)
        box.setSpacing(13)
        return card, box

    def _mode_label(self):
        self.mode.setText(
            "Проверка без действий" if self.config.settings.app.dry_run else "Выполнение включено"
        )
        self.pet_button.setText(
            "Скрыть питомца" if self.config.settings.pet.enabled else "Показать питомца"
        )

    def _get_service(self):
        if self.service is None:
            self.service = VoiceControlService(self.config)
        return self.service

    def _get_transcriber(self):
        if self.transcriber is None:
            self.transcriber = FasterWhisperTranscriber(resolved_asr_settings(self.config))
        return self.transcriber

    def _start(self, operation, function):
        if self.job is not None:
            return
        self.reset_timer.stop()
        self.operation = operation
        self.job = Task(function, self)
        self.job.done.connect(self._completed)
        self.job.failed.connect(self._failed)
        self.job.progress.connect(self._progress)
        self.job.finished.connect(self._finished)
        self.run_button.setEnabled(False)
        self.settings_button.setEnabled(False)
        self.input.setEnabled(False)
        self.yes_button.setEnabled(False)
        self.record.setEnabled(operation == "voice")
        self.job.start()

    def start_text(self):
        if self.job is not None:
            return
        text = self.input.text().strip()
        if not text:
            self.feedback.setText("Введи команду или включи микрофон.")
            return
        self.cancel_confirmation()
        self.set_state("thinking")
        self._start(
            "command", lambda progress, stop: self._get_service().process_text_command(text)
        )

    def start_voice(self):
        if self.job is not None:
            if self.operation == "voice" and self.is_recording:
                self.job.stop.set()
                self.record.setText("Завершаю запись…")
                self.record.setEnabled(False)
            return
        self.cancel_confirmation()
        self.set_state("thinking")

        def voice(progress, stop):
            transcriber = self._get_transcriber()
            progress("loading")
            transcriber.load()
            if stop.is_set():
                raise RuntimeError("Запись отменена")
            with tempfile.TemporaryDirectory(prefix="lumo-") as directory:
                path = Path(directory) / "command.wav"
                progress("listening")
                record_microphone_to_wav(path, self.config.settings.audio, stop_event=stop)
                if stop.cancelled:
                    raise RuntimeError("Запись отменена")
                progress("thinking")
                text = transcriber.transcribe_file(path)
                if stop.cancelled:
                    raise RuntimeError("Распознавание отменено")
            return self._get_service().process_text_command(text)

        self._start("voice", voice)

    def _progress(self, stage):
        self.is_recording = stage == "listening"
        self.set_state("listening" if self.is_recording else "thinking")
        self.status.setText(
            {
                "loading": "Загружаю модель…",
                "listening": "Говори, я слушаю…",
                "thinking": "Распознаю команду…",
            }.get(stage, stage)
        )
        self.record.setText("Остановить запись" if self.is_recording else "Обрабатываю…")
        self.record.setEnabled(self.is_recording)

    def _completed(self, value):
        if self.operation == "settings":
            devices, error = value
            self._devices = devices
            if error:
                self.footer.setText(error)
            QTimer.singleShot(0, self._show_settings)
            return
        if self.operation == "confirm":
            match, result = self.last_match, value
        else:
            match, result = value
        result = result.model_copy(deep=True)
        if result.status == "dry_run":
            result.message = "Команда проверена. Действие не выполнялось."
        elif result.status == "confirmation_required":
            result.message = "Проверь действие и подтверди, если всё верно."
        self.last_result = result
        self.last_match = match
        text = match.get("text", "")
        self.pending_text = text
        self.heard.setText(f"Услышал: {text}" if text else "Речь не распознана")
        self.interpretation.setText(describe_match(match))
        self.feedback.setText(result.message)
        if result.status == "confirmation_required":
            self.pending_token = result.artifacts["confirmation_token"]
            self.deadline = time.monotonic() + self.config.settings.execution.confirmation_ttl_sec
            self.confirm_box.show()
            self.confirm_timer.start()
            self._tick_confirmation()
            self.set_state("confirm")
        else:
            self.set_state("success" if result.success else "error")
            self.reset_timer.start(4000)
        try:
            self.history_store.append(text, result)
            self.history.clear()
            for row in reversed(self.history_store.read()):
                self._history_item(row)
        except OSError as error:
            self.footer.setText(f"Не удалось сохранить историю: {error}")

    def _finished(self):
        job, self.job = self.job, None
        if job is not None:
            job.deleteLater()
        self.is_recording = False
        self.record.setText("Слушать команду")
        self.record.setEnabled(True)
        self.run_button.setEnabled(True)
        self.settings_button.setEnabled(True)
        self.input.setEnabled(True)
        self.yes_button.setEnabled(True)

    def _failed(self, message):
        self.feedback.setText(message)
        self.set_state("error")
        self.reset_timer.start(5000)

    def set_state(self, state):
        self.reset_timer.stop() if hasattr(self, "reset_timer") else None
        self.portrait.set_state(state)
        if hasattr(self, "pet"):
            self.pet.set_state(state)
        self.status.setText(
            {
                "idle": "Готов к команде",
                "listening": "Слушаю…",
                "thinking": "Думаю…",
                "success": "Готово",
                "error": "Нужно внимание",
                "confirm": "Жду подтверждения",
            }[state]
        )

    def _tick_confirmation(self):
        remaining = math.ceil(self.deadline - time.monotonic())
        if remaining <= 0:
            self.cancel_confirmation()
            self.feedback.setText("Время подтверждения истекло. Повтори команду.")
            return
        self.confirm_label.setText(f"Выполнить это действие?\nОсталось {remaining} с")

    def confirm(self):
        if not self.pending_token or self.job is not None:
            return
        token = self.pending_token
        self.pending_token = ""
        self.confirm_timer.stop()
        self.confirm_box.hide()
        self.set_state("thinking")
        self._start("confirm", lambda progress, stop: self._get_service().confirm_command(token))

    def cancel_confirmation(self):
        self.pending_token = ""
        if hasattr(self, "confirm_timer"):
            self.confirm_timer.stop()
        self.confirm_box.hide()
        if self.service is not None and self.job is None:
            self.service.cancel_pending()
        if hasattr(self, "pet"):
            self.set_state("idle")

    def _history_item(self, row):
        stamp = row["time"][11:16]
        item = QListWidgetItem(f"{stamp}   {row['text']}\n          {row['message']}")
        item.setToolTip(row["status"])
        self.history.addItem(item)

    def clear_history(self):
        try:
            self.history_store.clear()
            self.history.clear()
        except OSError as error:
            self.footer.setText(str(error))

    def open_settings(self):
        if self.job is not None:
            return
        self.cancel_confirmation()

        def scan(progress, stop):
            try:
                return list_input_devices(), ""
            except Exception as error:
                return [], str(error)

        self._start("settings", scan)

    def _show_settings(self):
        if self.job is not None:
            QTimer.singleShot(20, self._show_settings)
            return
        dialog = SettingsDialog(self.config, self._devices, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        try:
            save_preferences(dialog.config)
            self.config = dialog.config
            self.service = self.transcriber = None
            self.pet.settings = self.config.settings.pet
            self.pet.apply_settings()
            self._bind_hotkey()
            self._mode_label()
            self.footer.setText("Настройки сохранены. Лумо готов к работе.")
        except Exception as error:
            QMessageBox.warning(self, "Настройки не сохранены", str(error))

    def _bind_hotkey(self):
        if self.keyboard_hook is not None:
            import keyboard

            keyboard.remove_hotkey(self.keyboard_hook)
            self.keyboard_hook = None
        if self.shortcut is not None:
            self.shortcut.setEnabled(False)
            self.shortcut.deleteLater()
        sequence = self.config.settings.app.hotkey
        self.hotkey_label.setText(sequence.upper())
        self.shortcut = QShortcut(QKeySequence(sequence), self)
        self.shortcut.activated.connect(self.start_voice)
        if sys.platform == "win32":
            try:
                import keyboard

                self.keyboard_hook = keyboard.add_hotkey(sequence, self.hotkey_requested.emit)
                self.shortcut.setEnabled(False)
            except Exception as error:
                self.footer.setText(
                    f"Глобальная клавиша недоступна: {error}. Используй кнопку записи."
                )

    def _pet_moved(self, x, y):
        self._save_pet()

    def _save_pet(self):
        self._mode_label()
        try:
            save_preferences(self.config)
        except OSError as error:
            self.footer.setText(f"Не удалось сохранить положение: {error}")

    def toggle_pet(self):
        self.config.settings.pet.enabled = not self.config.settings.pet.enabled
        self.pet.apply_settings()
        self._save_pet()
        self._mode_label()

    def reveal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def minimize_to_pet(self):
        self.config.settings.pet.enabled = True
        self.pet.apply_settings()
        self._save_pet()
        self.hide()

    def closeEvent(self, event):
        if self.job is not None:
            self.job.stop.cancel()
            self.footer.setText("Дождись завершения текущей операции и закрой окно снова.")
            event.ignore()
            return
        self.cancel_confirmation()
        if self.keyboard_hook is not None:
            import keyboard

            keyboard.remove_hotkey(self.keyboard_hook)
        self.pet.close()
        event.accept()


def run_gui(config: ResolvedConfig | None = None, dry_run: bool | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Лумо")
    app.setOrganizationName("Lumo")
    app.setWindowIcon(QIcon(str(files("voice_control_pc.resources").joinpath("lumo.svg"))))
    config = config or load_config_bundle()
    if dry_run is not None:
        config.settings.app.dry_run = dry_run
    window = LumoWindow(config)
    window.show()
    return app.exec()


def smoke_gui() -> int:
    """Check the packaged window, resources and event loop without accessing hardware."""
    with tempfile.TemporaryDirectory(prefix="lumo-smoke-") as directory:
        app = QApplication.instance() or QApplication(sys.argv[:1])
        window = LumoWindow(load_config_bundle(Path(directory)))
        window.show()
        QTimer.singleShot(200, window.close)
        return app.exec()
