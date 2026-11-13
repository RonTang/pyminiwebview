import ctypes
import gc
import json
import os
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROCESS_START = time.perf_counter()
IMPORT_START = time.perf_counter()
import pyminiwebview

print(f"import: {(time.perf_counter() - IMPORT_START) * 1000:.1f} ms")

BG_COLOR = "#f4f4f8"
BORDER_COLOR = 0x00F8F4F4
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCACTIVATE = 0x0086
WM_NCLBUTTONDOWN = 0x00A1
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_SIZE = 0x0005
WM_MOVE = 0x0003
WM_GETMINMAXINFO = 0x0024
SIZE_MAXIMIZED = 2
SW_SHOW = 5
SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
MONITOR_DEFAULTTONEAREST = 2
SM_CXFRAME = 32
SM_CXPADDEDBORDER = 92
SM_CXDOUBLECLK = 36
SM_CYDOUBLECLK = 37
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWCP_ROUNDSMALL = 3
HTCLIENT = 1
HTCAPTION = 2
HTLEFT, HTRIGHT, HTTOP, HTBOTTOM = 10, 11, 12, 15
HTTOPLEFT, HTTOPRIGHT = 13, 14
HTBOTTOMLEFT, HTBOTTOMRIGHT = 16, 17
HT_CODES = {
    "l": HTLEFT,
    "r": HTRIGHT,
    "t": HTTOP,
    "b": HTBOTTOM,
    "tl": HTTOPLEFT,
    "tr": HTTOPRIGHT,
    "bl": HTBOTTOMLEFT,
    "br": HTBOTTOMRIGHT,
}
WS_OVERLAPPEDWINDOW = 0x00CF0000

LONG_PTR = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(
    LONG_PTR, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class Point(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class NccalculateParams(ctypes.Structure):
    _fields_ = [("rgrc", Rect * 3), ("lppos", wintypes.LPVOID)]


class MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", Rect),
        ("rcWork", Rect),
        ("dwFlags", wintypes.DWORD),
    ]


class MinMaxInfo(ctypes.Structure):
    _fields_ = [
        ("ptReserved", Point),
        ("ptMaxSize", Point),
        ("ptMaxPosition", Point),
        ("ptMinTrackSize", Point),
        ("ptMaxTrackSize", Point),
    ]


class WndClass(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

user32.DefWindowProcW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.DefWindowProcW.restype = LONG_PTR
user32.RegisterClassW.argtypes = [ctypes.POINTER(WndClass)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.UpdateWindow.argtypes = [wintypes.HWND]
user32.UpdateWindow.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(Rect)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.IsZoomed.restype = wintypes.BOOL
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.GetDpiForWindow.argtypes = [wintypes.HWND]
user32.GetDpiForWindow.restype = wintypes.UINT
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetDoubleClickTime.restype = wintypes.UINT
user32.GetCursorPos.argtypes = [ctypes.POINTER(Point)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.ReleaseCapture.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.PostMessageW.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.SystemParametersInfoW.argtypes = [
    wintypes.UINT,
    wintypes.UINT,
    wintypes.LPVOID,
    wintypes.UINT,
]
user32.SystemParametersInfoW.restype = wintypes.BOOL
user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
user32.UnregisterClassW.restype = wintypes.BOOL
user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
gdi32.CreateSolidBrush.argtypes = [wintypes.DWORD]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
dwmapi.DwmSetWindowAttribute.argtypes = [
    wintypes.HWND,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
]
dwmapi.DwmSetWindowAttribute.restype = wintypes.LONG


def load_html():
    fixture = (
        Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "neon.html"
    )
    return fixture.read_text(encoding="utf-8")


class NeonWindow:
    def __init__(self, html):
        self.html = html
        self.hwnd = None
        self.view = None
        self.class_name = "NeonPyMiniWebViewHost"
        self.class_atom = None
        self.background_brush = None
        self.wndproc_ref = WNDPROC(self.wndproc)
        self.hinstance = kernel32.GetModuleHandleW(None)
        self.callbacks = []
        self.result = {}
        self.started = time.perf_counter()
        self.move_serial = 0
        self.last_title_down = None
        self.maximized = False
        self.close_timer = None

    def ring_padding(self):
        if not self.hwnd:
            return 0
        dpi = user32.GetDpiForWindow(self.hwnd) or 96
        try:
            metrics = user32.GetSystemMetricsForDpi
            metrics.argtypes = [ctypes.c_int, wintypes.UINT]
            metrics.restype = ctypes.c_int
            value = metrics(SM_CXFRAME, dpi) + metrics(SM_CXPADDEDBORDER, dpi)
        except (AttributeError, TypeError, OSError):
            value = user32.GetSystemMetrics(SM_CXFRAME) + user32.GetSystemMetrics(
                SM_CXPADDEDBORDER
            )
        return max(1, value - 1)

    def create(self):
        if not user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.background_brush = gdi32.CreateSolidBrush(BORDER_COLOR)
        window_class = WndClass()
        window_class.lpfnWndProc = self.wndproc_ref
        window_class.hInstance = self.hinstance
        window_class.hbrBackground = self.background_brush
        window_class.lpszClassName = self.class_name
        self.class_atom = user32.RegisterClassW(ctypes.byref(window_class))
        if not self.class_atom:
            raise ctypes.WinError(ctypes.get_last_error())

        work_area = wintypes.RECT()
        user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area), 0)
        x = work_area.left + (work_area.right - work_area.left - 880) // 2
        y = work_area.top + (work_area.bottom - work_area.top - 600) // 2
        self.hwnd = user32.CreateWindowExW(
            0,
            self.class_name,
            "NEON",
            WS_OVERLAPPEDWINDOW,
            x,
            y,
            880,
            600,
            None,
            None,
            self.hinstance,
            None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

        corner = ctypes.c_int(DWMWCP_ROUNDSMALL)
        color = ctypes.c_int(BORDER_COLOR)
        dwmapi.DwmSetWindowAttribute(
            self.hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner), 4
        )
        dwmapi.DwmSetWindowAttribute(
            self.hwnd, DWMWA_BORDER_COLOR, ctypes.byref(color), 4
        )
        dwmapi.DwmSetWindowAttribute(
            self.hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(color), 4
        )

        self.view = pyminiwebview.WebView(
            window=self.hwnd,
            autosize=True,
            bgcolor=BORDER_COLOR,
            app_name="pyminiwebview-local-test",
            user_data_folder=str(
                Path(__file__).resolve().parent.parent / ".webview-test-data"
            ),
        )
        padding = self.ring_padding()
        if not user32.SetWindowPos(
            self.hwnd,
            None,
            0,
            0,
            880 + 2 * padding,
            600 + padding,
            SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        self.bind_api()
        self.view.configure_app_mode()
        self.view.set_html(self.html)
        print(f"create: {(time.perf_counter() - self.started) * 1000:.1f} ms")

    def bind_api(self):
        api = {
            "__neon_minimize": self.minimize,
            "__neon_toggle_maximize": self.toggle_maximize,
            "__neon_close": self.close,
            "__neon_start_move": self.start_move,
            "__neon_start_resize": self.start_resize,
            "__neon_reveal": self.reveal,
        }
        for name, function in api.items():
            callback = self.make_callback(function)
            self.callbacks.append(callback)
            self.view.js_bind(name, callback)
        self.view.js_bind("__test_ready", self.on_ready)
        self.view.js_init(
            r"""
window.pywebview = {api: {
  minimize: () => __neon_minimize(),
  toggle_maximize: () => __neon_toggle_maximize(),
  close: () => __neon_close(),
  start_move: () => __neon_start_move(),
  start_resize: (direction) => __neon_start_resize(direction),
  reveal_window: () => __neon_reveal()
}};
document.addEventListener('DOMContentLoaded', () => {
  requestAnimationFrame(() => requestAnimationFrame(() => {
    window.dispatchEvent(new Event('pywebviewready'));
    __test_ready({
      title: document.title,
      heading: document.querySelector('h1').innerText,
      buttons: document.querySelectorAll('button').length,
      width: window.innerWidth,
      height: window.innerHeight
    });
  }));
});
"""
        )

    def make_callback(self, function):
        def callback(request_id, request):
            try:
                value = function(*json.loads(request))
                self.view.js_return(request_id, 0, json.dumps(value))
            except Exception as error:
                self.view.js_return(request_id, 1, json.dumps(str(error)))

        return callback

    def reveal(self):
        if self.hwnd:
            user32.ShowWindow(self.hwnd, SW_SHOW)
            user32.UpdateWindow(self.hwnd)
            user32.SetForegroundWindow(self.hwnd)
            self.view.set_focus()
        return True

    def on_ready(self, request_id, request):
        self.result.update(json.loads(request)[0])
        print(
            f"first frame: {(time.perf_counter() - self.started) * 1000:.1f} ms"
        )
        print(
            "process start to first frame: "
            f"{(time.perf_counter() - PROCESS_START) * 1000:.1f} ms"
        )
        print(f"page: {self.result}")
        self.view.js_return(request_id, 0, "null")
        self.reveal()

        close_after_ms = int(os.environ.get("NEON_TEST_CLOSE_MS", "0"))
        if close_after_ms > 0:
            self.close_timer = threading.Timer(
                close_after_ms / 1000, self.close_from_background
            )
            self.close_timer.start()

    def close_from_background(self):
        if self.view and self.hwnd:
            self.view.dispatch(lambda: user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0))

    def minimize(self):
        if self.hwnd:
            user32.ShowWindow(self.hwnd, SW_MINIMIZE)
        return None

    def toggle_maximize(self):
        if not self.hwnd:
            return False
        user32.ShowWindow(
            self.hwnd, SW_RESTORE if user32.IsZoomed(self.hwnd) else SW_MAXIMIZE
        )
        self.maximized = bool(user32.IsZoomed(self.hwnd))
        return self.maximized

    def close(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        return None

    def post_nonclient_action(self, hit_code):
        if not self.hwnd:
            return False
        point = Point()
        user32.ReleaseCapture()
        if not user32.GetCursorPos(ctypes.byref(point)):
            return False
        lparam = ((point.y & 0xFFFF) << 16) | (point.x & 0xFFFF)
        return bool(user32.PostMessageW(self.hwnd, WM_NCLBUTTONDOWN, hit_code, lparam))

    def start_move(self):
        point = Point()
        if not self.hwnd or not user32.GetCursorPos(ctypes.byref(point)):
            return False
        now = time.monotonic()
        candidate = (now, self.move_serial, point.x, point.y)
        previous = self.last_title_down
        self.last_title_down = candidate
        is_double = bool(
            previous
            and now - previous[0] <= user32.GetDoubleClickTime() / 1000
            and previous[1] == self.move_serial
            and abs(point.x - previous[2]) <= user32.GetSystemMetrics(SM_CXDOUBLECLK) / 2
            and abs(point.y - previous[3]) <= user32.GetSystemMetrics(SM_CYDOUBLECLK) / 2
        )
        if is_double:
            self.last_title_down = None
            self.toggle_maximize()
            return True
        return self.post_nonclient_action(HTCAPTION)

    def start_resize(self, direction):
        if (
            not self.hwnd
            or direction not in HT_CODES
            or user32.IsZoomed(self.hwnd)
        ):
            return False
        return self.post_nonclient_action(HT_CODES[direction])

    def update_maximized_state(self):
        if not self.view or not self.result:
            return
        maximized = bool(user32.IsZoomed(self.hwnd))
        self.maximized = maximized
        icon = "ICON_REST" if maximized else "ICON_MAX"
        self.view.js_eval(
            f"var b=document.getElementById('btn-max');"
            f"if(b)b.innerHTML=window.{icon};"
            f"document.body.classList.toggle('neon-max',{str(maximized).lower()});"
        )

    def wndproc(self, hwnd, message, wparam, lparam):
        if message == WM_NCCALCSIZE:
            if wparam:
                params = ctypes.cast(lparam, ctypes.POINTER(NccalculateParams)).contents
                if user32.IsZoomed(hwnd):
                    info = MonitorInfo()
                    info.cbSize = ctypes.sizeof(info)
                    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
                    if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                        params.rgrc[0] = info.rcWork
                else:
                    padding = self.ring_padding()
                    params.rgrc[0].left += padding
                    params.rgrc[0].right -= padding
                    params.rgrc[0].bottom -= padding
            return 0
        if message == WM_NCACTIVATE:
            return 1
        if message == WM_GETMINMAXINFO:
            info = ctypes.cast(lparam, ctypes.POINTER(MinMaxInfo)).contents
            info.ptMinTrackSize = Point(640, 480)
            monitor_info = MonitorInfo()
            monitor_info.cbSize = ctypes.sizeof(monitor_info)
            monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info)):
                work = monitor_info.rcWork
                info.ptMaxPosition = Point(work.left, work.top)
                info.ptMaxSize = Point(work.right - work.left, work.bottom - work.top)
            return 0
        if message == WM_NCHITTEST:
            if user32.IsZoomed(hwnd):
                return HTCLIENT
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            rect = Rect()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return HTCLIENT
            padding = self.ring_padding()
            left = x - rect.left
            right = rect.right - x
            bottom = rect.bottom - y
            if left < padding and bottom < padding:
                return HTBOTTOMLEFT
            if right < padding and bottom < padding:
                return HTBOTTOMRIGHT
            if left < padding:
                return HTLEFT
            if right < padding:
                return HTRIGHT
            if bottom < padding:
                return HTBOTTOM
            return HTCLIENT
        if message == WM_MOVE:
            self.move_serial += 1
            if self.view:
                self.view.notify_parent_position()
        elif message == WM_SIZE:
            self.update_maximized_state()
        elif message == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        elif message == WM_DESTROY:
            self.hwnd = None
            if self.view:
                self.view.terminate()
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def run(self):
        self.view.run()

    def dispose(self):
        if self.close_timer:
            self.close_timer.cancel()
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
        view = self.view
        self.view = None
        if view:
            view.close()
        del view
        gc.collect()
        if self.class_atom:
            user32.UnregisterClassW(self.class_name, self.hinstance)
            self.class_atom = None
        if self.background_brush:
            gdi32.DeleteObject(self.background_brush)
            self.background_brush = None


def main():
    app = NeonWindow(load_html())
    try:
        app.create()
        app.run()
        if app.result:
            assert app.result["title"] == "NEON"
            assert "自定义标题栏" in app.result["heading"]
            assert app.result["buttons"] == 5
            assert app.result["width"] > 0 and app.result["height"] > 0
            print("NEON borderless window and JavaScript bridge: OK")
    finally:
        app.dispose()


if __name__ == "__main__":
    main()
