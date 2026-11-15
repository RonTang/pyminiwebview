"""学习目标：用 AsyncBridge 并发运行 async def，并安全取消和关闭任务。

运行：python examples/07_async_bridge.py
预期：三个不同延迟的调用并发完成；慢任务可取消；关闭窗口会清理事件循环。
开发冒烟：python examples/07_async_bridge.py --smoke-test（真实执行并发调用）。
"""

import argparse
import asyncio
import threading

import pyminiwebview
from pyminiwebview_helpers import AsyncBridge


HTML = """
<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: #111827; color: #edf2ff; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }
  main { width: min(650px, 86vw); padding: 34px; border: 1px solid #334155;
    border-radius: 20px; background: #1e293b; box-shadow: 0 24px 70px #0005; }
  h1 { margin-top: 0; } p { color: #aebbd0; line-height: 1.7; }
  button { border: 0; border-radius: 8px; padding: 11px 16px; margin: 8px 8px 8px 0;
    background: #667eea; color: white; font: inherit; cursor: pointer; }
  button.secondary { background: #475569; }
  pre { min-height: 150px; padding: 18px; white-space: pre-wrap; border-radius: 12px;
    background: #0f172a; color: #a7f3d0; line-height: 1.7; }
  .error { color: #fda4af; }
</style>
<main>
  <h1>AsyncBridge</h1>
  <p>一个常驻 asyncio 事件循环并发处理调用，不为每次请求创建线程。</p>
  <button onclick="runBatch()">并发获取三项数据</button>
  <button class="secondary" onclick="runSlow()">启动 30 秒慢任务</button>
  <button class="secondary" onclick="cancelTasks()">取消全部</button>
  <pre id="output" aria-live="polite">准备就绪</pre>
</main>
<script>
const output = document.getElementById('output');
function show(value, isError = false) {
  output.className = isError ? 'error' : '';
  output.textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
}
function errorText(error) {
  return error && error.error ? `${error.error.type}: ${error.error.message}` : String(error);
}
async function runBatch() {
  show('三个任务正在并发执行…');
  try { show(await Promise.all([fetch_item(1), fetch_item(2), fetch_item(3)])); }
  catch (error) { show(errorText(error), true); }
}
async function runSlow() {
  show('慢任务已启动；UI 仍可操作，点击“取消全部”可取消。');
  try { show(await slow_task()); }
  catch (error) { show(errorText(error), true); }
}
function cancelTasks() {
  output.textContent = '已请求取消当前任务';
  cancel_all();
}
async function smoke() {
  const results = await Promise.all([fetch_item(1), fetch_item(2), fetch_item(3)]);
  await __smoke_finish(results);
}
window.addEventListener('DOMContentLoaded', () => {
  if (window.__SMOKE_TEST__) smoke();
});
</script></html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true",
                        help="真实执行三个并发调用后退出")
    args = parser.parse_args()
    smoke_results = []

    with pyminiwebview.WebView(
        title="07 · AsyncBridge",
        width=760,
        height=590,
        app_name="pyminiwebview-example-07",
    ) as view:
        with AsyncBridge(view) as bridge:
            @bridge.expose
            async def fetch_item(value):
                await asyncio.sleep((4 - value) * 0.1)
                return {"item": value, "message": f"数据 {value} 已完成"}

            @bridge.expose
            async def slow_task():
                await asyncio.sleep(30)
                return "慢任务已完成"

            @bridge.expose
            async def cancel_all():
                bridge.cancel_all()

            if args.smoke_test:
                @bridge.expose("__smoke_finish")
                async def smoke_finish(results):
                    smoke_results.append(results)
                    view.terminate()

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

    if args.smoke_test:
        if len(smoke_results) != 1 or len(smoke_results[0]) != 3:
            raise RuntimeError("异步示例未完成三个并发调用")
        assert [item["item"] for item in smoke_results[0]] == [1, 2, 3]
        print("07 async bridge smoke test: concurrent calls and clean shutdown OK")


if __name__ == "__main__":
    main()
