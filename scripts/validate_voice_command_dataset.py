"""Validate labels, audio existence, splits and duplicate recordings before training."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def validate(rows, root: Path, allow_draft=False):
    errors, warnings = [], []
    seen_ids, hashes = set(), {}
    counts = defaultdict(Counter)
    known = {
        row["intent"]
        for row in yaml.safe_load((ROOT / "configs/commands.yaml").read_text("utf-8"))["intents"]
    } | {"unknown_command"}
    for index, row in enumerate(rows, 1):
        fields = (
            ["audio_path"]
            if allow_draft
            else ["audio_path", "text", "intent", "canonical_text", "split"]
        )
        for field in fields:
            if not isinstance(row.get(field), str) or not row[field].strip():
                errors.append(f"line {index}: missing/invalid {field}")
        identity = row.get("id")
        if identity:
            if identity in seen_ids:
                errors.append(f"line {index}: duplicate id {identity}")
            seen_ids.add(identity)
        split, intent = row.get("split", ""), row.get("intent", "")
        if not allow_draft:
            if split not in {"train", "val", "test"}:
                errors.append(f"line {index}: invalid split {split}")
            if intent not in known:
                errors.append(f"line {index}: unknown intent {intent}")
            counts[intent][split] += 1
        path = Path(str(row.get("audio_path", "")))
        path = path if path.is_absolute() else root / path
        if not path.is_file():
            errors.append(f"line {index}: audio not found: {path}")
        else:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in hashes:
                errors.append(f"line {index}: duplicate audio of line {hashes[digest]}")
            hashes[digest] = index
    for intent, splits in sorted(counts.items()):
        if not splits["train"]:
            errors.append(f"{intent}: no training examples")
        for split in ("val", "test"):
            if not splits[split]:
                warnings.append(f"{intent}: not represented in {split}")
    return errors, warnings, dict(counts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / "data/dataset_curated/recovery_dataset_86.jsonl"
    )
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for line in args.dataset.read_text("utf-8-sig").splitlines()
        if line.strip()
    ]
    errors, warnings, counts = validate(rows, args.project_root, args.allow_draft)
    if args.expected_count is not None and len(rows) != args.expected_count:
        errors.append(f"Expected {args.expected_count} rows, found {len(rows)}")
    print(
        json.dumps(
            {
                "rows": len(rows),
                "status": "error" if errors else "ok",
                "errors": errors,
                "warnings": warnings,
                "counts": counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
