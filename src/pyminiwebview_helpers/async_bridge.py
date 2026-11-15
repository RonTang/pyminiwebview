import asyncio
import inspect
import json
import logging
import threading

from .bridge import _error_result, _reject_nonstandard_number
from .js import _dumps_json


_logger = logging.getLogger(__name__)


class AsyncBridge:
    """Expose coroutine functions through a dedicated, reusable asyncio loop.

    Args:
        view: An open WebView that implements ``js_bind``, ``js_unbind``, and
            ``js_return``.

    Each instance owns one daemon thread with one asyncio event loop. Calls are
    concurrent Tasks on that loop, not one thread per request. Registration and
    ``close()`` must run on the WebView's UI thread. Coroutine code runs on the
    event-loop thread and must use ``view.dispatch`` for UI-only WebView methods.

    The caller must close the AsyncBridge before closing the WebView, preferably
    with a nested context manager. Closing cancels all active Tasks and rejects
    their JS Promises. Cancellation is cooperative; coroutines should propagate
    ``asyncio.CancelledError`` after performing cleanup. Standard JSON rules and
    the synchronous Bridge's error-object format apply. Only coroutine functions
    are supported; blocking calls still block the event loop unless the caller
    explicitly moves them to an executor.
    """

    def __init__(self, view):
        self._view = view
        self._names = set()
        self._owner_thread = threading.get_ident()
        self._lock = threading.Lock()
        self._closed = False
        self._stopping = False
        self._tasks = {}
        self._loop = None
        self._ready = threading.Event()
        self._startup_errors = []
        self._thread = threading.Thread(
            target=self._thread_main,
            name=f"pyminiwebview-async-{id(self):x}",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=5)
        if not self._ready.is_set() or self._startup_errors:
            raise RuntimeError("Could not start the AsyncBridge event loop")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _thread_main(self):
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._ready.set()
            self._loop.run_forever()
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
        except BaseException as error:
            self._startup_errors.append(error)
            self._ready.set()
            _logger.exception("AsyncBridge event loop stopped unexpectedly")
        finally:
            if self._loop is not None:
                self._loop.close()

    def expose(self, function_or_name=None, *, name=None):
        """Register a coroutine function and return it unchanged.

        Use as ``@bridge.expose`` or ``@bridge.expose("javascriptName")``.
        JavaScript arguments are decoded from a JSON array and passed
        positionally. The coroutine runs concurrently with other calls on this
        instance's event loop. Its return value resolves the JS Promise; an
        ordinary exception or cancellation rejects it with an error object.

        Raises:
            TypeError: If the decorated object is not a coroutine function or
                the explicit binding name is not a string.
            ValueError: If a binding name is empty or already registered.

        ``KeyboardInterrupt``, ``SystemExit``, and other non-cancellation
        ``BaseException`` subclasses are logged but are not converted into
        ordinary business-error responses. Async generators are not supported.
        """
        if name is not None:
            if function_or_name is not None:
                raise TypeError("Specify the binding name only once")
            return self._decorator(name)
        if isinstance(function_or_name, str):
            return self._decorator(function_or_name)
        if function_or_name is None:
            return self._decorator(None)
        return self._register(function_or_name, None)

    def _decorator(self, name):
        def decorate(function):
            return self._register(function, name)

        return decorate

    def _register(self, function, name):
        if not inspect.iscoroutinefunction(function):
            raise TypeError("AsyncBridge only supports coroutine functions")
        if name is None:
            name = function.__name__
        if not isinstance(name, str):
            raise TypeError("AsyncBridge binding name must be a string")
        if not name:
            raise ValueError("AsyncBridge binding name must not be empty")
        if name in self._names:
            raise ValueError(f"AsyncBridge binding already exists: {name!r}")
        if self._closed:
            raise RuntimeError("AsyncBridge is closed")

        def callback(request_id, request_json):
            try:
                arguments = json.loads(
                    request_json, parse_constant=_reject_nonstandard_number
                )
                if not isinstance(arguments, list):
                    raise TypeError("AsyncBridge request must be a JSON array")
                coroutine = function(*arguments)
            except Exception as error:
                _logger.exception("AsyncBridge call %r could not start", name)
                self._respond(request_id, 1, _error_result(error))
                return
            self._submit(request_id, name, coroutine)

        self._view.js_bind(name, callback)
        self._names.add(name)
        return function

    def _submit(self, request_id, name, coroutine):
        with self._lock:
            closed = self._closed
        if closed:
            coroutine.close()
            self._respond(request_id, 1, _error_result(
                RuntimeError("AsyncBridge is closed")
            ))
            return
        try:
            self._loop.call_soon_threadsafe(
                self._start_task, request_id, name, coroutine
            )
        except RuntimeError as error:
            coroutine.close()
            _logger.exception("AsyncBridge call %r could not be scheduled", name)
            self._respond(request_id, 1, _error_result(error))

    def _start_task(self, request_id, name, coroutine):
        if self._closed:
            coroutine.close()
            self._respond(request_id, 1, _error_result(
                RuntimeError("AsyncBridge is closed")
            ))
            return
        task = self._loop.create_task(coroutine)
        self._tasks[task] = (request_id, name)
        task.add_done_callback(self._task_done)

    def _task_done(self, task):
        request_id, name = self._tasks.pop(task)
        try:
            response = _dumps_json(task.result())
        except asyncio.CancelledError:
            _logger.info("AsyncBridge call %r was cancelled", name)
            self._respond(request_id, 1, {
                "error": {"type": "CancelledError",
                          "message": "Async call was cancelled"}
            })
        except Exception as error:
            _logger.exception("AsyncBridge call %r failed", name)
            self._respond(request_id, 1, _error_result(error))
        except BaseException:
            _logger.critical(
                "AsyncBridge call %r terminated by BaseException", name,
                exc_info=True,
            )
        else:
            if self._closed:
                self._respond(request_id, 1, {
                    "error": {"type": "CancelledError",
                              "message": "Async call was cancelled"}
                })
            else:
                self._respond_raw(request_id, 0, response)
        finally:
            if self._stopping and not self._tasks:
                self._loop.stop()

    def _respond(self, request_id, status, result):
        self._respond_raw(request_id, status, _dumps_json(result))

    def _respond_raw(self, request_id, status, response):
        try:
            self._view.js_return(request_id, status, response)
        except Exception:
            _logger.exception("AsyncBridge response %r could not be sent", request_id)

    def cancel_all(self):
        """Request cancellation of every active call without closing the bridge.

        This method is thread-safe and returns immediately. Each affected JS
        Promise is rejected after its coroutine processes the cancellation.
        Calls submitted later are not affected.
        """
        with self._lock:
            if self._closed:
                return
        try:
            self._loop.call_soon_threadsafe(self._cancel_tasks)
        except RuntimeError:
            pass

    def _cancel_tasks(self):
        for task in list(self._tasks):
            task.cancel()

    def _close_on_loop(self):
        if self._stopping:
            return
        self._stopping = True
        self._cancel_tasks()
        if not self._tasks:
            self._loop.stop()

    def close(self, timeout=5.0):
        """Cancel active calls, stop the event loop, and unbind all functions.

        Must be called on the WebView UI thread before ``view.close()``. The
        method is idempotent. If cancellation does not finish within ``timeout``
        seconds, the loop is stopped forcibly and ``TimeoutError`` is raised;
        such coroutines are already outside the supported cancellation contract.
        """
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError("AsyncBridge.close() must run on the UI thread")
        if threading.current_thread() is self._thread:
            raise RuntimeError("AsyncBridge.close() cannot run inside its event loop")
        with self._lock:
            already_closed = self._closed
            self._closed = True
        timed_out = False
        if not already_closed and self._thread.is_alive():
            try:
                self._loop.call_soon_threadsafe(self._close_on_loop)
            except RuntimeError:
                pass
        if self._thread.is_alive():
            self._thread.join(timeout)
            if self._thread.is_alive():
                timed_out = True
                try:
                    self._loop.call_soon_threadsafe(self._loop.stop)
                    self._thread.join(1)
                except RuntimeError:
                    pass
        for name in list(self._names):
            try:
                self._view.js_unbind(name)
            except KeyError:
                pass
        self._names.clear()
        self._view = None
        if timed_out:
            raise TimeoutError("AsyncBridge tasks did not cancel before timeout")
