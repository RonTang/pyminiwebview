import ctypes
import math
import sys
import time
import warnings
from ctypes import wintypes

import pyminiwebview
from pyminiwebview_helpers import Bridge

_WM_DESTROY = 0x0002
_WM_MOVE = 0x0003
_WM_SIZE = 0x0005
_WM_CLOSE = 0x0010
_WM_ERASEBKGND = 0x0014
_WM_SETCURSOR = 0x0020
_WM_GETMINMAXINFO = 0x0024
_WM_NCDESTROY = 0x0082
_WM_NCCALCSIZE = 0x0083
_WM_NCHITTEST = 0x0084
_WM_NCPAINT = 0x0085
_WM_NCACTIVATE = 0x0086
_WM_NCMOUSEMOVE = 0x00A0
_WM_NCLBUTTONDOWN = 0x00A1
_WM_NCLBUTTONUP = 0x00A2
_WM_NCLBUTTONDBLCLK = 0x00A3
_WM_NCMOUSELEAVE = 0x02A2
_WM_NCUAHDRAWCAPTION = 0x00AE
_WM_NCUAHDRAWFRAME = 0x00AF
_WM_MOUSEMOVE = 0x0200
_WM_LBUTTONDOWN = 0x0201
_WM_LBUTTONUP = 0x0202
_WM_LBUTTONDBLCLK = 0x0203
_WM_RBUTTONDOWN = 0x0204
_WM_RBUTTONUP = 0x0205
_WM_RBUTTONDBLCLK = 0x0206
_WM_MBUTTONDOWN = 0x0207
_WM_MBUTTONUP = 0x0208
_WM_MBUTTONDBLCLK = 0x0209
_WM_MOUSEWHEEL = 0x020A
_WM_XBUTTONDOWN = 0x020B
_WM_XBUTTONUP = 0x020C
_WM_XBUTTONDBLCLK = 0x020D
_WM_MOUSEHWHEEL = 0x020E
_WM_CAPTURECHANGED = 0x0215
_WM_POINTERUPDATE = 0x0245
_WM_POINTERDOWN = 0x0246
_WM_POINTERUP = 0x0247
_WM_POINTERENTER = 0x0249
_WM_POINTERLEAVE = 0x024A
_WM_POINTERACTIVATE = 0x024B
_WM_DPICHANGED = 0x02E0
_WM_MOUSELEAVE = 0x02A3
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
_TME_LEAVE = 0x00000002
_TME_NONCLIENT = 0x00000010
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
_DWMWCP_DONOTROUND = 1
_DWMWCP_ROUND = 2
_WIN10_BORDER_ACTIVE = "#333333"
_WIN10_BORDER_INACTIVE = "#A0A0A0"
_HTNOWHERE = 0
_HTCLIENT = 1
_HTCAPTION = 2
_HTMAXBUTTON = 9
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
_COMPOSITION_MOUSE_MESSAGES = frozenset({
    _WM_MOUSEMOVE, _WM_LBUTTONDOWN, _WM_LBUTTONUP, _WM_LBUTTONDBLCLK,
    _WM_RBUTTONDOWN, _WM_RBUTTONUP, _WM_RBUTTONDBLCLK,
    _WM_MBUTTONDOWN, _WM_MBUTTONUP, _WM_MBUTTONDBLCLK,
    _WM_MOUSEWHEEL, _WM_XBUTTONDOWN, _WM_XBUTTONUP, _WM_XBUTTONDBLCLK,
    _WM_MOUSEHWHEEL, _WM_MOUSELEAVE,
})
_COMPOSITION_POINTER_MESSAGES = frozenset({
    _WM_POINTERUPDATE, _WM_POINTERDOWN, _WM_POINTERUP, _WM_POINTERENTER,
    _WM_POINTERLEAVE, _WM_POINTERACTIVATE,
})
_MOUSE_DOWN_MESSAGES = frozenset({
    _WM_LBUTTONDOWN, _WM_LBUTTONDBLCLK,
    _WM_RBUTTONDOWN, _WM_RBUTTONDBLCLK,
    _WM_MBUTTONDOWN, _WM_MBUTTONDBLCLK,
    _WM_XBUTTONDOWN, _WM_XBUTTONDBLCLK,
})
_MOUSE_UP_MESSAGES = frozenset({
    _WM_LBUTTONUP, _WM_RBUTTONUP, _WM_MBUTTONUP, _WM_XBUTTONUP,
})
_WS_CHILD = 0x40000000
_WS_VISIBLE = 0x10000000
_WS_CLIPSIBLINGS = 0x04000000
_WS_CAPTION = 0x00C00000
_WS_OVERLAPPEDWINDOW = 0x00CF0000
_WS_THICKFRAME = 0x00040000
_WS_MAXIMIZEBOX = 0x00010000
_ERROR_ACCESS_DENIED = 5
_NON_RUDE_PROPERTY = "NonRudeHWND"
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


class _TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("hwndTrack", wintypes.HWND),
        ("dwHoverTime", wintypes.DWORD),
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
_user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(_POINT)]
_user32.ScreenToClient.restype = wintypes.BOOL
_user32.GetCapture.argtypes = []
_user32.GetCapture.restype = wintypes.HWND
_user32.TrackMouseEvent.argtypes = [ctypes.POINTER(_TRACKMOUSEEVENT)]
_user32.TrackMouseEvent.restype = wintypes.BOOL
_user32.IsZoomed.argtypes = [wintypes.HWND]
_user32.IsZoomed.restype = wintypes.BOOL
_user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_user32.MonitorFromWindow.restype = wintypes.HANDLE
_user32.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
_user32.MonitorFromRect.restype = wintypes.HANDLE
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
_user32.SendMessageW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
]
_user32.SendMessageW.restype = _LONG_PTR
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
_user32.SetPropW.restype = wintypes.BOOL
_user32.RemovePropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
_user32.RemovePropW.restype = wintypes.HANDLE
_user32.SystemParametersInfoW.argtypes = [
    wintypes.UINT, wintypes.UINT, wintypes.LPVOID, wintypes.UINT,
]
_user32.SystemParametersInfoW.restype = wintypes.BOOL
_user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
_user32.UnregisterClassW.restype = wintypes.BOOL
_user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
_user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
_user32.GetThreadDpiAwarenessContext.argtypes = []
_user32.GetThreadDpiAwarenessContext.restype = wintypes.HANDLE
_user32.AreDpiAwarenessContextsEqual.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_user32.AreDpiAwarenessContextsEqual.restype = wintypes.BOOL
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
_dwmapi.DwmDefWindowProc.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ctypes.POINTER(_LONG_PTR),
]
_dwmapi.DwmDefWindowProc.restype = wintypes.BOOL
try:
    _user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
    _user32.GetSystemMetricsForDpi.restype = ctypes.c_int
except AttributeError:
    pass

def _is_windows_10():
    return sys.getwindowsversion().build < 22000


def _is_per_monitor_v2():
    try:
        context = _user32.GetThreadDpiAwarenessContext()
        return bool(_user32.AreDpiAwarenessContextsEqual(
            context, ctypes.c_void_p(-4)
        ))
    except (AttributeError, OSError):
        return False


def _enable_dpi_awareness():
    ctypes.set_last_error(0)
    if _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
        return
    error = ctypes.get_last_error()
    if error != _ERROR_ACCESS_DENIED:
        raise ctypes.WinError(error)
    try:
        result = ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        result = -1
    if result != 0 and not _is_per_monitor_v2():
        warnings.warn(
            "Per-Monitor V2 DPI awareness was not enabled because the process "
            "DPI context is locked; window geometry may be off by 1px",
            RuntimeWarning,
            stacklevel=2,
        )


class FramelessWindow:
    """Own a Win32 host, an embedded WebView, and its JS controls.

    ``frame="normal"`` selects the system frame and shadow. On Windows 11 it
    uses rounded corners; on Windows 10 it uses the native rectangular frame.
    ``frame="rect"`` selects four square corners with no border or shadow.
    ``frame="rect_corner"`` keeps rounded titlebar corners with no border or
    shadow. ``frame="rect_shadow"`` selects square corners, no border, and a
    shadow. Windows 10 uses top glass and native non-client messages to retain the
    shadow and system transitions. Unsupported DWM attributes are ignored safely.
    """

    def __init__(
        self,
        title="pyminiwebview",
        width=1100,
        height=740,
        *,
        min_width=640,
        min_height=480,
        resizable=True,
        app_name="pyminiwebview",
        debug=False,
        frame="normal",
        dark_mode=False,
        bgcolor=0xFFFFFF,
        user_data_folder=None,
        clipboard_permission="default",
        on_maximize_change=None,
    ):
        if width <= 0 or height <= 0 or min_width <= 0 or min_height <= 0:
            raise ValueError("Window dimensions must be positive")
        if min_width > width or min_height > height:
            raise ValueError("Minimum dimensions must not exceed initial dimensions")
        if not isinstance(resizable, bool):
            raise TypeError("resizable must be a bool")
        if not isinstance(dark_mode, bool):
            raise TypeError("dark_mode must be a bool")
        if frame == "round":
            frame = "normal"
        elif frame == "square_shadow":
            frame = "rect_shadow"
        if frame not in ("normal", "rect", "rect_corner", "rect_shadow"):
            raise ValueError(
                'frame must be "normal", "rect", "rect_corner", or "rect_shadow"'
            )
        self.hwnd = None
        self.view = None
        self.bridge = None
        self._widget = None
        self.ready = False
        self._running = False
        self.on_maximize_change = on_maximize_change
        self._title = title
        self._width = width
        self._height = height
        self._min_width = min_width
        self._min_height = min_height
        self._resizable = resizable
        self._app_name = app_name
        self._debug = debug
        self._frame = frame
        self._dark_mode = dark_mode
        self._bgcolor = bgcolor
        self._dwm_frame_width = None
        self._applied_dwm_border_color = None
        self._nc_active = False
        self._user_data_folder = user_data_folder
        self._clipboard_permission = clipboard_permission
        self._class_name = f"PyMiniWebViewFrameless_{id(self):x}"
        self._class_atom = None
        self._background_brush = None
        self._wndproc_ref = _WNDPROC(self._wndproc)
        self._overlay_wndproc_ref = _WNDPROC(self._overlay_wndproc)
        self._overlay_class_name = f"{self._class_name}_Resize"
        self._overlay_class_atom = None
        self._resize_overlays = {}
        self._hinstance = _kernel32.GetModuleHandleW(None)
        self._move_serial = 0
        self._last_title_down = None
        self._resize_direction = None
        self._resize_origin = None
        self._resize_bounds = None
        self._maximize_button_rect = None
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

    def _use_dwm_frame(self):
        return not _is_windows_10() and self._frame not in ("rect", "rect_corner")

    def _window_style(self):
        style = _WS_OVERLAPPEDWINDOW
        if not self._resizable:
            style &= ~(_WS_THICKFRAME | _WS_MAXIMIZEBOX)
        return style

    def _corner_preference(self):
        if self._frame == "normal" and self._use_dwm_frame():
            return _DWMWCP_ROUND
        return _DWMWCP_DONOTROUND

    def _apply_corner_preference(self):
        self._set_dwm_attribute(
            _DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.c_int(self._corner_preference()),
        )

    def _has_shadow(self):
        return self._frame not in ("rect", "rect_corner")

    def _set_dwm_attribute(self, attribute, value):
        _dwmapi.DwmSetWindowAttribute(
            self.hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
        )

    def _extend_dwm_frame(self):
        if not self.hwnd:
            return
        width = int(not _user32.IsZoomed(self.hwnd) and self._has_shadow())
        side = width
        top = 0
        if (
            not self._use_dwm_frame()
            and self._frame in ("normal", "rect_shadow")
        ):
            side = 0
            top = width
        if width == self._dwm_frame_width:
            return
        margins = _MARGINS(side, side, top, side)
        _dwmapi.DwmExtendFrameIntoClientArea(self.hwnd, ctypes.byref(margins))
        self._dwm_frame_width = width

    def _apply_dark_mode(self):
        self._set_dwm_attribute(
            _DWMWA_USE_IMMERSIVE_DARK_MODE, wintypes.BOOL(self._dark_mode)
        )

    def _apply_dwm_frame_policy(self):
        policy = (
            _DWMNCRP_DISABLED
            if self._frame == "rect_corner"
            else _DWMNCRP_ENABLED
        )
        self._set_dwm_attribute(_DWMWA_NCRENDERING_POLICY, ctypes.c_int(policy))

    def _set_dwm_border_color(self, color):
        self._set_dwm_attribute(_DWMWA_BORDER_COLOR, wintypes.DWORD(color))

    def _resolve_border_color(self):
        if self._frame != "normal" and not _is_windows_10():
            return _DWMWA_COLOR_NONE
        return _DWMWA_COLOR_DEFAULT

    def _apply_dwm_border_color(self):
        if not self.hwnd:
            return
        color = self._resolve_border_color()
        if color == self._applied_dwm_border_color:
            return
        self._set_dwm_border_color(color)
        self._applied_dwm_border_color = color

    def _use_win10_normal_border(self):
        return self._frame == "normal" and _is_windows_10()

    def _install_win10_normal_border(self):
        script = """
        (() => {
          const install = () => {
            if (window.__pyminiwebview_normal_border) return;
            let active = document.hasFocus();
            let maximized = false;
            const border = document.createElement('div');
            border.setAttribute('aria-hidden', 'true');
            border.style.cssText = 'position:fixed;inset:0;box-sizing:border-box;' +
              'border:1px solid;pointer-events:none;z-index:2147483647;';
            const update = () => {
              border.style.display = maximized ? 'none' : 'block';
              border.style.borderColor = active ? '__ACTIVE__' : '__INACTIVE__';
            };
            window.__pyminiwebview_normal_border = (nextActive, nextMaximized) => {
              active = nextActive;
              maximized = nextMaximized;
              update();
            };
            window.addEventListener('focus', () => { active = true; update(); });
            window.addEventListener('blur', () => { active = false; update(); });
            document.documentElement.appendChild(border);
            update();
          };
          if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', install, {once:true});
          } else {
            install();
          }
        })();
        """
        self.view.js_init(
            script.replace("__ACTIVE__", _WIN10_BORDER_ACTIVE)
            .replace("__INACTIVE__", _WIN10_BORDER_INACTIVE)
        )

    def _update_win10_normal_border(self):
        if self.view is None or not self._use_win10_normal_border():
            return
        active = str(self._nc_active).lower()
        maximized = str(bool(_user32.IsZoomed(self.hwnd))).lower()
        self.view.js_eval(
            "if (window.__pyminiwebview_normal_border) "
            f"window.__pyminiwebview_normal_border({active},{maximized});"
        )

    def _register_window_class(self, class_name, wndproc, background=None):
        window_class = _WNDCLASSW()
        window_class.lpfnWndProc = wndproc
        window_class.hInstance = self._hinstance
        window_class.hbrBackground = background
        window_class.lpszClassName = class_name
        atom = _user32.RegisterClassW(ctypes.byref(window_class))
        if not atom:
            raise ctypes.WinError(ctypes.get_last_error())
        return atom

    def _create_native_resize(self):
        self._overlay_class_atom = self._register_window_class(
            self._overlay_class_name, self._overlay_wndproc_ref
        )
        edges = ("t",)
        if not self._use_dwm_frame():
            edges = ("t", "l", "r", "b")
        for edge in edges:
            overlay = _user32.CreateWindowExW(
                0, self._overlay_class_name, None,
                _WS_CHILD | _WS_VISIBLE | _WS_CLIPSIBLINGS,
                0, 0, 0, 0, self.hwnd, None, self._hinstance, None,
            )
            if not overlay:
                raise ctypes.WinError(ctypes.get_last_error())
            self._resize_overlays[edge] = overlay

    def _layout_native_resize(self, width, height):
        if not self._resize_overlays:
            return
        if _user32.IsZoomed(self.hwnd):
            for overlay in self._resize_overlays.values():
                _user32.ShowWindow(overlay, _SW_HIDE)
            return
        padding = self._ring_padding()
        side_height = max(0, height - 2 * padding)
        bounds = {
            "t": (0, 0, width, padding),
            "l": (0, padding, padding, side_height),
            "r": (width - padding, padding, padding, side_height),
            "b": (0, height - padding, width, padding),
        }
        for edge, overlay in self._resize_overlays.items():
            _user32.SetWindowPos(
                overlay, None, *bounds[edge], _SWP_NOACTIVATE
            )
            _user32.ShowWindow(overlay, _SW_SHOWNOACTIVATE)

    def _overlay_wndproc(self, hwnd, message, wparam, lparam):
        if message == _WM_ERASEBKGND:
            return 1
        if message == _WM_NCHITTEST and self.hwnd:
            return self._native_hit_test(lparam)
        if (
            message == _WM_NCLBUTTONDOWN
            and wparam in _HT_RESIZE_CODES
            and self.hwnd
        ):
            _user32.SendMessageW(self.hwnd, message, wparam, lparam)
            return 0
        if message == _WM_NCDESTROY:
            for edge, overlay in list(self._resize_overlays.items()):
                if overlay == hwnd:
                    del self._resize_overlays[edge]
        return _user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _native_hit_test(self, lparam):
        if not self._resizable or _user32.IsZoomed(self.hwnd):
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

    def _dwm_def_window_proc(self, hwnd, message, wparam, lparam):
        result = _LONG_PTR()
        handled = _dwmapi.DwmDefWindowProc(
            hwnd, message, wparam, lparam, ctypes.byref(result)
        )
        return bool(handled), result.value

    def _composition_hit_test(self, lparam, native_hit):
        rect = self._maximize_button_rect
        if native_hit != _HTCLIENT or not self._resizable or rect is None:
            return native_hit
        point = _POINT(
            ctypes.c_short(lparam & 0xFFFF).value,
            ctypes.c_short((lparam >> 16) & 0xFFFF).value,
        )
        if not _user32.ScreenToClient(self.hwnd, ctypes.byref(point)):
            return native_hit
        left, top, right, bottom = rect
        if left <= point.x < right and top <= point.y < bottom:
            return _HTMAXBUTTON
        return native_hit

    def _track_composition_mouse_leave(self, nonclient):
        event = _TRACKMOUSEEVENT(
            ctypes.sizeof(_TRACKMOUSEEVENT),
            _TME_LEAVE | (_TME_NONCLIENT if nonclient else 0),
            self.hwnd,
            0,
        )
        _user32.TrackMouseEvent(ctypes.byref(event))

    def _forward_composition_mouse(self, message, wparam, lparam):
        if not self.view:
            return False
        if message in (_WM_MOUSEMOVE, _WM_NCMOUSEMOVE):
            self._track_composition_mouse_leave(message == _WM_NCMOUSEMOVE)
        handled = self.view.composition_mouse_input(message, wparam, lparam)
        if not handled:
            return False
        if message in _MOUSE_DOWN_MESSAGES or message in (
            _WM_NCLBUTTONDOWN, _WM_NCLBUTTONDBLCLK
        ):
            self.view.set_focus()
            if _user32.GetCapture() != self.hwnd:
                _user32.SetCapture(self.hwnd)
        elif (
            message in _MOUSE_UP_MESSAGES or message == _WM_NCLBUTTONUP
        ) and _user32.GetCapture() == self.hwnd:
            _user32.ReleaseCapture()
        return True

    def _forward_composition_pointer(self, message, wparam):
        if not self.view:
            return False
        handled = self.view.composition_pointer_input(message, wparam)
        if not handled:
            return False
        if message == _WM_POINTERDOWN:
            self.view.set_focus()
            if _user32.GetCapture() != self.hwnd:
                _user32.SetCapture(self.hwnd)
        elif message == _WM_POINTERUP and _user32.GetCapture() == self.hwnd:
            _user32.ReleaseCapture()
        return True

    def _layout_webview(self):
        if not self.hwnd or not self.view or not self._widget:
            return
        rect = wintypes.RECT()
        if not _user32.GetClientRect(self.hwnd, ctypes.byref(rect)):
            return
        width = max(0, rect.right - rect.left)
        height = max(0, rect.bottom - rect.top)
        _user32.SetWindowPos(
            self._widget, None, 0, 0, width, height,
            _SWP_NOZORDER | _SWP_NOACTIVATE,
        )
        self.view.composition_resize()
        self._layout_native_resize(width, height)

    def _create(self):
        _enable_dpi_awareness()
        self._background_brush = _gdi32.CreateSolidBrush(self._bgcolor)
        if not self._background_brush:
            raise ctypes.WinError(ctypes.get_last_error())
        self._class_atom = self._register_window_class(
            self._class_name, self._wndproc_ref, self._background_brush
        )

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
        style = self._window_style()
        self.hwnd = _user32.CreateWindowExW(
            0, self._class_name, self._title, style,
            x, y, self._width, self._height,
            None, None, self._hinstance, None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        _user32.SetPropW(self.hwnd, _NON_RUDE_PROPERTY, ctypes.c_void_p(1))

        self._apply_corner_preference()
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
            composition_hosting=True,
        )
        self._widget = self.view.get_native_handle(
            pyminiwebview.NATIVE_HANDLE_KIND_UI_WIDGET
        )
        if self._resizable:
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
            "__window_set_maximize_rect": self.set_maximize_button_rect,
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
        if self._use_win10_normal_border():
            self._install_win10_normal_border()
        self.view.configure_app_mode()

    def reveal(self):
        if not self.hwnd or not self.view:
            return False
        _user32.ShowWindow(self.hwnd, _SW_SHOW)
        _user32.UpdateWindow(self.hwnd)
        self.ready = True
        self._dwm_frame_width = None
        self._extend_dwm_frame()
        _user32.SetForegroundWindow(self.hwnd)
        self.view.set_focus()
        self._update_win10_normal_border()
        self._notify_maximized_state()
        return True

    def minimize(self):
        if not self.hwnd:
            return False
        _user32.ShowWindow(self.hwnd, _SW_MINIMIZE)
        return True

    def toggle_maximize(self):
        if not self.hwnd or not self._resizable:
            return False
        _user32.ShowWindow(
            self.hwnd, _SW_RESTORE if _user32.IsZoomed(self.hwnd) else _SW_MAXIMIZE
        )
        maximized = bool(_user32.IsZoomed(self.hwnd))
        self._notify_maximized_state()
        return maximized

    def set_maximize_button_rect(self, left, top, right, bottom):
        values = tuple(float(value) for value in (left, top, right, bottom))
        if not all(math.isfinite(value) for value in values):
            raise ValueError("maximize button rectangle must be finite")
        left, top, right, bottom = (round(value) for value in values)
        self._maximize_button_rect = (
            (left, top, right, bottom)
            if right > left and bottom > top else None
        )
        return True

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
            or not self._resizable
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

    def _get_monitor_info(self, monitor):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if not _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        return info

    def _handle_dpi_changed(self, hwnd, lparam):
        suggested = ctypes.cast(lparam, ctypes.POINTER(wintypes.RECT)).contents
        _user32.SetWindowPos(
            hwnd, None, suggested.left, suggested.top,
            suggested.right - suggested.left, suggested.bottom - suggested.top,
            _SWP_NOZORDER | _SWP_NOACTIVATE,
        )
        return 0

    def _handle_nc_calc_size(self, hwnd, wparam, lparam):
        use_dwm_frame = self._use_dwm_frame()
        if not use_dwm_frame and not _user32.IsZoomed(hwnd):
            return 0
        if wparam:
            params = ctypes.cast(
                lparam, ctypes.POINTER(_NCCALCSIZE_PARAMS)
            ).contents
            if _user32.IsZoomed(hwnd):
                monitor = _user32.MonitorFromRect(
                    ctypes.byref(params.rgrc[0]), _MONITOR_DEFAULTTONEAREST
                )
                info = self._get_monitor_info(monitor)
                if info is not None:
                    params.rgrc[0] = info.rcWork
            elif use_dwm_frame:
                padding = self._ring_padding()
                params.rgrc[0].left += padding
                params.rgrc[0].right -= padding
                params.rgrc[0].bottom -= padding
        return 0

    def _handle_get_min_max_info(self, hwnd, lparam):
        info = ctypes.cast(lparam, ctypes.POINTER(_MINMAXINFO)).contents
        info.ptMinTrackSize = _POINT(self._min_width, self._min_height)
        if not self._resizable:
            info.ptMinTrackSize = _POINT(self._width, self._height)
            info.ptMaxTrackSize = _POINT(self._width, self._height)
        monitor = _user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
        monitor_info = self._get_monitor_info(monitor)
        if monitor_info is not None:
            work = monitor_info.rcWork
            monitor_bounds = monitor_info.rcMonitor
            info.ptMaxPosition = _POINT(
                work.left - monitor_bounds.left, work.top - monitor_bounds.top
            )
            info.ptMaxSize = _POINT(
                work.right - work.left, work.bottom - work.top
            )
        return 0

    def _wndproc(self, hwnd, message, wparam, lparam):
        if message == _WM_NCCALCSIZE:
            return self._handle_nc_calc_size(hwnd, wparam, lparam)
        if (
            message == _WM_NCPAINT
            and not self._use_dwm_frame()
            and self._frame == "rect_corner"
        ):
            return 0
        if message == _WM_NCACTIVATE:
            border_color = self._resolve_border_color()
            self._set_dwm_border_color(border_color)
            self._applied_dwm_border_color = border_color
            win10_normal = self._use_win10_normal_border()
            if win10_normal:
                self._nc_active = bool(wparam)
            if not self._use_dwm_frame() and self._frame == "rect_corner":
                return 1
            result = _user32.DefWindowProcW(hwnd, message, wparam, -1)
            if win10_normal:
                self._update_win10_normal_border()
            return result
        if message in (_WM_NCUAHDRAWCAPTION, _WM_NCUAHDRAWFRAME):
            return 0
        if message == _WM_GETMINMAXINFO:
            return self._handle_get_min_max_info(hwnd, lparam)
        if message == _WM_DPICHANGED:
            return self._handle_dpi_changed(hwnd, lparam)
        if message == _WM_SETCURSOR and self.view:
            if (lparam & 0xFFFF) == _HTCLIENT and self.view.composition_cursor():
                return 1
        if message == _WM_NCMOUSELEAVE and self.view:
            self.view.composition_mouse_input(_WM_MOUSELEAVE, 0, 0)
        if message == _WM_NCMOUSEMOVE and wparam == _HTMAXBUTTON:
            self._forward_composition_mouse(message, wparam, lparam)
            handled, result = self._dwm_def_window_proc(
                hwnd, message, wparam, lparam
            )
            if handled:
                return result
        elif (
            message in (_WM_NCLBUTTONDOWN, _WM_NCLBUTTONUP, _WM_NCLBUTTONDBLCLK)
            and wparam == _HTMAXBUTTON
            and self._forward_composition_mouse(message, wparam, lparam)
        ):
            return 0
        if message == _WM_NCHITTEST:
            handled, result = self._dwm_def_window_proc(
                hwnd, message, wparam, lparam
            )
            if handled and result not in (_HTCLIENT, _HTNOWHERE):
                return result
            native_hit = self._native_hit_test(lparam)
            return self._composition_hit_test(lparam, native_hit)
        if message == _WM_MOUSEMOVE and self._resize_direction:
            self._resize()
            return 0
        if message == _WM_LBUTTONUP and self._resize_direction:
            self._finish_resize()
            _user32.ReleaseCapture()
            return 0
        if (
            message in _COMPOSITION_POINTER_MESSAGES
            and self._forward_composition_pointer(message, wparam)
        ):
            return 0
        if (
            message in _COMPOSITION_MOUSE_MESSAGES
            and self._forward_composition_mouse(message, wparam, lparam)
        ):
            return 0
        if message == _WM_CAPTURECHANGED:
            self._finish_resize()
        if message == _WM_MOVE:
            self._move_serial += 1
            if self.view:
                self.view.notify_parent_position()
        elif message == _WM_SIZE:
            if self.view:
                self.view.composition_visible(wparam != _SIZE_MINIMIZED)
            if wparam != _SIZE_MINIMIZED:
                self._layout_webview()
                self._apply_dwm_border_color()
            self._extend_dwm_frame()
            self._update_win10_normal_border()
            self._notify_maximized_state()
        elif message == _WM_CLOSE:
            _user32.DestroyWindow(hwnd)
            return 0
        elif message == _WM_DESTROY:
            _user32.RemovePropW(hwnd, _NON_RUDE_PROPERTY)
            self.hwnd = None
            if self.view and self._running:
                try:
                    self.view.terminate()
                except RuntimeError:
                    pass
            return 0
        return _user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def run(self):
        if not self.view:
            raise RuntimeError("FramelessWindow is closed")
        self._running = True
        try:
            self.view.run()
        finally:
            self._running = False

    def close(self):
        if self._resize_direction:
            self._finish_resize()
            _user32.ReleaseCapture()
        if self.hwnd:
            _user32.DestroyWindow(self.hwnd)
        if self.bridge:
            self.bridge.close()
            self.bridge = None
        if self.view:
            self.view.close()
            self.view = None
        self._widget = None
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
