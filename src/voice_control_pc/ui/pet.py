"""Native, edge-docked companion. The resting widget contains no text or controls."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from voice_control_pc.models import PetSettings
from voice_control_pc.ui.theme import STYLE

LABELS = {
    "idle": "",
    "listening": "Слушаю…",
    "thinking": "Думаю…",
    "success": "Готово",
    "error": "Нужно внимание",
    "confirm": "Жду подтверждения",
}
SIDES = {
    "top": "Верхний край",
    "right": "Правый край",
    "bottom": "Нижний край",
    "left": "Левый край",
}


def dock_position(area: QRect, size: QSize, side: str, offset: float) -> QPoint:
    """Place a widget inside a work area, including displays with negative coordinates."""
    dx, dy = max(0, area.width() - size.width()), max(0, area.height() - size.height())
    offset = max(0.0, min(1.0, offset))
    if side in ("top", "bottom"):
        return QPoint(area.x() + round(dx * offset), area.y() + (dy if side == "bottom" else 0))
    return QPoint(area.x() + (dx if side == "right" else 0), area.y() + round(dy * offset))


def nearest_dock(area: QRect, size: QSize, position: QPoint) -> tuple[str, float]:
    dx, dy = max(0, area.width() - size.width()), max(0, area.height() - size.height())
    x = max(0, min(dx, position.x() - area.x()))
    y = max(0, min(dy, position.y() - area.y()))
    side = min(
        ("top", "right", "bottom", "left"),
        key=lambda s: {
            "top": y,
            "right": dx - x,
            "bottom": dy - y,
            "left": x,
        }[s],
    )
    return side, (x / dx if dx else 0.0) if side in ("top", "bottom") else (y / dy if dy else 0.0)


class LumoFace(QWidget):
    """A soft black orb with a resting base and two forward-facing ivory eye rings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "idle"
        self.started = time.monotonic()
        self.blinking = False
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.update)
        self.blink_timer = QTimer(self)
        self.blink_timer.setSingleShot(True)
        self.blink_timer.timeout.connect(self._blink)
        self.setMinimumSize(48, 48)
        self.setAccessibleName("Лумо — круглый чёрный питомец")

    def _blink(self):
        self.blinking = not self.blinking
        self.update()
        self.blink_timer.start(140 if self.blinking else 4700)

    def showEvent(self, event):
        super().showEvent(event)
        self.blinking = False
        self.blink_timer.start(4700)
        self._animate()

    def hideEvent(self, event):
        self.timer.stop()
        self.blink_timer.stop()
        super().hideEvent(event)

    def _animate(self):
        if self.isVisible() and self.state in ("listening", "thinking"):
            self.timer.start()
        else:
            self.timer.stop()

    def set_state(self, state: str):
        self.state = state if state in LABELS else "idle"
        self._animate()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height() / 0.84)
        p.translate((self.width() - side) / 2, (self.height() - side * 0.84) / 2)
        p.scale(side / 200, side / 200)
        body = QPainterPath()
        body.moveTo(100, 9)
        body.cubicTo(47, 9, 10, 55, 10, 104)
        body.cubicTo(10, 146, 28, 160, 59, 160)
        body.lineTo(141, 160)
        body.cubicTo(172, 160, 190, 146, 190, 104)
        body.cubicTo(190, 55, 153, 9, 100, 9)
        body.closeSubpath()
        gradient = QRadialGradient(88, 15, 163)
        gradient.setColorAt(0, QColor("#343436"))
        gradient.setColorAt(0.5, QColor("#151516"))
        gradient.setColorAt(1, QColor("#070708"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gradient)
        p.drawPath(body)
        # The base remains still. Only the eyelids change; the gaze stays on the viewer.
        t = time.monotonic() - self.started
        eye_h = 75 + (math.sin(t * 3) * 2 if self.state == "listening" else 0)
        for cx in (60, 140):
            p.setBrush(QColor("#f4eed3"))
            if self.blinking:
                p.setPen(QPen(QColor("#f4eed3"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPoint(cx - 23, 96), QPoint(cx + 23, 96))
                p.setPen(Qt.PenStyle.NoPen)
            else:
                p.drawEllipse(QRectF(cx - 31, 94 - eye_h / 2, 62, eye_h))
                p.setBrush(QColor("#0c0c0d"))
                p.drawEllipse(QRectF(cx - 21, 94 - (eye_h - 22) / 2, 42, eye_h - 22))
        p.end()


class ActivityBars(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "idle"
        self.setFixedHeight(18)
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.update)

    def set_state(self, state):
        self.state = state
        if self.isVisible() and state in ("listening", "thinking"):
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.set_state(self.state)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#e9e3d3"))
        for i in range(22):
            moving = self.state in ("listening", "thinking")
            h = 4 + 12 * abs(math.sin(time.monotonic() * 3 + i * 0.8)) if moving else 3
            p.drawRoundedRect(QRectF(i * 7, (18 - h) / 2, 3, h), 1.5, 1.5)
        p.end()


class DesktopPet(QWidget):
    moved = Signal(int, int)
    open_requested = Signal()
    listen_requested = Signal()
    preferences_changed = Signal()
    quit_requested = Signal()

    def __init__(self, settings: PetSettings):
        super().__init__()
        self.settings = settings
        self.state = "idle"
        self.drag_offset = None
        self._initialized = False
        self._screens = set()
        self.setWindowTitle("Лумо · питомец")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAccessibleName(
            "Питомец Лумо. Перетащи к краю экрана. Двойной щелчок открывает приложение."
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        self.face = LumoFace(self)
        self.face.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.face)
        self.panel = QFrame(
            self,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.panel.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.panel.setObjectName("card")
        self.panel.setStyleSheet(STYLE)
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(10)
        self.status = QLabel()
        self.status.setObjectName("section")
        self.status.setWordWrap(True)
        panel_layout.addWidget(self.status)
        self.bars = ActivityBars()
        panel_layout.addWidget(self.bars)
        buttons = QHBoxLayout()
        self.listen_button = QPushButton("Слушать")
        self.listen_button.setObjectName("primary")
        self.listen_button.clicked.connect(self.listen_requested.emit)
        buttons.addWidget(self.listen_button)
        self.open_button = QPushButton("Открыть")
        self.open_button.clicked.connect(self.open_requested.emit)
        buttons.addWidget(self.open_button)
        panel_layout.addLayout(buttons)
        self.panel.installEventFilter(self)
        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self._show_panel)
        self.leave_timer = QTimer(self)
        self.leave_timer.setSingleShot(True)
        self.leave_timer.timeout.connect(self._hide_panel)
        app = QApplication.instance()
        app.screenAdded.connect(self._screens_changed)
        app.screenRemoved.connect(self._screens_changed)
        self._watch_screens()
        self.set_state("idle")
        self.apply_settings()

    def _watch_screens(self):
        for screen in QApplication.screens():
            if screen not in self._screens:
                screen.availableGeometryChanged.connect(self._screens_changed)
                self._screens.add(screen)

    def _screens_changed(self, *args):
        self._watch_screens()
        QTimer.singleShot(0, self.apply_settings)

    def _screen(self):
        screens = QApplication.screens()
        return next(
            (s for s in screens if s.name() == self.settings.screen_name),
            QApplication.primaryScreen(),
        )

    def apply_settings(self):
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        if self.settings.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if self.windowFlags() != flags:
            self.setWindowFlags(flags)
        self.panel.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.settings.always_on_top)
        screen = self._screen()
        area = screen.availableGeometry()
        self.setFixedSize(
            min(self.settings.size, area.width()),
            min(round(self.settings.size * 0.86), area.height()),
        )
        # Migrate an older free-floating location once, then retain side + relative offset.
        if (
            not self._initialized
            and not self.settings.screen_name
            and self.settings.x is not None
            and self.settings.y is not None
        ):
            point = QPoint(self.settings.x, self.settings.y)
            screen = (
                QApplication.screenAt(point + QPoint(self.width() // 2, self.height() // 2))
                or screen
            )
            area = screen.availableGeometry()
            self.settings.dock_side, self.settings.dock_offset = nearest_dock(
                area, self.size(), point
            )
        self._initialized = True
        self.settings.screen_name = screen.name()
        self.move(
            dock_position(area, self.size(), self.settings.dock_side, self.settings.dock_offset)
        )
        self.settings.x, self.settings.y = self.x(), self.y()
        self.setVisible(self.settings.enabled)
        if self.settings.enabled and self.state != "idle":
            self._show_panel()
        else:
            self.panel.hide()
        self.update()

    def set_state(self, state):
        self.state = state if state in LABELS else "idle"
        self.face.set_state(self.state)
        self.status.setText(LABELS[self.state] or "Чем помочь?")
        self.bars.set_state(self.state)
        self.bars.setVisible(self.state in ("listening", "thinking"))
        self.listen_button.setText("Остановить" if self.state == "listening" else "Слушать")
        self.listen_button.setEnabled(self.state not in ("thinking", "confirm"))
        self.open_button.setText("Подтвердить…" if self.state == "confirm" else "Открыть")
        if self.state != "idle":
            self._show_panel()
        else:
            self._hide_panel()

    def _show_panel(self):
        if not self.isVisible() or self.drag_offset is not None:
            return
        self.status.setText(LABELS[self.state] or "Чем помочь?")
        area = self._screen().availableGeometry()
        self.panel.setFixedWidth(min(280, area.width()))
        self.panel.adjustSize()
        side = self.settings.dock_side
        if side in ("top", "bottom"):
            x = self.x() + (self.width() - self.panel.width()) // 2
            y = (
                self.y() + self.height() + 6
                if side == "top"
                else self.y() - self.panel.height() - 6
            )
        else:
            x = self.x() + self.width() + 6 if side == "left" else self.x() - self.panel.width() - 6
            y = self.y() + (self.height() - self.panel.height()) // 2
        self.panel.move(
            max(area.x(), min(x, area.right() + 1 - self.panel.width())),
            max(area.y(), min(y, area.bottom() + 1 - self.panel.height())),
        )
        self.panel.show()

    def _hide_panel(self):
        if self.state == "idle" and not self.underMouse() and not self.panel.underMouse():
            self.panel.hide()

    def enterEvent(self, event):
        self.leave_timer.stop()
        self.hover_timer.start(250)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_timer.stop()
        self.leave_timer.start(350)
        super().leaveEvent(event)

    def eventFilter(self, watched, event):
        if watched == self.panel:
            if event.type() == event.Type.Enter:
                self.leave_timer.stop()
            elif event.type() == event.Type.Leave:
                self.leave_timer.start(350)
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#17181b"))
        p.setPen(QPen(QColor("#414248"), 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.settings.locked:
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            self.panel.hide()
            self.hover_timer.stop()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag_offset is not None:
            self.drag_offset = None
            screen = QApplication.screenAt(event.globalPosition().toPoint()) or self._screen()
            self.settings.screen_name = screen.name()
            self.settings.dock_side, self.settings.dock_offset = nearest_dock(
                screen.availableGeometry(), self.size(), self.pos()
            )
            self.apply_settings()
            self.moved.emit(self.x(), self.y())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = None
            self.apply_settings()
            self.open_requested.emit()

    def contextMenuEvent(self, event):
        self.hover_timer.stop()
        menu = QMenu(self)
        menu.setStyleSheet(STYLE)
        menu.addAction("Открыть Лумо", self.open_requested.emit)
        menu.addAction("Слушать команду", self.listen_requested.emit)
        docking = menu.addMenu("Прикрепить к краю")
        actions = {}
        for side, label in SIDES.items():
            action = docking.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.settings.dock_side == side)
            actions[action] = side
        menu.addSeparator()
        lock = menu.addAction("Закрепить положение")
        lock.setCheckable(True)
        lock.setChecked(self.settings.locked)
        top = menu.addAction("Поверх окон")
        top.setCheckable(True)
        top.setChecked(self.settings.always_on_top)
        hide = menu.addAction("Скрыть питомца")
        menu.addSeparator()
        menu.addAction("Закрыть Лумо", self.quit_requested.emit)
        selected = menu.exec(event.globalPos())
        if selected in actions:
            self.settings.dock_side = actions[selected]
        elif selected == lock:
            self.settings.locked = lock.isChecked()
        elif selected == top:
            self.settings.always_on_top = top.isChecked()
        elif selected == hide:
            self.open_requested.emit()
            self.settings.enabled = False
        else:
            return
        self.apply_settings()
        self.preferences_changed.emit()

    def hideEvent(self, event):
        self.panel.hide()
        self.hover_timer.stop()
        self.leave_timer.stop()
        super().hideEvent(event)
