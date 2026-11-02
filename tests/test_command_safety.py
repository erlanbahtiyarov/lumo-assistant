from pathlib import Path
from unittest.mock import Mock

import pytest

from voice_control_pc.config import load_config_bundle
from voice_control_pc.service import VoiceControlService


@pytest.fixture
def service():
    config = load_config_bundle(Path(__file__).resolve().parents[1])
    return VoiceControlService(config, dry_run=True)


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "!!!",
        "закрой",
        "выключи",
        "открой",
        "перезагрузи",
        "не закрой активное окно",
        "закрой окно не надо",
        "не выключай компьютер",
        "открой браузер и выключи компьютер",
        "открой браузер затем закрой окно",
        "открой браузер или блокнот",
        "открой браузерный",
        "открой папку неизвестная",
        "закрой текущее окно, выключи",
        "покажи рабочий стол; перезагрузи",
    ],
)
def test_unsafe_or_incomplete_input_does_not_execute(service, text):
    match, result = service.process_text_command(text)
    assert match["intent"] is None
    assert result.status == "no_match"


@pytest.mark.parametrize(
    "text,intent,slot,value",
    [
        ("запусти блокнот", "open_app", "app_name", "блокнот"),
        ("открой телеграм", "open_app", "app_name", "telegram"),
        ("открой проводник", "open_app", "app_name", "проводник"),
        ("открой папку изображения", "open_folder", "folder_name", "изображения"),
        ("покажи папку документы", "open_folder", "folder_name", "документы"),
        ("открой калькулятор пожалуйста", "open_app", "app_name", "калькулятор"),
    ],
)
def test_opening_verbs_work_with_allowlisted_objects(service, text, intent, slot, value):
    match, result = service.process_text_command(text)
    assert match["intent"] == intent
    assert match["slots"][slot] == value
    assert result.status == "dry_run"


@pytest.mark.parametrize("text", ["открой калькулятор", "не закрой активное окно", "", "закрой"])
def test_recovery_cannot_override_a_valid_command_or_bypass_input_guard(service, text):
    service.recovery = Mock()
    service.process_text_command(text)
    service.recovery.enhance_match.assert_not_called()


def test_recovery_must_agree_with_executable_intent(service):
    def recover(text, match):
        match.intent = "open_app"
        match.corrected_text = "выключи компьютер"
        return match

    service.recovery = Mock()
    service.recovery.enhance_match.side_effect = recover
    match, result = service.process_text_command("крой калькулятар")
    assert match["intent"] is None
    assert result.status == "no_match"


def test_recovery_preserves_raw_transcript_and_resolves_object(service):
    def recover(text, match):
        match.intent = "open_app"
        match.corrected_text = "открой калькулятор"
        match.correction_confidence = 0.9
        return match

    service.recovery = Mock()
    service.recovery.enhance_match.side_effect = recover
    match, result = service.process_text_command("крой калькулятар")
    assert match["text"] == "крой калькулятар"
    assert match["slots"] == {"app_name": "калькулятор"}
    assert match["corrected_text"] == "открой калькулятор"
    assert result.status == "confirmation_required"
    confirmed = service.confirm_command(result.artifacts["confirmation_token"])
    assert confirmed.status == "dry_run"


@pytest.mark.parametrize("text", ["как выключить компьютер", "объясни как закрыть окно"])
def test_instructional_questions_do_not_reach_neural_models(service, text):
    service.recovery = Mock()
    match, result = service.process_text_command(text)
    assert match["intent"] is None
    assert result.status == "no_match"
    service.recovery.enhance_match.assert_not_called()
