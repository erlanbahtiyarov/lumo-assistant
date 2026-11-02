"""Validated native settings, including allowlisted application and folder editors."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from voice_control_pc.models import AppEntry, FolderEntry, ResolvedConfig, Settings
from voice_control_pc.ui.pet import SIDES


class SettingsDialog(QDialog):
    def __init__(self, config: ResolvedConfig, devices: list, parent=None):
        super().__init__(parent)
        self.config = config.model_copy(deep=True)
        self.setWindowTitle("Настройки Лумо")
        self.resize(780, 610)
        layout = QVBoxLayout(self)
        title = QLabel("Настроим Лумо под тебя")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        audio = QFormLayout()
        self.device = QComboBox()
        self.device.addItem("Микрофон по умолчанию", None)
        for item in devices:
            self.device.addItem(f"{item['name']} · {item['index']}", item["index"])
        index = self.device.findData(config.settings.audio.device_index)
        if index < 0 and config.settings.audio.device_index is not None:
            self.device.addItem(
                f"Устройство {config.settings.audio.device_index}",
                config.settings.audio.device_index,
            )
            index = self.device.count() - 1
        self.device.setCurrentIndex(max(index, 0))
        audio.addRow("Микрофон", self.device)
        self.seconds = QSpinBox()
        self.seconds.setRange(1, 30)
        self.seconds.setValue(config.settings.audio.max_seconds)
        self.seconds.setSuffix(" с")
        audio.addRow("Максимальная запись", self.seconds)
        self.silence = QSpinBox()
        self.silence.setRange(200, 5000)
        self.silence.setValue(config.settings.audio.silence_timeout_ms)
        self.silence.setSuffix(" мс")
        audio.addRow("Пауза после речи", self.silence)
        self.threshold = QSpinBox()
        self.threshold.setRange(10, 10000)
        self.threshold.setValue(config.settings.audio.silence_threshold)
        audio.addRow("Порог тишины", self.threshold)
        self.hotkey = QLineEdit(config.settings.app.hotkey)
        self.hotkey.setPlaceholderText("F9")
        audio.addRow("Горячая клавиша", self.hotkey)
        self.dry = QCheckBox("Проверять команды без выполнения действий")
        self.dry.setChecked(config.settings.app.dry_run)
        audio.addRow(self.dry)
        audio.addRow(
            QLabel(
                "Глобальная клавиша поддерживается в Windows.\nВ Linux пока действует внутри окна приложения."
            )
        )
        tabs.addTab(self._page(audio), "Голос и управление")
        pet = QFormLayout()
        self.pet_enabled = QCheckBox("Показывать на рабочем столе")
        self.pet_enabled.setChecked(config.settings.pet.enabled)
        pet.addRow(self.pet_enabled)
        self.pet_size = QSpinBox()
        self.pet_size.setRange(96, 280)
        self.pet_size.setValue(config.settings.pet.size)
        self.pet_size.setSuffix(" px")
        pet.addRow("Размер питомца", self.pet_size)
        self.pet_top = QCheckBox("Поверх остальных окон")
        self.pet_top.setChecked(config.settings.pet.always_on_top)
        pet.addRow(self.pet_top)
        self.pet_lock = QCheckBox("Закрепить положение")
        self.pet_lock.setChecked(config.settings.pet.locked)
        pet.addRow(self.pet_lock)
        self.pet_edge = QComboBox()
        for side, label in SIDES.items():
            self.pet_edge.addItem(label, side)
        self.pet_edge.setCurrentIndex(self.pet_edge.findData(config.settings.pet.dock_side))
        pet.addRow("Край экрана", self.pet_edge)
        self.pet_offset = QSpinBox()
        self.pet_offset.setRange(0, 100)
        self.pet_offset.setValue(round(config.settings.pet.dock_offset * 100))
        self.pet_offset.setSuffix(" %")
        self.pet_offset.setToolTip("От левого края к правому или от верхнего к нижнему")
        pet.addRow("Положение вдоль края", self.pet_offset)
        self.reset_position = QCheckBox("Вернуть в центр верхнего края основного экрана")
        pet.addRow(self.reset_position)
        pet.addRow(
            QLabel(
                "Перетащи Лумо: он прикрепится к ближайшему краю экрана.\nВ ожидании — только питомец. Наведи мышь, чтобы открыть управление.\nДвойной щелчок — приложение. Правая кнопка — меню."
            )
        )
        tabs.addTab(self._page(pet), "Питомец")
        models = QFormLayout()
        self.asr_model = QComboBox()
        self.asr_model.setEditable(True)
        self.asr_model.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.asr_model.setCurrentText(config.settings.asr.model_name)
        models.addRow("Модель распознавания", self.asr_model)
        self.download = QCheckBox("Разрешить загрузку модели при первом распознавании")
        self.download.setChecked(config.settings.asr.allow_download)
        models.addRow(self.download)
        self.semantic = QCheckBox("Использовать локальную модель для свободных формулировок")
        self.semantic.setChecked(config.settings.nlu.semantic_enabled)
        models.addRow(self.semantic)
        self.semantic_name = QLineEdit(config.settings.nlu.semantic_model)
        models.addRow("Модель в Ollama", self.semantic_name)
        self.recovery = QCheckBox(
            "Использовать обученную модель восстановления, если она установлена"
        )
        self.recovery.setChecked(config.settings.nlu.neural_recovery_enabled)
        models.addRow(self.recovery)
        note = QLabel(
            "Для модели понимания нужен запущенный Ollama и загруженная модель.\nПредложения нейросети всегда требуют подтверждения.\nРечь и команды обрабатываются локально."
        )
        note.setWordWrap(True)
        models.addRow(note)
        tabs.addTab(self._page(models), "Модели")
        self.apps = self._table(config.apps.applications, True)
        self.folders = self._table(config.apps.folders, False)
        tabs.addTab(self._editor(self.apps, True), "Приложения")
        tabs.addTab(self._editor(self.folders, False), "Папки")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _page(self, form):
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.setContentsMargins(22, 24, 22, 24)
        form.setSpacing(20)
        box.addLayout(form)
        box.addStretch()
        return widget

    def _table(self, entries, apps):
        table = QTableWidget(len(entries), 3)
        table.setHorizontalHeaderLabels(
            ["Название", "Как можно назвать", "Программа" if apps else "Папка"]
        )
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().hide()
        for row, (key, item) in enumerate(entries.items()):
            values = [
                key,
                ", ".join(item.aliases),
                item.launch[0] if apps and item.launch else item.path if not apps else "",
            ]
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(value))
        return table

    def _editor(self, table, apps):
        widget = QWidget()
        box = QVBoxLayout(widget)
        label = QLabel(
            "Укажи название, варианты обращения через запятую и путь.\nЛумо открывает только приложения и папки из этого списка."
        )
        label.setWordWrap(True)
        box.addWidget(label)
        box.addWidget(table)
        buttons = QHBoxLayout()
        add = QPushButton("Добавить")
        remove = QPushButton("Удалить строку")
        browse = QPushButton("Выбрать путь…")

        def add_row():
            row = table.rowCount()
            table.insertRow(row)
            for col in range(3):
                table.setItem(row, col, QTableWidgetItem(""))
            table.setCurrentCell(row, 0)

        def choose():
            row = table.currentRow()
            if row < 0:
                return
            value = (
                QFileDialog.getOpenFileName(self, "Выберите программу")[0]
                if apps
                else QFileDialog.getExistingDirectory(self, "Выберите папку")
            )
            if value:
                table.item(row, 2).setText(value)

        add.clicked.connect(add_row)
        remove.clicked.connect(
            lambda: table.removeRow(table.currentRow()) if table.currentRow() >= 0 else None
        )
        browse.clicked.connect(choose)
        for button in (add, remove, browse):
            buttons.addWidget(button)
        box.addLayout(buttons)
        return widget

    def accept(self):
        try:
            s = self.config.settings
            s.audio.device_index = self.device.currentData()
            s.audio.max_seconds = self.seconds.value()
            s.audio.silence_timeout_ms = self.silence.value()
            s.audio.silence_threshold = self.threshold.value()
            hotkey = self.hotkey.text().strip().lower()
            if not hotkey or len(hotkey) > 40:
                raise ValueError("Укажите горячую клавишу, например F9")
            s.app.hotkey = hotkey
            s.app.dry_run = self.dry.isChecked()
            s.pet.enabled = self.pet_enabled.isChecked()
            s.pet.size = self.pet_size.value()
            s.pet.always_on_top = self.pet_top.isChecked()
            s.pet.locked = self.pet_lock.isChecked()
            s.pet.dock_side = self.pet_edge.currentData()
            s.pet.dock_offset = self.pet_offset.value() / 100
            if self.reset_position.isChecked():
                s.pet.x = s.pet.y = None
                s.pet.dock_side = "top"
                s.pet.dock_offset = 0.5
                s.pet.screen_name = ""
            s.asr.model_name = self.asr_model.currentText().strip()
            if not s.asr.model_name:
                raise ValueError("Укажите имя модели распознавания")
            s.asr.allow_download = self.download.isChecked()
            s.nlu.semantic_enabled = self.semantic.isChecked()
            s.nlu.semantic_model = self.semantic_name.text().strip()
            if s.nlu.semantic_enabled and not s.nlu.semantic_model:
                raise ValueError("Укажите имя модели Ollama")
            s.nlu.neural_recovery_enabled = self.recovery.isChecked()
            self.config.settings = Settings.model_validate(s.model_dump())
            for table, apps in ((self.apps, True), (self.folders, False)):
                entries = {}
                for row in range(table.rowCount()):
                    name, aliases, path = [table.item(row, col).text().strip() for col in range(3)]
                    if not name or not aliases or not path:
                        raise ValueError("Заполните все поля приложений и папок")
                    if name in entries:
                        raise ValueError(f"Повторяющееся название: {name}")
                    alias_list = [x.strip() for x in aliases.split(",") if x.strip()]
                    if not alias_list:
                        raise ValueError("Укажите хотя бы один вариант обращения")
                    old = self.config.apps.applications.get(name) if apps else None
                    arguments = old.launch[1:] if old is not None else []
                    entries[name] = (
                        AppEntry(aliases=alias_list, launch=[path, *arguments])
                        if apps
                        else FolderEntry(aliases=alias_list, path=path)
                    )
                if apps:
                    self.config.apps.applications = entries
                else:
                    self.config.apps.folders = entries
            super().accept()
        except Exception as error:
            QMessageBox.warning(self, "Проверь настройки", str(error))
