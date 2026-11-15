"""学习目标：用最少的代码创建、显示并清理一个 WebView2 窗口。

运行：python examples/01_hello.py
预期：看到一个独立的欢迎窗口；点击窗口关闭按钮后，进程正常退出。
开发冒烟：python examples/01_hello.py --smoke-test（启动后自动退出）。
"""

import argparse
import threading

import pyminiwebview


HTML = """
<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    color: #172033; background: linear-gradient(135deg, #eef4ff, #f8f5ff);
  }
  main { width: min(520px, 84vw); padding: 48px; border-radius: 24px;
    background: rgba(255,255,255,.88); box-shadow: 0 24px 70px #5368a626; }
  .mark { color: #5167e8; font-size: 13px; font-weight: 700; letter-spacing: 2px; }
  h1 { margin: 14px 0; font-size: 34px; }
  p { color: #63708a; line-height: 1.8; }
  code { color: #4659cf; }
</style>
<main>
  <div class="mark">PYMINIWEBVIEW · 01</div>
  <h1>Hello, WebView2!</h1>
  <p>这是一个由 Python 创建的原生 Windows 窗口，页面来自内联 HTML。</p>
  <p>关闭窗口后，<code>with</code> 会负责释放 WebView 资源。</p>
</main>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true",
                        help="自动启动并退出，供开发验证使用")
    args = parser.parse_args()

    with pyminiwebview.WebView(
        title="01 · Hello pyminiwebview",
        width=720,
        height=480,
        app_name="pyminiwebview-example-01",
    ) as view:
        view.set_html(HTML)
        timer = None
        if args.smoke_test:
            timer = threading.Timer(1.5, view.terminate)
            timer.start()
        try:
            view.run()
        finally:
            if timer:
                timer.cancel()
    if args.smoke_test:
        print("01 hello smoke test: startup and clean exit OK")


if __name__ == "__main__":
    main()
