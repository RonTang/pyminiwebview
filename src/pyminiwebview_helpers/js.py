import json
import re


_FUNCTION_PATH = re.compile(
    r"^[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*$"
)


def _dumps_json(value):
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, separators=(",", ":")
    )


def call_js(view, function_name, *args):
    """Call a global JavaScript function without waiting for its return value.

    Args:
        view: The WebView whose page should execute the call.
        function_name: A JavaScript identifier or dot-separated identifier path,
            such as ``"setProgress"`` or ``"app.setStatus"``.
        *args: Positional arguments to serialize as standard JSON values.

    Returns:
        None. This is a fire-and-forget operation; JavaScript return values and
        exceptions are not returned to Python.

    Raises:
        TypeError: If ``function_name`` is not a string or an argument cannot be
            JSON serialized.
        ValueError: If the function path is invalid or an argument contains NaN
            or infinity.

    ``js_eval`` is called directly on the current thread. As with the underlying
    WebView API, call this function on the WebView's UI thread. Background workers
    must explicitly use ``view.dispatch``. The caller remains responsible for the
    WebView's lifetime and for closing it on the UI thread.
    """
    if not isinstance(function_name, str):
        raise TypeError("JavaScript function name must be a string")
    if not _FUNCTION_PATH.fullmatch(function_name):
        raise ValueError(
            "JavaScript function name must be an identifier or dot-separated path"
        )
    serialized_args = ",".join(_dumps_json(argument) for argument in args)
    view.js_eval(f"{function_name}({serialized_args});")
