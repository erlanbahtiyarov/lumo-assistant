import ctypes
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest

from voice_control_pc import windows
from voice_control_pc.config import load_config_bundle, save_preferences
from voice_control_pc.models import AppEntry


def test_known_folder_uses_unicode_guid_and_releases_memory(monkeypatch):
    buffer = ctypes.create_unicode_buffer("D:/OneDrive/Документы")

    def query(guid, flags, token, output):
        assert ctypes.string_at(guid, 16) == UUID(windows.KNOWN_FOLDERS["документы"]).bytes_le
        assert flags == 0 and token is None
        output._obj.value = ctypes.addressof(buffer)
        return 0

    free = Mock()
    dlls = {
        "shell32": SimpleNamespace(SHGetKnownFolderPath=Mock(side_effect=query)),
        "ole32": SimpleNamespace(CoTaskMemFree=free),
    }
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **kwargs: dlls[name], raising=False)
    assert windows._known_folder_path(windows.KNOWN_FOLDERS["документы"]) == buffer.value
    free.assert_called_once()


def test_known_folder_failure_also_releases_allocated_memory(monkeypatch):
    buffer = ctypes.create_unicode_buffer("unused")

    def query(guid, flags, token, output):
        output._obj.value = ctypes.addressof(buffer)
        return -1

    free = Mock()
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda name, **kw: SimpleNamespace(
            SHGetKnownFolderPath=Mock(side_effect=query), CoTaskMemFree=free
        ),
        raising=False,
    )
    with pytest.raises(OSError):
        windows._known_folder_path(windows.KNOWN_FOLDERS["загрузки"])
    free.assert_called_once()


def test_default_browser_protocol_lookup_respects_two_pass_buffer(monkeypatch):
    expected = "C:/Program Files/Browser/browser.exe"

    def query(flags, kind, protocol, verb, output, length):
        assert flags & 0x1000 and kind == 2 and protocol == "https"
        if output is None:
            length._obj.value = len(expected) + 1
            return 1
        output.value = expected
        return 0

    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *args, **kw: SimpleNamespace(AssocQueryStringW=Mock(side_effect=query)),
        raising=False,
    )
    assert windows._browser_executable() == expected


def test_detection_does_not_pick_a_different_browser_when_default_is_missing(monkeypatch):
    monkeypatch.setattr(windows.sys, "platform", "win32")
    monkeypatch.setattr(windows, "_browser_executable", lambda: None)
    assert windows.find_application("браузер", "chrome.exe") is None


def test_registered_program_takes_precedence_over_path(monkeypatch, tmp_path):
    program = tmp_path / "Telegram.exe"
    program.touch()
    monkeypatch.setattr(windows.sys, "platform", "win32")
    monkeypatch.setattr(windows, "_registered_executable", lambda name: str(program))
    assert windows.find_application("telegram") == str(program)


def test_discovery_seeds_fresh_profiles_but_keeps_saved_manual_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(windows.sys, "platform", "win32")
    monkeypatch.setattr(windows, "known_folder", lambda name: f"D:/Moved/{name}")
    monkeypatch.setattr(
        windows, "find_application", lambda name, current="": f"C:/Installed/{name}.exe"
    )
    config = load_config_bundle(tmp_path)
    assert config.apps.folders["документы"].path == "D:/Moved/документы"
    assert config.apps.applications["браузер"].launch == ["C:/Installed/браузер.exe"]
    config.apps.folders["документы"].path = "E:/My documents"
    config.apps.applications["браузер"] = AppEntry(
        aliases=["браузер"], launch=["E:/Custom/browser.exe", "--custom"]
    )
    save_preferences(config)
    restored = load_config_bundle(tmp_path)
    assert restored.apps.folders["документы"].path == "E:/My documents"
    assert restored.apps.applications["браузер"].launch == ["E:/Custom/browser.exe", "--custom"]


def test_automatic_browser_refreshes_in_saved_profile(monkeypatch, tmp_path):
    monkeypatch.setattr(windows.sys, "platform", "win32")
    monkeypatch.setattr(windows, "known_folder", lambda name: None)
    monkeypatch.setattr(windows, "find_application", lambda *args: "C:/BrowserA.exe")
    config = load_config_bundle(tmp_path)
    save_preferences(config)
    monkeypatch.setattr(windows, "find_application", lambda *args: "D:/BrowserB.exe")
    restored = load_config_bundle(tmp_path)
    assert restored.apps.applications["браузер"].launch == ["D:/BrowserB.exe"]


def test_explicit_source_catalog_does_not_get_machine_paths(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(windows.sys, "platform", "win32")
    discover = Mock(side_effect=AssertionError("must not replace source configuration"))
    monkeypatch.setattr(windows, "discover_defaults", discover)
    monkeypatch.setattr(windows, "find_application", lambda *args: None)
    config = load_config_bundle(root)
    assert config.apps.folders["документы"].path == "~/Documents"
    discover.assert_not_called()


@pytest.mark.skipif(sys.platform != "win32", reason="Real read-only Windows API check")
def test_real_windows_folder_and_app_path_api():
    # A missing user folder is legitimate on a clean runner; the profile folder is mandatory.
    profile = windows._known_folder_path("5E6C858F-0E22-4760-9AFE-EA3317B67173")
    assert Path(profile).is_dir()
    browser = windows._browser_executable()
    assert browser is None or isinstance(browser, str)
    assert windows.find_application("проводник") is not None


def test_app_paths_checks_user_registration_and_expands_environment(monkeypatch, tmp_path):
    from types import ModuleType

    program = tmp_path / "Browser.exe"
    program.touch()
    monkeypatch.setenv("LUMO_TEST_APPS", str(tmp_path))
    registry = ModuleType("winreg")
    registry.HKEY_CURRENT_USER, registry.HKEY_LOCAL_MACHINE = "user", "machine"
    registry.KEY_WOW64_64KEY, registry.KEY_WOW64_32KEY, registry.KEY_READ = 256, 512, 1
    registry.REG_SZ, registry.REG_EXPAND_SZ = 1, 2
    key = Mock()
    key.__enter__ = Mock(return_value="handle")
    key.__exit__ = Mock(return_value=False)
    registry.OpenKey = Mock(return_value=key)
    registry.QueryValueEx = Mock(return_value=('"${LUMO_TEST_APPS}/Browser.exe"', 2))
    # os.path.expandvars uses the host's native syntax in this cross-platform test.
    if sys.platform == "win32":
        registry.QueryValueEx.return_value = ('"%LUMO_TEST_APPS%/Browser.exe"', 2)
    monkeypatch.setitem(sys.modules, "winreg", registry)
    assert Path(windows._registered_executable("Browser.exe")) == program
    assert registry.OpenKey.call_args.args[0] == "user"
    assert registry.OpenKey.call_args.args[3] == registry.KEY_READ | registry.KEY_WOW64_64KEY


def test_path_discovery_never_uses_relative_current_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(windows.sys, "platform", "win32")
    monkeypatch.setattr(windows, "_registered_executable", lambda name: None)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Telegram.exe").touch()
    monkeypatch.setenv("PATH", ".")
    monkeypatch.delenv("APPDATA", raising=False)
    assert windows.find_application("telegram") is None
