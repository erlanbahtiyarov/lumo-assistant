"""Readiness checks shared by the CLI and native UI. Never executes a command or records audio."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from voice_control_pc.audio import list_input_devices
from voice_control_pc.config import resolved_asr_settings
from voice_control_pc.models import ResolvedConfig
from voice_control_pc.semantic import NoRedirect


@dataclass(frozen=True)
class Check:
    key: str
    title: str
    status: str
    detail: str
    hint: str = ""
    diagnostic: str = ""

    def as_dict(self):
        return asdict(self)


def component_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def executable_available(command: list[str]) -> bool:
    if not command or not command[0].strip():
        return False
    executable = os.path.expandvars(os.path.expanduser(command[0]))
    if Path(executable).is_absolute():
        return Path(executable).is_file()
    # A bare configured command can be resolved on PATH, without launching it.
    return shutil.which(executable) is not None


def local_asr_directory(config: ResolvedConfig) -> Path:
    settings = resolved_asr_settings(config)
    direct = Path(settings.model_name).expanduser()
    if direct.is_dir():
        return direct
    from faster_whisper.utils import download_model

    return Path(
        download_model(settings.model_name, cache_dir=settings.model_path, local_files_only=True)
    )


def ollama_models() -> set[str]:
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open("http://127.0.0.1:11434/api/tags", timeout=2) as response:
        raw = response.read(128 * 1024 + 1)
    if len(raw) > 128 * 1024:
        raise ValueError("Слишком большой ответ Ollama")
    payload = json.loads(raw)
    return {item["name"] for item in payload["models"] if isinstance(item.get("name"), str)}


def check_readiness(config: ResolvedConfig, *, microphone=False, ollama=False) -> list[Check]:
    checks = []
    checks.append(
        Check(
            "platform",
            "Действия на компьютере",
            "ok" if sys.platform == "win32" else "info",
            "Windows поддерживается."
            if sys.platform == "win32"
            else "В Linux пока доступны интерфейс, распознавание и проверочный режим.",
        )
    )
    checks.append(
        Check(
            "mode",
            "Режим работы",
            "info",
            "Команды проверяются без выполнения."
            if config.settings.app.dry_run
            else "Выполнение действий включено.",
        )
    )
    root = config.user_dir or config.project_root
    parent = root
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    writable = parent.is_dir() and os.access(parent, os.W_OK)
    checks.append(
        Check(
            "profile",
            "Настройки и история",
            "ok" if writable else "error",
            str(root),
            "" if writable else "Проверь, доступна ли эта папка для сохранения настроек.",
        )
    )
    for name, entry in config.apps.applications.items():
        if sys.platform != "win32":
            continue
        found = executable_available(entry.launch)
        checks.append(
            Check(
                f"app:{name}",
                f"Приложение: {name}",
                "ok" if found else "warning",
                entry.launch[0] if entry.launch else "Путь не определён.",
                ""
                if found
                else "Настройки → Приложения: выбери строку и нажми «Найти в Windows» или укажи путь.",
            )
        )
    for name, entry in config.apps.folders.items():
        path = Path(os.path.expandvars(os.path.expanduser(entry.path)))
        found = path.is_dir()
        checks.append(
            Check(
                f"folder:{name}",
                f"Папка: {name.replace('_', ' ')}",
                "ok" if found else "warning",
                str(path),
                ""
                if found
                else "Настройки → Папки: найди системную папку или выбери путь вручную.",
            )
        )
    voice = component_available("faster_whisper")
    audio = component_available("pyaudio")
    checks.append(
        Check(
            "voice",
            "Голосовой компонент",
            "ok" if voice and audio else "warning",
            "Компоненты распознавания и микрофона установлены."
            if voice and audio
            else "Не хватает faster-whisper или PyAudio. Текстовые команды доступны.",
            ""
            if voice and audio
            else "Установи версию Лумо с голосовым компонентом или используй текстовые команды.",
        )
    )
    if voice:
        try:
            directory = local_asr_directory(config)
            required = ("model.bin", "config.json", "tokenizer.json")
            missing = [
                name
                for name in required
                if not (directory / name).is_file() or not (directory / name).stat().st_size
            ]
            if missing:
                raise ValueError("Не хватает файлов: " + ", ".join(missing))
            checks.append(
                Check(
                    "asr",
                    "Модель распознавания",
                    "ok",
                    f"Файлы {config.settings.asr.model_name} найдены: {directory}",
                    "Загрузка модели и качество речи проверяются при записи команды.",
                )
            )
        except Exception as error:
            hint = (
                "Загрузка разрешена: модель будет подготовлена при первой записи."
                if config.settings.asr.allow_download
                else "Настройки → Модели: разреши загрузку или укажи локальную модель."
            )
            checks.append(
                Check(
                    "asr",
                    "Модель распознавания",
                    "warning",
                    str(error)
                    if isinstance(error, ValueError) and str(error).startswith("Не хватает файлов:")
                    else f"Файлы модели «{config.settings.asr.model_name}» не найдены в локальном хранилище.",
                    hint,
                    diagnostic=str(error),
                )
            )
    if microphone and audio:
        try:
            devices = list_input_devices()
            selected = config.settings.audio.device_index
            if not devices:
                raise ValueError("Устройства ввода не найдены.")
            if selected is not None and not any(item["index"] == selected for item in devices):
                raise ValueError(f"Выбранный микрофон {selected} больше не доступен.")
            checks.append(
                Check(
                    "microphone",
                    "Микрофон",
                    "ok",
                    f"Доступно устройств ввода: {len(devices)}. Запись не включалась.",
                    "Проверь звук командой через кнопку «Слушать команду».",
                )
            )
        except Exception as error:
            checks.append(
                Check(
                    "microphone",
                    "Микрофон",
                    "warning",
                    str(error)
                    if isinstance(error, ValueError)
                    else "Не удалось получить список микрофонов.",
                    "Проверь подключение и разрешения Windows; затем выбери устройство в настройках.",
                    diagnostic=str(error),
                )
            )
    if config.settings.nlu.semantic_enabled:
        if ollama:
            try:
                names = ollama_models()
                name = config.settings.nlu.semantic_model
                target = name if ":" in name else name + ":latest"
                found = target in names
                checks.append(
                    Check(
                        "ollama",
                        "Понимание свободных команд",
                        "ok" if found else "warning",
                        f"Ollama доступен. Модель {name}: {'найдена' if found else 'не найдена'}.",
                        "" if found else f"Подготовь модель: ollama pull {name}",
                    )
                )
            except Exception as error:
                checks.append(
                    Check(
                        "ollama",
                        "Понимание свободных команд",
                        "warning",
                        "Локальный сервис Ollama недоступен или вернул некорректный ответ.",
                        "Запусти Ollama с выбранной моделью или отключи его в настройках моделей.",
                        diagnostic=str(error),
                    )
                )
        else:
            checks.append(
                Check(
                    "ollama",
                    "Понимание свободных команд",
                    "info",
                    "Ollama включён. Сервис не опрашивался.",
                    "Проверка сервиса доступна через doctor --ollama или кнопку проверки в приложении.",
                )
            )
    else:
        checks.append(
            Check(
                "ollama",
                "Понимание свободных команд",
                "info",
                "Локальная языковая модель отключена. Правила доступны.",
            )
        )
    return checks
