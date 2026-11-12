# pyminiwebview

`pyminiwebview` 是一个仅面向 Windows + Microsoft Edge WebView2 的轻量级 CPython 原生扩展。它提供窗口内 WebView2 控件、JavaScript 绑定和 UI 线程投递，不试图成为完整的桌面应用框架。

- Python 3.9+，使用 Stable ABI（`Py_LIMITED_API=0x03090000`）；wheel 标签为 `abi3`。
- 仅使用 CPython C API、Win32 和系统 WebView2 Runtime，无 Python 运行时依赖。
- 支持独立窗口和嵌入已有 `HWND` 两种模式。

## 架构与边界

分层如下：

1. `pyminiwebview.WebView`：重写的 CPython Stable ABI 绑定层，负责参数检查、GIL、Python 引用生命周期和异常转换。
2. `vendor/webview/`：vendored 的 webview C++ 引擎，负责 WebView2 COM 对象、消息窗口和事件循环；仅保留 `create_ex`、Win32 `run` 和 `dispatch` 三个 API 补丁。
3. 应用或 GUI 框架：负责宿主窗口和完整窗口生命周期。

本扩展只做 WebView2 内在操作。嵌入模式下，全屏、宿主窗口标题、窗口图标、菜单、快捷键、文件对话框、托盘、注册表等均由应用处理，可使用 `ctypes` 或 `pywin32`。因此没有沿用原项目通过 `SetParent` 拆出控件的 `set_fullscreen`；嵌入模式的 `set_title` 也不会修改宿主窗口。

除 `terminate`、`js_return` 和 `dispatch` 外，其余方法应在创建实例的 UI 线程调用。`dispatch(fn)` 接受无参数 callable，在 UI 线程执行； callable 抛出的异常通过 `PyErr_PrintEx(0)` 输出，不会跨原生消息边界传播。

## 安装与运行

系统需安装 Microsoft Edge WebView2 Runtime。Windows 11 通常已预装。

```bash
python -m pip install pyminiwebview
```

最小示例：

```python
import pyminiwebview

view = pyminiwebview.WebView(
    title="pyminiwebview",
    width=900,
    height=600,
    app_name="my-app",
    debug=True,
)
view.set_html("<h1>Hello from WebView2</h1>")
view.run()
```

JavaScript 调用 Python：

```python
import json
import pyminiwebview

view = pyminiwebview.WebView(app_name="binding-demo")

def add(request_id, request):
    values = json.loads(request)
    view.js_return(request_id, 0, json.dumps(sum(values)))

view.js_bind("add", add)
view.set_html("<script>add(20, 22).then(console.log)</script>")
view.run()
```

后台线程投递：

```python
import threading

def worker():
    view.dispatch(lambda: view.set_title("Updated on the UI thread"))

threading.Thread(target=worker).start()
view.run()
```

### 构造函数

```python
WebView(
    debug=False,
    window=0,
    autosize=False,
    width=320,
    height=240,
    url=None,
    title=None,
    icon=None,
    bgcolor=0xFFFFFF,
    user_data_folder=None,
    app_name="pyminiwebview",
    clipboard_permission="default",
)
```

- `window`：非零时嵌入该 `HWND`，否则创建独立窗口；按 64 位无符号句柄处理。
- `autosize`：仅嵌入模式，控件跟随宿主客户区尺寸。
- `title`、`icon`：仅独立窗口生效，不修改宿主窗口属性。
- `bgcolor`：Win32 `COLORREF`，字节顺序为 BGR。
- `user_data_folder`：显式指定 WebView2 用户数据目录。默认使用 `%LOCALAPPDATA%\<app_name>`，不再根据 `python.exe` 推导。
- `clipboard_permission`：`"default"`（默认，由 WebView2 询问用户）、`"allow"` 或 `"deny"`，控制剪贴板读取权限请求。

方法：`js_bind(name, fn)`、`js_eval(js)`、`js_init(js)`、`js_return(id, status, result)`、`js_unbind(name)`、`navigate(url)`、`set_html(html)`、`set_title(title)`、`set_size(width, height, hints=0)`、`set_focus()`、`get_native_handle(kind)`、`run(hwnd=0, haccel=0)`、`terminate()`、`dispatch(fn)`。

JS 绑定回调签名为 `fn(request_id, request_json)`；第二个参数是 JSON 数组字符串，回调返回值不会被隐式发送，需显式调用 `js_return`。

## 相对 python-webview2 的修复与差异

Python 扩展层完全重写，不复用原 `main.c`：

1. `run()` 用 `Py_BEGIN_ALLOW_THREADS` / `Py_END_ALLOW_THREADS` 释放 GIL；JS 和 dispatch 回调成对使用 `PyGILState_Ensure` / `PyGILState_Release`。
2. 每个绑定回调只有一个明确的强引用所有者；`js_unbind`、重复绑定失败和对象析构均正确释放。调用结果及参数元组均配对 `Py_DECREF`，Python 异常打印并清除。
3. 检查 WebView 创建结果和原生 API 错误码，非法参数、无效状态及运行时失败转换为 Python 异常。
4. `HWND` / `HACCEL` 使用 `"K"` 解析；原生句柄以 64 位整数返回。
5. `tp_init` 成功返回 `0`，类型通过 `PyType_FromSpec` 创建。
6. 用户数据目录可显式配置，默认改为 `%LOCALAPPDATA%\<app_name>`。
7. 剪贴板读取默认 `"default"`，不再无条件允许。
8. 删除破坏嵌入关系的 `set_fullscreen` 实现，窗口全屏交由宿主处理。
9. 新增线程安全的 `dispatch(fn)`；销毁时清理尚未执行的投递，避免回调引用泄漏。
10. 嵌入模式统一初始化 COM STA，焦点操作使用 `ICoreWebView2Controller::MoveFocus`，不再依赖 Chromium 内部窗口类名。

## 构建

需要 MSVC（Visual Studio 2022 的“使用 C++ 的桌面开发”组件）和 Python 3.9+。在 **x64 Native Tools Command Prompt** 或已初始化 MSVC 环境的终端执行：

```bash
python -m pip install setuptools wheel pytest
python setup.py build_ext --inplace
python -m pytest
```

构建 PEP 517 wheel：

```bash
python -m pip install build
python -m build --wheel
```

`setup.py` 同时设置 `py_limited_api=True`，`setup.cfg` 指定 `cp39` ABI 基线。GitHub Actions 使用 cibuildwheel 构建并测试 `win_amd64` 的 abi3 wheel；发布 GitHub Release 时通过 PyPI Trusted Publishing 发布。PyPI 项目需先配置对应仓库和工作流的 trusted publisher。

## vendored 代码与补丁管理

当前基线为 webview/webview **tag `0.12.0`**，完整 commit **`3ab4b5d722438fc8a13e6ca830c5e2372d19a01d`**，同步日期 **2026-11-12**。上游 `core/include/webview*` 映射到本仓库 `vendor/`；WebView2 SDK 使用上游配置的官方 `1.0.1150.38` 头文件。

本地仅保留三个引擎 API 补丁：

1. `webview_create_ex`：用户目录、应用名、剪贴板策略及嵌入 COM 初始化。
2. `webview_run(hwnd, haccel)`：Win32 加速键和消息循环错误检查。
3. `webview_dispatch`：投递错误、析构清理、异常边界及后台终止。

**补丁封顶原则：新需求只能放入 Python 层或项目自有源码，不再增加 vendor 补丁 API。** 背景色等 WebView2 操作已经直接在 `_module.cpp` 实现。

所有补丁点均以 `pyminiwebview patch begin/end` 成对标记；完整补丁为 `patches/0001-pyminiwebview-engine-extensions.patch`，详细元数据见 `vendor/README.md`。

同步上游的 runbook：

1. 用 `git ls-remote --tags` 选择最新 release tag，并将 annotated tag 解引用为完整 commit。
2. 在临时目录检出该 tag，确认文件布局和 WebView2 SDK 版本。
3. 用上游 `core/include/webview*` 替换 `vendor/` 对应文件，再执行 `git apply --check` 并应用现有 patch。
4. 若补丁冲突，只手工移植上述三个 API；检查所有改动均有成对标记。
5. 运行 `build_ext --inplace`、完整 pytest 和真实 `test2.py` 窗口测试。
6. 从干净上游基线重新生成 patch，验证应用后文件一致，再更新 tag、commit 和同步日期。

上游已实现同名功能时不能直接退役补丁。只有其公开 API 覆盖完整语义、`_module.cpp` 可完全移除本地扩展调用，且目录/权限/线程/析构行为与全部测试均无回归时才退役；删除对应补丁后重新生成 patch。

## 测试范围

pytest 在真实 WebView2 Runtime 中覆盖：

- 1000 次绑定/解绑的回调引用计数稳定，以及导航、HTML 加载和销毁。
- 实际 JS→Python 回调与 `js_return`。
- `run()` 期间 `threading.Timer` 能执行，且 `dispatch` 在 UI 线程运行。
- 通过 `CreateWindowExW` 创建宿主窗口并验证 autosize。
- 非法参数抛出 Python 异常，64 位 `HWND` 参数解析。

## 致谢与许可

- [webview/webview](https://github.com/webview/webview)：MIT，版权 Serge Zaitsev / Steffen André Langnes。
- [59de44955ebd/python-webview2](https://github.com/59de44955ebd/python-webview2)：MIT；本项目参考其功能设计，但 Python 绑定层为重写，当前引擎直接跟踪 webview 上游 tag。
- Microsoft WebView2 SDK 官方头文件保留原始版权声明，BSD 3-Clause 许可证见 `licenses/Microsoft-WebView2-LICENSE.txt`。

本项目采用根目录的 MIT License，Copyright (c) 2026 Ron Tang。第三方来源及改动说明见 `THIRD_PARTY_NOTICES.md`。
