"""学习目标：运行 per-pixel alpha 透明桌宠，并管理拖动、穿透和托盘。

运行：python examples/08_desk_pet.py
操作：拖动宠物移动；右键托盘图标可切换点击穿透、隐藏/显示或退出。
开发冒烟：python examples/08_desk_pet.py --smoke-test
"""

import argparse
import ctypes
import threading
from ctypes import wintypes

from pyminiwebview_win32 import FramelessWindow, TrayIcon


HTML = """
<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<style>
  html, body { margin: 0; width: 100%; height: 100%; overflow: hidden;
    background: transparent; }
  body { user-select: none; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }
  .pet { position: absolute; left: 50%; top: 46%; width: 156px; height: 164px;
    transform: translate(-50%, -50%); cursor: grab; touch-action: none;
    animation: bob 2.2s ease-in-out infinite; filter: drop-shadow(0 14px 10px #30205244); }
  .pet:active { cursor: grabbing; }
  .body { position: absolute; inset: 28px 4px 0; border-radius: 48% 48% 44% 44%;
    background: linear-gradient(145deg, #c4b5fded, #8b5cf6f2 58%, #6d28d9f5);
    border: 1px solid #ffffff70; box-shadow: inset 12px 10px 24px #ffffff35; }
  .ear { position: absolute; top: 4px; width: 58px; height: 68px; z-index: -1;
    background: #a78bfa; border: 1px solid #ffffff60; transform: rotate(45deg);
    border-radius: 12px 70% 12px 70%; }
  .ear.left { left: 15px; } .ear.right { right: 15px; transform: rotate(45deg) scaleX(-1); }
  .eye { position: absolute; top: 67px; width: 14px; height: 22px; border-radius: 50%;
    background: #241446; animation: blink 4s infinite; }
  .eye.left { left: 43px; } .eye.right { right: 43px; }
  .eye::after { content: ""; display: block; width: 5px; height: 7px; margin: 3px;
    border-radius: 50%; background: #ffffffd0; }
  .mouth { position: absolute; left: 50%; top: 96px; width: 22px; height: 12px;
    transform: translateX(-50%); border-bottom: 3px solid #40205f; border-radius: 50%; }
  .cheek { position: absolute; top: 91px; width: 26px; height: 13px; border-radius: 50%;
    background: #f0abfc70; filter: blur(1px); }
  .cheek.left { left: 19px; } .cheek.right { right: 19px; }
  .controls { position: absolute; left: 50%; bottom: 14px; transform: translateX(-50%);
    display: flex; gap: 7px; white-space: nowrap; }
  button { border: 1px solid #ffffff65; border-radius: 999px; padding: 7px 11px;
    background: #312e81b8; color: white; font-size: 12px; font-family: inherit;
    cursor: pointer;
    backdrop-filter: blur(8px); }
  button:hover { background: #4338cadf; }
  @keyframes bob { 0%, 100% { transform: translate(-50%, -50%) translateY(0) rotate(-2deg); }
    50% { transform: translate(-50%, -50%) translateY(-13px) rotate(2deg); } }
  @keyframes blink { 0%, 44%, 50%, 100% { transform: scaleY(1); }
    47% { transform: scaleY(.08); } }
</style>
<div class="pet" id="pet" role="img" aria-label="一只漂浮的紫色桌宠">
  <div class="ear left"></div><div class="ear right"></div><div class="body"></div>
  <div class="eye left"></div><div class="eye right"></div>
  <div class="cheek left"></div><div class="cheek right"></div><div class="mouth"></div>
</div>
<div class="controls">
  <button id="through">点击穿透</button><button id="exit">退出</button>
</div>
<script>
const pet = document.getElementById('pet');
pet.addEventListener('mousedown', event => {
  if (event.button === 0) __window_start_move();
});
document.getElementById('through').addEventListener('click', async () => {
  const enabled = await toggle_click_through();
  if (!enabled) document.getElementById('through').textContent = '点击穿透';
});
document.getElementById('exit').addEventListener('click', () => exit_app());
window.addEventListener('DOMContentLoaded', async () => {
  if (!window.__SMOKE_TEST__) return;
  const style = getComputedStyle(document.body);
  const animation = getComputedStyle(pet).animationName;
  await __smoke_finish({background: style.backgroundColor, animation});
});
</script></html>
"""

SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080
MF_CHECKED = 0x0008
ID_SHOW = 1001
ID_HIDE = 1002
ID_THROUGH = 1003
ID_EXIT = 1004

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [
    wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR,
]
user32.AppendMenuW.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.HWND, wintypes.LPVOID,
]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyMenu.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()
    smoke_results = []

    with FramelessWindow(
        title="08 · Desk Pet",
        width=280,
        height=300,
        min_width=280,
        min_height=300,
        resizable=False,
        app_name="pyminiwebview-example-08",
        transparent=True,
        topmost=True,
    ) as window:
        state = {"click_through": False}
        tray = None

        def toggle_click_through():
            state["click_through"] = window.set_click_through(
                not state["click_through"]
            )
            return state["click_through"]

        def exit_app():
            window.view.terminate()
            return True

        def show_window():
            if state["click_through"]:
                toggle_click_through()
            user32.ShowWindow(window.hwnd, SW_SHOWNOACTIVATE)

        def show_menu():
            menu = user32.CreatePopupMenu()
            if not menu:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                user32.AppendMenuW(menu, 0, ID_SHOW, "显示")
                user32.AppendMenuW(menu, 0, ID_HIDE, "隐藏")
                user32.AppendMenuW(
                    menu, MF_CHECKED if state["click_through"] else 0,
                    ID_THROUGH, "点击穿透",
                )
                user32.AppendMenuW(menu, 0, ID_EXIT, "退出")
                point = wintypes.POINT()
                if not user32.GetCursorPos(ctypes.byref(point)):
                    raise ctypes.WinError(ctypes.get_last_error())
                user32.SetForegroundWindow(window.hwnd)
                command = user32.TrackPopupMenu(
                    menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                    point.x, point.y, 0, window.hwnd, None,
                )
            finally:
                user32.DestroyMenu(menu)
            if command == ID_SHOW:
                show_window()
            elif command == ID_HIDE:
                user32.ShowWindow(window.hwnd, SW_HIDE)
            elif command == ID_THROUGH:
                toggle_click_through()
            elif command == ID_EXIT:
                exit_app()

        window.bridge.expose(toggle_click_through)
        window.bridge.expose(exit_app)
        if args.smoke_test:
            def smoke_finish(result):
                smoke_results.append(result)
                window.view.terminate()

            window.bridge.expose(smoke_finish, name="__smoke_finish")
            window.view.js_init("window.__SMOKE_TEST__ = true;")
        window.view.set_html(HTML)
        tray = TrayIcon(
            tooltip="pyminiwebview 桌宠 · 右键管理",
            on_left_click=show_window,
            on_right_click=show_menu,
        )
        watchdog = None
        if args.smoke_test:
            watchdog = threading.Timer(10, window.view.terminate)
            watchdog.start()
        try:
            window.run()
        finally:
            if watchdog:
                watchdog.cancel()
            tray.remove()

    if args.smoke_test:
        assert len(smoke_results) == 1
        result = smoke_results[0]
        assert result["background"] in ("rgba(0, 0, 0, 0)", "transparent")
        assert result["animation"] == "bob"
        print("08 desk pet smoke test: transparency, animation and clean exit OK")


if __name__ == "__main__":
    main()
