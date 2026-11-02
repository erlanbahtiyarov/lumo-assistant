"""Development scenarios for local language interpretation; no OS action or confirmation."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from voice_control_pc.config import load_config_bundle
from voice_control_pc.service import VoiceControlService

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:1.7b")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/semantic-scenarios.json")
    args = parser.parse_args()
    config = load_config_bundle(ROOT)
    config.settings.nlu.neural_recovery_enabled = False
    config.settings.nlu.semantic_enabled = True
    config.settings.nlu.semantic_model = args.model
    service = VoiceControlService(config, dry_run=True)
    rows = json.loads((ROOT / "data/semantic_scenarios.json").read_text("utf-8"))
    results = []
    for row in rows:
        started = time.perf_counter()
        match, result = service.process_text_command(row["text"])
        correct = match["intent"] == row["intent"] and match["slots"] == row["slots"]
        results.append(
            dict(
                row,
                predicted_intent=match["intent"],
                predicted_slots=match["slots"],
                correct=correct,
                status=result.status,
                seconds=round(time.perf_counter() - started, 3),
            )
        )
    report = {
        "model": args.model,
        "correct": sum(r["correct"] for r in results),
        "rows": len(results),
        "limitations": "Hand-written development scenarios, not an independent benchmark.",
        "predictions": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
