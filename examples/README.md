# Examples 学习路线

这些示例只使用 `pyminiwebview`、`pyminiwebview_win32`、`pyminiwebview_helpers` 和 Python 标准库，不需要 npm、CDN、Web 框架或前端构建。

## 前提

- 64 位 Windows、CPython 3.9+、Microsoft Edge WebView2 Runtime。
- 先安装项目 wheel。项目尚未发布 PyPI，请从 GitHub Actions Artifacts 获取 wheel，或按根 README 的说明本地构建。
- 在仓库根目录执行下列命令；`05` 的页面资源通过 `__file__` 定位，不依赖当前工作目录。

## 学习顺序

| 示例 | 目标 | 运行命令 | 预期现象 | 验证方式 |
|---|---|---|---|---|
| 01 Hello | 最小窗口与 `with` 清理 | `python examples/01_hello.py` | 独立欢迎窗口，关闭后进程退出 | 自动冒烟 |
| 02 JS Bridge | 同步 Python 函数、JSON 和 Promise 拒绝 | `python examples/02_js_bridge.py` | 加法、中文问候和除零错误都有页面反馈 | 自动冒烟，真实执行成功与拒绝分支 |
| 03 Background | 后台线程、取消、`dispatch` 和 `call_js` | `python examples/03_background_task.py` | 有限任务更新进度，可取消、重启，关闭时回收线程 | 自动冒烟，等待任务实际完成 |
| 04 Embed Host | 嵌入已有 Win32 `HWND` | `python examples/04_embed_host.py` | 页面随宿主缩放，移动时同步弹层位置 | 人工检查移动、缩放和关闭顺序 |
| 05 Frameless | 自定义标题栏与完整招牌应用 | `python examples/05_frameless_app/app.py` | 拖动、缩放、最小化、最大化/还原、Bridge 和后台同步均可用 | 人工交互验收；PNG/GIF 来自此示例 |
| 06 Tray & Files | 文件对话框、UTF-8 读写和托盘 | `python examples/06_tray_and_files.py` | 打开/保存文本，关闭时隐藏，托盘菜单可显示、隐藏和退出 | 人工检查对话框取消/成功、托盘和清理 |
| 07 Async Bridge | `async def`、并发任务、取消和事件循环清理 | `python examples/07_async_bridge.py` | 三个不同延迟的任务并发完成，慢任务可取消，关闭后无事件循环残留 | 自动冒烟，真实执行并发调用 |

01、02、03、07 的开发验证命令分别为：

```bash
python examples/01_hello.py --smoke-test
python examples/02_js_bridge.py --smoke-test
python examples/03_background_task.py --smoke-test
python examples/07_async_bridge.py --smoke-test
```

这些参数只用于开发测试：程序必须运行真实 WebView 消息循环并成功清理；02 必须收到 JS 端结果，03 必须等到后台任务完成，07 必须完成三个真实并发调用，否则以非零状态退出。

## 能力索引

- `Bridge`：02、05；06 也用它向页面返回文件操作结果。
- `AsyncBridge`：07；单个事件循环并发执行 `async def`，支持 `cancel_all()` 和关闭时任务清理。
- `view.dispatch` + `call_js`：03、05。后台线程不直接调用 `js_eval`。
- Win32 嵌入与 `notify_parent_position`：04、05。
- `configure_app_mode` 和无边框窗口技术：05。
- `open_file_dialog`、`save_file_dialog`、`TrayIcon`：06。

## 退出与清理

- 01–03：直接关闭窗口；上下文管理器负责 `close()`。03 会先取消并等待工作线程。
- 04：宿主 `WM_CLOSE` 销毁窗口，`WM_DESTROY` 结束共享消息循环，随后关闭 WebView 并注销窗口类。
- 05：标题栏关闭按钮走同样的宿主销毁路径；最大化只使用显示器工作区，不覆盖任务栏。
- 06：窗口关闭按钮仅隐藏页面。真正退出请用托盘 **Exit** 或页面“退出应用”；`finally` 中幂等移除托盘并关闭 WebView。
- 07：先关闭 AsyncBridge，再关闭 WebView。关闭会取消活动协程并停止事件循环；协程清理后应继续传播 `CancelledError`。
- 文件对话框取消返回 `None`，不会读取或写入文件；文本 I/O 和托盘退出策略均只存在于示例，不属于核心库。
