"""Record the real frameless example for README assets.

Development-only dependencies: Pillow, PyAutoGUI, and pywin32. Build the native
extension in place first, then run ``python tools/record_frameless_demo.py``.
These packages are not project runtime dependencies.
"""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pyautogui
from PIL import Image
import win32gui
import win32ui


ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "examples" / "05_frameless_app" / "app.py"
WINDOW_TITLE = "pyminiwebview · Frameless showcase"
DWMWA_EXTENDED_FRAME_BOUNDS = 9


class Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG), ("top", wintypes.LONG),
        ("right", wintypes.LONG), ("bottom", wintypes.LONG),
    ]


def configure_dpi():
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


def wait_for_window(process, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Frameless example exited before recording")
        hwnd = win32gui.FindWindow(None, WINDOW_TITLE)
        if hwnd and win32gui.IsWindowVisible(hwnd):
            return hwnd
        time.sleep(0.1)
    raise RuntimeError("Frameless example did not become visible")


def capture_window(hwnd):
    window_rect = win32gui.GetWindowRect(hwnd)
    width = window_rect[2] - window_rect[0]
    height = window_rect[3] - window_rect[1]
    window_dc = win32gui.GetWindowDC(hwnd)
    source_dc = win32ui.CreateDCFromHandle(window_dc)
    memory_dc = source_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(source_dc, width, height)
    memory_dc.SelectObject(bitmap)
    try:
        if not ctypes.windll.user32.PrintWindow(
                hwnd, memory_dc.GetSafeHdc(), 2):
            raise RuntimeError("PrintWindow failed")
        bitmap_info = bitmap.GetInfo()
        bitmap_bytes = bitmap.GetBitmapBits(True)
        image = Image.frombuffer(
            "RGB", (bitmap_info["bmWidth"], bitmap_info["bmHeight"]),
            bitmap_bytes, "raw", "BGRX", 0, 1,
        )
    finally:
        memory_dc.DeleteDC()
        source_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, window_dc)
        win32gui.DeleteObject(bitmap.GetHandle())

    visible_rect = Rect()
    result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(visible_rect), ctypes.sizeof(visible_rect),
    )
    if result == 0:
        crop = (
            visible_rect.left - window_rect[0],
            visible_rect.top - window_rect[1],
            visible_rect.right - window_rect[0],
            visible_rect.bottom - window_rect[1],
        )
        image = image.crop(crop)
    return image.copy()


def set_maximized(hwnd, expected):
    _, top, right, _ = win32gui.GetWindowRect(hwnd)
    pyautogui.moveTo(right - 100, top + 32, duration=0.25)
    pyautogui.click()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if bool(ctypes.windll.user32.IsZoomed(hwnd)) == expected:
            return
        time.sleep(0.05)
    raise RuntimeError(f"Window did not change maximized state to {expected}")


def click_demo_button(hwnd, sync=False):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top
    x = left + width * (0.585 if sync else 0.27)
    y = top + height * (0.845 if sync else 0.825)
    pyautogui.moveTo(x, y, duration=0.25)
    pyautogui.click()


def normalize_frame(image, size):
    frame = image.copy()
    frame.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "#0d1226")
    canvas.paste(frame, ((size[0] - frame.width) // 2,
                         (size[1] - frame.height) // 2))
    return canvas


def record(output_dir, seconds, fps):
    configure_dpi()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [
        str(ROOT / "src"), environment.get("PYTHONPATH"),
    ]))
    process = subprocess.Popen([sys.executable, str(APP)], cwd=ROOT, env=environment)
    frames = []
    timestamps = []
    try:
        hwnd = wait_for_window(process)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.5)
        start = time.monotonic()
        actions = [
            (1.0, lambda: set_maximized(hwnd, True)),
            (2.8, lambda: set_maximized(hwnd, False)),
            (4.5, lambda: click_demo_button(hwnd)),
            (6.1, lambda: click_demo_button(hwnd, sync=True)),
        ]
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= seconds:
                break
            while actions and elapsed >= actions[0][0]:
                actions.pop(0)[1]()
            frames.append(capture_window(hwnd))
            timestamps.append(time.monotonic() - start)
            time.sleep(max(0, 1 / fps - (time.monotonic() - start - elapsed)))

        final_image = capture_window(hwnd)
        output_dir.mkdir(parents=True, exist_ok=True)
        png_path = output_dir / "pyminiwebview-frameless.png"
        gif_path = output_dir / "pyminiwebview-frameless.gif"
        final_image.save(png_path, optimize=True)

        gif_size = (880, 598)
        normalized = [normalize_frame(frame, gif_size) for frame in frames]
        palette = normalized[0].quantize(colors=256)
        paletted = [
            frame.quantize(palette=palette, dither=Image.Dither.NONE)
            for frame in normalized
        ]
        durations = []
        for index, timestamp in enumerate(timestamps):
            if index + 1 < len(timestamps):
                durations.append(max(20, round((timestamps[index + 1] - timestamp) * 1000)))
            else:
                durations.append(max(20, round((seconds - timestamp) * 1000)))
        paletted[0].save(
            gif_path, save_all=True, append_images=paletted[1:],
            duration=durations, loop=0, optimize=False, disposal=2,
        )
        with Image.open(gif_path) as gif:
            gif_duration = 0
            for frame_index in range(gif.n_frames):
                gif.seek(frame_index)
                gif_duration += gif.info.get("duration", 0)
            actual_frames = gif.n_frames
        metadata = {
            "png": {"width": final_image.width, "height": final_image.height,
                    "bytes": png_path.stat().st_size},
            "gif": {"width": gif_size[0], "height": gif_size[1],
                    "frames": actual_frames,
                    "duration_seconds": gif_duration / 1000,
                    "bytes": gif_path.stat().st_size},
        }
        print(json.dumps(metadata, indent=2))
    finally:
        hwnd = win32gui.FindWindow(None, WINDOW_TITLE)
        if hwnd:
            win32gui.PostMessage(hwnd, 0x0010, 0, 0)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "assets")
    parser.add_argument("--seconds", type=float, default=12.0)
    parser.add_argument("--fps", type=float, default=8.0)
    args = parser.parse_args()
    record(args.output_dir.resolve(), args.seconds, args.fps)


if __name__ == "__main__":
    main()
