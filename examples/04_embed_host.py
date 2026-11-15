"""学习目标：把 WebView2 嵌入 ctypes 创建的 Win32 宿主窗口。

运行：python examples/04_embed_host.py
预期：WebView 随宿主客户区缩放；移动窗口会同步原生弹层位置；关闭后资源有序释放。
退出：点击宿主窗口关闭按钮。
"""

import ctypes
from ctypes import wintypes

import pyminiwebview


WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_MOVE = 0x0003
WS_OVERLAPPEDWINDOW = 0x00CF0000
SW_SHOW = 5
WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
    wintypes.WPARAM, wintypes.LPARAM,
)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.DefWindowProcW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.UpdateWindow.argtypes = [wintypes.HWND]
user32.UpdateWindow.restype = wintypes.BOOL
user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
user32.UnregisterClassW.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class WndClass(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


HTML = """
<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: #f4f7fb; color: #1c2b45; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }
  main { max-width: 560px; padding: 36px; }
  .badge { color: #5269df; font-weight: 700; letter-spacing: 1px; }
  h1 { font-size: 30px; } p, li { color: #5b6980; line-height: 1.8; }
  code { color: #4258c7; }
</style>
<main><div class="badge">04 · EMBED HOST</div>
<h1>WebView2 生活在已有 HWND 中</h1>
<p>标题栏和窗口边框属于 Win32 宿主，页面属于 WebView2。</p>
<ul><li><code>autosize=True</code>：拖动边缘即可同步缩放。</li>
<li><code>WM_MOVE</code>：通知 WebView2 更新原生弹层坐标。</li>
<li>先结束共享消息循环，再关闭 WebView，最后注销窗口类。</li></ul>
</main></html>
"""


class EmbeddedHost:
    def __init__(self):
        self.hinstance = kernel32.GetModuleHandleW(None)
        self.class_name = "PyMiniWebViewExample04"
        self.class_registered = False
        self.hwnd = None
        self.view = None
        self.wndproc_ref = WNDPROC(self.wndproc)

    def create(self):
        window_class = WndClass()
        window_class.lpfnWndProc = self.wndproc_ref
        window_class.hInstance = self.hinstance
        window_class.lpszClassName = self.class_name
        if not user32.RegisterClassW(ctypes.byref(window_class)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.class_registered = True

        self.hwnd = user32.CreateWindowExW(
            0, self.class_name, "04 · Embedded Win32 host",
            WS_OVERLAPPEDWINDOW, 180, 120, 800, 560,
            None, None, self.hinstance, None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.view = pyminiwebview.WebView(
            window=self.hwnd,
            autosize=True,
            app_name="pyminiwebview-example-04",
        )
        self.view.set_html(HTML)
        user32.ShowWindow(self.hwnd, SW_SHOW)
        user32.UpdateWindow(self.hwnd)
        self.view.set_focus()

    def wndproc(self, hwnd, message, wparam, lparam):
        if message == WM_MOVE and self.view:
            self.view.notify_parent_position()
        elif message == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        elif message == WM_DESTROY:
            self.hwnd = None
            if self.view:
                self.view.terminate()
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def run(self):
        self.view.run()

    def close(self):
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
        if self.view:
            self.view.close()
            self.view = None
        if self.class_registered:
            user32.UnregisterClassW(self.class_name, self.hinstance)
            self.class_registered = False


def main():
    app = EmbeddedHost()
    try:
        app.create()
        app.run()
    finally:
        app.close()


if __name__ == "__main__":
    main()
