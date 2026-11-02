"""Lumo's CLI and desktop launcher. Hardware dependencies are loaded only when needed."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from voice_control_pc.asr import FasterWhisperTranscriber
from voice_control_pc.audio import list_input_devices, record_microphone_to_wav
from voice_control_pc.config import load_config_bundle, resolved_asr_settings
from voice_control_pc.logging_utils import setup_logging
from voice_control_pc.service import VoiceControlService


def _mode(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", dest="dry_run", action="store_const", const=True, default=None)
    group.add_argument("--execute", dest="dry_run", action="store_const", const=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lumo", description="Лумо — настольный голосовой помощник"
    )
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command_name")
    subparsers.add_parser("devices", help="Микрофоны")
    doctor = subparsers.add_parser("doctor", help="Проверить окружение без загрузки моделей")
    doctor.add_argument(
        "--microphone", action="store_true", help="Проверить список микрофонов без записи"
    )
    doctor.add_argument(
        "--ollama",
        action="store_true",
        help="Проверить локальный Ollama и наличие выбранной модели",
    )
    transcribe = subparsers.add_parser("transcribe")
    transcribe.add_argument("audio_path", type=Path)
    command = subparsers.add_parser("command")
    command.add_argument("text")
    _mode(command)
    gui = subparsers.add_parser("gui")
    _mode(gui)
    listen = subparsers.add_parser("listen")
    _mode(listen)
    listen.add_argument("--duration", type=int, default=None)
    listen.add_argument("--device-index", type=int, default=None)
    return parser


def _run(args) -> int:
    if args.smoke_test:
        from voice_control_pc.gui import smoke_gui

        return smoke_gui()
    config = load_config_bundle(args.project_root)
    name = args.command_name or "gui"
    dry_run = getattr(args, "dry_run", None)
    if name == "gui":
        from voice_control_pc.gui import run_gui

        return run_gui(config, dry_run=dry_run)
    if name == "doctor":
        from voice_control_pc.diagnostics import check_readiness

        payload = {
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "data_directory": str(config.project_root),
            "execution_supported": sys.platform == "win32",
            "asr_model": config.settings.asr.model_name,
            "model_download_allowed": config.settings.asr.allow_download,
            "ollama_enabled": config.settings.nlu.semantic_enabled,
            "components": {
                key: importlib.util.find_spec(key) is not None
                for key in ("PySide6", "pyaudio", "faster_whisper", "torch")
            },
            "checks": [
                check.as_dict()
                for check in check_readiness(config, microphone=args.microphone, ollama=args.ollama)
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    logger = setup_logging(
        config.settings.logging.level,
        config.project_root / config.settings.logging.text_log_path,
        config.project_root / config.settings.logging.jsonl_path,
    )
    if name == "devices":
        print(json.dumps(list_input_devices(), ensure_ascii=False, indent=2))
        return 0
    if name == "transcribe":
        print(
            FasterWhisperTranscriber(resolved_asr_settings(config)).transcribe_file(args.audio_path)
        )
        return 0
    service = VoiceControlService(config, dry_run=dry_run)
    if name == "command":
        text = args.text
    else:
        transcriber = FasterWhisperTranscriber(resolved_asr_settings(config))
        with tempfile.TemporaryDirectory(prefix="lumo-") as directory:
            path = Path(directory) / "command.wav"
            print("Говори команду…", file=sys.stderr)
            record_microphone_to_wav(
                output_path=path,
                settings=config.settings.audio,
                duration_seconds=args.duration,
                device_index=args.device_index,
            )
            text = transcriber.transcribe_file(path)
    match, result = service.process_text_command(text)
    if result.status == "confirmation_required" and sys.stdin.isatty():
        from voice_control_pc.models import CommandResult

        action = match.get("action")
        target = match.get("slots")
        answer = input(f"Действие: {action}, объект: {target}. Подтвердить? Введите ДА: ")
        if answer.strip() == "ДА":
            result = service.confirm_command(result.artifacts["confirmation_token"])
        else:
            service.cancel_pending()
            result = CommandResult(success=False, status="cancelled", message="Действие отменено")
    logger.info("intent=%s status=%s", match["intent"], result.status)
    print(
        json.dumps(
            {"transcript": text, "match": match, "result": result.model_dump()},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.success else 1


def main() -> int:
    args = build_parser().parse_args()
    try:
        return _run(args)
    except (Exception, KeyboardInterrupt) as error:
        print(f"Лумо: {error or 'операция отменена'}", file=sys.stderr)
        return 2
