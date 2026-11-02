"""Native readiness report with concrete fixes, backed by shared diagnostic checks."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from voice_control_pc.diagnostics import Check

LABELS = {"ok": "Готово", "info": "Информация", "warning": "Проверь", "error": "Нужно исправить"}


class ReadinessDialog(QDialog):
    def __init__(self, checks: list[Check], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Готовность Лумо")
        self.resize(720, 650)
        layout = QVBoxLayout(self)
        title = QLabel("Проверим настройку")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        count = sum(check.status in ("warning", "error") for check in checks)
        summary = QLabel(f"Требуют внимания: {count}" if count else "Проверки пройдены")
        summary.setObjectName("section")
        layout.addWidget(summary)
        note = QLabel(
            "Здесь проверяются доступность компонентов и пути. Для проверки звука запиши команду."
        )
        note.setWordWrap(True)
        note.setObjectName("subtitle")
        layout.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        cards = QVBoxLayout(content)
        cards.setContentsMargins(0, 8, 8, 8)
        order = {"error": 0, "warning": 1, "ok": 2, "info": 3}
        for check in sorted(checks, key=lambda check: order[check.status]):
            card = QFrame()
            card.setObjectName("card")
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 12, 16, 12)
            label = QLabel(f"{LABELS[check.status]} · {check.title}")
            label.setObjectName("section")
            box.addWidget(label)
            for text in (check.detail, check.hint):
                if text:
                    detail = QLabel(text)
                    detail.setTextFormat(Qt.TextFormat.PlainText)
                    detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    detail.setWordWrap(True)
                    detail.setObjectName("subtitle")
                    box.addWidget(detail)
            cards.addWidget(card)
        cards.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox()
        configure = buttons.addButton("Настроить Лумо", QDialogButtonBox.ButtonRole.AcceptRole)
        configure.setObjectName("primary")
        buttons.addButton("Закрыть", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
