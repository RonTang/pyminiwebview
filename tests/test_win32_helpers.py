import ctypes
import sys
import threading
import warnings
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
        assert window._frame == "round"
        assert window._overlay_wndproc(
            window._resize_overlay, frameless._WM_ERASEBKGND, 0, 0
        ) == 1
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

        window.on_maximize_change = None
        assert window.toggle_maximize() is True
        assert user32.IsZoomed(hwnd)
        assert not user32.IsWindowVisible(window._resize_overlay)
        assert window.toggle_maximize() is False
        assert not user32.IsZoomed(hwnd)
        assert user32.IsWindowVisible(window._resize_overlay)

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


def test_fixed_frameless_window_disables_resizing_and_maximize():
    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
    window._resizable = False
    window._width = 760
    window._height = 540
    window._min_width = 640
    window._min_height = 480

    assert window.start_resize("br") is False
    assert window.toggle_maximize() is False
    assert window._native_hit_test(0) == frameless._HTCLIENT

    info = frameless._MINMAXINFO()
    assert window._wndproc(
        123, frameless._WM_GETMINMAXINFO, 0, ctypes.addressof(info)
    ) == 0
    assert (info.ptMinTrackSize.x, info.ptMinTrackSize.y) == (760, 540)
    assert (info.ptMaxTrackSize.x, info.ptMaxTrackSize.y) == (760, 540)


def test_frameless_maximize_uses_monitor_relative_position(monkeypatch):
    window = FramelessWindow.__new__(FramelessWindow)
    window._resizable = True
    window._min_width = 640
    window._min_height = 480

    monkeypatch.setattr(
        frameless._user32, "MonitorFromWindow", lambda _hwnd, _flags: 99
    )

    def get_monitor_info(_monitor, pointer):
        monitor_info = ctypes.cast(
            pointer, ctypes.POINTER(frameless._MONITORINFO)
        ).contents
        monitor_info.rcMonitor = wintypes.RECT(1920, 0, 3840, 1080)
        monitor_info.rcWork = wintypes.RECT(1980, 0, 3840, 1040)
        return True

    monkeypatch.setattr(frameless._user32, "GetMonitorInfoW", get_monitor_info)

    info = frameless._MINMAXINFO()
    assert window._wndproc(
        123, frameless._WM_GETMINMAXINFO, 0, ctypes.addressof(info)
    ) == 0
    assert (info.ptMaxPosition.x, info.ptMaxPosition.y) == (60, 0)
    assert (info.ptMaxSize.x, info.ptMaxSize.y) == (1860, 1040)


def test_frameless_window_validates_dimensions():
    with pytest.raises(ValueError, match="positive"):
        FramelessWindow(width=0)
    with pytest.raises(ValueError, match="must not exceed"):
        FramelessWindow(width=600, height=500, min_width=700)
    with pytest.raises(TypeError, match="resizable"):
        FramelessWindow(resizable=1)
    with pytest.raises(TypeError, match="dark_mode"):
        FramelessWindow(dark_mode=1)
    with pytest.raises(ValueError, match="round.*square_shadow"):
        FramelessWindow(frame="round_borderless")
    with pytest.raises(TypeError, match="shadow"):
        FramelessWindow(shadow=True)
    with pytest.raises(TypeError, match="inner_border_width"):
        FramelessWindow(inner_border_width=1)


def test_frameless_dpi_access_denied_uses_system_awareness(monkeypatch):
    calls = []
    monkeypatch.setattr(
        frameless._user32, "SetProcessDpiAwarenessContext", lambda _context: False
    )
    monkeypatch.setattr(frameless.ctypes, "get_last_error", lambda: 5)
    monkeypatch.setattr(
        frameless.ctypes.windll.shcore, "SetProcessDpiAwareness",
        lambda level: calls.append(level) or 0,
    )
    frameless._enable_dpi_awareness()
    assert calls == [2]


def test_frameless_dpi_failed_fallback_warns(monkeypatch):
    monkeypatch.setattr(
        frameless._user32, "SetProcessDpiAwarenessContext", lambda _context: False
    )
    monkeypatch.setattr(frameless.ctypes, "get_last_error", lambda: 5)
    monkeypatch.setattr(
        frameless.ctypes.windll.shcore, "SetProcessDpiAwareness",
        lambda _level: -1,
    )
    monkeypatch.setattr(frameless, "_is_per_monitor_v2", lambda: False)
    with pytest.warns(RuntimeWarning, match="Per-Monitor V2"):
        frameless._enable_dpi_awareness()


def test_frameless_dpi_does_not_warn_when_already_per_monitor_v2(monkeypatch):
    monkeypatch.setattr(
        frameless._user32, "SetProcessDpiAwarenessContext", lambda _context: False
    )
    monkeypatch.setattr(frameless.ctypes, "get_last_error", lambda: 5)
    monkeypatch.setattr(
        frameless.ctypes.windll.shcore, "SetProcessDpiAwareness",
        lambda _level: -1,
    )
    monkeypatch.setattr(frameless, "_is_per_monitor_v2", lambda: True)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        frameless._enable_dpi_awareness()


@pytest.mark.parametrize(
    "zoomed, expected_width",
    [(False, 1), (True, 0)],
)
def test_frameless_uses_dwm_frame_when_restored(
        monkeypatch, zoomed, expected_width):
    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
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


def test_frameless_always_enables_nonclient_rendering_policy(monkeypatch):
    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
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
        123, frameless._DWMWA_NCRENDERING_POLICY, frameless._DWMNCRP_ENABLED, 4
    )]


@pytest.mark.parametrize(
    "frame, expected_color",
    [
        ("round", frameless._DWMWA_COLOR_DEFAULT),
        ("square_shadow", frameless._DWMWA_COLOR_NONE),
    ],
)
def test_frameless_applies_dwm_border_color(monkeypatch, frame, expected_color):
    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
    window._frame = frame
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


def test_frameless_webview_fills_client_area(monkeypatch):
    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
    window.view = object()
    window._widget = 456
    window._resize_overlay = None
    calls = []

    def client_rect(_hwnd, pointer):
        rect = ctypes.cast(pointer, ctypes.POINTER(wintypes.RECT)).contents
        rect.left = 0
        rect.top = 0
        rect.right = 100
        rect.bottom = 80
        return True

    monkeypatch.setattr(frameless._user32, "GetClientRect", client_rect)
    monkeypatch.setattr(
        frameless._user32, "SetWindowPos", lambda *args: calls.append(args)
    )
    window._layout_webview()
    assert calls == [(
        456, None, 0, 0, 100, 80,
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


def test_frameless_destroy_ignores_already_closed_view():
    class ClosedView:
        def terminate(self):
            raise RuntimeError("closed")

    window = FramelessWindow.__new__(FramelessWindow)
    window.hwnd = 123
    window.view = ClosedView()
    assert window._wndproc(123, frameless._WM_DESTROY, 0, 0) == 0
    assert window.hwnd is None


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


def test_tray_icon_create_failure_unregisters_window_class(monkeypatch):
    unregister_calls = []
    monkeypatch.setattr(tray._user32, "RegisterClassW", lambda _pointer: 1)
    monkeypatch.setattr(tray._user32, "CreateWindowExW", lambda *args: None)
    monkeypatch.setattr(
        tray._user32, "UnregisterClassW",
        lambda *args: unregister_calls.append(args) or True,
    )

    with pytest.raises(OSError):
        TrayIcon()

    assert len(unregister_calls) == 1
    assert unregister_calls[0][0].startswith("PyMiniWebViewTray_")


def test_tray_icon_rejects_oversized_tooltip_before_creating_window(monkeypatch):
    monkeypatch.setattr(
        tray._kernel32, "GetModuleHandleW",
        lambda *_args: pytest.fail("must not create native resources"),
    )
    with pytest.raises(ValueError, match="127"):
        TrayIcon(tooltip="x" * 128)
    with pytest.raises(ValueError, match="127"):
        TrayIcon(tooltip="😀" * 64)


def test_tray_icon_remove_logs_destroy_failure_and_cleans_up(
        monkeypatch, caplog):
    icon = TrayIcon.__new__(TrayIcon)
    icon._hwnd = 123
    icon._icon_added = False
    icon._class_registered = True
    icon._class_name = "PyMiniWebViewTray_Test"
    icon._hinstance = 456
    unregister_calls = []
    monkeypatch.setattr(tray._user32, "DestroyWindow", lambda _hwnd: False)
    monkeypatch.setattr(tray.ctypes, "get_last_error", lambda: 5)
    monkeypatch.setattr(
        tray._user32, "UnregisterClassW",
        lambda *args: unregister_calls.append(args) or True,
    )

    with caplog.at_level("WARNING", logger="pyminiwebview_win32.tray"):
        icon.remove()
        icon.remove()

    assert "Win32 error 5" in caplog.text
    assert icon._hwnd is None
    assert not icon._class_registered
    assert unregister_calls == [("PyMiniWebViewTray_Test", 456)]
