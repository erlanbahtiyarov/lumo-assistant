"""Packaged defaults and atomic per-user preferences, independent of the working directory."""

from __future__ import annotations

import os
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from voice_control_pc.models import AppsCatalog, CommandCatalog, ResolvedConfig, Settings


def user_data_dir() -> Path:
    if os.environ.get("LUMO_HOME"):
        return Path(os.environ["LUMO_HOME"]).expanduser().resolve()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Lumo"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "lumo"


def load_yaml_file(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")
    return payload


def resolve_project_root(explicit_root: Path | None = None) -> Path:
    return explicit_root.resolve() if explicit_root is not None else user_data_dir()


def _merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        result[key] = (
            _merge(result[key], value)
            if isinstance(value, dict) and isinstance(result.get(key), dict)
            else value
        )
    return result


def _default(name: str, root: Path | None) -> dict:
    if root is not None and (root / "configs" / name).is_file():
        return load_yaml_file(root / "configs" / name)
    return yaml.safe_load(files("voice_control_pc.resources").joinpath(name).read_text("utf-8"))


def load_config_bundle(project_root: Path | None = None) -> ResolvedConfig:
    root = resolve_project_root(project_root)
    settings = _default("default.yaml", project_root)
    if (root / "settings.yaml").is_file():
        settings = _merge(settings, load_yaml_file(root / "settings.yaml"))
    apps = _default("apps.yaml", project_root)
    if (root / "apps.yaml").is_file():
        apps = load_yaml_file(root / "apps.yaml")
    return ResolvedConfig(
        settings=Settings.model_validate(settings),
        commands=CommandCatalog.model_validate(_default("commands.yaml", project_root)),
        apps=AppsCatalog.model_validate(apps),
        project_root=root,
        user_dir=root,
    )


def _atomic_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), "utf-8")
    temporary.replace(path)


def save_preferences(config: ResolvedConfig) -> None:
    root = config.user_dir or config.project_root
    _atomic_yaml(root / "settings.yaml", config.settings.model_dump())
    _atomic_yaml(root / "apps.yaml", config.apps.model_dump())


def resolved_asr_settings(config: ResolvedConfig):
    settings = config.settings.asr.model_copy(deep=True)
    path = Path(settings.model_path).expanduser()
    settings.model_path = str(path if path.is_absolute() else config.project_root / path)
    return settings
