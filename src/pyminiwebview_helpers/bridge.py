import inspect
import json
import logging

from .js import _dumps_json


_logger = logging.getLogger(__name__)


def _reject_nonstandard_number(value):
    raise ValueError(f"Non-standard JSON number: {value}")


def _error_result(error):
    try:
        message = str(error)
    except Exception:
        message = "Exception message could not be converted to a string"
    return {"error": {"type": type(error).__name__, "message": message}}


class Bridge:
    """Expose synchronous Python functions as Promise-returning JS functions.

    Args:
        view: An open WebView that implements ``js_bind`` and ``js_return``.

    The bridge does not create threads, dispatch work, or manage the WebView's
    lifetime. Registration and callbacks follow the underlying WebView's UI
    thread rules, and the caller must still close the WebView explicitly or use
    its context manager.
    """

    def __init__(self, view):
        self._view = view
        self._names = set()

    def expose(self, function_or_name=None, *, name=None):
        """Register a synchronous function and return it unchanged.

        Use as ``@bridge.expose``, ``@bridge.expose("javascriptName")``,
        ``@bridge.expose(name="javascriptName")``, or
        ``bridge.expose(function, name="javascriptName")``. With no explicit
        name, the Python function's ``__name__`` is used. JavaScript arguments are decoded
        from a JSON array and passed positionally. Return values are encoded as
        standard JSON; NaN, infinity, and non-serializable values are rejected.

        Raises:
            TypeError: If the decorated object is not callable, is a coroutine
                function, or an explicit binding name is not a string.
            ValueError: If a binding name is empty or already registered.

        Ordinary ``Exception`` instances raised by the function reject the JS
        Promise with ``{"error": {"type": ..., "message": ...}}`` and are
        logged without sending a traceback to the page. ``KeyboardInterrupt``,
        ``SystemExit``, and other ``BaseException`` subclasses are not caught.
        Malformed requests and result serialization failures also reject the
        Promise. Async functions are not supported.
        """
        if name is not None:
            if isinstance(function_or_name, str):
                raise TypeError("Specify the binding name only once")
            if function_or_name is not None:
                return self._register(function_or_name, name)
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
        if not callable(function):
            raise TypeError("Bridge can only expose a callable")
        if inspect.iscoroutinefunction(function):
            raise TypeError("Bridge only supports synchronous functions")
        if name is None:
            name = function.__name__
        if not isinstance(name, str):
            raise TypeError("Bridge binding name must be a string")
        if not name:
            raise ValueError("Bridge binding name must not be empty")
        if name in self._names:
            raise ValueError(f"Bridge binding already exists: {name!r}")

        view = self._view

        def callback(request_id, request_json):
            try:
                arguments = json.loads(
                    request_json, parse_constant=_reject_nonstandard_number
                )
                if not isinstance(arguments, list):
                    raise TypeError("Bridge request must be a JSON array")
                result = function(*arguments)
                response = _dumps_json(result)
            except Exception as error:
                _logger.exception("Bridge call %r failed", name)
                response = _dumps_json(_error_result(error))
                view.js_return(request_id, 1, response)
            else:
                view.js_return(request_id, 0, response)

        self._view.js_bind(name, callback)
        self._names.add(name)
        return function
