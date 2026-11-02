"""Reproducible per-intent holdout; augmentation must happen after this operation."""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


def assign_splits(rows: list[dict], seed: int = 42) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[row["intent"]].append(row)
    rng = random.Random(seed)
    assignments = {}
    for label in sorted(groups):
        group = sorted(groups[label], key=lambda row: row["id"])
        rng.shuffle(group)
        for index, row in enumerate(group):
            assignments[row["id"]] = (
                ("test" if index == 0 else "val" if index == 1 else "train")
                if len(group) >= 3
                else "train"
            )
    return [dict(row, split=assignments[row["id"]]) for row in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for line in args.dataset.read_text("utf-8-sig").splitlines()
        if line.strip()
    ]
    result = assign_splits(rows, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in result), "utf-8"
    )
    print(
        json.dumps(
            {"rows": len(result), "seed": args.seed, "output": str(args.output)}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
