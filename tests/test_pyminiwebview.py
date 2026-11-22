import ctypes
import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from ctypes import wintypes

import pytest

if sys.platform != "win32":
    pytest.skip("pyminiwebview only supports Windows", allow_module_level=True)

import pyminiwebview


class COREWEBVIEW2_COLOR(ctypes.Structure):
    _fields_ = [
        ("A", ctypes.c_ubyte), ("R", ctypes.c_ubyte),
        ("G", ctypes.c_ubyte), ("B", ctypes.c_ubyte),
    ]


def com_method(instance, index, restype, *argtypes):
    vtable = ctypes.c_void_p.from_address(instance).value
    address = ctypes.c_void_p.from_address(
        vtable + index * ctypes.sizeof(ctypes.c_void_p)
    ).value
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(address)


def default_background_color(view):
    controller = view.get_native_handle(
        pyminiwebview.NATIVE_HANDLE_KIND_BROWSER_CONTROLLER
    )
    getter = com_method(
        controller, 26, ctypes.c_long, ctypes.POINTER(COREWEBVIEW2_COLOR)
    )
    color = COREWEBVIEW2_COLOR()
    assert getter(controller, ctypes.byref(color)) == 0
    return color.A, color.R, color.G, color.B


def default_context_menus_enabled(view):
    controller = view.get_native_handle(
        pyminiwebview.NATIVE_HANDLE_KIND_BROWSER_CONTROLLER
    )
    core = ctypes.c_void_p()
    settings = ctypes.c_void_p()
    get_core = com_method(
        controller, 25, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p)
    )
    assert get_core(controller, ctypes.byref(core)) == 0
    try:
        get_settings = com_method(
            core.value, 3, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p)
        )
        assert get_settings(core, ctypes.byref(settings)) == 0
        try:
            get_enabled = com_method(
                settings.value, 13, ctypes.c_long, ctypes.POINTER(wintypes.BOOL)
            )
            enabled = wintypes.BOOL()
            assert get_enabled(settings, ctypes.byref(enabled)) == 0
            return bool(enabled.value)
        finally:
            com_method(settings.value, 2, wintypes.ULONG)(settings)
    finally:
        com_method(core.value, 2, wintypes.ULONG)(core)


def window_exists(hwnd):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    return bool(user32.IsWindow(hwnd))


def pump_until_closed(hwnd):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.PeekMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), wintypes.HWND,
        wintypes.UINT, wintypes.UINT, wintypes.UINT,
    ]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = ctypes.c_ssize_t
    deadline = time.monotonic() + 5
    message = wintypes.MSG()
    while window_exists(hwnd) and time.monotonic() < deadline:
        if user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        else:
            time.sleep(0.01)
    assert not window_exists(hwnd)


@pytest.fixture
def webview(tmp_path):
    instance = pyminiwebview.WebView(
        width=320,
        height=240,
        user_data_folder=str(tmp_path / "webview-data"),
    )
    yield instance
    instance.close()
    del instance
    gc.collect()


def test_standalone_reveals_first_frame_at_requested_size(tmp_path):
    instance = pyminiwebview.WebView(
        width=777,
        height=555,
        user_data_folder=str(tmp_path / "webview-data"),
    )
    hwnd = instance.get_native_handle(pyminiwebview.NATIVE_HANDLE_KIND_UI_WINDOW)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL

    def size():
        rect = wintypes.RECT()
        assert user32.GetClientRect(hwnd, ctypes.byref(rect))
        return rect.right - rect.left, rect.bottom - rect.top

    stop_polling = threading.Event()

    def terminate_after_reveal():
        while not stop_polling.wait(0.05):
            if user32.IsWindowVisible(hwnd):
                instance.terminate()
                return

    reveal_watcher = threading.Thread(target=terminate_after_reveal, daemon=True)
    watchdog = threading.Timer(10, instance.terminate)
    try:
        assert not user32.IsWindowVisible(hwnd)
        initial_size = size()
        instance.set_html("<style>body{background:#0d1226}</style><h1>ready</h1>")
        reveal_watcher.start()
        watchdog.start()
        try:
            instance.run()
        finally:
            stop_polling.set()
            reveal_watcher.join(timeout=1)
            watchdog.cancel()
        assert user32.IsWindowVisible(hwnd)
        assert size() == initial_size
    finally:
        stop_polling.set()
        watchdog.cancel()
        instance.close()


@pytest.mark.parametrize("transparent, expected_alpha", [(False, 255), (True, 0)])
def test_background_color_preserves_rgb_and_sets_alpha(
        tmp_path, transparent, expected_alpha):
    instance = pyminiwebview.WebView(
        bgcolor=0x123456,
        transparent=transparent,
        user_data_folder=str(tmp_path / "webview-data"),
    )
    try:
        assert default_background_color(instance) == (
            expected_alpha, 0x56, 0x34, 0x12
        )
    finally:
        instance.close()


def test_initialization_reposts_quit_for_outer_message_loop(tmp_path):
    script = r"""
import ctypes
import sys
from ctypes import wintypes
import pyminiwebview
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG), wintypes.HWND,
    wintypes.UINT, wintypes.UINT, wintypes.UINT,
]
user32.PeekMessageW.restype = wintypes.BOOL
user32.PostQuitMessage(37)
try:
    pyminiwebview.WebView(user_data_folder=sys.argv[1])
except RuntimeError:
    pass
else:
    raise AssertionError("WM_QUIT must cancel WebView initialization")
message = wintypes.MSG()
assert user32.PeekMessageW(ctypes.byref(message), None, 0x0012, 0x0012, 1)
assert message.message == 0x0012
assert message.wParam == 37
print("quit preserved")
"""
    environment = os.environ.copy()
    source_dir = str(Path(__file__).resolve().parent.parent / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, [source_dir, environment.get("PYTHONPATH")])
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "cancelled-data")],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "quit preserved" in result.stdout


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


@pytest.mark.parametrize("explicit_close", [False, True])
def test_queued_dispatch_is_canceled_and_releases_callable(
        tmp_path, explicit_close):
    calls = []

    def callback():
        calls.append("called")

    instance = pyminiwebview.WebView(
        user_data_folder=str(tmp_path / "webview-data")
    )
    baseline = sys.getrefcount(callback)
    instance.dispatch(callback)
    assert sys.getrefcount(callback) == baseline + 1
    if explicit_close:
        instance.close()
    del instance
    gc.collect()
    assert calls == []
    assert sys.getrefcount(callback) == baseline


def test_close_is_idempotent_and_context_manager_closes(tmp_path):
    with pyminiwebview.WebView(
            user_data_folder=str(tmp_path / "webview-data")) as instance:
        hwnd = instance.get_native_handle(
            pyminiwebview.NATIVE_HANDLE_KIND_UI_WINDOW
        )
        instance.close()
        instance.close()
        assert not window_exists(hwnd)
        with pytest.raises(RuntimeError):
            instance.set_html("closed")
    assert not window_exists(hwnd)


def test_binding_cycle_is_collected_and_destroys_native_window(tmp_path):
    instance = pyminiwebview.WebView(
        user_data_folder=str(tmp_path / "webview-data")
    )
    hwnd = instance.get_native_handle(pyminiwebview.NATIVE_HANDLE_KIND_UI_WINDOW)

    def callback(request_id, request, view=instance):
        view.js_return(request_id, 0, "null")

    instance.js_bind("cycle", callback)
    del callback
    del instance
    gc.collect()
    assert not window_exists(hwnd)


def test_binding_cycle_collected_off_ui_finalizes_on_ui_thread(tmp_path):
    instance = pyminiwebview.WebView(
        user_data_folder=str(tmp_path / "webview-data")
    )
    hwnd = instance.get_native_handle(pyminiwebview.NATIVE_HANDLE_KIND_UI_WINDOW)

    def callback(request_id, request, view=instance):
        view.js_return(request_id, 0, "null")

    instance.js_bind("cycle", callback)
    holder = [instance]
    del callback
    del instance

    def collect_off_ui():
        holder.clear()
        gc.collect()

    thread = threading.Thread(target=collect_off_ui)
    thread.start()
    thread.join()
    pump_until_closed(hwnd)


def test_repeated_cycles_and_canceled_dispatch(tmp_path):
    for index in range(12):
        calls = []
        instance = pyminiwebview.WebView(
            user_data_folder=str(tmp_path / f"webview-data-{index}")
        )

        def callback(request_id, request, view=instance):
            view.js_return(request_id, 0, "null")

        def queued(view=instance):
            calls.append(view)

        instance.js_bind("cycle", callback)
        instance.dispatch(queued)
        if index % 2:
            instance.close()
        del queued
        del callback
        del instance
        gc.collect()
        assert calls == []


def test_dispatch_terminate_and_close_are_synchronized(tmp_path):
    for index in range(8):
        instance = pyminiwebview.WebView(
            user_data_folder=str(tmp_path / f"webview-data-{index}")
        )
        errors = []

        def worker(view=instance):
            try:
                for dispatch_index in range(100):
                    if dispatch_index == 10:
                        view.terminate()
                        time.sleep(0.001)
                    view.dispatch(lambda: None)
            except RuntimeError as error:
                if "closed" not in str(error):
                    errors.append(error)
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=worker)
        thread.start()
        instance.run()
        instance.close()
        thread.join()
        assert not errors


def test_configure_app_mode_smoke(webview):
    assert default_context_menus_enabled(webview) is True
    webview.configure_app_mode()
    webview.configure_app_mode()
    assert default_context_menus_enabled(webview) is False
    webview.configure_app_mode(disable_default_context_menus=False)
    webview.configure_app_mode()
    assert default_context_menus_enabled(webview) is False


def test_notify_parent_position(webview):
    webview.notify_parent_position()


def test_standard_webview_does_not_enable_composition_hosting(webview):
    assert webview.composition_resize() is False
    assert webview.composition_mouse_input(0x0200, 0, 0) is False
    assert webview.composition_pointer_input(0x0245, 0) is False
    assert webview.composition_cursor() is False
    assert webview.composition_visible(True) is False


def test_invalid_arguments_raise_python_exceptions(webview, tmp_path):
    with pytest.raises(TypeError):
        pyminiwebview.WebView(width="wide")
    with pytest.raises(ValueError):
        pyminiwebview.WebView(window=0x7FFFFFFF00000000)
    with pytest.raises(ValueError):
        pyminiwebview.WebView(composition_hosting=True)
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
        if host:
            user32.DestroyWindow(host)
        if instance is not None:
            instance.close()
            del instance
            gc.collect()
        user32.UnregisterClassW(class_name, instance_handle)
