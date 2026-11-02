"""Typed models for configuration and runtime structures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    locale: str = "ru-RU"
    mode: str = "push_to_talk"
    hotkey: str = "f9"
    dry_run: bool = True
    single_command_mode: bool = True


class AudioSettings(BaseModel):
    device_index: int | None = None
    channels: int = 1
    sample_rate: int = 16000
    chunk_size: int = 1024
    sample_format: str = "int16"
    max_seconds: int = Field(default=8, ge=1, le=30)
    silence_timeout_ms: int = Field(default=700, ge=200, le=5000)
    silence_threshold: int = Field(default=250, ge=10, le=10000)


class AsrSettings(BaseModel):
    engine: str = "faster-whisper"
    model_name: str = "small"
    model_path: str = "models"
    allow_download: bool = False
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 5
    language: str = "ru"
    vad_filter: bool = True
    condition_on_previous_text: bool = False
    warmup_on_start: bool = False


class NluSettings(BaseModel):
    min_confidence: float = 0.7
    fallback_to_keywords: bool = True
    neural_recovery_enabled: bool = True
    neural_model_path: str = "models/command_recovery.pt"
    neural_confidence: float = 0.65
    semantic_enabled: bool = False
    semantic_model: str = "qwen3:4b"
    semantic_timeout: int = Field(default=30, ge=3, le=120)


class ExecutionSettings(BaseModel):
    require_confirmation_for: list[str] = Field(default_factory=list)
    confirmation_ttl_sec: int = Field(default=15, ge=3, le=120)
    screenshot_dir: str = "artifacts/screenshots"
    allow_shell: bool = False


class GuiSettings(BaseModel):
    theme: str = "system"
    always_on_top: bool = False
    show_transcript: bool = True
    show_intent: bool = True


class PetSettings(BaseModel):
    enabled: bool = True
    size: int = Field(default=160, ge=96, le=280)
    always_on_top: bool = True
    locked: bool = False
    x: int | None = None
    y: int | None = None


class LoggingSettings(BaseModel):
    level: str = "INFO"
    jsonl_path: str = "logs/app.jsonl"
    text_log_path: str = "logs/app.log"


class Settings(BaseModel):
    app: AppSettings = Field(default_factory=AppSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    asr: AsrSettings = Field(default_factory=AsrSettings)
    nlu: NluSettings = Field(default_factory=NluSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    gui: GuiSettings = Field(default_factory=GuiSettings)
    pet: PetSettings = Field(default_factory=PetSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


class CommandSpec(BaseModel):
    intent: str
    action: str
    dangerous: bool = False
    examples: list[str]


class CommandCatalog(BaseModel):
    intents: list[CommandSpec]


class AppEntry(BaseModel):
    aliases: list[str]
    launch: list[str]


class FolderEntry(BaseModel):
    aliases: list[str]
    path: str


class SystemCommandEntry(BaseModel):
    launch: list[str]


class AppsCatalog(BaseModel):
    applications: dict[str, AppEntry]
    folders: dict[str, FolderEntry]
    system_commands: dict[str, SystemCommandEntry] = Field(default_factory=dict)


class IntentMatch(BaseModel):
    text: str
    normalized_text: str
    intent: str | None
    action: str | None
    confidence: float
    slots: dict[str, Any] = Field(default_factory=dict)
    dangerous: bool = False
    matched_example: str | None = None
    corrected_text: str | None = None
    correction_confidence: float | None = None


class CommandResult(BaseModel):
    success: bool
    status: str
    message: str
    intent: str | None = None
    action: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)


class ResolvedConfig(BaseModel):
    settings: Settings
    commands: CommandCatalog
    apps: AppsCatalog
    project_root: Path
    user_dir: Path | None = None
