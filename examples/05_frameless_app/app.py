"""学习目标：使用 FramelessWindow、Bridge、后台线程和 UI 更新。

运行：python examples/05_frameless_app/app.py
预期：可拖动/缩放窗口，最小化、最大化、还原和关闭；两个演示按钮均真实工作。
退出：点击标题栏右侧关闭按钮；关闭时会取消并回收后台线程。
开发冒烟：python examples/05_frameless_app/app.py --smoke-test
"""

import argparse
import threading
from pathlib import Path

from pyminiwebview_helpers import call_js
from pyminiwebview_win32 import FramelessWindow


BG_COLOR = 0x0026120D


def get_dashboard_data():
    return {
        "items": 3,
        "total": 128,
        "checkedAt": "今天 14:30",
        "message": "Python 已确认：3 项演示数据，合计 128",
    }


class DemoTasks:
    def __init__(self):
        self.view = None
        self._closed = threading.Event()
        self._task_lock = threading.Lock()
        self._task_thread = None
        self._task_cancel = None

    def start(self):
        with self._task_lock:
            if self._task_thread and self._task_thread.is_alive():
                return {"started": False, "message": "同步正在运行，请勿重复启动"}
            self._task_cancel = threading.Event()
            self._task_thread = threading.Thread(
                target=self._worker,
                args=(self._task_cancel,),
                name="frameless-sync-demo",
                daemon=True,
            )
            self._task_thread.start()
        return {"started": True, "message": "后台同步已启动"}

    def cancel(self):
        if not self._task_thread or not self._task_thread.is_alive():
            return {"cancelled": False, "message": "当前没有运行中的同步"}
        self._task_cancel.set()
        return {"cancelled": True, "message": "正在取消同步…"}

    def _post(self, function):
        if self._closed.is_set():
            return
        try:
            self.view.dispatch(function)
        except RuntimeError:
            pass

    def _worker(self, cancel):
        for value in (12, 28, 46, 64, 82, 100):
            if cancel.wait(0.22) or self._closed.is_set():
                self._post(lambda: call_js(self.view, "app.taskFinished", False))
                return
            self._post(lambda value=value: call_js(
                self.view, "app.updateTask", value, f"后台线程正在同步：{value}%"
            ))
        self._post(lambda: call_js(self.view, "app.taskFinished", True))

    def stop(self):
        self._closed.set()
        if self._task_cancel:
            self._task_cancel.set()
        thread = self._task_thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)
        if thread and thread.is_alive():
            raise RuntimeError("演示后台线程未能及时退出")


def load_html():
    source_dir = Path(__file__).resolve().parent
    html = (source_dir / "index.html").read_text(encoding="utf-8")
    css = (source_dir / "app.css").read_text(encoding="utf-8")
    javascript = (source_dir / "app.js").read_text(encoding="utf-8")
    return html.replace(
        '<link rel="stylesheet" href="app.css">', f"<style>{css}</style>"
    ).replace('<script src="app.js"></script>', f"<script>{javascript}</script>")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke-test", action="store_true",
        help="真实打开无边框窗口、调用 Bridge 并正常退出",
    )
    args = parser.parse_args()
    smoke_results = []
    tasks = DemoTasks()

    with FramelessWindow(
        title="pyminiwebview · Frameless showcase",
        width=1100,
        height=740,
        min_width=720,
        min_height=520,
        app_name="pyminiwebview-example-05",
        bgcolor=BG_COLOR,
    ) as window:
        tasks.view = window.view
        window.on_maximize_change = lambda maximized: call_js(
            window.view, "app.setMaximized", maximized
        )
        window.bridge.expose(get_dashboard_data, name="get_dashboard_data")
        window.bridge.expose(tasks.start, name="start_sync")
        window.bridge.expose(tasks.cancel, name="cancel_sync")

        watchdog = None
        if args.smoke_test:
            def smoke_finish(result):
                smoke_results.append(result)
                window.close_window()

            window.bridge.expose(smoke_finish, name="__smoke_finish")
            window.view.js_init(
                """
                document.addEventListener('DOMContentLoaded', async () => {
                  const result = await get_dashboard_data();
                  await __smoke_finish(result);
                });
                """
            )
            watchdog = threading.Timer(10, window.view.terminate)
            watchdog.start()

        window.view.set_html(load_html())
        try:
            window.run()
        finally:
            if watchdog:
                watchdog.cancel()
            tasks.stop()

    if args.smoke_test:
        if len(smoke_results) != 1 or smoke_results[0]["total"] != 128:
            raise RuntimeError("无边框示例未完成真实 Bridge 调用")
        print("05 frameless helper: startup, bridge and clean exit OK")


if __name__ == "__main__":
    main()
