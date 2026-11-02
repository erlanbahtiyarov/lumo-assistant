"""Docking behaviour, persistence and native companion interactions."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from voice_control_pc.config import load_config_bundle, save_preferences
from voice_control_pc.models import PetSettings
from voice_control_pc.ui.pet import DesktopPet, dock_position, nearest_dock
from voice_control_pc.ui.settings import SettingsDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("side", ["top", "right", "bottom", "left"])
@pytest.mark.parametrize("offset", [0.0, 0.37, 1.0])
def test_dock_stays_inside_negative_coordinate_display(side, offset):
    area = QRect(-1920, -300, 1920, 1040)
    size = QSize(128, 110)
    point = dock_position(area, size, side, offset)
    assert area.contains(QRect(point, size))
    if side == "top":
        assert point.y() == area.top()
    elif side == "bottom":
        assert point.y() + size.height() == area.bottom() + 1
    elif side == "left":
        assert point.x() == area.left()
    else:
        assert point.x() + size.width() == area.right() + 1
    # Corner ties may select either adjoining edge; the physical position stays identical.
    recovered_side, recovered_offset = nearest_dock(area, size, point)
    assert dock_position(area, size, recovered_side, recovered_offset) == point


@pytest.mark.parametrize(
    "side,position",
    [
        ("top", QPoint(300, 3)),
        ("right", QPoint(897, 250)),
        ("bottom", QPoint(340, 697)),
        ("left", QPoint(2, 250)),
    ],
)
def test_drag_selects_the_nearest_edge(side, position):
    actual_side, offset = nearest_dock(QRect(0, 0, 1000, 800), QSize(100, 100), position)
    assert actual_side == side
    assert 0 <= offset <= 1


@pytest.fixture
def pet(app):
    widget = DesktopPet(PetSettings())
    app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def test_idle_is_only_the_framed_pet_and_stops_continuous_animation(pet):
    pet.set_state("thinking")
    assert pet.panel.isVisible()
    pet.set_state("idle")
    assert not pet.panel.isVisible()
    assert not pet.face.timer.isActive()
    assert not pet.bars.timer.isActive()
    assert pet.width() > pet.height()


@pytest.mark.parametrize("side", ["top", "right", "bottom", "left"])
def test_active_panel_opens_inside_the_screen_at_both_ends(pet, side):
    for offset in (0, 1):
        pet.settings.dock_side = side
        pet.settings.dock_offset = offset
        pet.apply_settings()
        pet.set_state("confirm")
        assert pet.panel.isVisible()
        area = pet.screen().availableGeometry()
        assert area.contains(pet.panel.geometry())
        assert area.contains(pet.geometry())
        # Confirmation is reviewed in the main application, never accepted by the pet.
        assert not pet.listen_button.isEnabled()
        assert pet.open_button.text() == "Подтвердить…"


def test_release_snaps_to_edge_and_persists_after_reload(pet, tmp_path):
    area = pet.screen().availableGeometry()
    pet.move(area.left() + 2, area.top() + 250)
    pet.drag_offset = QPoint(5, 5)
    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(5, 5),
        pet.pos() + QPoint(5, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    pet.mouseReleaseEvent(release)
    assert pet.settings.dock_side == "left"
    assert pet.x() == area.left()
    config = load_config_bundle(tmp_path)
    config.settings.pet = pet.settings
    save_preferences(config)
    restored = DesktopPet(load_config_bundle(tmp_path).settings.pet)
    try:
        assert restored.pos() == pet.pos()
        # A size change keeps the relative position along the same side.
        restored.settings.size = 200
        restored.apply_settings()
        expected = dock_position(area, restored.size(), "left", pet.settings.dock_offset)
        assert restored.pos() == expected
    finally:
        restored.close()
        restored.deleteLater()


def test_hidden_pet_does_not_leak_active_popup(pet):
    pet.set_state("listening")
    assert pet.panel.isVisible()
    pet.settings.enabled = False
    pet.apply_settings()
    assert not pet.isVisible()
    assert not pet.panel.isVisible()
    assert not pet.face.timer.isActive()
    assert not pet.bars.timer.isActive()


def test_pet_buttons_request_actions_and_confirmation_opens_review(pet):
    requests = []
    pet.listen_requested.connect(lambda: requests.append("listen"))
    pet.open_requested.connect(lambda: requests.append("open"))
    pet.set_state("listening")
    QTest.mouseClick(pet.listen_button, Qt.MouseButton.LeftButton)
    pet.set_state("confirm")
    QTest.mouseClick(pet.open_button, Qt.MouseButton.LeftButton)
    assert requests == ["listen", "open"]


def test_settings_save_dock_side_and_offset(app, tmp_path):
    dialog = SettingsDialog(load_config_bundle(tmp_path), [])
    dialog.pet_edge.setCurrentIndex(dialog.pet_edge.findData("bottom"))
    dialog.pet_offset.setValue(73)
    dialog.accept()
    assert dialog.config.settings.pet.dock_side == "bottom"
    assert dialog.config.settings.pet.dock_offset == 0.73
    dialog.deleteLater()


def test_removed_monitor_falls_back_inside_primary_screen(pet):
    pet.settings.screen_name = "disconnected-monitor"
    pet.settings.dock_side = "right"
    pet.settings.dock_offset = 0.83
    pet.apply_settings()
    screen = QApplication.primaryScreen()
    assert pet.settings.screen_name == screen.name()
    assert screen.availableGeometry().contains(pet.geometry())


def test_locked_pet_cannot_be_dragged(pet):
    pet.settings.locked = True
    previous = pet.pos()
    QTest.mousePress(pet, Qt.MouseButton.LeftButton)
    assert pet.drag_offset is None
    QTest.mouseRelease(pet, Qt.MouseButton.LeftButton)
    assert pet.pos() == previous
