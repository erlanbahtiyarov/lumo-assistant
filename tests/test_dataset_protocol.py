import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_split_is_reproducible_and_covers_train_for_rare_class():
    split = script("split_dataset").assign_splits
    rows = [{"id": f"a{i}", "intent": "open_app"} for i in range(6)] + [
        {"id": "rare", "intent": "take_screenshot"}
    ]
    result = split(rows)
    assert result == split(rows)
    assert {r["split"] for r in result if r["intent"] == "open_app"} == {"train", "val", "test"}
    assert result[-1]["split"] == "train"
    assert all("split" not in row for row in rows)


def test_validator_detects_missing_audio_duplicate_id_and_invalid_split(tmp_path):
    validate = script("validate_voice_command_dataset").validate
    row = {
        "id": "one",
        "intent": "open_app",
        "audio_path": "missing.wav",
        "text": "открой браузер",
        "canonical_text": "открой браузер",
        "split": "invalid",
    }
    errors, _, _ = validate([row, row], tmp_path)
    assert any("audio not found" in e for e in errors)
    assert any("duplicate id" in e for e in errors)
    assert any("invalid split" in e for e in errors)


def test_manifest_and_training_dataset_have_identical_assignments():
    base = ROOT / "data/dataset_curated"

    def assignments(name):
        return {
            r["id"]: r["split"]
            for r in [
                json.loads(line)
                for line in (base / name).read_text("utf-8-sig").splitlines()
                if line.strip()
            ]
        }

    assert assignments("dataset_manifest.jsonl") == assignments("recovery_dataset_86.jsonl")
