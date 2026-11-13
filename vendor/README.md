# vendored WebView 基线与补丁

## 基线

- 上游仓库：https://github.com/webview/webview
- 基线 tag：`0.12.0`（当前最新 release tag）
- 基线 commit：`3ab4b5d722438fc8a13e6ca830c5e2372d19a01d`
- 同步日期：2026-11-12
- 上游文件 `core/include/webview/webview.h` → `vendor/webview/webview.h`
- 上游文件 `core/include/webview.h` → `vendor/webview.h`
- WebView2 SDK：`Microsoft.Web.WebView2 1.0.1150.38`，与上游该 tag 的 CMake 配置一致；官方头文件位于 `vendor/WebView2*.h`。

只有 `vendor/webview/webview.h` 含本地补丁。所有补丁区域均由以下标记成对包围：

```cpp
// ==== pyminiwebview patch begin ====
// ==== pyminiwebview patch end ====
```

每段还注明了对应 API、改动原因和 `src/pyminiwebview/_module.cpp` 中的依赖函数。

## 补丁封顶原则

引擎补丁仅限 `webview_create_ex`、`webview_run_with_accelerators(hwnd, haccel)`、`webview_dispatch` 这三个 API 及其必需的内部实现。`webview_run(w)` 保持上游公开签名，并转调加速键版本且传入空句柄。新需求必须放在 Python 绑定层或项目自有源码文件中，不再扩充 vendor 改动范围。

## 补丁清单

1. `webview_create_ex`
   - 显式传入用户数据目录、应用名和剪贴板权限。
   - 默认目录为 `%LOCALAPPDATA%\<app_name>`。
   - 剪贴板读取支持 `default`、`allow`、`deny`，不再无条件允许。
   - 嵌入模式也初始化 COM STA。
   - Python 依赖：`WebView_init`。
   - 背景色不属于本补丁，由 `_module.cpp` 直接调用 WebView2 API。
2. `webview_run_with_accelerators(hwnd, haccel)`
   - 仅为 Win32 后端增加可选加速键句柄。
   - `webview_run(w)` 恢复上游公开签名，内部以空句柄转调加速键版本；不改变其他平台的公开接口。
   - 检查 `GetMessageW` 失败。
   - Python 依赖：`WebView_run`。
3. `webview_dispatch`
   - 上游 0.12.0 已公开该 API；本项目补丁是加固（投递错误上报、析构排空、异常边界和跨线程终止），不是新增 API。
   - 检查 `PostMessageW` 失败并释放投递参数。
   - 析构时排空未执行的投递，释放 Python 回调引用。
   - 阻止 C++ 异常跨 Win32 回调边界。
   - 将后台线程的 `terminate` 转发到 UI 线程。
   - Python 依赖：`WebView_dispatch`、`WebView_terminate`、`WebView_dealloc`。

## 如何同步上游

1. 查询最新 tag，不直接跟随分支：
   ```bash
   git ls-remote --tags https://github.com/webview/webview.git
   ```
2. 解析 tag 的完整 commit hash； annotated tag 要解引用到 `^{}` 的 commit。
3. 在临时目录检出该 tag，并确认 `core/include/webview*` 的文件布局是否变化。
4. 用新上游文件替换 `vendor/webview.h` 和 `vendor/webview/webview.h`，保持上述路径映射。
5. 尝试应用现有补丁：
   ```bash
   git apply --check patches/0001-pyminiwebview-engine-extensions.patch
   git apply patches/0001-pyminiwebview-engine-extensions.patch
   ```
   若上下文已变化，则手工移植，且仍只能包含上述三个 API。
6. 检查所有修改区域都有成对标记，并确认没有未标记的引擎差异：
   ```bash
   grep -R "pyminiwebview patch" vendor/
   ```
7. 按上游新 tag 的 `cmake/webview.cmake` 核对 WebView2 SDK 版本；如需更新，使用该 NuGet 包的官方头文件，不采用第三方修改版。
8. 重新构建并执行完整验证：
   ```bash
   python setup.py build_ext --inplace
   python -m pytest -q
   python test2.py
   ```
9. 重新导出 patch，并验证它能从干净上游基线重现当前文件。
10. 更新本文件的 tag、完整 commit 和同步日期，以及根 README 的基线信息。

## 补丁退役判断标准

上游只有名称相似的功能不足以退役补丁。必须同时满足：

- 上游公开 API 覆盖本补丁的完整语义，而非仅覆盖部分参数或单一线程场景。
- `_module.cpp` 能完全改用上游 API，不再调用本地扩展入口。
- 创建目录、权限默认值、加速键、后台终止、投递失败及析构清理行为均无回归。
- pytest 与真实 `test2.py` 窗口测试全部通过。

满足后删除对应补丁区和 Python 侧适配，并重新生成 patch。若三个补丁全部退役，patch 文件可以为空，但本文件仍记录所用上游基线。
