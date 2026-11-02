from unittest.mock import Mock

import pytest

from voice_control_pc import diagnostics
from voice_control_pc.config import load_config_bundle


@pytest.fixture
def config(tmp_path, monkeypatch):
    config = load_config_bundle(tmp_path)
    monkeypatch.setattr(diagnostics, "component_available", lambda name: False)
    return config


def checks_by_key(config, **kwargs):
    return {check.key: check for check in diagnostics.check_readiness(config, **kwargs)}


def test_basic_check_never_probes_microphone_or_ollama_or_creates_profile(config, monkeypatch):
    config.settings.nlu.semantic_enabled = True
    mic = Mock(side_effect=AssertionError("recording or microphone probe not requested"))
    llm = Mock(side_effect=AssertionError("network probe not requested"))
    monkeypatch.setattr(diagnostics, "list_input_devices", mic)
    monkeypatch.setattr(diagnostics, "ollama_models", llm)
    before = list(config.project_root.iterdir())
    checks = checks_by_key(config)
    assert checks["voice"].status == "warning"
    assert checks["ollama"].status == "info"
    assert list(config.project_root.iterdir()) == before
    mic.assert_not_called()
    llm.assert_not_called()


def test_moved_folder_and_missing_application_are_reported(config, monkeypatch, tmp_path):
    folder = tmp_path / "Перенесённые документы"
    folder.mkdir()
    config.apps.folders["документы"].path = str(folder)
    config.apps.applications["браузер"].launch = []
    monkeypatch.setattr(diagnostics.sys, "platform", "win32")
    monkeypatch.setattr(diagnostics.shutil, "which", lambda executable: None)
    checks = checks_by_key(config)
    assert checks["folder:документы"].status == "ok"
    assert checks["app:браузер"].status == "warning"
    assert "Настройки" in checks["app:браузер"].hint


def test_missing_and_incomplete_asr_do_not_download(config, monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostics, "component_available", lambda name: True)
    monkeypatch.setattr(diagnostics, "local_asr_directory", lambda config: tmp_path)
    checks = checks_by_key(config)
    assert checks["asr"].status == "warning"
    assert "model.bin" in checks["asr"].detail
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (tmp_path / name).write_bytes(b"present")
    assert checks_by_key(config)["asr"].status == "ok"


def test_offline_model_lookup_forces_local_files_only(config, monkeypatch):
    import sys
    from types import ModuleType

    fake = ModuleType("faster_whisper.utils")
    fake.download_model = Mock(return_value=str(config.project_root))
    monkeypatch.setitem(sys.modules, "faster_whisper.utils", fake)
    diagnostics.local_asr_directory(config)
    fake.download_model.assert_called_once_with(
        "small", cache_dir=str(config.project_root / "models"), local_files_only=True
    )


def test_removed_selected_microphone_has_actionable_warning(config, monkeypatch):
    config.settings.audio.device_index = 4
    monkeypatch.setattr(diagnostics, "component_available", lambda name: name == "pyaudio")
    monkeypatch.setattr(
        diagnostics, "list_input_devices", lambda: [{"index": 2, "name": "Другой", "channels": 1}]
    )
    checks = checks_by_key(config, microphone=True)
    assert checks["microphone"].status == "warning"
    assert "4" in checks["microphone"].detail
    assert "устройство" in checks["microphone"].hint


@pytest.mark.parametrize("names,status", [({"qwen3:1.7b"}, "ok"), ({"other:latest"}, "warning")])
def test_ollama_checks_selected_model_without_generating_text(config, monkeypatch, names, status):
    config.settings.nlu.semantic_enabled = True
    monkeypatch.setattr(diagnostics, "ollama_models", lambda: names)
    assert checks_by_key(config, ollama=True)["ollama"].status == status


def test_unavailable_ollama_is_a_report_not_an_exception(config, monkeypatch):
    config.settings.nlu.semantic_enabled = True
    monkeypatch.setattr(diagnostics, "ollama_models", Mock(side_effect=ConnectionError("offline")))
    result = checks_by_key(config, ollama=True)["ollama"]
    assert result.status == "warning"
    assert "offline" in result.diagnostic
    assert "недоступен" in result.detail


def test_ollama_uses_loopback_bounded_read_and_no_proxy(monkeypatch):
    import json

    response = Mock()
    response.read.return_value = json.dumps({"models": [{"name": "qwen3:1.7b"}]}).encode()
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = context
    builder = Mock(return_value=opener)
    monkeypatch.setattr(diagnostics, "build_opener", builder)
    assert diagnostics.ollama_models() == {"qwen3:1.7b"}
    opener.open.assert_called_once_with("http://127.0.0.1:11434/api/tags", timeout=2)
    response.read.assert_called_once_with(128 * 1024 + 1)
    handlers = builder.call_args.args
    assert handlers[0].proxies == {}
    assert isinstance(handlers[1], diagnostics.NoRedirect)
