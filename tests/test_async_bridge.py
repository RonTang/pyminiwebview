import asyncio
import gc
import json
import sys
import threading
import time
import weakref

import pytest

from pyminiwebview_helpers import AsyncBridge


class FakeView:
    def __init__(self):
        self.bindings = {}
        self.returns = []

    def js_bind(self, name, callback):
        if name in self.bindings:
            raise ValueError(name)
        self.bindings[name] = callback

    def js_unbind(self, name):
        del self.bindings[name]

    def js_return(self, request_id, status, result):
        self.returns.append((request_id, status, result))


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    assert predicate()


def decoded_returns(view):
    return [(request_id, status, json.loads(result))
            for request_id, status, result in view.returns]


@pytest.fixture
def fake_bridge():
    view = FakeView()
    bridge = AsyncBridge(view)
    yield view, bridge
    bridge.close()


def test_startup_failure_reaps_thread(monkeypatch):
    created_threads = []
    original_start = threading.Thread.start

    def record_start(thread):
        created_threads.append(thread)
        original_start(thread)

    def fail_to_create_loop():
        raise OSError("loop creation failed")

    monkeypatch.setattr(threading.Thread, "start", record_start)
    monkeypatch.setattr(asyncio, "new_event_loop", fail_to_create_loop)
    with pytest.raises(RuntimeError, match="Could not start") as exc_info:
        AsyncBridge(FakeView())
    assert isinstance(exc_info.value.__cause__, OSError)
    assert len(created_threads) == 1
    assert not created_threads[0].is_alive()


def test_startup_timeout_prevents_delayed_loop_from_running(monkeypatch):
    created_threads = []
    original_start = threading.Thread.start
    original_new_event_loop = asyncio.new_event_loop

    def record_start(thread):
        created_threads.append(thread)
        original_start(thread)

    def delayed_event_loop():
        time.sleep(0.1)
        return original_new_event_loop()

    monkeypatch.setattr(threading.Thread, "start", record_start)
    monkeypatch.setattr(asyncio, "new_event_loop", delayed_event_loop)
    monkeypatch.setattr(AsyncBridge, "_STARTUP_TIMEOUT", 0.01)
    with pytest.raises(RuntimeError, match="Could not start"):
        AsyncBridge(FakeView())
    assert len(created_threads) == 1
    assert not created_threads[0].is_alive()


def test_registration_rejects_sync_functions_duplicates_and_closed(fake_bridge):
    view, bridge = fake_bridge
    with pytest.raises(TypeError, match="coroutine"):
        bridge.expose(lambda: None)

    @bridge.expose
    async def same():
        return None

    with pytest.raises(ValueError, match="already exists"):
        bridge.expose("same")(same)
    bridge.close()
    assert view.bindings == {}
    with pytest.raises(RuntimeError, match="closed"):
        bridge.expose("other")(same)
    bridge.close()


@pytest.mark.parametrize(
    "value", [42, 3.5, True, None, [1, "中文"], {"答案": 42}]
)
def test_async_results_follow_standard_json(fake_bridge, value):
    view, bridge = fake_bridge

    @bridge.expose
    async def result():
        await asyncio.sleep(0)
        return value

    view.bindings["result"]("id", "[]")
    wait_until(lambda: len(view.returns) == 1)
    assert decoded_returns(view) == [("id", 0, value)]


def test_async_arguments_chinese_and_event_loop_thread(fake_bridge):
    view, bridge = fake_bridge
    thread_ids = set()

    @bridge.expose("greet")
    async def hello(name, punctuation):
        thread_ids.add(threading.get_ident())
        await asyncio.sleep(0)
        return f"你好，{name}{punctuation}"

    view.bindings["greet"]("id", json.dumps(["世界", "！"]))
    wait_until(lambda: len(view.returns) == 1)
    assert decoded_returns(view)[0][2] == "你好，世界！"
    assert thread_ids == {bridge._thread.ident}


def test_expose_accepts_coroutine_with_keyword_name(fake_bridge):
    view, bridge = fake_bridge

    async def load():
        return 42

    assert bridge.expose(load, name="load_data") is load
    view.bindings["load_data"]("id", "[]")
    wait_until(lambda: len(view.returns) == 1)
    assert decoded_returns(view) == [("id", 0, 42)]
    assert bridge._thread.ident != threading.get_ident()


@pytest.mark.parametrize(
    "request_json,error_type",
    [("bad", "JSONDecodeError"), ('{"a":1}', "TypeError"),
     ("[NaN]", "ValueError"), ("[Infinity]", "ValueError")],
)
def test_invalid_async_requests_reject_without_starting_task(
        fake_bridge, request_json, error_type):
    view, bridge = fake_bridge

    @bridge.expose
    async def identity(value=None):
        return value

    view.bindings["identity"]("id", request_json)
    assert decoded_returns(view)[0][0:2] == ("id", 1)
    assert decoded_returns(view)[0][2]["error"]["type"] == error_type
    assert bridge._tasks == {}


@pytest.mark.parametrize(
    "value", [object(), {1, 2}, float("nan"), float("inf")]
)
def test_bad_async_results_reject_exactly_once(fake_bridge, value):
    view, bridge = fake_bridge

    @bridge.expose
    async def result():
        return value

    view.bindings["result"]("id", "[]")
    wait_until(lambda: len(view.returns) == 1)
    request_id, status, result = decoded_returns(view)[0]
    assert request_id == "id" and status == 1
    assert result["error"]["type"] in {"TypeError", "ValueError"}


def test_async_exception_rejects_with_type_and_message(fake_bridge):
    view, bridge = fake_bridge

    @bridge.expose
    async def divide(a, b):
        await asyncio.sleep(0)
        return a / b

    view.bindings["divide"]("id", "[20,0]")
    wait_until(lambda: len(view.returns) == 1)
    _, status, result = decoded_returns(view)[0]
    assert status == 1
    assert result["error"] == {
        "type": "ZeroDivisionError", "message": "division by zero"
    }


def test_cancel_all_runs_cleanup_and_rejects_promise(fake_bridge):
    view, bridge = fake_bridge
    started = threading.Event()
    cleaned = threading.Event()

    @bridge.expose
    async def wait_for_work():
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            cleaned.set()

    view.bindings["wait_for_work"]("id", "[]")
    assert started.wait(2)
    bridge.cancel_all()
    wait_until(lambda: len(view.returns) == 1)
    assert cleaned.wait(2)
    _, status, result = decoded_returns(view)[0]
    assert status == 1 and result["error"]["type"] == "CancelledError"


def test_close_cancels_tasks_unbinds_and_is_idempotent():
    view = FakeView()
    bridge = AsyncBridge(view)

    @bridge.expose
    async def pending():
        await asyncio.sleep(60)

    view.bindings["pending"]("id", "[]")
    wait_until(lambda: len(bridge._tasks) == 1)
    bridge.close()
    bridge.close()
    assert not bridge._thread.is_alive()
    assert view.bindings == {}
    _, status, result = decoded_returns(view)[0]
    assert status == 1 and result["error"]["type"] == "CancelledError"


def test_close_cancels_to_thread_wait_but_not_running_blocking_work():
    view = FakeView()
    bridge = AsyncBridge(view)
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocking_work():
        started.set()
        release.wait(5)
        finished.set()
        return "finished"

    @bridge.expose
    async def work():
        return await asyncio.to_thread(blocking_work)

    try:
        view.bindings["work"]("id", "[]")
        assert started.wait(2)
        bridge.close()
        assert not bridge._thread.is_alive()
        _, status, result = decoded_returns(view)[0]
        assert status == 1 and result["error"]["type"] == "CancelledError"
        assert not finished.is_set()
    finally:
        release.set()
        bridge.close()
    assert finished.wait(2)


def test_close_rejects_even_if_coroutine_suppresses_cancellation():
    view = FakeView()
    bridge = AsyncBridge(view)
    started = threading.Event()

    @bridge.expose
    async def stubborn_but_returns():
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            return "ignored cancellation"

    view.bindings["stubborn_but_returns"]("id", "[]")
    assert started.wait(2)
    bridge.close()
    _, status, result = decoded_returns(view)[0]
    assert status == 1 and result["error"]["type"] == "CancelledError"


def test_close_has_bounded_timeout_for_unkillable_coroutine():
    view = FakeView()
    bridge = AsyncBridge(view)
    started = threading.Event()

    @bridge.expose
    async def ignores_cancellation():
        started.set()
        while True:
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                pass

    view.bindings["ignores_cancellation"]("id", "[]")
    assert started.wait(2)
    with pytest.raises(TimeoutError):
        bridge.close(timeout=0.05)
    wait_until(lambda: not bridge._thread.is_alive())


def test_base_exception_is_not_returned_as_business_error(fake_bridge):
    view, bridge = fake_bridge

    class StopProcessing(BaseException):
        pass

    @bridge.expose
    async def stop():
        raise StopProcessing("stop")

    view.bindings["stop"]("id", "[]")
    wait_until(lambda: not bridge._tasks)
    assert view.returns == []


def test_one_loop_handles_1000_concurrent_calls_exactly_once(fake_bridge):
    view, bridge = fake_bridge
    count = 1000

    @bridge.expose
    async def work(value):
        if value % 17 == 0:
            await asyncio.sleep(0)
        return value * 2

    for index in range(count):
        view.bindings["work"](f"id-{index}", f"[{index}]")
    wait_until(lambda: len(view.returns) == count, timeout=15)
    results = decoded_returns(view)
    assert len({request_id for request_id, _, _ in results}) == count
    assert all(status == 0 for _, status, _ in results)
    assert sorted(result for _, _, result in results) == [
        index * 2 for index in range(count)
    ]
    assert bridge._tasks == {}


def test_close_rejects_non_ui_thread_and_releases_bridge_reference():
    view = FakeView()
    bridge = AsyncBridge(view)
    bridge_ref = weakref.ref(bridge)
    errors = []

    def close_from_worker():
        try:
            bridge.close()
        except RuntimeError as error:
            errors.append(str(error))

    thread = threading.Thread(target=close_from_worker)
    thread.start()
    thread.join()
    assert errors == ["AsyncBridge.close() must run on the UI thread"]
    bridge.close()
    del bridge
    gc.collect()
    assert bridge_ref() is None


def test_close_cancels_200_pending_calls_exactly_once():
    view = FakeView()
    bridge = AsyncBridge(view)

    @bridge.expose
    async def pending(value):
        await asyncio.sleep(60)

    for index in range(200):
        view.bindings["pending"](f"id-{index}", f"[{index}]")
    wait_until(lambda: len(bridge._tasks) == 200)
    bridge.close()
    results = decoded_returns(view)
    assert len(results) == 200
    assert len({request_id for request_id, _, _ in results}) == 200
    assert all(status == 1 for _, status, _ in results)
    assert all(result["error"]["type"] == "CancelledError"
               for _, _, result in results)
    assert bridge._tasks == {}
    assert not bridge._thread.is_alive()


def test_repeated_create_close_does_not_leak_loop_threads():
    baseline = {thread.ident for thread in threading.enumerate()}
    for _ in range(25):
        view = FakeView()
        bridge = AsyncBridge(view)

        @bridge.expose
        async def answer():
            return 42

        view.bindings["answer"]("id", "[]")
        wait_until(lambda: len(view.returns) == 1)
        bridge.close()
    wait_until(lambda: not {
        thread.ident for thread in threading.enumerate()
        if thread.name.startswith("pyminiwebview-async-")
    } - baseline)


@pytest.mark.skipif(sys.platform != "win32", reason="requires WebView2 Runtime")
def test_real_webview_async_success_error_and_callback_release(tmp_path):
    import pyminiwebview

    received = []
    view = pyminiwebview.WebView(
        width=420, height=300,
        user_data_folder=str(tmp_path / "webview-data"),
    )
    bridge = AsyncBridge(view)

    @bridge.expose
    async def add(a, b):
        await asyncio.sleep(0.01)
        return a + b

    @bridge.expose("greet")
    async def hello(name):
        await asyncio.sleep(0)
        return f"你好，{name}"

    @bridge.expose
    async def divide(a, b):
        return a / b

    function_ref = weakref.ref(add)

    @bridge.expose
    async def finish(results):
        received.append(results)
        view.terminate()

    view.set_html("""
      <script>
      const results = {};
      Promise.all([
        add(20, 22).then(value => { results.sum = value; }),
        greet('世界').then(value => { results.greeting = value; }),
        divide(20, 0).catch(error => { results.error = error; })
      ]).then(() => finish(results));
      </script>
    """)
    watchdog = threading.Timer(10, view.terminate)
    watchdog.start()
    try:
        view.run()
    finally:
        watchdog.cancel()
        bridge.close()
        view.close()
    assert received == [{
        "sum": 42, "greeting": "你好，世界",
        "error": {"error": {
            "type": "ZeroDivisionError", "message": "division by zero"
        }},
    }]
    del add
    del bridge
    gc.collect()
    assert function_ref() is None


@pytest.mark.skipif(sys.platform != "win32", reason="requires WebView2 Runtime")
def test_real_webview_cancel_all_rejects_promise(tmp_path):
    import pyminiwebview

    received = []
    view = pyminiwebview.WebView(
        user_data_folder=str(tmp_path / "webview-data")
    )
    bridge = AsyncBridge(view)
    started = threading.Event()

    @bridge.expose
    async def pending():
        started.set()
        await asyncio.sleep(60)

    @bridge.expose
    async def finish(result):
        received.append(result)
        view.terminate()

    view.set_html("""
      <script>pending().catch(error => finish(error));</script>
    """)
    def cancel_when_started():
        if started.wait(timeout=5):
            bridge.cancel_all()

    canceller = threading.Thread(
        target=cancel_when_started, name="async-cancel-test", daemon=True
    )
    watchdog = threading.Timer(10, view.terminate)
    canceller.start()
    watchdog.start()
    try:
        view.run()
    finally:
        canceller.join(timeout=1)
        watchdog.cancel()
        bridge.close()
        view.close()
    assert not canceller.is_alive()
    assert received == [{
        "error": {"type": "CancelledError",
                  "message": "Async call was cancelled"}
    }]


@pytest.mark.skipif(sys.platform != "win32", reason="requires WebView2 Runtime")
def test_real_webview_300_mixed_async_calls_stress(tmp_path):
    import pyminiwebview

    received = []
    view = pyminiwebview.WebView(
        width=420, height=300,
        user_data_folder=str(tmp_path / "webview-data"),
    )
    bridge = AsyncBridge(view)

    @bridge.expose
    async def work(value):
        await asyncio.sleep((value % 5) * 0.001)
        if value % 37 == 0:
            raise ValueError(f"expected-{value}")
        return value * 2

    @bridge.expose
    async def finish(results):
        received.append(results)
        view.terminate()

    view.set_html("""
      <script>
      const calls = [];
      for (let index = 0; index < 300; index++) {
        calls.push(work(index).then(
          value => ({index, value}),
          error => ({index, error})
        ));
      }
      Promise.all(calls).then(results => finish(results));
      </script>
    """)
    watchdog = threading.Timer(20, view.terminate)
    watchdog.start()
    try:
        view.run()
    finally:
        watchdog.cancel()
        bridge.close()
        view.close()

    assert len(received) == 1
    results = received[0]
    assert len(results) == 300
    for index, result in enumerate(results):
        assert result["index"] == index
        if index % 37 == 0:
            assert result["error"]["error"] == {
                "type": "ValueError", "message": f"expected-{index}"
            }
        else:
            assert result["value"] == index * 2
