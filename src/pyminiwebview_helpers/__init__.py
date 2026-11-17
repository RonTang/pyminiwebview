__all__ = ["AsyncBridge", "Bridge", "call_js"]


def __getattr__(name):
    if name == "AsyncBridge":
        from .async_bridge import AsyncBridge
        value = AsyncBridge
    elif name == "Bridge":
        from .bridge import Bridge
        value = Bridge
    elif name == "call_js":
        from .js import call_js
        value = call_js
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
