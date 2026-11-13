import ctypes
import os
import sys
import threading
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import pyminiwebview
from pyminiwebview_win32 import TrayIcon

WM_CLOSE = 0x0010
GWLP_WNDPROC = -4
SW_HIDE = 0
SW_SHOW = 5
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080
ID_TOGGLE = 1001
ID_EXIT = 1002

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
    wintypes.WPARAM, wintypes.LPARAM,
)
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.CallWindowProcW.argtypes = [
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
    wintypes.WPARAM, wintypes.LPARAM,
]
user32.CallWindowProcW.restype = ctypes.c_ssize_t
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
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


class TrayApplication:
    def __init__(self):
        self.view = pyminiwebview.WebView(
            title="Tray application", width=480, height=320
        )
        self.view.set_html(
            "<h2>Tray application</h2>"
            "<p>Closing this window hides it.</p>"
            "<p>Left click: show/hide. Right click: menu.</p>"
        )
        self.hwnd = self.view.get_native_handle(
            pyminiwebview.NATIVE_HANDLE_KIND_UI_WINDOW
        )
        self._wndproc_ref = WNDPROC(self._wndproc)
        self._old_wndproc = user32.SetWindowLongPtrW(
            self.hwnd, GWLP_WNDPROC,
            ctypes.cast(self._wndproc_ref, ctypes.c_void_p).value,
        )
        if not self._old_wndproc:
            raise ctypes.WinError(ctypes.get_last_error())
        self.tray = TrayIcon(
            tooltip="pyminiwebview tray application",
            on_left_click=self.toggle_window,
            on_right_click=self.show_menu,
        )

    def show_window(self):
        user32.ShowWindow(self.hwnd, SW_SHOW)
        user32.SetForegroundWindow(self.hwnd)
        self.view.set_focus()

    def toggle_window(self):
        if user32.IsWindowVisible(self.hwnd):
            user32.ShowWindow(self.hwnd, SW_HIDE)
        else:
            self.show_window()

    def show_menu(self):
        menu = user32.CreatePopupMenu()
        if not menu:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            user32.AppendMenuW(menu, 0, ID_TOGGLE, "Show / Hide")
            user32.AppendMenuW(menu, 0, ID_EXIT, "Exit")
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            user32.SetForegroundWindow(self.hwnd)
            command = user32.TrackPopupMenu(
                menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                point.x, point.y, 0, self.hwnd, None,
            )
        finally:
            user32.DestroyMenu(menu)
        if command == ID_TOGGLE:
            self.toggle_window()
        elif command == ID_EXIT:
            self.view.terminate()

    def _wndproc(self, hwnd, message, wparam, lparam):
        if message == WM_CLOSE:
            user32.ShowWindow(hwnd, SW_HIDE)
            return 0
        return user32.CallWindowProcW(
            self._old_wndproc, hwnd, message, wparam, lparam
        )

    def run(self):
        seconds = float(os.environ.get("TRAY_TEST_SECONDS", "0"))
        timer = None
        if seconds > 0:
            timer = threading.Timer(seconds, self.view.terminate)
            timer.start()
        try:
            self.view.run()
        finally:
            if timer:
                timer.cancel()
            self.tray.remove()
            user32.SetWindowLongPtrW(
                self.hwnd, GWLP_WNDPROC, self._old_wndproc
            )
            self.view.close()


def main():
    print("Close button: hide window.", flush=True)
    print("Tray left click: show/hide. Right click: Show / Hide or Exit.", flush=True)
    print("Use the tray Exit menu to quit.", flush=True)
    TrayApplication().run()


if __name__ == "__main__":
    main()
