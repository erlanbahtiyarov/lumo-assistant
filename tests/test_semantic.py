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
    opener = answer(monkeypatch, {"intent": "open_app", "target": "блокнот", "confidence": 0.9})
    match = interpret_local("мне нужен текстовый редактор", load_config_bundle(tmp_path))
    assert match.action == "open_app"
    assert match.slots == {"app_name": "блокнот"}
    assert match.dangerous  # every suggestion requires confirmation
    request = opener.open.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:11434/api/chat"


@pytest.mark.parametrize(
    "payload",
    [
        {"intent": "run_shell", "target": "", "confidence": 1.0},
        {"intent": "open_app", "target": "malware.exe", "confidence": 1.0},
        {"intent": "open_folder", "target": "блокнот", "confidence": 1.0},
        {"intent": "shutdown_pc", "target": "блокнот", "confidence": 1.0},
        {"intent": "open_app", "target": "блокнот", "confidence": 0.4},
    ],
)
def test_invalid_or_uncertain_suggestions_are_rejected(tmp_path, monkeypatch, payload):
    answer(monkeypatch, payload)
    assert interpret_local("пожалуйста помоги", load_config_bundle(tmp_path)).intent is None
