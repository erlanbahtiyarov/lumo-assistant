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
