"""Lumo's original vector-drawn companion, animated by the native Qt paint engine."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from voice_control_pc.models import PetSettings

LABELS = {
    "idle": "Лумо рядом",
    "listening": "Слушаю…",
    "thinking": "Думаю…",
    "success": "Готово!",
    "error": "Давай ещё раз",
    "confirm": "Подтвердить?",
}
COLORS = {
    "idle": "#91aa8a",
    "listening": "#80bfa0",
    "thinking": "#d7b56b",
    "success": "#71b493",
    "error": "#d68a7a",
    "confirm": "#d7b56b",
}


class LumoFace(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "idle"
        self.started = time.monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(40)
        self.setMinimumSize(96, 96)

    def set_state(self, state: str):
        self.state = state if state in LABELS else "idle"
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        p.translate((self.width() - side) / 2, (self.height() - side) / 2)
        p.scale(side / 200, side / 200)
        t = time.monotonic() - self.started
        bob = math.sin(t * (4 if self.state == "listening" else 1.8)) * 2.5
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 24))
        p.drawEllipse(QRectF(43, 171, 117, 10))
        p.translate(0, bob)
        # Ears, curled tail, and soft body are drawn directly, with no web view or raster dependency.
        p.setPen(QPen(QColor("#111d18"), 16, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        tail = QPainterPath(QPoint(144, 145))
        tail.cubicTo(188, 170, 190, 111, 168, 123)
        p.drawPath(tail)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#14231c"))
        for points in (((46, 67), (41, 24), (83, 49)), ((122, 46), (161, 24), (157, 77))):
            ear = QPainterPath()
            ear.moveTo(*points[0])
            ear.lineTo(*points[1])
            ear.lineTo(*points[2])
            ear.closeSubpath()
            p.drawPath(ear)
        glow = QRadialGradient(76, 62, 115)
        glow.setColorAt(0, QColor("#253c2c"))
        glow.setColorAt(1, QColor("#0b100e"))
        p.setBrush(glow)
        p.drawEllipse(QRectF(27, 40, 145, 135))
        p.setPen(QPen(QColor("#344632"), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(34, 45, 131, 121), 25 * 16, 130 * 16)
        blink = t % 5.7 < 0.13 and self.state != "listening"
        eye_h = 5 if blink else (67 if self.state == "listening" else 60)
        for x in (49, 108):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#e6ebc7"))
            p.drawEllipse(QRectF(x, 100 - eye_h / 2, 43, eye_h))
            if not blink:
                cursor = self.mapFromGlobal(QCursor.pos())
                dx = max(-4, min(4, (cursor.x() - self.width() / 2) / 60))
                dy = max(-3, min(3, (cursor.y() - self.height() / 2) / 60))
                p.setBrush(QColor("#0a110d"))
                p.drawEllipse(QRectF(x + 12 + dx, 78 + dy, 25, 43))
                p.setBrush(QColor("#ffffff"))
                p.drawEllipse(QRectF(x + 16 + dx, 82 + dy, 7, 10))
        p.setPen(QPen(QColor("#a8b397"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(92, 127, 16, 12), 190 * 16, 160 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(COLORS[self.state]))
        p.drawEllipse(QRectF(144, 146, 11, 11))
        p.end()


class DesktopPet(LumoFace):
    moved = Signal(int, int)
    open_requested = Signal()
    listen_requested = Signal()
    preferences_changed = Signal()

    def __init__(self, settings: PetSettings):
        super().__init__()
        self.settings = settings
        self.drag_offset = None
        self.setWindowTitle("Лумо · питомец")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setToolTip("Двойной щелчок — открыть Лумо. Правая кнопка — меню.")
        self.apply_settings()

    def apply_settings(self):
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if self.settings.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setFixedSize(self.settings.size, self.settings.size)
        screens = QApplication.screens()
        rect = QApplication.primaryScreen().availableGeometry()
        x = self.settings.x if self.settings.x is not None else rect.right() - self.width() - 28
        y = self.settings.y if self.settings.y is not None else rect.bottom() - self.height() - 20
        saved = QRectF(x, y, self.width(), self.height())
        if not any(QRectF(screen.availableGeometry()).intersects(saved) for screen in screens):
            x, y = rect.right() - self.width() - 28, rect.bottom() - self.height() - 20
        self.move(x, y)
        self.setVisible(self.settings.enabled)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.settings.locked:
            self.drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event):
        if self.drag_offset is not None:
            self.drag_offset = None
            self.settings.x, self.settings.y = self.x(), self.y()
            self.moved.emit(self.x(), self.y())

    def mouseDoubleClickEvent(self, event):
        self.open_requested.emit()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("Открыть Лумо", self.open_requested.emit)
        menu.addAction("Слушать команду", self.listen_requested.emit)
        menu.addSeparator()
        lock = menu.addAction("Закрепить положение")
        lock.setCheckable(True)
        lock.setChecked(self.settings.locked)
        top = menu.addAction("Поверх окон")
        top.setCheckable(True)
        top.setChecked(self.settings.always_on_top)
        hide = menu.addAction("Скрыть питомца")
        selected = menu.exec(event.globalPos())
        if selected == lock:
            self.settings.locked = lock.isChecked()
        elif selected == top:
            self.settings.always_on_top = top.isChecked()
        elif selected == hide:
            self.settings.enabled = False
        else:
            return
        self.apply_settings()
        self.preferences_changed.emit()
