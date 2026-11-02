from pathlib import Path
from unittest.mock import Mock

import pytest

from voice_control_pc.config import load_config_bundle, resolved_asr_settings, save_preferences
from voice_control_pc.history import HistoryStore
from voice_control_pc.models import CommandResult
from voice_control_pc.service import VoiceControlService


@pytest.fixture
def service(tmp_path):
    return VoiceControlService(load_config_bundle(tmp_path), dry_run=True)


def token(service, text="выключи компьютер"):
    _, result = service.process_text_command(text)
    assert result.status == "confirmation_required"
    return result.artifacts["confirmation_token"]


def test_confirmation_is_single_use_and_bound_to_action(service):
    first = token(service)
    assert service.confirm_command(first).status == "dry_run"
    assert service.confirm_command(first).status == "confirmation_invalid"
    first = token(service)
    second = token(service, "перезагрузи компьютер")
    assert first != second
    assert service.confirm_command(second).action == "restart_pc"


def test_new_or_cancelled_command_revokes_confirmation(service):
    first = token(service)
    service.process_text_command("открой браузер")
    assert service.confirm_command(first).status == "confirmation_invalid"
    second = token(service)
    service.cancel_pending()
    assert service.confirm_command(second).status == "confirmation_invalid"


def test_expired_confirmation_does_not_execute(service, monkeypatch):
    monkeypatch.setattr("voice_control_pc.service.time.monotonic", lambda: 100)
    pending = token(service)
    service.executor.execute = Mock()
    monkeypatch.setattr("voice_control_pc.service.time.monotonic", lambda: 1000)
    assert service.confirm_command(pending).status == "confirmation_expired"
    service.executor.execute.assert_not_called()


def test_confirmation_cannot_be_pre_authorized_or_change_mode(service):
    _, result = service.process_text_command("выключи компьютер", confirmed=True)
    assert result.status == "confirmation_required"
    service.executor.dry_run = False
    assert (
        service.confirm_command(result.artifacts["confirmation_token"]).status
        == "confirmation_invalid"
    )


def test_dangerous_actions_cannot_be_enabled_by_removing_config_flag(service):
    service.config.settings.execution.require_confirmation_for.clear()
    assert token(service)


def test_user_preferences_survive_reload_and_keep_packaged_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMO_HOME", str(tmp_path))
    config = load_config_bundle()
    assert config.project_root == tmp_path
    config.settings.pet.x, config.settings.pet.y = 42, 180
    config.settings.audio.max_seconds = 6
    config.apps.applications["браузер"].launch = ["my-browser.exe"]
    config.apps.applications["браузер"].auto_detect = False
    save_preferences(config)
    restored = load_config_bundle()
    assert restored.settings.pet.x == 42
    assert restored.settings.pet.y == 180
    assert restored.settings.audio.max_seconds == 6
    assert restored.apps.applications["браузер"].launch == ["my-browser.exe"]
    assert restored.commands.intents
    assert resolved_asr_settings(restored).model_path == str(tmp_path / "models")


def test_history_is_bounded_and_does_not_store_tokens(tmp_path):
    store = HistoryStore(tmp_path / "history.jsonl", limit=2)
    result = CommandResult(
        success=False,
        status="confirmation_required",
        message="Подтвердить",
        artifacts={"confirmation_token": "secret"},
    )
    for text in ("one", "two", "three"):
        store.append(text, result)
    assert [row["text"] for row in store.read()] == ["two", "three"]
    assert "secret" not in store.path.read_text()
    store.clear()
    assert store.read() == []


def test_executor_errors_are_results(service, monkeypatch):
    service.executor.dry_run = False
    monkeypatch.setattr("voice_control_pc.executor.sys.platform", "win32")
    monkeypatch.setattr(
        "voice_control_pc.executor.subprocess.Popen",
        Mock(side_effect=FileNotFoundError("not found")),
    )
    _, result = service.process_text_command("открой браузер")
    assert result.status == "execution_error"
    assert not result.success


def test_dry_run_does_not_create_screenshot_directories(service):
    _, result = service.process_text_command("сделай скриншот")
    assert result.status == "dry_run"
    assert not (service.config.project_root / "artifacts").exists()


def test_model_suggestion_requires_validation_and_confirmation(service, monkeypatch):
    from voice_control_pc.models import IntentMatch

    service.config.settings.nlu.semantic_enabled = True
    suggestion = IntentMatch(
        text="хочу браузер",
        normalized_text="хочу браузер",
        intent="open_app",
        action="open_app",
        confidence=0.9,
        dangerous=True,
        slots={"app_name": "браузер"},
    )
    monkeypatch.setattr(
        "voice_control_pc.semantic.interpret_local", lambda text, config: suggestion
    )
    _, result = service.process_text_command("хочу браузер")
    assert result.status == "confirmation_required"


def test_source_and_packaged_configs_agree():
    root = Path(__file__).resolve().parents[1]
    for path in (root / "configs").glob("*.yaml"):
        assert (
            path.read_bytes() == (root / "src/voice_control_pc/resources" / path.name).read_bytes()
        )


def test_close_window_refuses_to_close_lumo_itself(service, monkeypatch):
    import ctypes
    import os
    from types import SimpleNamespace

    def process_id(hwnd, target):
        target._obj.value = os.getpid()

    user32 = SimpleNamespace(
        GetForegroundWindow=Mock(return_value=123),
        GetWindowThreadProcessId=Mock(side_effect=process_id),
    )
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=user32), raising=False)
    monkeypatch.setattr("voice_control_pc.executor.sys.platform", "win32")
    service.executor.dry_run = False
    _, result = service.process_text_command("закрой окно")
    assert result.status == "execution_error"
    assert "Переключись" in result.message
