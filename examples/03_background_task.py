"""学习目标：后台线程执行工作，dispatch + call_js 在 UI 线程更新页面。

运行：python examples/03_background_task.py
预期：可开始、取消和重复开始有限任务；关闭窗口会取消并回收工作线程。
开发冒烟：python examples/03_background_task.py --smoke-test（等待任务真实完成）。
"""

import argparse
import threading

import pyminiwebview
from pyminiwebview_helpers import Bridge, call_js


HTML = """
<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: #101828; color: #edf2ff; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }
  main { width: min(560px, 84vw); padding: 36px; border: 1px solid #344054;
    border-radius: 22px; background: #1d2939; box-shadow: 0 24px 80px #0005; }
  h1 { font-size: 27px; margin: 0 0 10px; } p { color: #b7c3d8; line-height: 1.7; }
  progress { width: 100%; height: 18px; accent-color: #7f8cff; }
  .row { display: flex; align-items: center; gap: 14px; margin: 24px 0 14px; }
  button { border: 0; border-radius: 9px; padding: 11px 20px; font: inherit;
    cursor: pointer; color: white; background: #6574e8; }
  button.secondary { background: #475467; }
  #status { min-height: 30px; color: #b7c5ff; }
</style>
<main>
  <h1>后台任务，前台更新</h1>
  <p>工作线程只计算进度；每次页面更新都先经过 <code>view.dispatch</code>。</p>
  <div class="row"><progress id="progress" max="100" value="0"></progress>
    <strong id="percent">0%</strong></div>
  <button onclick="startTask()">开始任务</button>
  <button class="secondary" onclick="cancelTask()">取消</button>
  <p id="status" aria-live="polite">准备就绪</p>
</main>
<script>
const progress = document.getElementById('progress');
const percent = document.getElementById('percent');
const status = document.getElementById('status');
window.app = {
  update(value, message) {
    progress.value = value;
    percent.textContent = `${value}%`;
    status.textContent = message;
  }
};
async function startTask() {
  try { status.textContent = await start_task(); }
  catch (error) { status.textContent = String(error); }
}
async function cancelTask() {
  status.textContent = await cancel_task();
}
window.addEventListener('DOMContentLoaded', () => {
  if (window.__SMOKE_TEST__) startTask();
});
</script>
</html>
"""


class BackgroundTask:
    def __init__(self, view, smoke_test=False):
        self.view = view
        self.smoke_test = smoke_test
        self.smoke_completed = False
        self._lock = threading.Lock()
        self._thread = None
        self._cancel = None
        self._closed = threading.Event()

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return "任务正在运行，请等待或先取消"
            self._cancel = threading.Event()
            self._thread = threading.Thread(
                target=self._work, args=(self._cancel,),
                name="example-03-worker", daemon=True,
            )
            self._thread.start()
        return "任务已启动"

    def cancel(self):
        cancel = self._cancel
        if not cancel or not self._thread or not self._thread.is_alive():
            return "当前没有运行中的任务"
        cancel.set()
        return "正在取消任务…"

    def _post(self, function):
        if self._closed.is_set():
            return
        try:
            self.view.dispatch(function)
        except RuntimeError:
            pass

    def _work(self, cancel):
        for value in range(0, 101, 5):
            if cancel.is_set() or self._closed.is_set():
                self._post(lambda: self._finish(False))
                return
            self._post(lambda value=value: call_js(
                self.view, "app.update", value, f"后台工作中：{value}%"
            ))
            cancel.wait(0.04)
        self._post(lambda: self._finish(True))

    def _finish(self, completed):
        if self._closed.is_set():
            return
        message = "任务完成" if completed else "任务已取消"
        call_js(self.view, "app.update", 100 if completed else 0, message)
        self.smoke_completed = completed
        if self.smoke_test:
            self.view.terminate()

    def close(self):
        self._closed.set()
        if self._cancel:
            self._cancel.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)
        if thread and thread.is_alive():
            raise RuntimeError("后台线程未能及时退出")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true",
                        help="启动真实后台任务，等待完成后退出")
    args = parser.parse_args()

    with pyminiwebview.WebView(
        title="03 · Background task",
        width=720,
        height=500,
        app_name="pyminiwebview-example-03",
    ) as view:
        task = BackgroundTask(view, args.smoke_test)
        bridge = Bridge(view)
        bridge.expose("start_task")(task.start)
        bridge.expose("cancel_task")(task.cancel)
        if args.smoke_test:
            view.js_init("window.__SMOKE_TEST__ = true;")
        view.set_html(HTML)
        watchdog = None
        if args.smoke_test:
            watchdog = threading.Timer(10, view.terminate)
            watchdog.start()
        try:
            view.run()
        finally:
            if watchdog:
                watchdog.cancel()
            task.close()
    if args.smoke_test:
        if not task.smoke_completed:
            raise RuntimeError("后台任务未完成")
        print("03 background smoke test: thread, dispatch and completion OK")


if __name__ == "__main__":
    main()
