"""ASR integration layer."""

from __future__ import annotations

from pathlib import Path

from voice_control_pc.models import AsrSettings


class FasterWhisperTranscriber:
    def __init__(self, settings: AsrSettings):
        self.settings = settings
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError(
                'Установите голосовой компонент: pip install "lumo-assistant[voice]"'
            ) from error

        try:
            self._model = WhisperModel(
                self.settings.model_name,
                device=self.settings.device,
                compute_type=self.settings.compute_type,
                download_root=self.settings.model_path,
                local_files_only=not self.settings.allow_download,
            )
        except Exception as error:
            hint = (
                "Разрешите загрузку в настройках «Модели» или укажите локальную модель. "
                if not self.settings.allow_download
                else ""
            )
            raise RuntimeError(
                f"Не удалось загрузить модель {self.settings.model_name}. {hint}{error}"
            ) from error

    def transcribe_file(self, audio_path: Path) -> str:
        self.load()
        assert self._model is not None
        segments, _info = self._model.transcribe(
            str(audio_path),
            beam_size=self.settings.beam_size,
            language=self.settings.language,
            vad_filter=self.settings.vad_filter,
            condition_on_previous_text=self.settings.condition_on_previous_text,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
