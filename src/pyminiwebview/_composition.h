/*
 * MIT License
 * Copyright (c) 2026 Ron Tang
 */

#include <dcomp.h>
#include <windowsx.h>

#include <atomic>
#include <functional>
#include <string>

class CompositionCreateHandler final
    : public ICoreWebView2CreateCoreWebView2CompositionControllerCompletedHandler {
public:
  using Callback =
      std::function<void(HRESULT, ICoreWebView2CompositionController *)>;

  explicit CompositionCreateHandler(Callback callback) : m_callback(callback) {}

  HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid,
                                           void **object) override {
    if (object == nullptr) {
      return E_POINTER;
    }
    if (IsEqualIID(riid, IID_IUnknown) ||
        IsEqualIID(
            riid,
            IID_ICoreWebView2CreateCoreWebView2CompositionControllerCompletedHandler)) {
      *object = static_cast<
          ICoreWebView2CreateCoreWebView2CompositionControllerCompletedHandler *>(
          this);
      AddRef();
      return S_OK;
    }
    *object = nullptr;
    return E_NOINTERFACE;
  }

  ULONG STDMETHODCALLTYPE AddRef() override {
    return static_cast<ULONG>(InterlockedIncrement(&m_ref_count));
  }

  ULONG STDMETHODCALLTYPE Release() override {
    ULONG count = static_cast<ULONG>(InterlockedDecrement(&m_ref_count));
    if (count == 0) {
      delete this;
    }
    return count;
  }

  HRESULT STDMETHODCALLTYPE
  Invoke(HRESULT result,
         ICoreWebView2CompositionController *controller) override {
    m_callback(result, controller);
    return S_OK;
  }

private:
  Callback m_callback;
  LONG m_ref_count = 1;
};

class CompositionEventHandler final
    : public ICoreWebView2WebMessageReceivedEventHandler,
      public ICoreWebView2PermissionRequestedEventHandler {
public:
  using MessageCallback = std::function<void(const std::string &)>;

  CompositionEventHandler(MessageCallback callback, int clipboard_permission)
      : m_callback(callback), m_clipboard_permission(
                                  static_cast<COREWEBVIEW2_PERMISSION_STATE>(
                                      clipboard_permission)) {}

  HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid,
                                           void **object) override {
    if (object == nullptr) {
      return E_POINTER;
    }
    if (IsEqualIID(riid, IID_IUnknown) ||
        IsEqualIID(riid, IID_ICoreWebView2WebMessageReceivedEventHandler)) {
      *object = static_cast<ICoreWebView2WebMessageReceivedEventHandler *>(this);
      AddRef();
      return S_OK;
    }
    if (IsEqualIID(riid, IID_ICoreWebView2PermissionRequestedEventHandler)) {
      *object = static_cast<ICoreWebView2PermissionRequestedEventHandler *>(this);
      AddRef();
      return S_OK;
    }
    *object = nullptr;
    return E_NOINTERFACE;
  }

  ULONG STDMETHODCALLTYPE AddRef() override {
    return static_cast<ULONG>(InterlockedIncrement(&m_ref_count));
  }

  ULONG STDMETHODCALLTYPE Release() override {
    ULONG count = static_cast<ULONG>(InterlockedDecrement(&m_ref_count));
    if (count == 0) {
      delete this;
    }
    return count;
  }

  HRESULT STDMETHODCALLTYPE
  Invoke(ICoreWebView2 *sender,
         ICoreWebView2WebMessageReceivedEventArgs *args) override {
    (void)sender;
    if (args == nullptr) {
      return E_POINTER;
    }
    LPWSTR message = nullptr;
    HRESULT result = args->TryGetWebMessageAsString(&message);
    if (SUCCEEDED(result) && message != nullptr) {
      m_callback(webview::detail::narrow_string(message));
    }
    CoTaskMemFree(message);
    return result;
  }

  HRESULT STDMETHODCALLTYPE
  Invoke(ICoreWebView2 *sender,
         ICoreWebView2PermissionRequestedEventArgs *args) override {
    (void)sender;
    if (args == nullptr) {
      return E_POINTER;
    }
    COREWEBVIEW2_PERMISSION_KIND kind;
    HRESULT result = args->get_PermissionKind(&kind);
    if (FAILED(result)) {
      return result;
    }
    if (kind == COREWEBVIEW2_PERMISSION_KIND_CLIPBOARD_READ) {
      return args->put_State(m_clipboard_permission);
    }
    return S_OK;
  }

private:
  MessageCallback m_callback;
  COREWEBVIEW2_PERMISSION_STATE m_clipboard_permission;
  LONG m_ref_count = 1;
};

class CompositionWebViewEngine final
    : public webview::detail::win32_edge_engine {
public:
  CompositionWebViewEngine(bool debug, void *window,
                           const char *user_data_folder, const char *app_name,
                           int clipboard_permission)
      : webview::detail::win32_edge_engine(
            debug, window, user_data_folder, app_name, clipboard_permission),
        m_host(static_cast<HWND>(window)) {
    try {
      initialize(clipboard_permission);
    } catch (...) {
      release();
      throw;
    }
  }

  ~CompositionWebViewEngine() override { release(); }

  void resize() {
    if (m_controller == nullptr || m_host == nullptr) {
      return;
    }
    RECT bounds{};
    if (GetClientRect(m_host, &bounds)) {
      m_controller->put_Bounds(bounds);
    }
  }

  void set_visible(BOOL visible) {
    if (m_controller != nullptr) {
      m_controller->put_IsVisible(visible);
    }
  }

  bool update_cursor() const {
    if (m_composition == nullptr) {
      return false;
    }
    HCURSOR cursor = nullptr;
    UINT32 system_cursor = 0;
    if (FAILED(m_composition->get_Cursor(&cursor))) {
      return false;
    }
    if (cursor == nullptr &&
        SUCCEEDED(m_composition->get_SystemCursorId(&system_cursor)) &&
        system_cursor != 0) {
      cursor = LoadCursorW(nullptr, MAKEINTRESOURCEW(system_cursor));
    }
    if (cursor == nullptr) {
      return false;
    }
    SetCursor(cursor);
    return true;
  }

  bool send_mouse_input(UINT message, WPARAM wparam, LPARAM lparam) {
    if (m_composition == nullptr) {
      return false;
    }
    UINT event_kind = message;
    UINT virtual_keys = static_cast<UINT>(LOWORD(wparam));
    bool nonclient = false;
    switch (message) {
    case WM_NCMOUSEMOVE:
      event_kind = WM_MOUSEMOVE;
      virtual_keys = 0;
      nonclient = true;
      break;
    case WM_NCLBUTTONDOWN:
      event_kind = WM_LBUTTONDOWN;
      virtual_keys = MK_LBUTTON;
      nonclient = true;
      break;
    case WM_NCLBUTTONUP:
      event_kind = WM_LBUTTONUP;
      virtual_keys = 0;
      nonclient = true;
      break;
    case WM_NCLBUTTONDBLCLK:
      event_kind = WM_LBUTTONDBLCLK;
      virtual_keys = MK_LBUTTON;
      nonclient = true;
      break;
    case WM_MOUSELEAVE:
      event_kind = COREWEBVIEW2_MOUSE_EVENT_KIND_LEAVE;
      break;
    default:
      break;
    }
    POINT point{GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam)};
    if (nonclient || message == WM_MOUSEWHEEL || message == WM_MOUSEHWHEEL) {
      if (!ScreenToClient(m_host, &point)) {
        return false;
      }
    }
    UINT32 mouse_data = 0;
    if (message == WM_MOUSEWHEEL || message == WM_MOUSEHWHEEL) {
      mouse_data = static_cast<UINT32>(static_cast<INT16>(HIWORD(wparam)));
    } else if (message == WM_XBUTTONDOWN || message == WM_XBUTTONUP ||
               message == WM_XBUTTONDBLCLK) {
      mouse_data = static_cast<UINT32>(HIWORD(wparam));
    }
    return SUCCEEDED(m_composition->SendMouseInput(
        static_cast<COREWEBVIEW2_MOUSE_EVENT_KIND>(event_kind),
        static_cast<COREWEBVIEW2_MOUSE_EVENT_VIRTUAL_KEYS>(virtual_keys),
        mouse_data, point));
  }

  bool send_pointer_input(UINT message, WPARAM wparam) {
    if (m_composition == nullptr || m_environment == nullptr) {
      return false;
    }
    COREWEBVIEW2_POINTER_EVENT_KIND kind;
    switch (message) {
    case WM_POINTERUPDATE:
      kind = COREWEBVIEW2_POINTER_EVENT_KIND_UPDATE;
      break;
    case WM_POINTERDOWN:
      kind = COREWEBVIEW2_POINTER_EVENT_KIND_DOWN;
      break;
    case WM_POINTERUP:
      kind = COREWEBVIEW2_POINTER_EVENT_KIND_UP;
      break;
    case WM_POINTERENTER:
      kind = COREWEBVIEW2_POINTER_EVENT_KIND_ENTER;
      break;
    case WM_POINTERLEAVE:
      kind = COREWEBVIEW2_POINTER_EVENT_KIND_LEAVE;
      break;
    case WM_POINTERACTIVATE:
      kind = COREWEBVIEW2_POINTER_EVENT_KIND_ACTIVATE;
      break;
    default:
      return false;
    }
    POINTER_INFO source{};
    if (!GetPointerInfo(GET_POINTERID_WPARAM(wparam), &source)) {
      return false;
    }
    ICoreWebView2PointerInfo *info = nullptr;
    if (FAILED(m_environment->CreateCoreWebView2PointerInfo(&info)) ||
        info == nullptr) {
      return false;
    }
    info->put_PointerKind(source.pointerType);
    info->put_PointerId(source.pointerId);
    info->put_FrameId(source.frameId);
    info->put_PointerFlags(source.pointerFlags);
    info->put_PixelLocation(source.ptPixelLocation);
    info->put_HimetricLocation(source.ptHimetricLocation);
    info->put_PixelLocationRaw(source.ptPixelLocationRaw);
    info->put_HimetricLocationRaw(source.ptHimetricLocationRaw);
    info->put_Time(source.dwTime);
    info->put_HistoryCount(source.historyCount);
    info->put_InputData(source.InputData);
    info->put_KeyStates(source.dwKeyStates);
    info->put_PerformanceCount(source.PerformanceCount);
    info->put_ButtonChangeKind(source.ButtonChangeType);
    MONITORINFO monitor{};
    monitor.cbSize = sizeof(monitor);
    HMONITOR display = MonitorFromPoint(
        source.ptPixelLocation, MONITOR_DEFAULTTONEAREST);
    if (GetMonitorInfoW(display, &monitor)) {
      info->put_PointerDeviceRect(monitor.rcMonitor);
      info->put_DisplayRect(monitor.rcMonitor);
    }
    if (source.pointerType == PT_PEN) {
      POINTER_PEN_INFO pen{};
      if (GetPointerPenInfo(source.pointerId, &pen)) {
        info->put_PenFlags(pen.penFlags);
        info->put_PenMask(pen.penMask);
        info->put_PenPressure(pen.pressure);
        info->put_PenRotation(pen.rotation);
        info->put_PenTiltX(pen.tiltX);
        info->put_PenTiltY(pen.tiltY);
      }
    } else if (source.pointerType == PT_TOUCH) {
      POINTER_TOUCH_INFO touch{};
      if (GetPointerTouchInfo(source.pointerId, &touch)) {
        info->put_TouchFlags(touch.touchFlags);
        info->put_TouchMask(touch.touchMask);
        info->put_TouchContact(touch.rcContact);
        info->put_TouchContactRaw(touch.rcContactRaw);
        info->put_TouchOrientation(touch.orientation);
        info->put_TouchPressure(touch.pressure);
      }
    }
    HRESULT result = m_composition->SendPointerInput(kind, info);
    info->Release();
    return SUCCEEDED(result);
  }

protected:
  webview::result<void *> browser_controller_impl() override {
    if (m_controller != nullptr) {
      return m_controller;
    }
    return webview::error_info{WEBVIEW_ERROR_INVALID_STATE};
  }

  webview::noresult navigate_impl(const std::string &url) override {
    m_webview->Navigate(webview::detail::widen_string(url).c_str());
    return {};
  }

  webview::noresult eval_impl(const std::string &js) override {
    m_webview->ExecuteScript(webview::detail::widen_string(js).c_str(), nullptr);
    return {};
  }

  webview::noresult set_html_impl(const std::string &html) override {
    m_webview->NavigateToString(webview::detail::widen_string(html).c_str());
    return {};
  }

  webview::detail::user_script
  add_user_script_impl(const std::string &js) override {
    auto wide_js = webview::detail::widen_string(js);
    std::wstring script_id;
    bool done = false;
    webview::detail::webview2_user_script_added_handler handler{
        [&](HRESULT result, LPCWSTR id) {
          if (SUCCEEDED(result)) {
            script_id = id;
          }
          done = true;
        }};
    HRESULT result = m_webview->AddScriptToExecuteOnDocumentCreated(
        wide_js.c_str(), &handler);
    if (SUCCEEDED(result)) {
      pump_until(done);
    }
    return webview::detail::user_script{
        js, std::unique_ptr<webview::detail::user_script::impl>(
                new webview::detail::user_script::impl{script_id, wide_js})};
  }

  void remove_all_user_scripts_impl(
      const std::list<webview::detail::user_script> &scripts) override {
    for (const auto &script : scripts) {
      m_webview->RemoveScriptToExecuteOnDocumentCreated(
          script.get_impl().get_id().c_str());
    }
  }

  bool are_user_scripts_equal_impl(
      const webview::detail::user_script &first,
      const webview::detail::user_script &second) override {
    return first.get_impl().get_id() == second.get_impl().get_id();
  }

private:
  static void require(HRESULT result) {
    if (FAILED(result)) {
      throw webview::exception{WEBVIEW_ERROR_UNSPECIFIED,
                               "Composition WebView2 initialization failed"};
    }
  }

  static void pump_until(bool &done) {
    while (!done) {
      MSG message;
      BOOL result = GetMessageW(&message, nullptr, 0, 0);
      if (result <= 0) {
        if (result == 0) {
          PostQuitMessage(static_cast<int>(message.wParam));
        }
        throw webview::exception{WEBVIEW_ERROR_CANCELED,
                                 "Composition WebView2 initialization canceled"};
      }
      TranslateMessage(&message);
      DispatchMessageW(&message);
    }
  }

  void initialize(int clipboard_permission) {
    auto regular_result =
        webview::detail::win32_edge_engine::browser_controller_impl();
    regular_result.ensure_ok();
    auto *regular_controller =
        static_cast<ICoreWebView2Controller *>(regular_result.value());
    regular_controller->AddRef();
    m_regular_controller = regular_controller;
    ICoreWebView2 *regular_core = nullptr;
    require(regular_controller->get_CoreWebView2(&regular_core));
    ICoreWebView2_2 *core2 = nullptr;
    require(regular_core->QueryInterface(IID_PPV_ARGS(&core2)));
    regular_core->Release();
    ICoreWebView2Environment *environment = nullptr;
    require(core2->get_Environment(&environment));
    core2->Release();
    require(environment->QueryInterface(IID_PPV_ARGS(&m_environment)));
    environment->Release();

    bool done = false;
    HRESULT completion = E_FAIL;
    auto *handler = new CompositionCreateHandler{
        [&](HRESULT result, ICoreWebView2CompositionController *controller) {
          completion = result;
          if (SUCCEEDED(result) && controller != nullptr) {
            controller->AddRef();
            m_composition = controller;
          }
          done = true;
        }};
    HRESULT create_result = m_environment->CreateCoreWebView2CompositionController(
        m_host, handler);
    handler->Release();
    require(create_result);
    pump_until(done);
    require(completion);
    if (m_composition == nullptr) {
      require(E_FAIL);
    }
    require(m_composition->QueryInterface(IID_PPV_ARGS(&m_controller)));

    require(DCompositionCreateDevice(nullptr, IID_PPV_ARGS(&m_device)));
    require(m_device->CreateTargetForHwnd(m_host, TRUE, &m_target));
    require(m_device->CreateVisual(&m_visual));
    require(m_composition->put_RootVisualTarget(m_visual));
    require(m_target->SetRoot(m_visual));
    require(m_device->Commit());
    require(m_controller->get_CoreWebView2(&m_webview));

    m_events = new CompositionEventHandler{
        [this](const std::string &message) { on_message(message); },
        clipboard_permission};
    require(m_webview->add_WebMessageReceived(m_events, &m_message_token));
    require(m_webview->add_PermissionRequested(m_events, &m_permission_token));
    add_init_script("function(message) {\n\
  return window.chrome.webview.postMessage(message);\n\
}");
    resize();
    require(m_controller->put_IsVisible(TRUE));
    regular_controller->put_IsVisible(FALSE);
    auto widget_result =
        webview::detail::win32_edge_engine::widget_impl();
    widget_result.ensure_ok();
    ShowWindow(static_cast<HWND>(widget_result.value()), SW_HIDE);
  }

  void release() {
    if (m_webview != nullptr && m_events != nullptr) {
      m_webview->remove_WebMessageReceived(m_message_token);
      m_webview->remove_PermissionRequested(m_permission_token);
    }
    if (m_events != nullptr) {
      m_events->Release();
      m_events = nullptr;
    }
    if (m_composition != nullptr) {
      m_composition->put_RootVisualTarget(nullptr);
    }
    if (m_controller != nullptr) {
      m_controller->Close();
      m_controller->Release();
      m_controller = nullptr;
    }
    if (m_webview != nullptr) {
      m_webview->Release();
      m_webview = nullptr;
    }
    if (m_composition != nullptr) {
      m_composition->Release();
      m_composition = nullptr;
    }
    if (m_environment != nullptr) {
      m_environment->Release();
      m_environment = nullptr;
    }
    if (m_regular_controller != nullptr) {
      m_regular_controller->Close();
      m_regular_controller->Release();
      m_regular_controller = nullptr;
    }
    if (m_visual != nullptr) {
      m_visual->Release();
      m_visual = nullptr;
    }
    if (m_target != nullptr) {
      m_target->Release();
      m_target = nullptr;
    }
    if (m_device != nullptr) {
      m_device->Release();
      m_device = nullptr;
    }
  }

  HWND m_host = nullptr;
  ICoreWebView2Environment3 *m_environment = nullptr;
  ICoreWebView2CompositionController *m_composition = nullptr;
  ICoreWebView2Controller *m_controller = nullptr;
  ICoreWebView2Controller *m_regular_controller = nullptr;
  ICoreWebView2 *m_webview = nullptr;
  CompositionEventHandler *m_events = nullptr;
  EventRegistrationToken m_message_token{};
  EventRegistrationToken m_permission_token{};
  IDCompositionDevice *m_device = nullptr;
  IDCompositionTarget *m_target = nullptr;
  IDCompositionVisual *m_visual = nullptr;
};
