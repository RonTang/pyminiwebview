"""学习目标：使用 Bridge 完成 JS → Python → JS 的双向调用。

运行：python examples/02_js_bridge.py
预期：可计算加法、生成中文问候，并在除零时看到 Promise 拒绝信息。
开发冒烟：python examples/02_js_bridge.py --smoke-test（真实执行三组调用）。
"""

import argparse
import threading

import pyminiwebview
from pyminiwebview_helpers import Bridge


HTML = """
<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; padding: 34px; background: #f3f6fb; color: #172033;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }
  main { max-width: 700px; margin: auto; }
  h1 { margin: 0 0 8px; } .sub { color: #68758d; margin-top: 0; }
  section { background: white; padding: 20px; margin: 16px 0; border-radius: 16px;
    box-shadow: 0 8px 28px #2537640d; }
  h2 { font-size: 17px; margin: 0 0 14px; }
  input { width: 120px; padding: 10px; border: 1px solid #d5dceb; border-radius: 8px;
    font: inherit; }
  button { padding: 10px 18px; border: 0; border-radius: 8px; background: #5369e8;
    color: white; font: inherit; cursor: pointer; margin-left: 8px; }
  button:hover { background: #4056ce; }
  #greet-name { width: 220px; }
  #output { min-height: 92px; white-space: pre-wrap; line-height: 1.7; }
  .ok { color: #147a55; } .error { color: #c43d52; }
</style>
<main>
  <h1>JavaScript 与 Python 对话</h1>
  <p class="sub">Bridge 负责请求 JSON、返回值和 Promise 拒绝，示例只写业务函数。</p>
  <section>
    <h2>1. 加法</h2>
    <input id="a" type="text" value="20" aria-label="加数 A"> +
    <input id="b" type="text" value="22" aria-label="加数 B">
    <button onclick="runAdd()">调用 add</button>
  </section>
  <section>
    <h2>2. 中文问候</h2>
    <input id="greet-name" value="世界" aria-label="名字">
    <button onclick="runGreet()">调用 greet</button>
  </section>
  <section>
    <h2>3. Python 异常</h2>
    <p>用上面的加数作为被除数和除数；除数为零时进入 Promise 拒绝分支。</p>
    <button onclick="runDivide()">调用 divide</button>
  </section>
  <section id="output" aria-live="polite">等待调用…</section>
</main>
<script>
const output = document.getElementById('output');
function show(message, isError = false) {
  output.className = isError ? 'error' : 'ok';
  output.textContent = message;
}
function readNumber(id, label) {
  const text = document.getElementById(id).value.trim();
  if (!text) throw new Error(`请输入${label}`);
  const value = Number(text);
  if (!Number.isFinite(value)) throw new Error(`${label}必须是有效数字`);
  return value;
}
function errorText(error) {
  return error && error.error ? `${error.error.type}: ${error.error.message}` : String(error);
}
async function runAdd() {
  try { show(`成功：${await add(readNumber('a', '加数 A'), readNumber('b', '加数 B'))}`); }
  catch (error) { show(errorText(error), true); }
}
async function runGreet() {
  const name = document.getElementById('greet-name').value.trim();
  if (!name) { show('请输入名字', true); return; }
  try { show(`成功：${await greet(name)}`); }
  catch (error) { show(errorText(error), true); }
}
async function runDivide() {
  try { show(`成功：${await divide(readNumber('a', '被除数'), readNumber('b', '除数'))}`); }
  catch (error) { show(`Promise 已拒绝：${errorText(error)}`, true); }
}

if (window.__SMOKE_TEST__) {
  window.addEventListener('DOMContentLoaded', async () => {
    const results = {sum: await add(20, 22), greeting: await greet('世界')};
    try { await divide(20, 0); } catch (error) { results.rejection = error; }
    await __smoke_finish(results);
  });
}
</script>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true",
                        help="在真实页面中验证成功与拒绝分支后退出")
    args = parser.parse_args()
    smoke_results = []

    with pyminiwebview.WebView(
        title="02 · JavaScript Bridge",
        width=780,
        height=720,
        app_name="pyminiwebview-example-02",
    ) as view:
        bridge = Bridge(view)

        @bridge.expose
        def add(a, b):
            return a + b

        @bridge.expose("greet")
        def hello(name):
            return f"你好，{name}"

        @bridge.expose
        def divide(a, b):
            return a / b

        if args.smoke_test:
            @bridge.expose("__smoke_finish")
            def smoke_finish(results):
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
        if len(smoke_results) != 1:
            raise RuntimeError("页面未完成 Bridge 冒烟调用")
        results = smoke_results[0]
        assert results["sum"] == 42
        assert results["greeting"] == "你好，世界"
        assert results["rejection"]["error"]["type"] == "ZeroDivisionError"
        print("02 bridge smoke test: success, Chinese and rejection OK")


if __name__ == "__main__":
    main()
