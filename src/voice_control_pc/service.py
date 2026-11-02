"""High-level command processing service."""

from __future__ import annotations

from voice_control_pc.executor import SafeCommandExecutor
from voice_control_pc.ml.command_recovery import maybe_load_recovery_model
from voice_control_pc.models import CommandResult, ResolvedConfig
from voice_control_pc.nlu import RuleBasedNLU, is_actionable_text


class VoiceControlService:
    def __init__(self, config: ResolvedConfig, dry_run: bool | None = None):
        effective_dry_run = config.settings.app.dry_run if dry_run is None else dry_run
        self.nlu = RuleBasedNLU(
            commands=config.commands,
            apps=config.apps,
            min_confidence=config.settings.nlu.min_confidence,
        )
        self.recovery = maybe_load_recovery_model(
            settings=config.settings.nlu,
            commands=config.commands,
            project_root=config.project_root,
        )
        self.executor = SafeCommandExecutor(
            apps=config.apps,
            settings=config.settings.execution,
            project_root=config.project_root,
            dry_run=effective_dry_run,
        )

    def process_text_command(self, text: str, confirmed: bool = False) -> tuple[dict, CommandResult]:
        initial_match = self.nlu.match(text)
        if self.recovery is not None and initial_match.intent is None and is_actionable_text(text):
            recovered_match = self.recovery.enhance_match(text, initial_match)
            recovered_text = recovered_match.corrected_text or text
            match = self.nlu.match(recovered_text)
            # A recovered class must agree with the executable command and its slots.
            if recovered_match.intent != match.intent:
                match = self.nlu.match("")
            match.text = text
            match.normalized_text = initial_match.normalized_text
            match.corrected_text = recovered_match.corrected_text
            match.correction_confidence = recovered_match.correction_confidence
        else:
            match = initial_match
        result = self.executor.execute(match, confirmed=confirmed)
        return match.model_dump(), result
