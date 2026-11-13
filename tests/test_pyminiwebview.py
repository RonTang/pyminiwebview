import ctypes
import gc
import json
import sys
import threading
from ctypes import wintypes

import pytest

if sys.platform != "win32":
    pytest.skip("pyminiwebview only supports Windows", allow_module_level=True)

import pyminiwebview


@pytest.fixture
def webview(tmp_path):
    instance = pyminiwebview.WebView(
        width=320,
        height=240,
        user_data_folder=str(tmp_path / "webview-data"),
    )
    yield instance
    del instance
    gc.collect()


def test_bind_navigate_destroy_refcount_is_stable(webview):
    calls = []

    def callback(request_id, request):
        calls.append((request_id, request))

    baseline = sys.getrefcount(callback)
    for _ in range(1000):
        webview.js_bind("fromPythonTests", callback)
        assert sys.getrefcount(callback) == baseline + 1
        webview.js_unbind("fromPythonTests")
        assert sys.getrefcount(callback) == baseline

    webview.navigate("data:text/html,%3Cp%3Enavigation%3C%2Fp%3E")
    webview.set_html("<p>done</p>")
    assert sys.getrefcount(callback) == baseline


def test_javascript_callback_and_return(webview):
    received = []

    def callback(request_id, request):
        received.append(json.loads(request))
        webview.js_return(request_id, 0, '"python result"')
        webview.terminate()

    webview.js_bind("callPython", callback)
    webview.set_html("<script>callPython(42, 'ok')</script>")
    watchdog = threading.Timer(5, webview.terminate)
    watchdog.start()
    try:
        webview.run()
    finally:
        watchdog.cancel()
    assert received == [[42, "ok"]]


def test_run_releases_gil_and_dispatch_uses_ui_thread(webview):
    timer_fired = threading.Event()
    dispatch_thread = []
    errors = []
    ui_thread = threading.get_ident()

    def stop_from_dispatch():
        dispatch_thread.append(threading.get_ident())
        webview.terminate()

    def background_work():
        try:
            timer_fired.set()
            webview.dispatch(stop_from_dispatch)
        except BaseException as error:
            errors.append(error)
            webview.terminate()

    timer = threading.Timer(0.05, background_work)
    watchdog = threading.Timer(5, webview.terminate)
    timer.start()
    watchdog.start()
    try:
        webview.run()
    finally:
        timer.cancel()
        watchdog.cancel()

    assert not errors
    assert timer_fired.is_set()
    assert dispatch_thread == [ui_thread]


def test_queued_dispatch_releases_callable_on_destruction(tmp_path):
    calls = []

    def callback():
        calls.append("called")

    instance = pyminiwebview.WebView(
        user_data_folder=str(tmp_path / "webview-data")
    )
    baseline = sys.getrefcount(callback)
    instance.dispatch(callback)
    assert sys.getrefcount(callback) == baseline + 1
    del instance
    gc.collect()
    assert calls == ["called"]
    assert sys.getrefcount(callback) == baseline


def test_configure_app_mode_smoke(webview):
    webview.configure_app_mode()
    webview.configure_app_mode()


def test_notify_parent_position(webview):
    webview.notify_parent_position()


def test_invalid_arguments_raise_python_exceptions(webview, tmp_path):
    with pytest.raises(TypeError):
        pyminiwebview.WebView(width="wide")
    with pytest.raises(ValueError):
        pyminiwebview.WebView(window=0x7FFFFFFF00000000)
    with pytest.raises(ValueError):
        pyminiwebview.WebView(clipboard_permission="always")
    with pytest.raises(ValueError):
        pyminiwebview.WebView(width=0)
    with pytest.raises(TypeError):
        webview.js_bind("notCallable", 42)
    with pytest.raises(TypeError):
        webview.js_eval(42)
    with pytest.raises(KeyError):
        webview.js_unbind("missing")
    with pytest.raises(ValueError):
        webview.set_size(-1, 100)
    with pytest.raises(ValueError):
        webview.set_size(100, 100, 999)
    with pytest.raises(ValueError):
        webview.get_native_handle(999)
    with pytest.raises(TypeError):
        webview.dispatch(42)


def test_run_parses_64_bit_hwnd(webview):
    watchdog = threading.Timer(0.05, webview.terminate)
    watchdog.start()
    try:
        webview.run(0x7FFFFFFF00000000, 0)
    finally:
        watchdog.cancel()


LONG_PTR = ctypes.c_ssize_t
UINT_PTR = ctypes.c_size_t
LRESULT = LONG_PTR
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             UINT_PTR, LONG_PTR)


class WNDCLASSW(ctypes.Structure):
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


def configure_winapi(user32):
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                      UINT_PTR, LONG_PTR]
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.BOOL]
    user32.MoveWindow.restype = wintypes.BOOL
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    user32.UnregisterClassW.restype = wintypes.BOOL


def client_size(user32, hwnd):
    rect = wintypes.RECT()
    assert user32.GetClientRect(hwnd, ctypes.byref(rect))
    return rect.right - rect.left, rect.bottom - rect.top


def test_embedded_autosize_follows_createwindowex_host(tmp_path):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    configure_winapi(user32)
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
    instance_handle = kernel32.GetModuleHandleW(None)
    class_name = "pyminiwebview-pytest-host"

    @WNDPROC
    def window_proc(hwnd, message, wparam, lparam):
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    window_class = WNDCLASSW()
    window_class.lpfnWndProc = window_proc
    window_class.hInstance = instance_handle
    window_class.lpszClassName = class_name
    atom = user32.RegisterClassW(ctypes.byref(window_class))
    if not atom:
        raise ctypes.WinError(ctypes.get_last_error())

    host = None
    instance = None
    try:
        host = user32.CreateWindowExW(
            0, class_name, class_name, 0x00CF0000,
            0, 0, 500, 350, None, None, instance_handle, None,
        )
        if not host:
            raise ctypes.WinError(ctypes.get_last_error())
        instance = pyminiwebview.WebView(
            window=host,
            autosize=True,
            user_data_folder=str(tmp_path / "webview-data"),
        )
        widget = instance.get_native_handle(
            pyminiwebview.NATIVE_HANDLE_KIND_UI_WIDGET
        )
        initial_host_size = client_size(user32, host)
        assert client_size(user32, widget) == initial_host_size

        assert user32.MoveWindow(host, 0, 0, 730, 490, True)
        resized_host_size = client_size(user32, host)
        assert resized_host_size != initial_host_size
        assert client_size(user32, widget) == resized_host_size
    finally:
        if instance is not None:
            del instance
            gc.collect()
        if host:
            user32.DestroyWindow(host)
        user32.UnregisterClassW(class_name, instance_handle)
