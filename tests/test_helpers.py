import gc
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import weakref

import pytest

from pyminiwebview_helpers import Bridge, call_js


class FakeView:
    def __init__(self):
        self.bindings = {}
        self.returns = []
        self.evaluations = []

    def js_bind(self, name, callback):
        if name in self.bindings:
            raise ValueError(name)
        self.bindings[name] = callback

    def js_unbind(self, name):
        del self.bindings[name]

    def js_return(self, request_id, status, result):
        self.returns.append((request_id, status, result))

    def js_eval(self, script):
        self.evaluations.append(script)


def decoded_return(view):
    assert len(view.returns) == 1
    request_id, status, result = view.returns[0]
    return request_id, status, json.loads(result)


def test_sync_exports_do_not_import_asyncio():
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(sys.path)
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; "
            "from pyminiwebview_helpers import Bridge, call_js; "
            "assert 'asyncio' not in sys.modules; "
            "assert 'pyminiwebview_helpers.async_bridge' not in sys.modules",
        ],
        check=True,
        env=environment,
    )


def test_expose_supports_no_args_multiple_args_and_chinese():
    view = FakeView()
    bridge = Bridge(view)

    @bridge.expose
    def answer():
        return 42

    @bridge.expose("greet")
    def hello(name, punctuation):
        return f"你好，{name}{punctuation}"

    manager = type("Manager", (), {"open_excel": lambda self: "opened"})()
    returned = bridge.expose(lambda: manager.open_excel(), name="open_excel")

    assert callable(returned)
    assert view.bindings["answer"]("id-1", "[]") is None
    assert decoded_return(view) == ("id-1", 0, 42)

    view.returns.clear()
    view.bindings["greet"]("id-2", json.dumps(["世界", "！"]))
    assert decoded_return(view) == ("id-2", 0, "你好，世界！")

    view.returns.clear()
    view.bindings["open_excel"]("id-3", "[]")
    assert decoded_return(view) == ("id-3", 0, "opened")


@pytest.mark.parametrize(
    "value",
    [3.5, True, None, [1, "中文", False], {"答案": 42, "items": [None]}],
)
def test_expose_serializes_standard_json_values(value):
    view = FakeView()
    bridge = Bridge(view)

    @bridge.expose
    def result():
        return value

    view.bindings["result"]("id", "[]")
    assert decoded_return(view) == ("id", 0, value)


def test_python_exception_rejects_with_stable_error_and_logs(caplog):
    view = FakeView()
    bridge = Bridge(view)

    @bridge.expose
    def divide(a, b):
        return a / b

    with caplog.at_level(logging.ERROR, logger="pyminiwebview_helpers.bridge"):
        view.bindings["divide"]("id", "[20, 0]")

    request_id, status, result = decoded_return(view)
    assert request_id == "id"
    assert status == 1
    assert result["error"]["type"] == "ZeroDivisionError"
    assert result["error"]["message"]
    assert "traceback" not in result
    assert "Bridge call 'divide' failed" in caplog.text


@pytest.mark.parametrize(
    "request_json, error_type",
    [
        ("not json", "JSONDecodeError"),
        ('{"value": 42}', "TypeError"),
        ('"text"', "TypeError"),
        ("[NaN]", "ValueError"),
        ("[Infinity]", "ValueError"),
    ],
)
def test_bad_requests_reject_exactly_once(request_json, error_type):
    view = FakeView()
    bridge = Bridge(view)

    @bridge.expose
    def identity(value=None):
        return value

    view.bindings["identity"]("id", request_json)
    request_id, status, result = decoded_return(view)
    assert request_id == "id"
    assert status == 1
    assert result["error"]["type"] == error_type


@pytest.mark.parametrize(
    "value", [object(), {1, 2}, float("nan"), float("inf"), float("-inf")]
)
def test_unserializable_and_nonstandard_results_reject_exactly_once(value):
    view = FakeView()
    bridge = Bridge(view)

    @bridge.expose
    def result():
        return value

    view.bindings["result"]("id", "[]")
    request_id, status, error = decoded_return(view)
    assert request_id == "id"
    assert status == 1
    assert error["error"]["type"] in {"TypeError", "ValueError"}


def test_duplicate_binding_and_coroutine_registration_fail_early():
    view = FakeView()
    bridge = Bridge(view)

    @bridge.expose
    def same():
        return None

    with pytest.raises(ValueError, match="already exists"):
        bridge.expose("same")(lambda: None)

    async def asynchronous():
        return None

    with pytest.raises(TypeError, match="synchronous"):
        bridge.expose(asynchronous)
    assert set(view.bindings) == {"same"}


def test_close_unbinds_all_functions_and_is_idempotent():
    view = FakeView()
    with Bridge(view) as bridge:
        bridge.expose(lambda: 1, name="one")
        bridge.expose(lambda: 2, name="two")

    assert view.bindings == {}
    assert bridge._view is None
    bridge.close()
    with pytest.raises(RuntimeError, match="closed"):
        bridge.expose(lambda: 3, name="three")


def test_callback_does_not_respond_after_bridge_closes():
    view = FakeView()
    bridge = Bridge(view)

    @bridge.expose
    def close_now():
        bridge.close()

    view.bindings["close_now"]("request", "[]")
    assert view.returns == []


def test_base_exception_is_not_converted_to_a_business_error():
    view = FakeView()
    bridge = Bridge(view)

    class StopProcessing(BaseException):
        pass

    @bridge.expose
    def stop():
        raise StopProcessing("stop")

    with pytest.raises(StopProcessing):
        view.bindings["stop"]("id", "[]")
    assert view.returns == []


def test_call_js_serializes_arguments_and_is_fire_and_forget():
    view = FakeView()
    arguments = ["中文", 'quote: " and \\', "first\nsecond", "</script>"]

    assert call_js(view, "app.setStatus", *arguments) is None
    assert len(view.evaluations) == 1
    script = view.evaluations[0]
    assert script.startswith("app.setStatus(") and script.endswith(");")
    encoded = script[len("app.setStatus("):-2]
    assert json.loads(f"[{encoded}]") == arguments
    assert not hasattr(view, "dispatch")


@pytest.mark.parametrize(
    "name",
    [
        "",
        "app..status",
        "app.status()",
        "app.status;alert(1)",
        "app-status",
        "1app.status",
        "app['status']",
        "app.status\nalert(1)",
    ],
)
def test_call_js_rejects_invalid_function_paths_without_evaluating(name):
    view = FakeView()
    with pytest.raises(ValueError):
        call_js(view, name, "value")
    assert view.evaluations == []


def test_call_js_rejects_bad_names_and_arguments_before_evaluating():
    view = FakeView()
    with pytest.raises(TypeError):
        call_js(view, None)
    for value in (float("nan"), float("inf"), object()):
        with pytest.raises((TypeError, ValueError)):
            call_js(view, "update", value)
    assert view.evaluations == []


if sys.platform == "win32":
    import pyminiwebview


@pytest.mark.skipif(sys.platform != "win32", reason="requires WebView2 Runtime")
def test_real_webview_bridge_success_rejection_and_call_js(tmp_path):
    import pyminiwebview

    received = []
    view = pyminiwebview.WebView(
        width=420,
        height=300,
        user_data_folder=str(tmp_path / "webview-data"),
    )
    bridge = Bridge(view)

    @bridge.expose
    def add(a, b):
        return a + b

    @bridge.expose("greet")
    def hello(name):
        return f"你好，{name}"

    @bridge.expose
    def divide(a, b):
        return a / b

    @bridge.expose
    def exercise_call_js():
        call_js(view, "app.setStatus", "中文\"引号\"\n</script>")
        return "called"

    @bridge.expose
    def finish(results):
        received.append(results)
        view.terminate()

    view.set_html(
        """
        <script>
        window.app = {
          setStatus(value) {
            window.statusValue = value;
          }
        };
        const results = {};
        Promise.all([
          add(20, 22).then(value => { results.add = value; }),
          greet('世界').then(value => { results.greeting = value; }),
          divide(20, 0).then(
            () => { results.error = 'resolved'; },
            error => { results.error = error; }
          ),
          exercise_call_js().then(value => {
            results.callJsReturn = value;
            results.status = window.statusValue;
          })
        ]).then(() => finish(results));
        </script>
        """
    )
    watchdog = threading.Timer(10, view.terminate)
    watchdog.start()
    try:
        view.run()
    finally:
        watchdog.cancel()
        view.close()

    assert received == [{
        "add": 42,
        "greeting": "你好，世界",
        "error": {
            "error": {
                "type": "ZeroDivisionError",
                "message": "division by zero",
            }
        },
        "callJsReturn": "called",
        "status": "中文\"引号\"\n</script>",
    }]


@pytest.mark.skipif(sys.platform != "win32", reason="requires WebView2 Runtime")
@pytest.mark.parametrize("kind", ["standalone", "frameless"])
def test_close_from_bridge_callback_exits_run_loop(tmp_path, kind):
    script = r"""
import sys
import pyminiwebview
from pyminiwebview_helpers import Bridge
from pyminiwebview_win32 import FramelessWindow

if sys.argv[2] == "frameless":
    host = FramelessWindow(
        width=420, height=300, min_width=320, min_height=240,
        user_data_folder=sys.argv[1],
    )
    view = host.view
    bridge = host.bridge
else:
    host = pyminiwebview.WebView(
        width=420, height=300, user_data_folder=sys.argv[1]
    )
    view = host
    bridge = Bridge(view)

@bridge.expose
def close_now():
    host.close()
    return "closed"

view.set_html(
    "<script>document.addEventListener('DOMContentLoaded', () => close_now())</script>"
)
host.run()
host.close()
print("CLOSE_CALLBACK_OK")
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(sys.path)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "webview-data"), kind],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        env=environment,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "CLOSE_CALLBACK_OK" in result.stdout
    assert "Traceback" not in output


@pytest.mark.skipif(sys.platform != "win32", reason="requires WebView2 Runtime")
@pytest.mark.parametrize("mode", ["unbind", "rebind", "close"])
def test_queued_bindings_are_safe_during_unbind_rebind_and_close(
        tmp_path, mode):
    script = r"""
import sys
import threading
import pyminiwebview
from pyminiwebview_helpers import Bridge

mode = sys.argv[2]
for index in range(10):
    view = pyminiwebview.WebView(
        width=420, height=300,
        user_data_folder=f"{sys.argv[1]}-{index}",
    )
    bridge = Bridge(view)
    old_calls = []
    new_calls = []

    @bridge.expose
    def second():
        old_calls.append("old")
        return "old"

    def new_second(request_id, request_json):
        new_calls.append("new")
        view.js_return(request_id, 0, '"new"')

    @bridge.expose
    def first():
        old_calls.append("first")
        bridge.close()
        if mode == "rebind":
            view.js_bind("second", new_second)
        elif mode == "close":
            view.close()
        return "first"

    view.set_html(
        "<script>first(); for (let i = 0; i < 40; i++) second();</script>"
    )
    watchdog = threading.Timer(0.1, view.terminate)
    if mode != "close":
        watchdog.start()
    try:
        view.run()
    finally:
        watchdog.cancel()
        bridge.close()
        view.close()
    assert old_calls == ["first"], (mode, index, old_calls)
    if mode != "rebind":
        assert not new_calls, (mode, index, new_calls)
print("QUEUED_BINDING_STRESS_OK", flush=True)
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(sys.path)
    result = subprocess.run(
        [
            sys.executable,
            "-u",
            "-c",
            script,
            str(tmp_path / "webview-data"),
            mode,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
        env=environment,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "QUEUED_BINDING_STRESS_OK" in result.stdout
    assert "Traceback" not in output


@pytest.mark.skipif(sys.platform != "win32", reason="requires WebView2 Runtime")
@pytest.mark.parametrize("periodic_calls", [False, True])
def test_ctrl_c_stops_run_loop_while_idle_or_in_bridge(
        tmp_path, periodic_calls):
    script = r"""
import ctypes
import sys
import threading
import pyminiwebview
from pyminiwebview_helpers import Bridge

ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)
view = pyminiwebview.WebView(
    width=420, height=300, user_data_folder=sys.argv[1]
)
bridge = Bridge(view)

@bridge.expose
def ping():
    return "pong"

if sys.argv[2] == "periodic":
    view.set_html("<script>setInterval(() => ping(), 50)</script>")
else:
    view.set_html("<p>idle</p>")

def stop_after_timeout():
    print("WATCHDOG", flush=True)
    view.terminate()

watchdog = threading.Timer(6, stop_after_timeout)
watchdog.start()
try:
    view.run()
finally:
    watchdog.cancel()
    bridge.close()
    view.close()
print("EXITED", flush=True)
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(sys.path)
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            script,
            str(tmp_path / "webview-data"),
            "periodic" if periodic_calls else "idle",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        time.sleep(2)
        process.send_signal(signal.CTRL_C_EVENT)
        stdout, stderr = process.communicate(timeout=9)
    finally:
        if process.poll() is None:
            process.kill()
            stdout, stderr = process.communicate()
    output = stdout + stderr
    assert process.returncode == 0, output
    assert "EXITED" in stdout, output
    assert "WATCHDOG" not in stdout, output
    assert "KeyboardInterrupt" in stderr, output


@pytest.mark.skipif(sys.platform != "win32", reason="requires WebView2 Runtime")
@pytest.mark.parametrize("explicit_close", [False, True])
def test_real_webview_close_or_gc_releases_bridge_callback(
        tmp_path, explicit_close):
    view = pyminiwebview.WebView(
        user_data_folder=str(tmp_path / "webview-data")
    )
    bridge = Bridge(view)
    bridge_ref = weakref.ref(bridge)

    @bridge.expose
    def callback():
        return view

    callback_ref = weakref.ref(callback)
    del callback
    del bridge
    gc.collect()
    assert bridge_ref() is None
    assert callback_ref() is not None

    if explicit_close:
        view.close()
    del view
    gc.collect()
    assert callback_ref() is None
