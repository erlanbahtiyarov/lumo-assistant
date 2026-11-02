"""Evaluate actual ASR + command service in dry-run; no desktop action is performed."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from voice_control_pc.asr import FasterWhisperTranscriber
from voice_control_pc.config import load_config_bundle
from voice_control_pc.models import AsrSettings
from voice_control_pc.service import VoiceControlService

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / "data/dataset_curated/recovery_dataset_86.jsonl"
    )
    parser.add_argument("--split", choices=["train", "val", "test", "all"], default="test")
    parser.add_argument(
        "--asr", action="store_true", help="Transcribe actual audio instead of using saved ASR text"
    )
    parser.add_argument("--model", default="tiny")
    parser.add_argument("--model-path", type=Path, default=ROOT / "artifacts/asr-smoke")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--semantic-model", default="qwen3:1.7b")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/evaluation.json")
    args = parser.parse_args()
    config = load_config_bundle(ROOT)
    config.settings.nlu.neural_recovery_enabled = False
    config.settings.nlu.semantic_enabled = args.semantic
    config.settings.nlu.semantic_model = args.semantic_model
    service = VoiceControlService(config, dry_run=True)
    transcriber = None
    if args.asr:
        transcriber = FasterWhisperTranscriber(
            AsrSettings(
                model_name=args.model,
                model_path=str(args.model_path.resolve()),
                allow_download=args.allow_download,
            )
        )
        transcriber.load()
    rows = [json.loads(l) for l in args.dataset.read_text("utf-8-sig").splitlines() if l.strip()]
    rows = [r for r in rows if args.split == "all" or r["split"] == args.split]
    results = []
    for row in rows:
        started = time.perf_counter()
        text = transcriber.transcribe_file(ROOT / row["audio_path"]) if transcriber else row["text"]
        match, result = service.process_text_command(text)
        expected = None if row["intent"] == "unknown_command" else row["intent"]
        results.append(
            {
                "id": row["id"],
                "transcript": text,
                "expected_intent": expected,
                "predicted_intent": match["intent"],
                "slots": match["slots"],
                "status": result.status,
                "intent_correct": match["intent"] == expected,
                "seconds": round(time.perf_counter() - started, 4),
            }
        )
    summary = {
        "pipeline": (f"{args.model} ASR" if args.asr else "saved ASR text")
        + " + rules"
        + (" + local LLM" if args.semantic else ""),
        "semantic_model": args.semantic_model if args.semantic else None,
        "model": args.model if args.asr else None,
        "split": args.split,
        "rows": len(results),
        "intent_accuracy": sum(r["intent_correct"] for r in results) / max(len(results), 1),
        "unknown_false_positives": sum(
            r["expected_intent"] is None and r["predicted_intent"] is not None for r in results
        ),
        "median_seconds_excluding_model_load": statistics.median([r["seconds"] for r in results])
        if results
        else None,
        "limitations": [
            "Small synthesized corpus; not speaker-independent.",
            "Measures intent recognition, not verified Windows execution or slot accuracy.",
            "No evaluation of take_screenshot on held-out data: only one recording.",
        ],
        "predictions": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "predictions"}, ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
