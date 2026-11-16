"""Run the full test suite against an installed wheel, outside the source tree."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent
IMPORT_CHECK = """
from pyminiwebview_helpers import AsyncBridge, Bridge, call_js
from pyminiwebview_win32 import FramelessWindow, TrayIcon, open_file_dialog, save_file_dialog
import pyminiwebview
import pyminiwebview_helpers
import pyminiwebview_win32
print(pyminiwebview.__file__)
print(pyminiwebview_helpers.__file__)
print(pyminiwebview_win32.__file__)
"""


def run(command, cwd, environment):
    return subprocess.run(command, cwd=cwd, env=environment).returncode


def main():
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    with tempfile.TemporaryDirectory(prefix="pyminiwebview-wheel-test-") as temp:
        temp_path = Path(temp)
        shutil.copytree(
            ROOT / "tests", temp_path / "tests",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(
            ROOT / "examples", temp_path / "examples",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        result = run([sys.executable, "-c", IMPORT_CHECK], temp, environment)
        if result:
            return result
        return run(
            [sys.executable, "-m", "pytest", str(temp_path / "tests")],
            temp, environment,
        )


if __name__ == "__main__":
    raise SystemExit(main())
