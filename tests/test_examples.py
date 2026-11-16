import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(sys.platform != "win32", reason="requires WebView2 Runtime")
@pytest.mark.parametrize(
    "example, marker",
    [
        ("01_hello.py", "startup and clean exit OK"),
        ("02_js_bridge.py", "success, Chinese and rejection OK"),
        ("03_background_task.py", "thread, dispatch and completion OK"),
        ("05_frameless_app/app.py", "startup, bridge and clean exit OK"),
        ("07_async_bridge.py", "concurrent calls and clean shutdown OK"),
    ],
)
def test_example_smoke_startup_interaction_and_clean_exit(example, marker):
    environment = os.environ.copy()
    source_dir = str(ROOT / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, [source_dir, environment.get("PYTHONPATH")])
    )
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / example), "--smoke-test"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert marker in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="requires Win32")
def test_tray_show_focuses_only_after_successful_activation(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "example06", ROOT / "examples" / "06_tray_and_files.py"
    )
    example06 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example06)
    app = example06.TrayTextApp.__new__(example06.TrayTextApp)
    app.hwnd = 123
    focus_calls = []

    class View:
        def set_focus(self):
            focus_calls.append(True)

    app.view = View()
    monkeypatch.setattr(example06.user32, "ShowWindow", lambda *_args: True)
    monkeypatch.setattr(
        example06.user32, "SetForegroundWindow", lambda *_args: False
    )
    app.show_window()
    assert focus_calls == []
    monkeypatch.setattr(
        example06.user32, "SetForegroundWindow", lambda *_args: True
    )
    app.show_window()
    assert focus_calls == [True]
