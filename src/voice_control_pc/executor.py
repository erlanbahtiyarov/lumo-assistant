"""Safe allowlist-based command executor."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from voice_control_pc.models import AppsCatalog, CommandResult, ExecutionSettings, IntentMatch


class ConfirmationRequiredError(RuntimeError):
    """Raised when a dangerous action requires explicit confirmation."""


class SafeCommandExecutor:
    def __init__(
        self, apps: AppsCatalog, settings: ExecutionSettings, project_root: Path, dry_run: bool
    ):
        self.apps = apps
        self.settings = settings
        self.project_root = project_root
        self.dry_run = dry_run

    def execute(self, match: IntentMatch, confirmed: bool = False) -> CommandResult:
        if not match.intent or not match.action:
            return CommandResult(
                success=False,
                status="no_match",
                message="Команда не распознана",
            )

        if (
            match.dangerous
            or match.action
            in {"shutdown_pc", "restart_pc", *self.settings.require_confirmation_for}
        ) and not confirmed:
            return CommandResult(
                success=False,
                status="confirmation_required",
                message=f"Для команды {match.action} требуется подтверждение",
                intent=match.intent,
                action=match.action,
            )

        handler_name = f"_handle_{match.action}"
        handler = getattr(self, handler_name, None)
        if handler is None:
            return CommandResult(
                success=False,
                status="unsupported_action",
                message=f"Нет обработчика для действия {match.action}",
                intent=match.intent,
                action=match.action,
            )
        if not self.dry_run and sys.platform != "win32":
            return CommandResult(
                success=False,
                status="unsupported_platform",
                message="Реальное выполнение пока поддерживается только в Windows",
                intent=match.intent,
                action=match.action,
            )
        try:
            return handler(match)
        except Exception as error:
            return CommandResult(
                success=False,
                status="execution_error",
                message=str(error),
                intent=match.intent,
                action=match.action,
            )

    def _handle_open_app(self, match: IntentMatch) -> CommandResult:
        app_name = match.slots.get("app_name")
        if not app_name or app_name not in self.apps.applications:
            return CommandResult(
                success=False,
                status="missing_slot",
                message="Не удалось определить приложение",
                intent=match.intent,
                action=match.action,
            )
        entry = self.apps.applications[app_name]
        launch = entry.launch
        if entry.auto_detect and not launch:
            if self.dry_run:
                return CommandResult(
                    success=True,
                    status="dry_run",
                    message="[dry-run] Системный браузер Windows",
                    intent=match.intent,
                    action=match.action,
                )
            raise FileNotFoundError(
                "Не удалось определить браузер. Выберите его путь в настройках приложений."
            )
        return self._run_process(launch, f"Запущено приложение: {app_name}", match)

    def _handle_open_folder(self, match: IntentMatch) -> CommandResult:
        folder_name = match.slots.get("folder_name")
        if not folder_name or folder_name not in self.apps.folders:
            return CommandResult(
                success=False,
                status="missing_slot",
                message="Не удалось определить папку",
                intent=match.intent,
                action=match.action,
            )
        folder_path = Path(
            os.path.expandvars(os.path.expanduser(self.apps.folders[folder_name].path))
        )
        if self.dry_run:
            return CommandResult(
                success=True,
                status="dry_run",
                message=f"[dry-run] Открытие папки: {folder_path}",
                intent=match.intent,
                action=match.action,
            )
        if not folder_path.is_dir():
            raise FileNotFoundError(f"Папка не найдена: {folder_path}")
        os.startfile(folder_path)
        return CommandResult(
            success=True,
            status="success",
            message=f"Открыта папка: {folder_path}",
            intent=match.intent,
            action=match.action,
        )

    def _handle_take_screenshot(self, match: IntentMatch) -> CommandResult:
        screenshot_dir = self.project_root / self.settings.screenshot_dir
        screenshot_path = screenshot_dir / f"screenshot_{datetime.now():%Y%m%d_%H%M%S_%f}.png"
        if self.dry_run:
            return CommandResult(
                success=True,
                status="dry_run",
                message=f"[dry-run] Скриншот будет сохранен в {screenshot_path}",
                intent=match.intent,
                action=match.action,
                artifacts={"screenshot_path": str(screenshot_path)},
            )

        import pyautogui

        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot = pyautogui.screenshot()
        screenshot.save(screenshot_path)
        return CommandResult(
            success=True,
            status="success",
            message=f"Скриншот сохранен: {screenshot_path}",
            intent=match.intent,
            action=match.action,
            artifacts={"screenshot_path": str(screenshot_path)},
        )

    def _handle_close_window(self, match: IntentMatch) -> CommandResult:
        if not self.dry_run:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.GetWindowThreadProcessId.argtypes = [
                wintypes.HWND,
                ctypes.POINTER(wintypes.DWORD),
            ]
            pid = wintypes.DWORD()
            foreground = user32.GetForegroundWindow()
            user32.GetWindowThreadProcessId(foreground, ctypes.byref(pid))
            if pid.value == os.getpid():
                raise RuntimeError("Переключись в нужное окно и вызови команду горячей клавишей")
        return self._run_pyautogui_hotkey(("alt", "f4"), "Активное окно закрыто", match)

    def _handle_show_desktop(self, match: IntentMatch) -> CommandResult:
        return self._run_pyautogui_hotkey(("win", "d"), "Показан рабочий стол", match)

    def _handle_open_task_manager(self, match: IntentMatch) -> CommandResult:
        return self._run_process(
            self.apps.system_commands["task_manager"].launch,
            "Открыт диспетчер задач",
            match,
        )

    def _handle_open_settings(self, match: IntentMatch) -> CommandResult:
        return self._run_process(
            self.apps.system_commands["settings"].launch,
            "Открыты настройки",
            match,
        )

    def _handle_open_terminal(self, match: IntentMatch) -> CommandResult:
        return self._run_process(
            self.apps.system_commands["terminal"].launch,
            "Открыт терминал",
            match,
        )

    def _handle_lock_pc(self, match: IntentMatch) -> CommandResult:
        return self._run_process(
            ["rundll32.exe", "user32.dll,LockWorkStation"],
            "Компьютер заблокирован",
            match,
        )

    def _handle_shutdown_pc(self, match: IntentMatch) -> CommandResult:
        return self._run_process(["shutdown", "/s", "/t", "0"], "Компьютер выключается", match)

    def _handle_restart_pc(self, match: IntentMatch) -> CommandResult:
        return self._run_process(["shutdown", "/r", "/t", "0"], "Компьютер перезагружается", match)

    def _run_process(self, command: list[str], message: str, match: IntentMatch) -> CommandResult:
        if not command or not command[0].strip():
            raise ValueError("Укажите путь к приложению в настройках")
        command = [os.path.expandvars(os.path.expanduser(command[0])), *command[1:]]
        if self.dry_run:
            return CommandResult(
                success=True,
                status="dry_run",
                message=f"[dry-run] {' '.join(command)}",
                intent=match.intent,
                action=match.action,
            )
        subprocess.Popen(command, shell=False)
        return CommandResult(
            success=True,
            status="success",
            message=message,
            intent=match.intent,
            action=match.action,
        )

    def _run_pyautogui_hotkey(
        self, hotkey: tuple[str, ...], message: str, match: IntentMatch
    ) -> CommandResult:
        if self.dry_run:
            return CommandResult(
                success=True,
                status="dry_run",
                message=f"[dry-run] hotkey={' + '.join(hotkey)}",
                intent=match.intent,
                action=match.action,
            )

        import pyautogui

        pyautogui.hotkey(*hotkey)
        return CommandResult(
            success=True,
            status="success",
            message=message,
            intent=match.intent,
            action=match.action,
        )
