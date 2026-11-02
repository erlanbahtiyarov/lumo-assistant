import json
from unittest.mock import Mock

import pytest

from voice_control_pc.config import load_config_bundle
from voice_control_pc.semantic import interpret_local


def answer(monkeypatch, payload):
    response = Mock()
    response.read.return_value = json.dumps({"message": {"content": json.dumps(payload)}}).encode()
    response.__enter__ = lambda self: self
    response.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = response
    monkeypatch.setattr("voice_control_pc.semantic.build_opener", lambda *args: opener)
    return opener


def test_local_model_can_only_suggest_an_allowlisted_object(tmp_path, monkeypatch):
    opener = answer(monkeypatch, {"intent": "open_app", "target": "блокнот"})
    match = interpret_local("мне нужен текстовый редактор", load_config_bundle(tmp_path))
    assert match.action == "open_app"
    assert match.slots == {"app_name": "блокнот"}
    assert match.dangerous  # every suggestion requires confirmation
    request = opener.open.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:11434/api/chat"


@pytest.mark.parametrize(
    "payload",
    [
        {"intent": "run_shell", "target": ""},
        {"intent": "open_app", "target": "malware.exe"},
        {"intent": "open_folder", "target": "блокнот"},
        {"intent": "shutdown_pc", "target": "блокнот"},
        {"intent": "unknown", "target": ""},
    ],
)
def test_invalid_or_uncertain_suggestions_are_rejected(tmp_path, monkeypatch, payload):
    answer(monkeypatch, payload)
    assert interpret_local("пожалуйста помоги", load_config_bundle(tmp_path)).intent is None


def test_model_cannot_turn_switching_windows_into_closing_them(tmp_path, monkeypatch):
    answer(monkeypatch, {"intent": "close_window", "target": ""})
    match = interpret_local("переключись на следующее окно", load_config_bundle(tmp_path))
    assert match.intent is None


def test_destructive_suggestion_with_explicit_action_still_needs_confirmation(
    tmp_path, monkeypatch
):
    answer(monkeypatch, {"intent": "shutdown_pc", "target": ""})
    match = interpret_local("пожалуйста выключи компьютер", load_config_bundle(tmp_path))
    assert match.intent == "shutdown_pc"
    assert match.dangerous
