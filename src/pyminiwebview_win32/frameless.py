import ctypes
import time
from ctypes import wintypes

import pyminiwebview
from pyminiwebview_helpers import Bridge

_WM_DESTROY = 0x0002
_WM_MOVE = 0x0003
_WM_SIZE = 0x0005
_WM_CLOSE = 0x0010
_WM_GETMINMAXINFO = 0x0024
_WM_NCDESTROY = 0x0082
_WM_NCCALCSIZE = 0x0083
_WM_NCHITTEST = 0x0084
_WM_NCACTIVATE = 0x0086
_WM_NCUAHDRAWCAPTION = 0x00AE
_WM_NCUAHDRAWFRAME = 0x00AF
_WM_NCLBUTTONDOWN = 0x00A1
_WM_MOUSEMOVE = 0x0200
_WM_LBUTTONUP = 0x0202
_WM_CAPTURECHANGED = 0x0215
_SIZE_MINIMIZED = 1
_SW_HIDE = 0
_SW_MAXIMIZE = 3
_SW_SHOWNOACTIVATE = 4
_SW_SHOW = 5
_SW_MINIMIZE = 6
_SW_RESTORE = 9
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020
_MONITOR_DEFAULTTONEAREST = 2
_SM_CXFRAME = 32
_SM_CXDOUBLECLK = 36
_SM_CYDOUBLECLK = 37
_SM_CXPADDEDBORDER = 92
_SPI_GETWORKAREA = 48
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_NCRENDERING_POLICY = 2
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWA_BORDER_COLOR = 34
_DWMWA_COLOR_NONE = 0xFFFFFFFE
_DWMWA_COLOR_DEFAULT = 0xFFFFFFFF
_DWMNCRP_DISABLED = 1
_DWMNCRP_ENABLED = 2
_DWMWCP_ROUND = 2
_HTCLIENT = 1
_HTCAPTION = 2
_HTLEFT, _HTRIGHT, _HTTOP, _HTBOTTOM = 10, 11, 12, 15
_HTTOPLEFT, _HTTOPRIGHT = 13, 14
_HTBOTTOMLEFT, _HTBOTTOMRIGHT = 16, 17
_HT_CODES = {
    "l": _HTLEFT,
    "r": _HTRIGHT,
    "t": _HTTOP,
    "b": _HTBOTTOM,
    "tl": _HTTOPLEFT,
    "tr": _HTTOPRIGHT,
    "bl": _HTBOTTOMLEFT,
    "br": _HTBOTTOMRIGHT,
}
_HT_RESIZE_CODES = frozenset(_HT_CODES.values())
_WS_CHILD = 0x40000000
_WS_VISIBLE = 0x10000000
_WS_CLIPSIBLINGS = 0x04000000
_WS_FRAMELESS_RESIZABLE = 0x00CF0000
_ERROR_ACCESS_DENIED = 5
_LONG_PTR = ctypes.c_ssize_t
_WNDPROC = ctypes.WINFUNCTYPE(
    _LONG_PTR, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class _NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", wintypes.LPVOID)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class _MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", _POINT),
        ("ptMaxSize", _POINT),
        ("ptMaxPosition", _POINT),
        ("ptMinTrackSize", _POINT),
        ("ptMaxTrackSize", _POINT),
    ]


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

_user32.DefWindowProcW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
]
_user32.DefWindowProcW.restype = _LONG_PTR
_user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASSW)]
_user32.RegisterClassW.restype = wintypes.ATOM
_user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.DestroyWindow.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.UpdateWindow.argtypes = [wintypes.HWND]
_user32.UpdateWindow.restype = wintypes.BOOL
_user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.restype = wintypes.BOOL
_user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetClientRect.restype = wintypes.BOOL
_user32.IsZoomed.argtypes = [wintypes.HWND]
_user32.IsZoomed.restype = wintypes.BOOL
_user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_user32.MonitorFromWindow.restype = wintypes.HANDLE
_user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFO)]
_user32.GetMonitorInfoW.restype = wintypes.BOOL
_user32.GetDpiForWindow.argtypes = [wintypes.HWND]
_user32.GetDpiForWindow.restype = wintypes.UINT
_user32.GetSystemMetrics.argtypes = [ctypes.c_int]
_user32.GetSystemMetrics.restype = ctypes.c_int
_user32.GetDoubleClickTime.restype = wintypes.UINT
_user32.GetCursorPos.argtypes = [ctypes.POINTER(_POINT)]
_user32.GetCursorPos.restype = wintypes.BOOL
_user32.ReleaseCapture.restype = wintypes.BOOL
_user32.SetCapture.argtypes = [wintypes.HWND]
_user32.SetCapture.restype = wintypes.HWND
_user32.PostMessageW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
]
_user32.PostMessageW.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.SystemParametersInfoW.argtypes = [
    wintypes.UINT, wintypes.UINT, wintypes.LPVOID, wintypes.UINT,
]
_user32.SystemParametersInfoW.restype = wintypes.BOOL
_user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
_user32.UnregisterClassW.restype = wintypes.BOOL
_user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
_user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_gdi32.CreateSolidBrush.argtypes = [wintypes.DWORD]
_gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteObject.restype = wintypes.BOOL
_dwmapi.DwmSetWindowAttribute.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
]
_dwmapi.DwmSetWindowAttribute.restype = wintypes.LONG
_dwmapi.DwmExtendFrameIntoClientArea.argtypes = [
    wintypes.HWND, ctypes.POINTER(_MARGINS),
]
_dwmapi.DwmExtendFrameIntoClientArea.restype = wintypes.LONG
try:
    _user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
    _user32.GetSystemMetricsForDpi.restype = ctypes.c_int
except AttributeError:
    pass


class FramelessWindow:
    """Own a borderless Win32 host, an embedded WebView, and its JS controls."""

    def __init__(
        self,
        title="pyminiwebview",
        width=1100,
        height=740,
        *,
        min_width=640,
        min_height=480,
        app_name="pyminiwebview",
        debug=False,
        bgcolor=0xFFFFFF,
        shadow=True,
        dark_mode=False,
        dwm_border=True,
        dwm_border_color=None,
        inner_border_width=1,
        inner_border_color=None,
        user_data_folder=None,
        clipboard_permission="default",
        on_maximize_change=None,
    ):
        if width <= 0 or height <= 0 or min_width <= 0 or min_height <= 0:
            raise ValueError("Window dimensions must be positive")
        if min_width > width or min_height > height:
            raise ValueError("Minimum dimensions must not exceed initial dimensions")
        if not isinstance(shadow, bool):
            raise TypeError("shadow must be a bool")
        if not isinstance(dark_mode, bool):
            raise TypeError("dark_mode must be a bool")
        if not isinstance(dwm_border, bool):
            raise TypeError("dwm_border must be a bool")
        if not isinstance(inner_border_width, int) or isinstance(
            inner_border_width, bool
        ):
            raise TypeError("inner_border_width must be an integer")
        if inner_border_width < 0:
            raise ValueError("inner_border_width must not be negative")
        for name, color in (
            ("dwm_border_color", dwm_border_color),
            ("inner_border_color", inner_border_color),
        ):
            if color is not None:
                if not isinstance(color, int) or isinstance(color, bool):
                    raise TypeError(f"{name} must be an integer COLORREF or None")
                if not 0 <= color <= 0xFFFFFFFF:
                    raise ValueError(f"{name} must fit in 32 bits")
        self.hwnd = None
        self.view = None
        self.bridge = None
        self._widget = None
        self.ready = False
        self.on_maximize_change = on_maximize_change
        self._title = title
        self._width = width
        self._height = height
        self._min_width = min_width
        self._min_height = min_height
        self._app_name = app_name
        self._debug = debug
        self._bgcolor = bgcolor
        self._shadow = shadow
        self._dark_mode = dark_mode
        self._dwm_border = dwm_border
        self._dwm_border_color = dwm_border_color
        self._dwm_frame_width = None
        self._applied_dwm_border_color = None
        self._inner_border_width = inner_border_width
        self._inner_border_color = inner_border_color
        self._user_data_folder = user_data_folder
        self._clipboard_permission = clipboard_permission
        self._class_name = f"PyMiniWebViewFrameless_{id(self):x}"
        self._class_atom = None
        self._background_brush = None
        self._wndproc_ref = _WNDPROC(self._wndproc)
        self._overlay_wndproc_ref = _WNDPROC(self._overlay_wndproc)
        self._overlay_class_name = f"{self._class_name}_TopResize"
        self._overlay_class_atom = None
        self._resize_overlay = None
        self._hinstance = _kernel32.GetModuleHandleW(None)
        self._move_serial = 0
        self._last_title_down = None
        self._resize_direction = None
        self._resize_origin = None
        self._resize_bounds = None
        try:
            self._create()
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _ring_padding(self):
        if not self.hwnd:
            return 0
        dpi = _user32.GetDpiForWindow(self.hwnd) or 96
        try:
            value = _user32.GetSystemMetricsForDpi(
                _SM_CXFRAME, dpi
            ) + _user32.GetSystemMetricsForDpi(_SM_CXPADDEDBORDER, dpi)
        except (AttributeError, OSError):
            value = _user32.GetSystemMetrics(_SM_CXFRAME) + _user32.GetSystemMetrics(
                _SM_CXPADDEDBORDER
            )
        return max(1, value - 1)

    def _extend_dwm_frame(self):
        width = int(self._shadow and not _user32.IsZoomed(self.hwnd))
        if width == self._dwm_frame_width:
            return
        margins = _MARGINS(width, width, 0, width)
        _dwmapi.DwmExtendFrameIntoClientArea(self.hwnd, ctypes.byref(margins))
        self._dwm_frame_width = width

    def _apply_dark_mode(self):
        value = wintypes.BOOL(self._dark_mode)
        _dwmapi.DwmSetWindowAttribute(
            self.hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), 4
        )

    def _apply_dwm_frame_policy(self):
        policy = _DWMNCRP_ENABLED if self._shadow else _DWMNCRP_DISABLED
        value = ctypes.c_int(policy)
        _dwmapi.DwmSetWindowAttribute(
            self.hwnd, _DWMWA_NCRENDERING_POLICY, ctypes.byref(value), 4
        )

    def _set_dwm_border_color(self, color):
        value = wintypes.DWORD(color)
        _dwmapi.DwmSetWindowAttribute(
            self.hwnd, _DWMWA_BORDER_COLOR, ctypes.byref(value), 4
        )

    def _apply_dwm_border_color(self):
        if not self._dwm_border:
            color = _DWMWA_COLOR_NONE
        elif self._dwm_border_color is not None:
            color = self._dwm_border_color
        else:
            color = _DWMWA_COLOR_DEFAULT
        if color == self._applied_dwm_border_color:
            return
        self._set_dwm_border_color(color)
        self._applied_dwm_border_color = color

    def _create_native_resize(self):
        window_class = _WNDCLASSW()
        window_class.lpfnWndProc = self._overlay_wndproc_ref
        window_class.hInstance = self._hinstance
        window_class.lpszClassName = self._overlay_class_name
        self._overlay_class_atom = _user32.RegisterClassW(
            ctypes.byref(window_class)
        )
        if not self._overlay_class_atom:
            raise ctypes.WinError(ctypes.get_last_error())
        self._resize_overlay = _user32.CreateWindowExW(
            0, self._overlay_class_name, None,
            _WS_CHILD | _WS_VISIBLE | _WS_CLIPSIBLINGS,
            0, 0, self._width, self._ring_padding(),
            self.hwnd, None, self._hinstance, None,
        )
        if not self._resize_overlay:
            raise ctypes.WinError(ctypes.get_last_error())

    def _layout_native_resize(self, width):
        if not self._resize_overlay:
            return
        if _user32.IsZoomed(self.hwnd):
            _user32.ShowWindow(self._resize_overlay, _SW_HIDE)
            return
        _user32.SetWindowPos(
            self._resize_overlay, None, 0, 0, width, self._ring_padding(),
            _SWP_NOACTIVATE,
        )
        _user32.ShowWindow(self._resize_overlay, _SW_SHOWNOACTIVATE)

    def _overlay_wndproc(self, hwnd, message, wparam, lparam):
        if message == _WM_NCHITTEST and self.hwnd:
            return self._native_hit_test(lparam)
        if (
            message == _WM_NCLBUTTONDOWN
            and wparam in _HT_RESIZE_CODES
            and self.hwnd
        ):
            _user32.PostMessageW(self.hwnd, message, wparam, lparam)
            return 0
        if message == _WM_NCDESTROY:
            self._resize_overlay = None
        return _user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _native_hit_test(self, lparam):
        if _user32.IsZoomed(self.hwnd):
            return _HTCLIENT
        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        rect = wintypes.RECT()
        if not _user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            return _HTCLIENT
        padding = self._ring_padding()
        left = x - rect.left
        top = y - rect.top
        right = rect.right - x
        bottom = rect.bottom - y
        if left < padding and top < padding:
            return _HTTOPLEFT
        if right < padding and top < padding:
            return _HTTOPRIGHT
        if left < padding and bottom < padding:
            return _HTBOTTOMLEFT
        if right < padding and bottom < padding:
            return _HTBOTTOMRIGHT
        if left < padding:
            return _HTLEFT
        if right < padding:
            return _HTRIGHT
        if top < padding:
            return _HTTOP
        if bottom < padding:
            return _HTBOTTOM
        return _HTCLIENT

    def _layout_webview(self):
        if not self.hwnd or not self.view or not self._widget:
            return
        rect = wintypes.RECT()
        if not _user32.GetClientRect(self.hwnd, ctypes.byref(rect)):
            return
        border = 0 if _user32.IsZoomed(self.hwnd) else self._inner_border_width
        width = max(0, rect.right - rect.left - 2 * border)
        height = max(0, rect.bottom - rect.top - 2 * border)
        _user32.SetWindowPos(
            self._widget, None, border, border, width, height,
            _SWP_NOZORDER | _SWP_NOACTIVATE,
        )
        self._layout_native_resize(rect.right - rect.left)

    def _create(self):
        ctypes.set_last_error(0)
        if not _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            error = ctypes.get_last_error()
            if error != _ERROR_ACCESS_DENIED:
                raise ctypes.WinError(error)
        host_color = (
            self._inner_border_color
            if self._inner_border_color is not None
            else self._bgcolor
        )
        self._background_brush = _gdi32.CreateSolidBrush(host_color)
        if not self._background_brush:
            raise ctypes.WinError(ctypes.get_last_error())
        window_class = _WNDCLASSW()
        window_class.lpfnWndProc = self._wndproc_ref
        window_class.hInstance = self._hinstance
        window_class.hbrBackground = self._background_brush
        window_class.lpszClassName = self._class_name
        self._class_atom = _user32.RegisterClassW(ctypes.byref(window_class))
        if not self._class_atom:
            raise ctypes.WinError(ctypes.get_last_error())

        work_area = wintypes.RECT()
        if not _user32.SystemParametersInfoW(
            _SPI_GETWORKAREA, 0, ctypes.byref(work_area), 0
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        x = work_area.left + (
            work_area.right - work_area.left - self._width
        ) // 2
        y = work_area.top + (
            work_area.bottom - work_area.top - self._height
        ) // 2
        self.hwnd = _user32.CreateWindowExW(
            0, self._class_name, self._title, _WS_FRAMELESS_RESIZABLE,
            x, y, self._width, self._height,
            None, None, self._hinstance, None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

        corner = ctypes.c_int(_DWMWCP_ROUND)
        _dwmapi.DwmSetWindowAttribute(
            self.hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner), 4
        )
        self._apply_dark_mode()
        self._apply_dwm_frame_policy()
        self._extend_dwm_frame()
        self._apply_dwm_border_color()
        self.view = pyminiwebview.WebView(
            window=self.hwnd,
            autosize=False,
            width=self._width,
            height=self._height,
            debug=self._debug,
            bgcolor=self._bgcolor,
            app_name=self._app_name,
            user_data_folder=self._user_data_folder,
            clipboard_permission=self._clipboard_permission,
        )
        self._widget = self.view.get_native_handle(
            pyminiwebview.NATIVE_HANDLE_KIND_UI_WIDGET
        )
        self._create_native_resize()
        if not _user32.SetWindowPos(
            self.hwnd, None, 0, 0,
            self._width, self._height,
            _SWP_NOMOVE | _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_FRAMECHANGED,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        self._layout_webview()
        self.bridge = Bridge(self.view)
        controls = {
            "__window_minimize": self.minimize,
            "__window_toggle_maximize": self.toggle_maximize,
            "__window_close": self.close_window,
            "__window_start_move": self.start_move,
            "__window_start_resize": self.start_resize,
            "__window_ready": self.reveal,
        }
        for name, function in controls.items():
            self.bridge.expose(function, name=name)
        self.view.js_init(
            """
            document.addEventListener('DOMContentLoaded', () => {
              requestAnimationFrame(() => requestAnimationFrame(() => {
                __window_ready();
              }));
            });
            """
        )
        self.view.configure_app_mode()

    def reveal(self):
        if not self.hwnd or not self.view:
            return False
        _user32.ShowWindow(self.hwnd, _SW_SHOW)
        _user32.UpdateWindow(self.hwnd)
        self.ready = True
        _user32.SetForegroundWindow(self.hwnd)
        self.view.set_focus()
        self._notify_maximized_state()
        return True

    def minimize(self):
        if not self.hwnd:
            return False
        _user32.ShowWindow(self.hwnd, _SW_MINIMIZE)
        return True

    def toggle_maximize(self):
        if not self.hwnd:
            return False
        _user32.ShowWindow(
            self.hwnd, _SW_RESTORE if _user32.IsZoomed(self.hwnd) else _SW_MAXIMIZE
        )
        maximized = bool(_user32.IsZoomed(self.hwnd))
        self._notify_maximized_state()
        return maximized

    def close_window(self):
        if not self.hwnd:
            return False
        return bool(_user32.PostMessageW(self.hwnd, _WM_CLOSE, 0, 0))

    def _post_nonclient_action(self, hit_code):
        if not self.hwnd:
            return False
        point = _POINT()
        _user32.ReleaseCapture()
        if not _user32.GetCursorPos(ctypes.byref(point)):
            return False
        lparam = ((point.y & 0xFFFF) << 16) | (point.x & 0xFFFF)
        return bool(_user32.PostMessageW(
            self.hwnd, _WM_NCLBUTTONDOWN, hit_code, lparam
        ))

    def start_move(self):
        point = _POINT()
        if not self.hwnd or not _user32.GetCursorPos(ctypes.byref(point)):
            return False
        now = time.monotonic()
        candidate = (now, self._move_serial, point.x, point.y)
        previous = self._last_title_down
        self._last_title_down = candidate
        is_double = bool(
            previous
            and now - previous[0] <= _user32.GetDoubleClickTime() / 1000
            and previous[1] == self._move_serial
            and abs(point.x - previous[2]) <= _user32.GetSystemMetrics(_SM_CXDOUBLECLK) / 2
            and abs(point.y - previous[3]) <= _user32.GetSystemMetrics(_SM_CYDOUBLECLK) / 2
        )
        if is_double:
            self._last_title_down = None
            self.toggle_maximize()
            return True
        return self._post_nonclient_action(_HTCAPTION)

    def start_resize(self, direction):
        if (
            not self.hwnd
            or direction not in _HT_CODES
            or _user32.IsZoomed(self.hwnd)
        ):
            return False
        point = _POINT()
        rect = wintypes.RECT()
        if not _user32.GetCursorPos(ctypes.byref(point)):
            return False
        if not _user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            return False
        self._resize_direction = direction
        self._resize_origin = (point.x, point.y)
        self._resize_bounds = (rect.left, rect.top, rect.right, rect.bottom)
        _user32.ReleaseCapture()
        _user32.SetCapture(self.hwnd)
        return True

    def _resize(self):
        point = _POINT()
        if not _user32.GetCursorPos(ctypes.byref(point)):
            return
        dx = point.x - self._resize_origin[0]
        dy = point.y - self._resize_origin[1]
        left, top, right, bottom = self._resize_bounds
        direction = self._resize_direction
        if "l" in direction:
            left = min(left + dx, right - self._min_width)
        if "r" in direction:
            right = max(right + dx, left + self._min_width)
        if "t" in direction:
            top = min(top + dy, bottom - self._min_height)
        if "b" in direction:
            bottom = max(bottom + dy, top + self._min_height)
        _user32.SetWindowPos(
            self.hwnd, None, left, top, right - left, bottom - top,
            _SWP_NOZORDER | _SWP_NOACTIVATE,
        )

    def _finish_resize(self):
        self._resize_direction = None
        self._resize_origin = None
        self._resize_bounds = None

    def _notify_maximized_state(self):
        if self.ready and self.on_maximize_change is not None:
            self.on_maximize_change(bool(_user32.IsZoomed(self.hwnd)))

    def _wndproc(self, hwnd, message, wparam, lparam):
        if message == _WM_NCCALCSIZE:
            if wparam:
                params = ctypes.cast(
                    lparam, ctypes.POINTER(_NCCALCSIZE_PARAMS)
                ).contents
                if _user32.IsZoomed(hwnd):
                    info = _MONITORINFO()
                    info.cbSize = ctypes.sizeof(info)
                    monitor = _user32.MonitorFromWindow(
                        hwnd, _MONITOR_DEFAULTTONEAREST
                    )
                    if _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                        params.rgrc[0] = info.rcWork
                else:
                    padding = self._ring_padding()
                    params.rgrc[0].left += padding
                    params.rgrc[0].right -= padding
                    params.rgrc[0].bottom -= padding
            return 0
        if message == _WM_NCACTIVATE:
            return _user32.DefWindowProcW(hwnd, message, wparam, -1)
        if message in (_WM_NCUAHDRAWCAPTION, _WM_NCUAHDRAWFRAME):
            return 0
        if message == _WM_GETMINMAXINFO:
            info = ctypes.cast(lparam, ctypes.POINTER(_MINMAXINFO)).contents
            info.ptMinTrackSize = _POINT(self._min_width, self._min_height)
            monitor_info = _MONITORINFO()
            monitor_info.cbSize = ctypes.sizeof(monitor_info)
            monitor = _user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
            if _user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info)):
                work = monitor_info.rcWork
                info.ptMaxPosition = _POINT(work.left, work.top)
                info.ptMaxSize = _POINT(
                    work.right - work.left, work.bottom - work.top
                )
            return 0
        if message == _WM_NCHITTEST:
            return self._native_hit_test(lparam)
        if message == _WM_MOUSEMOVE and self._resize_direction:
            self._resize()
            return 0
        if message == _WM_LBUTTONUP and self._resize_direction:
            self._finish_resize()
            _user32.ReleaseCapture()
            return 0
        if message == _WM_CAPTURECHANGED:
            self._finish_resize()
        if message == _WM_MOVE:
            self._move_serial += 1
            if self.view:
                self.view.notify_parent_position()
        elif message == _WM_SIZE:
            if wparam != _SIZE_MINIMIZED:
                self._layout_webview()
                self._apply_dwm_border_color()
            self._extend_dwm_frame()
            self._notify_maximized_state()
        elif message == _WM_CLOSE:
            _user32.DestroyWindow(hwnd)
            return 0
        elif message == _WM_DESTROY:
            self.hwnd = None
            if self.view:
                self.view.terminate()
            return 0
        return _user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def run(self):
        if not self.view:
            raise RuntimeError("FramelessWindow is closed")
        self.view.run()

    def close(self):
        if self._resize_direction:
            self._finish_resize()
            _user32.ReleaseCapture()
        if self.hwnd:
            _user32.DestroyWindow(self.hwnd)
        if self.view:
            self.view.close()
            self.view = None
        self._widget = None
        self.bridge = None
        self.ready = False
        if self._class_atom:
            _user32.UnregisterClassW(self._class_name, self._hinstance)
            self._class_atom = None
        if self._overlay_class_atom:
            _user32.UnregisterClassW(self._overlay_class_name, self._hinstance)
            self._overlay_class_atom = None
        if self._background_brush:
            _gdi32.DeleteObject(self._background_brush)
            self._background_brush = None
