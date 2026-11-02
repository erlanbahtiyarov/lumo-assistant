"""CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from voice_control_pc.asr import FasterWhisperTranscriber
from voice_control_pc.audio import list_input_devices, record_microphone_to_wav
from voice_control_pc.config import load_config_bundle
from voice_control_pc.logging_utils import setup_logging
from voice_control_pc.service import VoiceControlService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lumo")
    parser.add_argument("--project-root", type=Path, default=None)

    subparsers = parser.add_subparsers(dest="command_name", required=True)

    subparsers.add_parser("devices")

    transcribe_parser = subparsers.add_parser("transcribe")
    transcribe_parser.add_argument("audio_path", type=Path)

    text_command_parser = subparsers.add_parser("command")
    text_command_parser.add_argument("text")
    text_command_parser.add_argument("--confirm", action="store_true")
    text_command_parser.add_argument("--dry-run", action="store_true")

    gui_parser = subparsers.add_parser("gui")
    gui_parser.add_argument("--dry-run", action="store_true")

    listen_parser = subparsers.add_parser("listen")
    listen_parser.add_argument("--dry-run", action="store_true")
    listen_parser.add_argument("--confirm", action="store_true")
    listen_parser.add_argument("--duration", type=int, default=None)
    listen_parser.add_argument("--device-index", type=int, default=None)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config = load_config_bundle(args.project_root)
    logger = setup_logging(
        level=config.settings.logging.level,
        text_log_path=config.project_root / config.settings.logging.text_log_path,
        jsonl_log_path=config.project_root / config.settings.logging.jsonl_path,
    )

    if args.command_name == "devices":
        devices = list_input_devices()
        print(json.dumps(devices, ensure_ascii=False, indent=2))
        return 0

    if args.command_name == "transcribe":
        transcriber = FasterWhisperTranscriber(config.settings.asr)
        text = transcriber.transcribe_file(args.audio_path)
        print(text)
        return 0

    if args.command_name == "command":
        service = VoiceControlService(config=config, dry_run=args.dry_run or config.settings.app.dry_run)
        match, result = service.process_text_command(args.text, confirmed=args.confirm)
        logger.info("intent=%s status=%s", match["intent"], result.status)
        print(json.dumps({"match": match, "result": result.model_dump()}, ensure_ascii=False, indent=2))
        return 0 if result.success else 1

    if args.command_name == "gui":
        from voice_control_pc.gui import run_gui

        logger.info("starting gui")
        run_gui()
        return 0

    if args.command_name == "listen":
        transcriber = FasterWhisperTranscriber(config.settings.asr)
        service = VoiceControlService(config=config, dry_run=args.dry_run or config.settings.app.dry_run)

        (config.project_root / "artifacts").mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
            dir=str(config.project_root / "artifacts"),
        ) as temp_audio:
            temp_audio_path = Path(temp_audio.name)

        print("Говорите команду после начала записи...")
        logger.info("recording microphone audio into %s", temp_audio_path)
        record_microphone_to_wav(
            output_path=temp_audio_path,
            settings=config.settings.audio,
            duration_seconds=args.duration,
            device_index=args.device_index,
        )

        text = transcriber.transcribe_file(temp_audio_path)
        logger.info("transcribed text: %s", text)

        match, result = service.process_text_command(text, confirmed=args.confirm)
        print(
            json.dumps(
                {
                    "audio_path": str(temp_audio_path),
                    "transcript": text,
                    "corrected_transcript": match.get("corrected_text"),
                    "match": match,
                    "result": result.model_dump(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if result.success else 1

    parser.print_help()
    return 1
