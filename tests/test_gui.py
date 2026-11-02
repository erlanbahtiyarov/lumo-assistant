import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from voice_control_pc.config import load_config_bundle
from voice_control_pc.gui import LumoWindow
from voice_control_pc.ui.settings import SettingsDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    config = load_config_bundle(tmp_path)
    config.settings.pet.enabled = False
    widget = LumoWindow(config)
    widget.show()
    app.processEvents()
    yield widget
    wait_finished(widget)
    widget.close()
    app.processEvents()


def wait_finished(window):
    deadline = time.monotonic() + 5
    while window.job is not None and time.monotonic() < deadline:
        QTest.qWait(10)
    assert window.job is None
    # Showing the confirmation schedules a layout pass after the worker's signals.
    QApplication.processEvents()


def test_text_command_updates_native_ui_and_history(window):
    window.input.setText("запусти блокнот")
    QTest.mouseClick(window.run_button, Qt.MouseButton.LeftButton)
    wait_finished(window)
    assert "блокнот" in window.interpretation.text()
    assert window.last_result.status == "dry_run"
    assert "не выполнялось" in window.feedback.text()
    assert window.history.count() == 1
    assert window.pet.state == "success"
    assert window.input.isEnabled()


def test_dangerous_command_needs_explicit_ui_confirmation(window):
    window.input.setText("выключи компьютер")
    window.start_text()
    wait_finished(window)
    assert window.confirm_box.isVisible()
    assert window.pending_token
    QTest.mouseClick(window.yes_button, Qt.MouseButton.LeftButton)
    wait_finished(window)
    assert not window.confirm_box.isVisible()
    assert window.last_result.status == "dry_run"
    assert window.history.count() == 2


def test_confirmation_can_be_cancelled(window):
    window.input.setText("перезагрузи компьютер")
    window.start_text()
    wait_finished(window)
    token = window.pending_token
    window.cancel_confirmation()
    assert window.service.confirm_command(token).status == "confirmation_invalid"
    assert not window.confirm_box.isVisible()


def test_recording_pipeline_deletes_temp_audio(window, monkeypatch):
    recorded_paths = []

    class FakeTranscriber:
        def load(self):
            pass

        def transcribe_file(self, path):
            assert path.is_file()
            return "открой браузер"

    window.transcriber = FakeTranscriber()

    def record(path, settings, stop_event):
        recorded_paths.append(path)
        path.write_bytes(b"audio")

    monkeypatch.setattr("voice_control_pc.gui.record_microphone_to_wav", record)
    window.start_voice()
    wait_finished(window)
    assert "браузер" in window.interpretation.text()
    assert recorded_paths and not recorded_paths[0].exists()


def test_settings_roundtrip_and_pet_controls(window):
    dialog = SettingsDialog(window.config, [], window)
    dialog.pet_size.setValue(200)
    dialog.pet_enabled.setChecked(True)
    dialog.accept()
    assert dialog.result() == SettingsDialog.DialogCode.Accepted
    assert dialog.config.settings.pet.size == 200
    assert dialog.config.settings.pet.enabled
    assert not window.config.settings.pet.enabled
    window.toggle_pet()
    assert window.pet.isVisible()
    window.toggle_pet()
    assert not window.pet.isVisible()


def test_worker_error_keeps_window_usable(window):
    def fail(progress, stop):
        raise RuntimeError("нет микрофона")

    window._start("voice", fail)
    wait_finished(window)
    assert "нет микрофона" in window.feedback.text()
    assert window.record.isEnabled()
    assert window.run_button.isEnabled()


def test_closing_during_recording_cancels_interpretation(window, monkeypatch):
    class FakeTranscriber:
        def load(self):
            pass

        def transcribe_file(self, path):
            raise AssertionError("Cancelled audio must not be transcribed")

    window.transcriber = FakeTranscriber()

    def record(path, settings, stop_event):
        stop_event.wait(2)
        path.write_bytes(b"audio")

    monkeypatch.setattr("voice_control_pc.gui.record_microphone_to_wav", record)
    window.start_voice()
    QTest.qWait(30)
    window.close()
    wait_finished(window)
    assert window.history.count() == 0
    assert "отменен" in window.feedback.text() or "отменена" in window.feedback.text()


def test_pet_only_mode_can_restore_the_main_window(window):
    window.minimize_to_pet()
    assert not window.isVisible()
    assert window.pet.isVisible()
    window.reveal()
    assert window.isVisible()


def test_readiness_runs_in_background_without_executing_commands(window, monkeypatch):
    from unittest.mock import Mock

    from voice_control_pc.diagnostics import Check

    checks = [Check("voice", "Голос", "warning", "Не установлен")]
    collector = Mock(return_value=checks)
    show = Mock()
    monkeypatch.setattr("voice_control_pc.gui.check_readiness", collector)
    monkeypatch.setattr(window, "_show_readiness", show)
    QTest.mouseClick(window.check_button, Qt.MouseButton.LeftButton)
    wait_finished(window)
    assert window.readiness_checks == checks
    assert window.service is None
    assert window.check_button.isEnabled()
    assert window.history.count() == 0
    assert collector.call_args.kwargs == {"microphone": True, "ollama": True}


def test_browser_manual_choice_and_return_to_windows_default(window, monkeypatch):
    dialog = SettingsDialog(window.config, [], window)
    row = next(
        i for i in range(dialog.apps.rowCount()) if dialog.apps.item(i, 0).text() == "браузер"
    )
    dialog.default_browser.setChecked(False)
    dialog.apps.item(row, 2).setText("D:/My Browser/browser.exe")
    dialog.accept()
    browser = dialog.config.apps.applications["браузер"]
    assert browser.launch == ["D:/My Browser/browser.exe"]
    assert not browser.auto_detect
    again = SettingsDialog(dialog.config, [], window)
    monkeypatch.setattr(
        "voice_control_pc.ui.settings.find_application", lambda name: "C:/Default/browser.exe"
    )
    again.default_browser.setChecked(True)
    again.accept()
    restored = again.config.apps.applications["браузер"]
    assert restored.auto_detect
    assert restored.launch == ["C:/Default/browser.exe"]


def test_discovery_updates_only_selected_settings_row_and_can_be_cancelled(window, monkeypatch):
    from PySide6.QtWidgets import QPushButton

    dialog = SettingsDialog(window.config, [], window)
    original = window.config.apps.model_copy(deep=True)
    row = next(
        i for i in range(dialog.apps.rowCount()) if dialog.apps.item(i, 0).text() == "telegram"
    )
    dialog.apps.setCurrentCell(row, 2)
    monkeypatch.setattr(
        "voice_control_pc.ui.settings.find_application", lambda *args: "D:/Telegram/Telegram.exe"
    )
    button = next(
        b
        for b in dialog.apps.parentWidget().findChildren(QPushButton)
        if b.text() == "Найти в Windows"
    )
    button.setEnabled(True)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert dialog.apps.item(row, 2).text() == "D:/Telegram/Telegram.exe"
    for i in range(dialog.apps.rowCount()):
        if i != row:
            name = dialog.apps.item(i, 0).text()
            launch = original.applications[name].launch
            assert dialog.apps.item(i, 2).text() == (launch[0] if launch else "")
    dialog.reject()
    assert window.config.apps == original
