import ctypes
import sys
import threading
from ctypes import wintypes

import pytest

if sys.platform != "win32":
    pytest.skip("Win32 helpers only support Windows", allow_module_level=True)

from pyminiwebview_win32 import (
    FramelessWindow,
    TrayIcon,
    open_file_dialog,
    save_file_dialog,
)
from pyminiwebview_win32 import dialogs
from pyminiwebview_win32 import frameless
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


def test_frameless_window_owns_webview_controls_and_first_frame(tmp_path):
    maximized_states = []
    window = FramelessWindow(
        title="pyminiwebview pytest frameless",
        width=760,
        height=540,
        min_width=640,
        min_height=480,
        app_name="pyminiwebview-pytest-frameless",
        user_data_folder=str(tmp_path / "webview-data"),
    )
    hwnd = window.hwnd

    def finish_on_first_frame(maximized):
        maximized_states.append(maximized)
        window.view.terminate()

    window.on_maximize_change = finish_on_first_frame

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    watchdog = threading.Timer(10, window.view.terminate)
    try:
        assert user32.IsWindow(hwnd)
        assert not user32.IsWindowVisible(hwnd)
        assert {
            "__window_minimize",
            "__window_toggle_maximize",
            "__window_close",
            "__window_start_move",
            "__window_start_resize",
            "__window_ready",
        } <= set(window.bridge._names)
        window.view.set_html("<h1>Frameless helper</h1>")
        window.run()
        assert window.ready
        assert user32.IsWindowVisible(hwnd)
        assert maximized_states == [False]
        assert window.start_resize("invalid") is False

        params = frameless._NCCALCSIZE_PARAMS()
        params.rgrc[0] = wintypes.RECT(0, 0, 760, 540)
        assert window._wndproc(
            hwnd, frameless._WM_NCCALCSIZE, 1, ctypes.addressof(params)
        ) == 0
        padding = window._ring_padding()
        assert params.rgrc[0].left == padding
        assert params.rgrc[0].top == 0
        assert params.rgrc[0].right == 760 - padding
        assert params.rgrc[0].bottom == 540 - padding

        rect = wintypes.RECT()
        assert user32.GetWindowRect(hwnd, ctypes.byref(rect))
        middle_x = (rect.left + rect.right) // 2
        middle_y = (rect.top + rect.bottom) // 2
        hit_tests = {
            "tl": (rect.left, rect.top, frameless._HTTOPLEFT),
            "tr": (rect.right, rect.top, frameless._HTTOPRIGHT),
            "bl": (rect.left, rect.bottom, frameless._HTBOTTOMLEFT),
            "br": (rect.right, rect.bottom, frameless._HTBOTTOMRIGHT),
            "l": (rect.left, middle_y, frameless._HTLEFT),
            "r": (rect.right, middle_y, frameless._HTRIGHT),
            "t": (middle_x, rect.top, frameless._HTTOP),
            "b": (middle_x, rect.bottom, frameless._HTBOTTOM),
        }
        for direction, (x, y, expected) in hit_tests.items():
            lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
            assert window._wndproc(
                hwnd, frameless._WM_NCHITTEST, 0, lparam
            ) == expected, direction
    finally:
        watchdog.cancel()
        window.close()
    assert not user32.IsWindow(hwnd)
    window.close()


def test_frameless_window_validates_dimensions():
    with pytest.raises(ValueError, match="positive"):
        FramelessWindow(width=0)
    with pytest.raises(ValueError, match="must not exceed"):
        FramelessWindow(width=600, height=500, min_width=700)
    with pytest.raises(TypeError, match="shadow"):
        FramelessWindow(shadow=1)
    with pytest.raises(TypeError, match="dark_mode"):
        FramelessWindow(dark_mode=1)
    with pytest.raises(TypeError, match="dwm_border"):
        FramelessWindow(dwm_border=1)
    with pytest.raises(ValueError, match="negative"):
        FramelessWindow(inner_border_width=-1)
    with pytest.raises(TypeError, match="inner_border_width"):
        FramelessWindow(inner_border_width=1.5)
    with pytest.raises(ValueError, match="dwm_border_color.*32 bits"):
        FramelessWindow(dwm_border_color=0x100000000)
    with pytest.raises(ValueError, match="inner_border_color.*32 bits"):
        FramelessWindow(inner_border_color=0x100000000)


@pytest.mark.parametrize(
    "zoomed, shadow, expected_width",
    [
        (False, True, 1),
        (True, True, 0),
        (False, False, 0),
    ],
)
def test_frameless_uses_dwm_frame_when_shadow_enabled_and_restored(
        monkeypatch, zoomed, shadow, expected_width):
    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
    window._shadow = shadow
    window._dwm_frame_width = None
    calls = []

    def extend(hwnd, pointer):
        margins = ctypes.cast(
            pointer, ctypes.POINTER(frameless._MARGINS)
        ).contents
        calls.append((
            hwnd,
            margins.cxLeftWidth,
            margins.cxRightWidth,
            margins.cyTopHeight,
            margins.cyBottomHeight,
        ))
        return 0

    monkeypatch.setattr(frameless._user32, "IsZoomed", lambda _hwnd: zoomed)
    monkeypatch.setattr(frameless._dwmapi, "DwmExtendFrameIntoClientArea", extend)
    window._extend_dwm_frame()
    window._extend_dwm_frame()
    assert calls == [(
        123, expected_width, expected_width, 0, expected_width
    )]


@pytest.mark.parametrize("dark_mode, expected", [(True, 1), (False, 0)])
def test_frameless_applies_dark_mode(monkeypatch, dark_mode, expected):
    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
    window._dark_mode = dark_mode
    calls = []

    def set_attribute(hwnd, attribute, pointer, size):
        calls.append((
            hwnd, attribute, ctypes.cast(
                pointer, ctypes.POINTER(wintypes.BOOL)
            ).contents.value, size,
        ))
        return 0

    monkeypatch.setattr(frameless._dwmapi, "DwmSetWindowAttribute", set_attribute)
    window._apply_dark_mode()
    assert calls == [(
        123, frameless._DWMWA_USE_IMMERSIVE_DARK_MODE, expected, 4
    )]


@pytest.mark.parametrize(
    "shadow, expected_policy",
    [
        (True, frameless._DWMNCRP_ENABLED),
        (False, frameless._DWMNCRP_DISABLED),
    ],
)
def test_frameless_shadow_controls_nonclient_rendering_policy(
        monkeypatch, shadow, expected_policy):
    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
    window._shadow = shadow
    calls = []

    def set_attribute(hwnd, attribute, pointer, size):
        calls.append((
            hwnd, attribute, ctypes.cast(
                pointer, ctypes.POINTER(ctypes.c_int)
            ).contents.value, size,
        ))
        return 0

    monkeypatch.setattr(frameless._dwmapi, "DwmSetWindowAttribute", set_attribute)
    window._apply_dwm_frame_policy()
    assert calls == [(
        123, frameless._DWMWA_NCRENDERING_POLICY, expected_policy, 4
    )]


@pytest.mark.parametrize(
    "dwm_border, dwm_border_color, expected_color",
    [
        (False, None, frameless._DWMWA_COLOR_NONE),
        (False, 0x00112233, frameless._DWMWA_COLOR_NONE),
        (True, None, frameless._DWMWA_COLOR_DEFAULT),
        (True, 0x00112233, 0x00112233),
    ],
)
def test_frameless_applies_dwm_border_color(
        monkeypatch, dwm_border, dwm_border_color, expected_color):
    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
    window._dwm_border = dwm_border
    window._dwm_border_color = dwm_border_color
    window._applied_dwm_border_color = None
    calls = []

    def set_attribute(hwnd, attribute, pointer, size):
        calls.append((
            hwnd, attribute, ctypes.cast(
                pointer, ctypes.POINTER(wintypes.DWORD)
            ).contents.value, size,
        ))
        return 0

    monkeypatch.setattr(frameless._dwmapi, "DwmSetWindowAttribute", set_attribute)
    window._apply_dwm_border_color()
    window._apply_dwm_border_color()
    assert calls == [(123, frameless._DWMWA_BORDER_COLOR, expected_color, 4)]


@pytest.mark.parametrize("zoomed, border", [(False, 3), (True, 0)])
def test_frameless_inner_border_width_insets_webview(monkeypatch, zoomed, border):
    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
    window.view = object()
    window._widget = 456
    window._resize_overlay = None
    window._inner_border_width = 3
    calls = []

    def client_rect(_hwnd, pointer):
        rect = ctypes.cast(pointer, ctypes.POINTER(wintypes.RECT)).contents
        rect.left = 0
        rect.top = 0
        rect.right = 100
        rect.bottom = 80
        return True

    monkeypatch.setattr(frameless._user32, "IsZoomed", lambda _hwnd: zoomed)
    monkeypatch.setattr(frameless._user32, "GetClientRect", client_rect)
    monkeypatch.setattr(
        frameless._user32, "SetWindowPos", lambda *args: calls.append(args)
    )
    window._layout_webview()
    assert calls == [(
        456, None, border, border, 100 - 2 * border, 80 - 2 * border,
        frameless._SWP_NOZORDER | frameless._SWP_NOACTIVATE,
    )]


def test_frameless_native_overlay_forwards_resize_to_host(monkeypatch):
    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
    calls = []
    monkeypatch.setattr(
        frameless._user32, "PostMessageW",
        lambda *args: calls.append(args) or True,
    )

    assert window._overlay_wndproc(
        456, frameless._WM_NCLBUTTONDOWN, frameless._HTTOPLEFT, 789
    ) == 0
    assert calls == [(
        123, frameless._WM_NCLBUTTONDOWN, frameless._HTTOPLEFT, 789
    )]


@pytest.mark.parametrize("size, expected_layouts", [(0, 1), (1, 0), (2, 1)])
def test_frameless_minimize_preserves_webview_layout(monkeypatch, size, expected_layouts):
    window = FramelessWindow.__new__(FramelessWindow)
    layouts = []
    border_updates = []
    window._layout_webview = lambda: layouts.append(size)
    window._apply_dwm_border_color = lambda: border_updates.append(size)
    window._extend_dwm_frame = lambda: None
    window._notify_maximized_state = lambda: None
    monkeypatch.setattr(frameless._user32, "DefWindowProcW", lambda *args: 0)

    window._wndproc(123, frameless._WM_SIZE, size, 0)

    assert layouts == [size] * expected_layouts
    assert border_updates == [size] * expected_layouts


@pytest.mark.parametrize(
    "direction, expected",
    [
        ("l", (120, 100, 600, 500)),
        ("r", (100, 100, 620, 500)),
        ("t", (100, 130, 600, 500)),
        ("b", (100, 100, 600, 530)),
        ("tl", (120, 130, 600, 500)),
        ("tr", (100, 130, 620, 500)),
        ("bl", (120, 100, 600, 530)),
        ("br", (100, 100, 620, 530)),
    ],
)
def test_frameless_resize_tracks_each_axis(monkeypatch, direction, expected):
    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
    window._min_width = 200
    window._min_height = 150
    window._resize_direction = direction
    window._resize_origin = (150, 150)
    window._resize_bounds = (100, 100, 600, 500)
    calls = []

    def cursor(pointer):
        point = ctypes.cast(pointer, ctypes.POINTER(frameless._POINT)).contents
        point.x = 170
        point.y = 180
        return True

    monkeypatch.setattr(frameless._user32, "GetCursorPos", cursor)
    monkeypatch.setattr(
        frameless._user32, "SetWindowPos", lambda *args: calls.append(args)
    )
    window._resize()
    left, top, right, bottom = expected
    assert calls == [(
        123, None, left, top, right - left, bottom - top,
        frameless._SWP_NOZORDER | frameless._SWP_NOACTIVATE,
    )]


def test_frameless_resize_clamps_to_minimum_size(monkeypatch):
    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
    window._min_width = 200
    window._min_height = 150
    window._resize_direction = "tl"
    window._resize_origin = (150, 150)
    window._resize_bounds = (100, 100, 600, 500)
    calls = []

    def cursor(pointer):
        point = ctypes.cast(pointer, ctypes.POINTER(frameless._POINT)).contents
        point.x = 1000
        point.y = 1000
        return True

    monkeypatch.setattr(frameless._user32, "GetCursorPos", cursor)
    monkeypatch.setattr(
        frameless._user32, "SetWindowPos", lambda *args: calls.append(args)
    )
    window._resize()
    assert calls[0][2:6] == (400, 350, 200, 150)


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
