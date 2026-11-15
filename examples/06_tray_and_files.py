"""学习目标：组合文件对话框、UTF-8 文本编辑和托盘菜单。

运行：python examples/06_tray_and_files.py
预期：可打开、编辑和保存 UTF-8 文本；关闭按钮只隐藏窗口，托盘菜单可显示或退出。
退出：右键托盘图标选择 Exit，或点击页面“退出应用”。托盘和 WebView 会被清理。
"""

import ctypes
from ctypes import wintypes
from pathlib import Path

import pyminiwebview
from pyminiwebview_helpers import Bridge
from pyminiwebview_win32 import TrayIcon, open_file_dialog, save_file_dialog


WM_CLOSE = 0x0010
GWLP_WNDPROC = -4
SW_HIDE = 0
SW_SHOW = 5
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080
ID_SHOW = 1001
ID_HIDE = 1002
ID_EXIT = 1003
WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
    wintypes.WPARAM, wintypes.LPARAM,
)
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.CallWindowProcW.argtypes = [
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
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


HTML = """
<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; height: 100vh; display: flex; flex-direction: column;
    background: #f5f6fa; color: #202a3d; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }
  header { padding: 20px 26px 12px; } h1 { font-size: 22px; margin: 0 0 5px; }
  header p { margin: 0; color: #6c7688; font-size: 12px; }
  .toolbar { display: flex; gap: 8px; padding: 0 26px 14px; }
  button { border: 0; border-radius: 8px; padding: 9px 16px; cursor: pointer;
    background: #586ddd; color: white; font: inherit; }
  button.secondary { background: #e0e4ef; color: #39445b; }
  textarea { flex: 1; resize: none; margin: 0 26px; padding: 16px; border: 1px solid #d9deea;
    border-radius: 12px; outline: none; background: white; color: #263149;
    font: 14px/1.7 Consolas, "Microsoft YaHei", monospace; }
  textarea:focus { border-color: #7183e5; }
  footer { display: flex; justify-content: space-between; gap: 12px; padding: 13px 26px 18px;
    color: #687489; font-size: 12px; }
  #status.error { color: #c43d52; } #status.ok { color: #147a55; }
</style>
<header><h1>托盘文本编辑器</h1><p>UTF-8 · 文件读写留在示例中 · 关闭窗口不会退出应用</p></header>
<div class="toolbar"><button onclick="openFile()">打开…</button>
<button onclick="saveFile()">保存…</button><button class="secondary" onclick="exitApp()">退出应用</button></div>
<textarea id="editor" spellcheck="false">在这里输入文本，或打开一个 UTF-8 文本文件。</textarea>
<footer><span id="file-name">未命名</span><span id="status" aria-live="polite">准备就绪</span></footer>
<script>
const editor = document.getElementById('editor');
const status = document.getElementById('status');
const fileName = document.getElementById('file-name');
function show(result) {
  status.textContent = result.message;
  status.className = result.ok ? 'ok' : 'error';
}
function message(error) { return error && error.error ? error.error.message : String(error); }
async function openFile() {
  try { const result = await open_text_file(); show(result);
    if (result.ok && !result.cancelled) { editor.value = result.content; fileName.textContent = result.name; }
  } catch (error) { show({ok: false, message: message(error)}); }
}
async function saveFile() {
  try { const result = await save_text_file(editor.value); show(result);
    if (result.ok && !result.cancelled) fileName.textContent = result.name;
  } catch (error) { show({ok: false, message: message(error)}); }
}
async function exitApp() { await exit_app(); }
</script></html>
"""


class TrayTextApp:
    def __init__(self):
        self.view = pyminiwebview.WebView(
            title="06 · Tray and text files",
            width=780,
            height=600,
            app_name="pyminiwebview-example-06",
        )
        self.hwnd = self.view.get_native_handle(
            pyminiwebview.NATIVE_HANDLE_KIND_UI_WINDOW
        )
        self.current_path = None
        self.tray = None
        self._wndproc_ref = WNDPROC(self._wndproc)
        self._old_wndproc = user32.SetWindowLongPtrW(
            self.hwnd, GWLP_WNDPROC,
            ctypes.cast(self._wndproc_ref, ctypes.c_void_p).value,
        )
        if not self._old_wndproc:
            self.view.close()
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            bridge = Bridge(self.view)
            bridge.expose("open_text_file")(self.open_text_file)
            bridge.expose("save_text_file")(self.save_text_file)
            bridge.expose("exit_app")(self.exit_app)
            self.view.set_html(HTML)
            self.tray = TrayIcon(
                tooltip="pyminiwebview 文本编辑器",
                on_left_click=self.toggle_window,
                on_right_click=self.show_menu,
            )
        except BaseException:
            user32.SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC, self._old_wndproc)
            self.view.close()
            raise

    def _owner(self):
        return self.hwnd

    def open_text_file(self):
        path = open_file_dialog(
            hwnd_owner=self._owner(), title="打开 UTF-8 文本",
            filters=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if path is None:
            return {"ok": True, "cancelled": True, "message": "已取消打开，未读取任何文件"}
        try:
            content = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            return {"ok": False, "message": f"打开失败：{error}"}
        self.current_path = Path(path)
        return {
            "ok": True, "content": content, "name": self.current_path.name,
            "message": f"已打开 {self.current_path.name}",
        }

    def save_text_file(self, content):
        path = save_file_dialog(
            hwnd_owner=self._owner(), title="保存 UTF-8 文本",
            filters=[("Text Files", "*.txt"), ("All Files", "*.*")],
            initial_file=self.current_path.name if self.current_path else "untitled.txt",
        )
        if path is None:
            return {"ok": True, "cancelled": True, "message": "已取消保存，未写入任何文件"}
        try:
            Path(path).write_text(content, encoding="utf-8")
        except (OSError, UnicodeError) as error:
            return {"ok": False, "message": f"保存失败：{error}"}
        self.current_path = Path(path)
        return {
            "ok": True, "name": self.current_path.name,
            "message": f"保存成功：{self.current_path.name}",
        }

    def show_window(self):
        user32.ShowWindow(self.hwnd, SW_SHOW)
        user32.SetForegroundWindow(self.hwnd)
        self.view.set_focus()

    def hide_window(self):
        user32.ShowWindow(self.hwnd, SW_HIDE)

    def toggle_window(self):
        if user32.IsWindowVisible(self.hwnd):
            self.hide_window()
        else:
            self.show_window()

    def exit_app(self):
        self.view.terminate()
        return True

    def show_menu(self):
        menu = user32.CreatePopupMenu()
        if not menu:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            user32.AppendMenuW(menu, 0, ID_SHOW, "Show")
            user32.AppendMenuW(menu, 0, ID_HIDE, "Hide")
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
        if command == ID_SHOW:
            self.show_window()
        elif command == ID_HIDE:
            self.hide_window()
        elif command == ID_EXIT:
            self.exit_app()

    def _wndproc(self, hwnd, message, wparam, lparam):
        if message == WM_CLOSE:
            self.hide_window()
            return 0
        return user32.CallWindowProcW(
            self._old_wndproc, hwnd, message, wparam, lparam
        )

    def run(self):
        try:
            self.view.run()
        finally:
            if self.tray:
                self.tray.remove()
                self.tray = None
            user32.SetWindowLongPtrW(
                self.hwnd, GWLP_WNDPROC, self._old_wndproc
            )
            self.view.close()


def main():
    print("关闭按钮：隐藏窗口。托盘左键：显示/隐藏；右键：Show / Hide / Exit。")
    TrayTextApp().run()


if __name__ == "__main__":
    main()
