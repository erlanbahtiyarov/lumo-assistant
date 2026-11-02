"""Rule-based NLU for Russian desktop commands."""

from __future__ import annotations

import re
from collections.abc import Iterable

from voice_control_pc.models import (
    AppsCatalog,
    CommandCatalog,
    CommandSpec,
    IntentMatch,
)


def normalize_text(text: str) -> str:
    normalized = text.lower().replace("ё", "е").strip()
    normalized = re.sub(r"[^\w\s-]", " ", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def token_overlap_score(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return intersection / union


def is_actionable_text(text: str) -> bool:
    """Conservatively reject empty, negated and compound requests before recovery."""
    words = normalize_text(text).split()
    blocked = {"не", "нет", "нельзя", "отмена", "отмени", "потом", "затем", "и", "или"}
    verbs = {
        "открой",
        "запусти",
        "покажи",
        "сделай",
        "сохрани",
        "закрой",
        "сверни",
        "заблокируй",
        "выключи",
        "заверши",
        "перезагрузи",
        "перезапусти",
    }
    return (
        len(words) >= 2
        and not blocked.intersection(words)
        and sum(word in verbs for word in words) <= 1
    )


class RuleBasedNLU:
    def __init__(self, commands: CommandCatalog, apps: AppsCatalog, min_confidence: float = 0.7):
        self.commands = commands
        self.apps = apps
        self.min_confidence = min_confidence

    def match(self, text: str) -> IntentMatch:
        normalized_text = normalize_text(text)
        rejected = IntentMatch(
            text=text, normalized_text=normalized_text, intent=None, action=None, confidence=0.0
        )
        if not is_actionable_text(text):
            return rejected
        normalized_text = " ".join(
            word for word in normalized_text.split() if word not in {"пожалуйста"}
        )
        best_spec: CommandSpec | None = None
        best_example: str | None = None
        best_score = 0.0

        # Resolve objects independently of the opening verb; reject alias collisions.
        opening = re.fullmatch(r"(?:открой|запусти|покажи) (.+)", normalized_text)
        if opening:
            target = opening.group(1)
            folder_target = re.sub(r"^папк[ауи] ", "", target)
            candidates = []
            for intent, aliases, slot in (
                ("open_app", self._iter_app_aliases(), "app_name"),
                ("open_folder", self._iter_folder_aliases(), "folder_name"),
            ):
                if intent == "open_app" and folder_target != target:
                    continue
                names = {name for alias, name in aliases if alias in {target, folder_target}}
                spec = next((item for item in self.commands.intents if item.intent == intent), None)
                if spec is not None:
                    candidates.extend((spec, {slot: name}) for name in sorted(names))
            for spec in self.commands.intents:
                if spec.intent not in {"open_task_manager", "open_settings", "open_terminal"}:
                    continue
                targets = {normalize_text(example).split(" ", 1)[-1] for example in spec.examples}
                if target in targets:
                    candidates.append((spec, {}))
            if len(candidates) > 1:
                return rejected
            if candidates:
                spec, slots = candidates[0]
                return IntentMatch(
                    text=text,
                    normalized_text=normalized_text,
                    intent=spec.intent,
                    action=spec.action,
                    confidence=1.0,
                    slots=slots,
                    dangerous=spec.dangerous,
                )

        for spec in self.commands.intents:
            for example in spec.examples:
                normalized_example = normalize_text(example)
                score = self._score(normalized_text, normalized_example)
                if score > best_score:
                    best_score = score
                    best_spec = spec
                    best_example = example

        if not best_spec or best_score < self.min_confidence:
            return IntentMatch(
                text=text,
                normalized_text=normalized_text,
                intent=None,
                action=None,
                confidence=best_score,
                slots={},
                dangerous=False,
                matched_example=best_example,
            )

        slots = self._extract_slots(best_spec.intent, normalized_text)
        required_slot = {"open_app": "app_name", "open_folder": "folder_name"}.get(best_spec.intent)
        if required_slot and required_slot not in slots:
            return rejected
        return IntentMatch(
            text=text,
            normalized_text=normalized_text,
            intent=best_spec.intent,
            action=best_spec.action,
            confidence=best_score,
            slots=slots,
            dangerous=best_spec.dangerous,
            matched_example=best_example,
        )

    def _score(self, normalized_text: str, normalized_example: str) -> float:
        if not normalized_text or len(normalized_text.split()) < 2:
            return 0.0
        if normalized_text == normalized_example:
            return 1.0
        if normalized_text.split()[0] != normalized_example.split()[0]:
            return 0.0
        return token_overlap_score(normalized_text, normalized_example)

    def _extract_slots(self, intent: str, normalized_text: str) -> dict[str, str]:
        slots: dict[str, str] = {}
        if intent == "open_app":
            app_name = self._find_alias(normalized_text, self._iter_app_aliases())
            if app_name:
                slots["app_name"] = app_name
        elif intent == "open_folder":
            folder_name = self._find_alias(normalized_text, self._iter_folder_aliases())
            if folder_name:
                slots["folder_name"] = folder_name
        elif intent == "take_screenshot":
            if "главного экрана" in normalized_text:
                slots["screen_area"] = "главного экрана"
            elif "экрана" in normalized_text:
                slots["screen_area"] = "экрана"
        return slots

    def _iter_app_aliases(self) -> Iterable[tuple[str, str]]:
        for canonical_name, entry in self.apps.applications.items():
            for alias in entry.aliases:
                yield normalize_text(alias), canonical_name

    def _iter_folder_aliases(self) -> Iterable[tuple[str, str]]:
        for canonical_name, entry in self.apps.folders.items():
            for alias in entry.aliases:
                yield normalize_text(alias), canonical_name

    def _find_alias(self, normalized_text: str, aliases: Iterable[tuple[str, str]]) -> str | None:
        best_name: str | None = None
        best_length = -1
        for alias, canonical_name in aliases:
            if f" {alias} " in f" {normalized_text} " and len(alias) > best_length:
                best_name = canonical_name
                best_length = len(alias)
        return best_name
