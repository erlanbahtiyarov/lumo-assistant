"""Train a CNN intent classifier directly from the 86 curated audio recordings."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import av
import matplotlib.pyplot as plt
import numpy as np
import torch
import torchaudio
from torch import nn


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "data" / "dataset_curated" / "recovery_dataset_86.jsonl"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "audio_training_86"
DEFAULT_MODEL = PROJECT_ROOT / "models" / "audio_intent_classifier.pt"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-out", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--augmentations", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--max-seconds", type=float, default=6.0)
    parser.add_argument("--n-mels", type=int, default=64)
    parser.add_argument("--patience", type=int, default=18)
    return parser


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def resolve_audio_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def decode_audio(path: Path, sample_rate: int, max_samples: int) -> torch.Tensor:
    container = av.open(str(path))
    resampler = av.audio.resampler.AudioResampler(format="fltp", layout="mono", rate=sample_rate)
    chunks: list[np.ndarray] = []
    for frame in container.decode(audio=0):
        converted = resampler.resample(frame)
        frames = converted if isinstance(converted, list) else [converted]
        for converted_frame in frames:
            chunks.append(converted_frame.to_ndarray().reshape(-1).astype(np.float32))
    container.close()
    if not chunks:
        raise ValueError(f"No audio samples decoded from {path}")
    waveform = torch.from_numpy(np.concatenate(chunks))
    peak = waveform.abs().max()
    if peak > 0:
        waveform = waveform / peak
    if waveform.numel() > max_samples:
        waveform = waveform[:max_samples]
    elif waveform.numel() < max_samples:
        waveform = torch.nn.functional.pad(waveform, (0, max_samples - waveform.numel()))
    return waveform


def augment_waveform(waveform: torch.Tensor, rng: random.Random) -> torch.Tensor:
    result = waveform.clone()
    gain = rng.uniform(0.70, 1.15)
    result = result * gain
    shift = rng.randint(-2400, 2400)
    result = torch.roll(result, shifts=shift)
    noise_level = rng.uniform(0.001, 0.025)
    result = result + torch.randn_like(result) * noise_level
    if rng.random() < 0.35:
        width = rng.randint(200, 1600)
        start = rng.randint(0, max(result.numel() - width, 0))
        result[start : start + width] = 0
    return result.clamp(-1.0, 1.0)


def create_stratified_split(rows: list[dict[str, Any]], seed: int) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[str(row["intent"])].append(index)
    rng = random.Random(seed)
    split = {"train": [], "val": [], "test": []}
    for indexes in grouped.values():
        rng.shuffle(indexes)
        if len(indexes) >= 3:
            split["test"].append(indexes[0])
            split["val"].append(indexes[1])
            split["train"].extend(indexes[2:])
        else:
            split["train"].extend(indexes)
    for indexes in split.values():
        rng.shuffle(indexes)
    return split


class AudioIntentCNN(nn.Module):
    def __init__(self, class_count: int):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 24, kernel_size=3, padding=1),
            nn.BatchNorm2d(24),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(24, 48, kernel_size=3, padding=1),
            nn.BatchNorm2d(48),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(48, 96, kernel_size=3, padding=1),
            nn.BatchNorm2d(96),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 4)),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(96 * 4 * 4, 256),
            nn.ReLU(),
            nn.Dropout(0.30),
            nn.Linear(256, class_count),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(features))


def confusion_matrix(
    targets: list[int], predictions: list[int], class_count: int
) -> list[list[int]]:
    matrix = [[0 for _ in range(class_count)] for _ in range(class_count)]
    for target, prediction in zip(targets, predictions):
        matrix[target][prediction] += 1
    return matrix


def per_class_metrics(matrix: list[list[int]], labels: list[str]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    class_count = len(labels)
    for index, label in enumerate(labels):
        tp = matrix[index][index]
        fp = sum(matrix[row][index] for row in range(class_count) if row != index)
        fn = sum(matrix[index][col] for col in range(class_count) if col != index)
        support = sum(matrix[index])
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-12)
        metrics.append(
            {
                "intent": label,
                "support": support,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
            }
        )
    return metrics


def evaluate(
    model: nn.Module,
    features: torch.Tensor,
    targets: torch.Tensor,
    criterion: nn.Module,
) -> dict[str, Any]:
    model.eval()
    with torch.no_grad():
        logits = model(features)
        loss = criterion(logits, targets)
        predictions = logits.argmax(dim=1)
        probabilities = torch.softmax(logits, dim=1)
    accuracy = float((predictions == targets).float().mean().item())
    return {
        "loss": float(loss.item()),
        "accuracy": accuracy,
        "predictions": predictions.tolist(),
        "targets": targets.tolist(),
        "confidences": probabilities.max(dim=1).values.tolist(),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def plot_history(history: list[dict[str, Any]], output_dir: Path) -> None:
    epochs = [item["epoch"] for item in history]
    for metric, title in [("loss", "Loss"), ("accuracy", "Accuracy")]:
        plt.figure(figsize=(10, 6))
        plt.plot(epochs, [item[f"train_{metric}"] for item in history], label="Train", linewidth=2)
        plt.plot(
            epochs, [item[f"val_{metric}"] for item in history], label="Validation", linewidth=2
        )
        plt.title(f"Audio CNN {title}")
        plt.xlabel("Epoch")
        plt.ylabel(title)
        plt.grid(alpha=0.25)
        plt.legend()
        plt.tight_layout()
        plt.savefig(output_dir / f"{metric}_curve.png", dpi=180)
        plt.close()


def plot_confusion(matrix: list[list[int]], labels: list[str], output_path: Path) -> None:
    plt.figure(figsize=(13, 11))
    plt.imshow(matrix, cmap="Blues")
    plt.colorbar()
    plt.xticks(range(len(labels)), labels, rotation=55, ha="right", fontsize=8)
    plt.yticks(range(len(labels)), labels, fontsize=8)
    plt.xlabel("Predicted intent")
    plt.ylabel("True intent")
    plt.title("Audio CNN Test Confusion Matrix")
    for row_index, row in enumerate(matrix):
        for col_index, value in enumerate(row):
            plt.text(col_index, row_index, str(value), ha="center", va="center", fontsize=8)
    plt.tight_layout()
    plt.savefig(output_path, dpi=180)
    plt.close()


def plot_distribution(
    rows: list[dict[str, Any]], split: dict[str, list[int]], output_path: Path
) -> None:
    labels = sorted({str(row["intent"]) for row in rows})
    split_counts = {
        split_name: Counter(str(rows[index]["intent"]) for index in indexes)
        for split_name, indexes in split.items()
    }
    x = np.arange(len(labels))
    width = 0.25
    plt.figure(figsize=(14, 7))
    for position, split_name in enumerate(["train", "val", "test"]):
        values = [split_counts[split_name][label] for label in labels]
        plt.bar(x + (position - 1) * width, values, width, label=split_name.title())
    plt.xticks(x, labels, rotation=55, ha="right", fontsize=8)
    plt.ylabel("Recordings")
    plt.title("Distribution of 86 Audio Recordings")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=180)
    plt.close()


def main() -> int:
    args = build_parser().parse_args()
    set_seed(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.model_out.parent.mkdir(parents=True, exist_ok=True)
    start_time = time.perf_counter()

    rows = load_rows(args.dataset)
    if not rows:
        raise SystemExit("Dataset is empty")
    missing = [
        row["audio_path"] for row in rows if not resolve_audio_path(row["audio_path"]).exists()
    ]
    if missing:
        raise SystemExit(f"Missing audio files: {len(missing)}")

    labels = sorted({str(row["intent"]) for row in rows})
    label_to_index = {label: index for index, label in enumerate(labels)}
    split = {
        name: [i for i, row in enumerate(rows) if row.get("split") == name]
        for name in ("train", "val", "test")
    }
    if any(not indexes for indexes in split.values()) or sum(map(len, split.values())) != len(rows):
        raise SystemExit("Dataset must have explicit non-empty train, val and test splits")
    missing_train = set(labels) - {str(rows[i]["intent"]) for i in split["train"]}
    if missing_train:
        raise SystemExit(f"No training examples for: {sorted(missing_train)}")

    max_samples = int(args.sample_rate * args.max_seconds)
    mel_transform = torchaudio.transforms.MelSpectrogram(
        sample_rate=args.sample_rate,
        n_fft=512,
        win_length=400,
        hop_length=160,
        n_mels=args.n_mels,
    )

    waveforms: list[torch.Tensor] = []
    durations: list[float] = []
    for row in rows:
        waveform = decode_audio(
            resolve_audio_path(row["audio_path"]), args.sample_rate, max_samples
        )
        nonzero = int((waveform.abs() > 1e-5).sum().item())
        durations.append(nonzero / args.sample_rate)
        waveforms.append(waveform)

    def to_feature(waveform: torch.Tensor) -> torch.Tensor:
        mel = mel_transform(waveform)
        log_mel = torch.log(mel + 1e-6)
        log_mel = (log_mel - log_mel.mean()) / (log_mel.std() + 1e-6)
        return log_mel.unsqueeze(0)

    train_features: list[torch.Tensor] = []
    train_targets: list[int] = []
    rng = random.Random(args.seed)
    for index in split["train"]:
        train_features.append(to_feature(waveforms[index]))
        train_targets.append(label_to_index[str(rows[index]["intent"])])
        for _ in range(args.augmentations):
            train_features.append(to_feature(augment_waveform(waveforms[index], rng)))
            train_targets.append(label_to_index[str(rows[index]["intent"])])

    def build_eval_tensors(indexes: list[int]) -> tuple[torch.Tensor, torch.Tensor]:
        features = torch.stack([to_feature(waveforms[index]) for index in indexes])
        targets = torch.tensor(
            [label_to_index[str(rows[index]["intent"])] for index in indexes],
            dtype=torch.long,
        )
        return features, targets

    train_x = torch.stack(train_features)
    train_y = torch.tensor(train_targets, dtype=torch.long)
    val_x, val_y = build_eval_tensors(split["val"])
    test_x, test_y = build_eval_tensors(split["test"])

    model = AudioIntentCNN(len(labels))
    train_class_counts = Counter(train_targets)
    class_weights = torch.tensor(
        [
            len(train_targets) / max(len(labels) * train_class_counts[index], 1)
            for index in range(len(labels))
        ],
        dtype=torch.float32,
    )
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", patience=6, factor=0.5
    )
    train_dataset = torch.utils.data.TensorDataset(train_x, train_y)
    generator = torch.Generator().manual_seed(args.seed)
    train_loader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        generator=generator,
    )

    history: list[dict[str, Any]] = []
    best_val_accuracy = -1.0
    best_epoch = 0
    best_state: dict[str, torch.Tensor] | None = None
    no_improvement = 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0
        correct = 0
        total = 0
        for batch_x, batch_y in train_loader:
            optimizer.zero_grad()
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())
            correct += int((logits.argmax(dim=1) == batch_y).sum().item())
            total += int(batch_y.numel())

        val_result = evaluate(model, val_x, val_y, criterion)
        train_accuracy = correct / max(total, 1)
        history.append(
            {
                "epoch": epoch,
                "train_loss": round(epoch_loss / max(len(train_loader), 1), 6),
                "train_accuracy": round(train_accuracy, 6),
                "val_loss": round(val_result["loss"], 6),
                "val_accuracy": round(val_result["accuracy"], 6),
                "learning_rate": optimizer.param_groups[0]["lr"],
            }
        )
        scheduler.step(val_result["accuracy"])
        if val_result["accuracy"] > best_val_accuracy:
            best_val_accuracy = val_result["accuracy"]
            best_epoch = epoch
            best_state = {
                name: value.detach().clone() for name, value in model.state_dict().items()
            }
            no_improvement = 0
        else:
            no_improvement += 1
        if no_improvement >= args.patience:
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    test_result = evaluate(model, test_x, test_y, criterion)
    matrix = confusion_matrix(test_result["targets"], test_result["predictions"], len(labels))
    class_metrics = per_class_metrics(matrix, labels)
    supported_f1 = [item["f1"] for item in class_metrics if item["support"] > 0]
    macro_f1 = sum(supported_f1) / max(len(supported_f1), 1)

    torch.save(
        {
            "state_dict": model.state_dict(),
            "intent_labels": labels,
            "sample_rate": args.sample_rate,
            "max_seconds": args.max_seconds,
            "n_mels": args.n_mels,
            "architecture": "AudioIntentCNN",
        },
        args.model_out,
    )

    epoch_rows = list(history)
    write_csv(args.output_dir / "epoch_metrics.csv", epoch_rows)
    write_csv(args.output_dir / "per_class_test_metrics.csv", class_metrics)

    prediction_rows: list[dict[str, Any]] = []
    for position, row_index in enumerate(split["test"]):
        prediction_rows.append(
            {
                "id": rows[row_index]["id"],
                "audio_path": rows[row_index]["audio_path"],
                "true_intent": labels[test_result["targets"][position]],
                "predicted_intent": labels[test_result["predictions"][position]],
                "confidence": round(test_result["confidences"][position], 6),
                "correct": test_result["targets"][position] == test_result["predictions"][position],
            }
        )
    write_csv(args.output_dir / "test_predictions.csv", prediction_rows)

    distribution_rows: list[dict[str, Any]] = []
    for split_name, indexes in split.items():
        counts = Counter(str(rows[index]["intent"]) for index in indexes)
        for label in labels:
            distribution_rows.append(
                {"split": split_name, "intent": label, "count": counts.get(label, 0)}
            )
    write_csv(args.output_dir / "dataset_distribution.csv", distribution_rows)

    plot_history(history, args.output_dir)
    plot_confusion(matrix, labels, args.output_dir / "test_confusion_matrix.png")
    plot_distribution(rows, split, args.output_dir / "dataset_distribution.png")

    summary = {
        "experiment": "audio_intent_classifier_86",
        "dataset": str(args.dataset.resolve()),
        "audio_rows": len(rows),
        "audio_files_found": len(rows) - len(missing),
        "intent_count": len(labels),
        "intent_labels": labels,
        "split_sizes": {name: len(indexes) for name, indexes in split.items()},
        "original_train_rows": len(split["train"]),
        "augmented_train_samples": len(train_features),
        "augmentations_per_train_recording": args.augmentations,
        "sample_rate": args.sample_rate,
        "max_seconds": args.max_seconds,
        "n_mels": args.n_mels,
        "model_architecture": "3-layer CNN over log-Mel spectrograms",
        "model_parameters": sum(parameter.numel() for parameter in model.parameters()),
        "epochs_requested": args.epochs,
        "epochs_completed": len(history),
        "best_epoch": best_epoch,
        "best_val_accuracy": round(best_val_accuracy, 6),
        "test_accuracy": round(test_result["accuracy"], 6),
        "test_loss": round(test_result["loss"], 6),
        "test_macro_f1_supported_classes": round(macro_f1, 6),
        "test_confusion_matrix": matrix,
        "mean_audio_duration_seconds": round(sum(durations) / len(durations), 4),
        "total_audio_duration_seconds": round(sum(durations), 4),
        "elapsed_seconds": round(time.perf_counter() - start_time, 3),
        "seed": args.seed,
        "limitations": [
            "The dataset contains only one take_screenshot recording; it is used for training but cannot be independently evaluated.",
            "Metrics are based on a small holdout set and should be interpreted as a pilot experiment.",
        ],
    }
    (args.output_dir / "training_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report_lines = [
        "# Отчёт об обучении аудиомодели на 86 записях",
        "",
        f"- Исходных аудиозаписей: **{summary['audio_rows']}**",
        f"- Число классов намерений: **{summary['intent_count']}**",
        f"- Разбиение: **train={summary['split_sizes']['train']}**, **val={summary['split_sizes']['val']}**, **test={summary['split_sizes']['test']}**",
        f"- Обучающих примеров после аудиоаугментации: **{summary['augmented_train_samples']}**",
        f"- Архитектура: **{summary['model_architecture']}**",
        f"- Число параметров модели: **{summary['model_parameters']}**",
        f"- Выполнено эпох: **{summary['epochs_completed']}**, лучшая эпоха: **{summary['best_epoch']}**",
        f"- Лучшая validation accuracy: **{summary['best_val_accuracy']:.4f}**",
        f"- Test accuracy: **{summary['test_accuracy']:.4f}**",
        f"- Test macro-F1 по представленным в test классам: **{summary['test_macro_f1_supported_classes']:.4f}**",
        f"- Время эксперимента: **{summary['elapsed_seconds']:.3f} с**",
        "",
        "## Артефакты",
        "",
        "- `epoch_metrics.csv` — журнал обучения по эпохам",
        "- `test_predictions.csv` — предсказания для каждой тестовой аудиозаписи",
        "- `per_class_test_metrics.csv` — Precision, Recall и F1 по классам",
        "- `dataset_distribution.csv` — распределение записей по выборкам",
        "- `loss_curve.png`, `accuracy_curve.png` — кривые обучения",
        "- `test_confusion_matrix.png` — матрица ошибок",
        "- `dataset_distribution.png` — распределение 86 записей",
        "",
        "## Ограничения",
        "",
        "- В классе `take_screenshot` имеется только одна запись, поэтому независимая оценка этого класса невозможна.",
        "- Результаты являются пилотными из-за малого объёма контрольной выборки.",
    ]
    (args.output_dir / "TRAINING_REPORT.md").write_text("\n".join(report_lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
