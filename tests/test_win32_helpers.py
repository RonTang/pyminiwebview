import ctypes
import sys
from ctypes import wintypes

import pytest

if sys.platform != "win32":
    pytest.skip("Win32 helpers only support Windows", allow_module_level=True)

from pyminiwebview_win32 import TrayIcon, open_file_dialog, save_file_dialog
from pyminiwebview_win32 import dialogs
from pyminiwebview_win32 import tray


def file_buffer(ofn):
    address = ctypes.addressof(ofn) + dialogs._OPENFILENAMEW.lpstrFile.offset
    return ctypes.c_void_p.from_address(address).value


def write_path(target, path, max_chars):
    size = min(len(path) + 1, max_chars) * ctypes.sizeof(wintypes.WCHAR)
    ctypes.memmove(target, ctypes.c_wchar_p(path), size)


def test_open_file_dialog_uses_open_flags_and_returns_buffer(monkeypatch):
    captured = {}

    def choose(pointer):
        ofn = ctypes.cast(pointer, ctypes.POINTER(dialogs._OPENFILENAMEW)).contents
        captured["flags"] = ofn.Flags
        captured["owner"] = ofn.hwndOwner
        captured["max_file"] = ofn.nMaxFile
        write_path(file_buffer(ofn), r"C:\selected\report.txt", ofn.nMaxFile)
        return 1

    monkeypatch.setattr(
        dialogs._comdlg32, "GetOpenFileNameW", choose
    )
    result = open_file_dialog(
        hwnd_owner=1234,
        filters=[("Text Files", "*.txt")],
        initial_dir=r"C:\selected",
    )
    assert result == r"C:\selected\report.txt"
    assert captured["owner"] == 1234
    assert captured["max_file"] == 32768
    assert captured["flags"] & dialogs._OFN_FILEMUSTEXIST
    assert not captured["flags"] & dialogs._OFN_OVERWRITEPROMPT


def test_save_file_dialog_allows_new_file_and_prompts_overwrite(monkeypatch):
    captured = {}

    def choose(pointer):
        ofn = ctypes.cast(pointer, ctypes.POINTER(dialogs._OPENFILENAMEW)).contents
        captured["flags"] = ofn.Flags
        captured["initial"] = ofn.lpstrFile
        write_path(file_buffer(ofn), r"C:\selected\new.txt", ofn.nMaxFile)
        return 1

    monkeypatch.setattr(
        dialogs._comdlg32, "GetSaveFileNameW", choose
    )
    result = save_file_dialog(
        filters=[("Text Files", "*.txt")], initial_file="new.txt"
    )
    assert result == r"C:\selected\new.txt"
    assert captured["initial"] == "new.txt"
    assert captured["flags"] & dialogs._OFN_OVERWRITEPROMPT
    assert not captured["flags"] & dialogs._OFN_FILEMUSTEXIST


def test_file_dialog_distinguishes_cancel_and_error(monkeypatch):
    monkeypatch.setattr(
        dialogs._comdlg32, "GetOpenFileNameW", lambda _pointer: 0
    )
    monkeypatch.setattr(
        dialogs._comdlg32, "CommDlgExtendedError", lambda: 0
    )
    assert open_file_dialog() is None

    monkeypatch.setattr(
        dialogs._comdlg32, "CommDlgExtendedError", lambda: 1
    )
    with pytest.raises(OSError):
        open_file_dialog()


def test_tray_icon_receives_messages_and_removes_cleanly():
    events = []
    icon = TrayIcon(
        tooltip="pyminiwebview pytest",
        on_click=lambda: events.append("clicked"),
    )
    hwnd = icon.hwnd
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL

    assert ctypes.sizeof(tray._NOTIFYICONDATAW) == 976
    assert user32.IsWindow(hwnd)
    try:
        user32.SendMessageW(hwnd, tray._WM_TRAYICON, 0, tray._WM_LBUTTONUP)
        user32.SendMessageW(hwnd, tray._WM_TRAYICON, 0, tray._WM_RBUTTONUP)
        assert events == ["clicked", "clicked"]
    finally:
        icon.remove()
    assert not user32.IsWindow(hwnd)
    icon.remove()


def test_tray_icon_distinguishes_left_and_right_click():
    events = []
    icon = TrayIcon(
        tooltip="pyminiwebview pytest buttons",
        on_left_click=lambda: events.append("left"),
        on_right_click=lambda: events.append("right"),
    )
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    try:
        user32.SendMessageW(
            icon.hwnd, tray._WM_TRAYICON, 0, tray._WM_LBUTTONUP
        )
        user32.SendMessageW(
            icon.hwnd, tray._WM_TRAYICON, 0, tray._WM_RBUTTONUP
        )
        assert events == ["left", "right"]
    finally:
        icon.remove()
