import ctypes
import logging
import uuid
from ctypes import wintypes


_logger = logging.getLogger(__name__)

_NIM_ADD = 0
_NIM_DELETE = 2
_NIF_MESSAGE = 0x01
_NIF_ICON = 0x02
_NIF_TIP = 0x04
_WM_USER = 0x0400
_WM_TRAYICON = _WM_USER + 1
_WM_LBUTTONUP = 0x0202
_WM_RBUTTONUP = 0x0205
_IDI_APPLICATION = 32512
_HWND_MESSAGE = ctypes.c_void_p(-3).value


class _WNDCLASSW(ctypes.Structure):
    pass


_WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
    wintypes.WPARAM, wintypes.LPARAM,
)
_WNDCLASSW._fields_ = [
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


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeout", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", _GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.DefWindowProcW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
]
_user32.DefWindowProcW.restype = ctypes.c_ssize_t
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
_user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
_user32.UnregisterClassW.restype = wintypes.BOOL
_user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
_user32.LoadIconW.restype = wintypes.HICON
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_shell32.Shell_NotifyIconW.argtypes = [
    wintypes.DWORD, ctypes.POINTER(_NOTIFYICONDATAW)
]
_shell32.Shell_NotifyIconW.restype = wintypes.BOOL


class TrayIcon:
    """Create a tray icon on the thread that owns the application's message loop."""

    def __init__(self, parent_hwnd=None, tooltip="App", on_click=None,
                 on_left_click=None, on_right_click=None):
        if len(tooltip.encode("utf-16-le")) // 2 > 127:
            raise ValueError("tooltip must fit in 127 UTF-16 code units")
        self._on_click = on_click
        self._on_left_click = on_left_click
        self._on_right_click = on_right_click
        self._class_name = f"PyMiniWebViewTray_{uuid.uuid4().hex}"
        self._hinstance = _kernel32.GetModuleHandleW(None)
        self._hwnd = None
        self._class_registered = False
        self._icon_added = False
        self._wndproc_ref = _WNDPROC(self._wndproc)
        try:
            self._hwnd = self._create_window(parent_hwnd)
            self._add_icon(tooltip)
        except BaseException:
            self.remove()
            raise

    @property
    def hwnd(self):
        return self._hwnd

    def _create_window(self, parent):
        window_class = _WNDCLASSW()
        window_class.lpfnWndProc = self._wndproc_ref
        window_class.hInstance = self._hinstance
        window_class.lpszClassName = self._class_name
        if not _user32.RegisterClassW(ctypes.byref(window_class)):
            raise ctypes.WinError(ctypes.get_last_error())
        self._class_registered = True
        hwnd = _user32.CreateWindowExW(
            0, self._class_name, "Tray", 0, 0, 0, 0, 0,
            _HWND_MESSAGE if parent is None else parent,
            None, self._hinstance, None,
        )
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        return hwnd

    def _notify_data(self):
        data = _NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = 1
        return data

    def _add_icon(self, tooltip):
        data = self._notify_data()
        data.uFlags = _NIF_MESSAGE | _NIF_ICON | _NIF_TIP
        data.uCallbackMessage = _WM_TRAYICON
        data.hIcon = _user32.LoadIconW(
            None, ctypes.cast(ctypes.c_void_p(_IDI_APPLICATION), wintypes.LPCWSTR)
        )
        data.szTip = tooltip
        if not _shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(data)):
            raise ctypes.WinError(ctypes.get_last_error())
        self._icon_added = True

    def _wndproc(self, hwnd, message, wparam, lparam):
        if message == _WM_TRAYICON:
            if lparam == _WM_LBUTTONUP:
                callback = self._on_left_click or self._on_click
            elif lparam == _WM_RBUTTONUP:
                callback = self._on_right_click or self._on_click
            else:
                callback = None
            if callback:
                callback()
            return 0
        return _user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def remove(self):
        if self._hwnd is not None:
            if self._icon_added:
                _shell32.Shell_NotifyIconW(
                    _NIM_DELETE, ctypes.byref(self._notify_data())
                )
                self._icon_added = False
            if not _user32.DestroyWindow(self._hwnd):
                _logger.warning(
                    "TrayIcon window destruction failed (Win32 error %s)",
                    ctypes.get_last_error(),
                )
            self._hwnd = None
        if self._class_registered:
            _user32.UnregisterClassW(self._class_name, self._hinstance)
            self._class_registered = False
