"""Local neural recovery for imperfect ASR command transcripts."""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from voice_control_pc.models import CommandCatalog, IntentMatch, NluSettings
from voice_control_pc.nlu import normalize_text


def _require_torch():
    try:
        import torch
        from torch import nn
    except ImportError as error:
        raise RuntimeError(
            "Для neural recovery требуется torch. Установите: pip install -e .[ml]"
        ) from error
    return torch, nn


class HashedTextVectorizer:
    def __init__(self, num_features: int = 4096, char_ngram_range: tuple[int, int] = (2, 5)):
        self.num_features = num_features
        self.char_ngram_range = char_ngram_range

    def _hash(self, value: str) -> int:
        digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "little") % self.num_features

    def _iter_features(self, text: str):
        normalized = normalize_text(text)
        if not normalized:
            return

        for word in normalized.split():
            yield f"word:{word}"

        padded = f"  {normalized}  "
        min_n, max_n = self.char_ngram_range
        for size in range(min_n, max_n + 1):
            for index in range(len(padded) - size + 1):
                yield f"char:{padded[index : index + size]}"

    def transform_one(self, text: str):
        torch, _nn = _require_torch()
        vector = torch.zeros(self.num_features, dtype=torch.float32)
        counts = Counter(self._hash(feature) for feature in self._iter_features(text))
        for feature_index, count in counts.items():
            vector[feature_index] = float(count)
        return vector

    def transform_many(self, texts: list[str]):
        torch, _nn = _require_torch()
        if not texts:
            return torch.empty(0, self.num_features, dtype=torch.float32)
        return torch.stack([self.transform_one(text) for text in texts])


def build_network(input_dim: int, output_dim: int, hidden_dim: int, dropout: float):
    _torch, nn = _require_torch()
    return nn.Sequential(
        nn.Linear(input_dim, hidden_dim),
        nn.ReLU(),
        nn.Dropout(dropout),
        nn.Linear(hidden_dim, hidden_dim),
        nn.ReLU(),
        nn.Dropout(dropout),
        nn.Linear(hidden_dim, output_dim),
    )


def sequence_similarity(left: str, right: str) -> float:
    left_tokens = set(normalize_text(left).split())
    right_tokens = set(normalize_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def build_confusion_matrix(
    predicted_indexes: list[int],
    target_indexes: list[int],
    class_count: int,
) -> list[list[int]]:
    matrix = [[0 for _ in range(class_count)] for _ in range(class_count)]
    for predicted, target in zip(predicted_indexes, target_indexes):
        matrix[target][predicted] += 1
    return matrix


def macro_f1_from_confusion_matrix(matrix: list[list[int]]) -> float:
    if not matrix:
        return 0.0
    f1_scores: list[float] = []
    class_count = len(matrix)
    for index in range(class_count):
        true_positive = matrix[index][index]
        false_positive = sum(matrix[row][index] for row in range(class_count) if row != index)
        false_negative = sum(matrix[index][col] for col in range(class_count) if col != index)
        precision = true_positive / max(true_positive + false_positive, 1)
        recall = true_positive / max(true_positive + false_negative, 1)
        if precision + recall == 0:
            f1_scores.append(0.0)
            continue
        f1_scores.append((2 * precision * recall) / (precision + recall))
    return sum(f1_scores) / max(len(f1_scores), 1)


class NeuralCommandRecovery:
    def __init__(
        self,
        model,
        vectorizer: HashedTextVectorizer,
        intent_labels: list[str],
        canonical_texts_by_intent: dict[str, list[str]],
        confidence_threshold: float,
    ):
        self.model = model
        self.vectorizer = vectorizer
        self.intent_labels = intent_labels
        self.canonical_texts_by_intent = canonical_texts_by_intent
        self.confidence_threshold = confidence_threshold
        self.model.eval()

    @classmethod
    def load(cls, model_path: Path, confidence_threshold: float):
        torch, _nn = _require_torch()
        checkpoint = torch.load(model_path, map_location="cpu")
        vectorizer = HashedTextVectorizer(
            num_features=checkpoint["num_features"],
            char_ngram_range=tuple(checkpoint["char_ngram_range"]),
        )
        model = build_network(
            input_dim=checkpoint["num_features"],
            output_dim=len(checkpoint["intent_labels"]),
            hidden_dim=checkpoint["hidden_dim"],
            dropout=checkpoint["dropout"],
        )
        model.load_state_dict(checkpoint["state_dict"])
        return cls(
            model=model,
            vectorizer=vectorizer,
            intent_labels=checkpoint["intent_labels"],
            canonical_texts_by_intent=checkpoint["canonical_texts_by_intent"],
            confidence_threshold=confidence_threshold,
        )

    def predict(self, text: str) -> dict[str, Any]:
        torch, _nn = _require_torch()
        features = self.vectorizer.transform_many([text])
        with torch.no_grad():
            logits = self.model(features)
            probabilities = torch.softmax(logits, dim=1)[0]
            confidence, predicted_index = torch.max(probabilities, dim=0)

        predicted_intent = self.intent_labels[predicted_index.item()]
        canonical_text = self._retrieve_canonical_text(text, predicted_intent)
        return {
            "intent": predicted_intent,
            "confidence": float(confidence.item()),
            "canonical_text": canonical_text,
            "scores": {
                label: float(probabilities[index].item())
                for index, label in enumerate(self.intent_labels)
            },
        }

    def enhance_match(self, raw_text: str, match: IntentMatch) -> IntentMatch:
        prediction = self.predict(raw_text)
        if prediction["confidence"] < self.confidence_threshold:
            return match

        if match.intent is None or prediction["intent"] != match.intent:
            match.intent = prediction["intent"]
        match.corrected_text = prediction["canonical_text"]
        match.correction_confidence = round(prediction["confidence"], 4)
        return match

    def _retrieve_canonical_text(self, raw_text: str, intent: str) -> str:
        candidates = self.canonical_texts_by_intent.get(intent, [])
        if not candidates:
            return normalize_text(raw_text)
        best_candidate = candidates[0]
        best_score = -1.0
        for candidate in candidates:
            score = sequence_similarity(raw_text, candidate)
            if normalize_text(raw_text) in normalize_text(candidate):
                score += 0.2
            if score > best_score:
                best_score = score
                best_candidate = candidate
        return best_candidate


def build_canonical_texts_from_commands(commands: CommandCatalog) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for spec in commands.intents:
        mapping[spec.intent] = list(spec.examples)
    return mapping


def load_training_rows(dataset_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if "text" not in payload or "intent" not in payload:
                continue
            rows.append(payload)
    return rows


def train_command_recovery_model(
    rows: list[dict[str, Any]],
    output_path: Path,
    hidden_dim: int = 256,
    num_features: int = 4096,
    epochs: int = 25,
    batch_size: int = 32,
    learning_rate: float = 1e-3,
    seed: int = 42,
) -> dict[str, Any]:
    torch, nn = _require_torch()
    started_at = time.perf_counter()
    torch.manual_seed(seed)

    filtered_rows = [row for row in rows if row.get("intent")]
    if not filtered_rows:
        raise ValueError("Training dataset is empty after filtering")

    train_rows = [row for row in filtered_rows if str(row.get("split", "")).strip() == "train"]
    val_rows = [row for row in filtered_rows if str(row.get("split", "")).strip() == "val"]
    test_rows = [row for row in filtered_rows if str(row.get("split", "")).strip() == "test"]
    if not train_rows:
        raise ValueError("Dataset must contain an explicit train split")

    intent_labels = sorted({str(row["intent"]) for row in filtered_rows})
    missing_train = set(intent_labels) - {str(row["intent"]) for row in train_rows}
    if missing_train:
        raise ValueError(f"No training examples for: {sorted(missing_train)}")
    intent_to_index = {label: index for index, label in enumerate(intent_labels)}

    canonical_texts_by_intent: dict[str, list[str]] = {}
    for row in train_rows:
        intent = str(row["intent"])
        canonical_text = str(row.get("canonical_text") or row.get("text"))
        canonical_texts_by_intent.setdefault(intent, [])
        if canonical_text not in canonical_texts_by_intent[intent]:
            canonical_texts_by_intent[intent].append(canonical_text)

    vectorizer = HashedTextVectorizer(num_features=num_features)
    model = build_network(
        input_dim=num_features,
        output_dim=len(intent_labels),
        hidden_dim=hidden_dim,
        dropout=0.15,
    )
    model_parameters = sum(parameter.numel() for parameter in model.parameters())

    train_texts = [str(row["text"]) for row in train_rows]
    train_targets = [intent_to_index[str(row["intent"])] for row in train_rows]

    features = vectorizer.transform_many(train_texts)
    targets = torch.tensor(train_targets, dtype=torch.long)

    dataset = torch.utils.data.TensorDataset(features, targets)
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)

    def build_eval_tensors(eval_rows: list[dict[str, Any]]):
        if not eval_rows:
            return None, None
        eval_texts = [str(row["text"]) for row in eval_rows]
        eval_target_indexes = [intent_to_index[str(row["intent"])] for row in eval_rows]
        eval_features = vectorizer.transform_many(eval_texts)
        eval_targets = torch.tensor(eval_target_indexes, dtype=torch.long)
        return eval_features, eval_targets

    val_features, val_targets = build_eval_tensors(val_rows)
    test_features, test_targets = build_eval_tensors(test_rows)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

    def evaluate_split(eval_features, eval_targets) -> dict[str, Any] | None:
        if eval_features is None or eval_targets is None or eval_targets.numel() == 0:
            return None
        model.eval()
        with torch.no_grad():
            eval_logits = model(eval_features)
            eval_loss = criterion(eval_logits, eval_targets)
            eval_predicted = eval_logits.argmax(dim=1)
            eval_correct = int((eval_predicted == eval_targets).sum().item())
            eval_total = int(eval_targets.numel())
        predicted_indexes = [int(item) for item in eval_predicted.tolist()]
        target_indexes = [int(item) for item in eval_targets.tolist()]
        confusion_matrix = build_confusion_matrix(
            predicted_indexes=predicted_indexes,
            target_indexes=target_indexes,
            class_count=len(intent_labels),
        )
        return {
            "loss": float(eval_loss.item()),
            "accuracy": eval_correct / max(eval_total, 1),
            "predicted_indexes": predicted_indexes,
            "target_indexes": target_indexes,
            "confusion_matrix": confusion_matrix,
            "macro_f1": macro_f1_from_confusion_matrix(confusion_matrix),
        }

    history: list[dict[str, Any]] = []
    best_val_loss = float("inf")
    best_state = None
    best_epoch = 0
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        correct = 0
        total = 0

        for batch_features, batch_targets in dataloader:
            optimizer.zero_grad()
            logits = model(batch_features)
            loss = criterion(logits, batch_targets)
            loss.backward()
            optimizer.step()

            total_loss += float(loss.item())
            predicted = logits.argmax(dim=1)
            correct += int((predicted == batch_targets).sum().item())
            total += int(batch_targets.numel())

        history.append(
            {
                "epoch": epoch,
                "loss": round(total_loss / max(len(dataloader), 1), 4),
                "accuracy": round(correct / max(total, 1), 4),
            }
        )

        val_metrics = evaluate_split(val_features, val_targets)
        if val_metrics is not None:
            history[-1]["val_loss"] = round(float(val_metrics["loss"]), 4)
            history[-1]["val_accuracy"] = round(float(val_metrics["accuracy"]), 4)
            history[-1]["val_macro_f1"] = round(float(val_metrics["macro_f1"]), 4)
            if float(val_metrics["loss"]) < best_val_loss:
                best_val_loss = float(val_metrics["loss"])
                best_epoch = epoch
                best_state = {
                    name: value.detach().clone() for name, value in model.state_dict().items()
                }

    if best_state is not None:
        model.load_state_dict(best_state)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "intent_labels": intent_labels,
            "canonical_texts_by_intent": canonical_texts_by_intent,
            "num_features": num_features,
            "char_ngram_range": list(vectorizer.char_ngram_range),
            "hidden_dim": hidden_dim,
            "dropout": 0.15,
        },
        output_path,
    )

    test_metrics = evaluate_split(test_features, test_targets)

    summary = {
        "rows": len(filtered_rows),
        "train_rows": len(train_rows),
        "val_rows": len(val_rows),
        "test_rows": len(test_rows),
        "intent_count": len(intent_labels),
        "intent_labels": intent_labels,
        "model_parameters": model_parameters,
        "epochs": epochs,
        "best_epoch": best_epoch or epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "seed": seed,
        "output_path": str(output_path),
        "history": history,
    }
    if test_metrics is not None:
        summary["test_loss"] = round(float(test_metrics["loss"]), 4)
        summary["test_accuracy"] = round(float(test_metrics["accuracy"]), 4)
        summary["test_macro_f1"] = round(float(test_metrics["macro_f1"]), 4)
        summary["test_confusion_matrix"] = test_metrics["confusion_matrix"]
    summary["elapsed_seconds"] = round(time.perf_counter() - started_at, 3)
    return summary


def maybe_load_recovery_model(
    settings: NluSettings, commands: CommandCatalog, project_root: Path
) -> NeuralCommandRecovery | None:
    if not settings.neural_recovery_enabled:
        return None

    model_path = project_root / settings.neural_model_path
    if not model_path.exists():
        return None

    recovery = NeuralCommandRecovery.load(
        model_path=model_path,
        confidence_threshold=settings.neural_confidence,
    )

    fallback_mapping = build_canonical_texts_from_commands(commands)
    for intent, examples in fallback_mapping.items():
        recovery.canonical_texts_by_intent.setdefault(intent, examples)
    return recovery
