"""Read-only Windows discovery. No registry changes, program launches or folder creation."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path, PureWindowsPath
from uuid import UUID

from voice_control_pc.models import AppsCatalog

KNOWN_FOLDERS = {
    "загрузки": "374DE290-123F-4565-9164-39C4925E467B",
    "документы": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "рабочий_стол": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "изображения": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "видео": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}
PROGRAMS = {
    "блокнот": "notepad.exe",
    "калькулятор": "calc.exe",
    "проводник": "explorer.exe",
    "telegram": "Telegram.exe",
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "after_effects": "AfterFX.exe",
}


class GUID(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]


def _known_folder_path(identifier: str) -> str:
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    ole = ctypes.WinDLL("ole32", use_last_error=True)
    query = shell.SHGetKnownFolderPath
    query.argtypes = [
        ctypes.POINTER(GUID),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    query.restype = ctypes.c_int32
    free = ole.CoTaskMemFree
    free.argtypes, free.restype = [ctypes.c_void_p], None
    guid = GUID.from_buffer_copy(UUID(identifier).bytes_le)
    pointer = ctypes.c_void_p()
    try:
        status = query(ctypes.byref(guid), 0, None, ctypes.byref(pointer))
        if status != 0 or not pointer.value:
            raise OSError(f"SHGetKnownFolderPath: HRESULT 0x{status & 0xFFFFFFFF:08x}")
        return ctypes.wstring_at(pointer)
    finally:
        if pointer.value:
            free(pointer)


def known_folder(name: str) -> str | None:
    if sys.platform != "win32" or name not in KNOWN_FOLDERS:
        return None
    try:
        return _known_folder_path(KNOWN_FOLDERS[name])
    except (OSError, ValueError):
        return None


def _browser_executable() -> str | None:
    query = ctypes.WinDLL("shlwapi", use_last_error=True).AssocQueryStringW
    query.argtypes = [
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    query.restype = ctypes.c_int32
    length = ctypes.c_uint32()
    # ASSOCF_IS_PROTOCOL | ASSOCF_NOTRUNCATE, ASSOCSTR_EXECUTABLE.
    flags = 0x1000 | 0x20
    query(flags, 2, "https", "open", None, ctypes.byref(length))
    if not 1 < length.value <= 32768:
        return None
    buffer = ctypes.create_unicode_buffer(length.value)
    if query(flags, 2, "https", "open", buffer, ctypes.byref(length)) != 0:
        return None
    return buffer.value or None


def _registered_executable(executable: str) -> str | None:
    import winreg

    subkey = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{executable}"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ | view) as key:
                    value, kind = winreg.QueryValueEx(key, "")
                if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and isinstance(value, str):
                    path = os.path.expandvars(value).strip().strip('"')
                    if Path(path).is_file():
                        return path
            except OSError:
                continue
    return None


def find_application(name: str, current: str = "") -> str | None:
    if sys.platform != "win32":
        return None
    if name == "браузер":
        try:
            path = _browser_executable()
            return path if path and Path(path).is_file() else None
        except OSError:
            return None
    executable = PROGRAMS.get(name) or PureWindowsPath(current).name
    if not executable.lower().endswith(".exe"):
        return None
    registered = _registered_executable(executable)
    if registered:
        return registered
    # PATH is trusted configuration, but do not discover executables in the current directory.
    search_path = os.pathsep.join(
        p for p in os.environ.get("PATH", "").split(os.pathsep) if p and Path(p).is_absolute()
    )
    for directory in search_path.split(os.pathsep):
        if directory:
            candidate = Path(directory) / executable
            if candidate.is_file():
                return str(candidate)
    if executable.lower() == "telegram.exe" and os.environ.get("APPDATA"):
        candidate = Path(os.environ["APPDATA"]) / "Telegram Desktop" / "Telegram.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def discover_defaults(catalog: AppsCatalog) -> AppsCatalog:
    """Seed a fresh default catalog; callers must not pass saved user preferences."""
    discovered = catalog.model_copy(deep=True)
    for name, item in discovered.folders.items():
        path = known_folder(name)
        if path:
            item.path = path
    for name, item in discovered.applications.items():
        path = find_application(name, item.launch[0] if item.launch else "")
        if path:
            item.launch = [path, *item.launch[1:]]
    return discovered
