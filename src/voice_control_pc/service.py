"""Command interpretation and expiring, single-use confirmation of a specific action."""

from __future__ import annotations

import time
import uuid

from voice_control_pc.executor import SafeCommandExecutor
from voice_control_pc.ml.command_recovery import maybe_load_recovery_model
from voice_control_pc.models import CommandResult, ResolvedConfig
from voice_control_pc.nlu import RuleBasedNLU, is_actionable_text


class VoiceControlService:
    def __init__(self, config: ResolvedConfig, dry_run: bool | None = None):
        self.config = config
        self.nlu = RuleBasedNLU(config.commands, config.apps, config.settings.nlu.min_confidence)
        self.recovery_error = ""
        try:
            self.recovery = maybe_load_recovery_model(
                config.settings.nlu, config.commands, config.project_root
            )
        except Exception as error:
            self.recovery = None
            self.recovery_error = str(error)
        self.executor = SafeCommandExecutor(
            config.apps,
            config.settings.execution,
            config.project_root,
            config.settings.app.dry_run if dry_run is None else dry_run,
        )
        self._pending = None

    def process_text_command(
        self, text: str, confirmed: bool = False
    ) -> tuple[dict, CommandResult]:
        # A new request invalidates any earlier confirmation. The legacy boolean
        # cannot pre-authorize an action that has not yet been interpreted.
        self.cancel_pending()
        initial_match = self.nlu.match(text)
        if self.recovery is not None and initial_match.intent is None and is_actionable_text(text):
            recovered = self.recovery.enhance_match(text, initial_match.model_copy(deep=True))
            match = self.nlu.match(recovered.corrected_text or text)
            if recovered.intent != match.intent:
                match = self.nlu.match("")
            match.text = text
            match.normalized_text = initial_match.normalized_text
            match.corrected_text = recovered.corrected_text
            match.correction_confidence = recovered.correction_confidence
            if match.intent is not None and match.corrected_text:
                match.dangerous = True
        else:
            match = initial_match
        if (
            match.intent is None
            and is_actionable_text(text)
            and self.config.settings.nlu.semantic_enabled
        ):
            from voice_control_pc.semantic import interpret_local

            try:
                match = interpret_local(text, self.config)
            except Exception as error:
                result = CommandResult(
                    success=False,
                    status="model_unavailable",
                    message=f"Модель понимания недоступна: {error}",
                )
                return match.model_dump(), result
        result = self.executor.execute(match)
        if result.status == "confirmation_required":
            token = uuid.uuid4().hex
            self._pending = (
                token,
                time.monotonic(),
                match.model_copy(deep=True),
                self.executor.dry_run,
            )
            result.artifacts["confirmation_token"] = token
        return match.model_dump(), result

    def confirm_command(self, token: str) -> CommandResult:
        pending, self._pending = self._pending, None
        if pending is None or pending[0] != token:
            return CommandResult(
                success=False,
                status="confirmation_invalid",
                message="Подтверждение недействительно. Повторите команду.",
            )
        if time.monotonic() - pending[1] > self.config.settings.execution.confirmation_ttl_sec:
            return CommandResult(
                success=False,
                status="confirmation_expired",
                message="Время подтверждения истекло. Повторите команду.",
            )
        if pending[3] != self.executor.dry_run:
            return CommandResult(
                success=False,
                status="confirmation_invalid",
                message="Режим выполнения изменился. Повторите команду.",
            )
        return self.executor.execute(pending[2], confirmed=True)

    def cancel_pending(self) -> None:
        self._pending = None
