/*
 * MIT License
 * Copyright (c) 2026 Ron Tang
 */

#define Py_LIMITED_API 0x03090000
#include <Python.h>

#define WEBVIEW_IMPLEMENTATION
#include <webview/webview.h>

#include <windows.h>
#include <commctrl.h>
#include <shellapi.h>

#include <climits>
#include <cwchar>
#include <memory>
#include <mutex>
#include <new>
#include <string>

#include "_composition.h"

constexpr UINT_PTR STARTUP_REVEAL_TIMER_ID = 0x504D5677;
constexpr UINT SIGNAL_CHECK_INTERVAL_MS = 100;
static thread_local bool initialization_signal_check_active = false;

static PyObject *new_none_reference() {
  Py_IncRef(Py_None);
  return Py_None;
}

static void clear_reference(PyObject **object) {
  PyObject *value = *object;
  *object = nullptr;
  Py_DecRef(value);
}

static void handle_ui_callback_exception() {
  if (PyErr_ExceptionMatches(PyExc_KeyboardInterrupt)) {
    PostQuitMessage(0);
  }
  PyErr_PrintEx(0);
}

static void CALLBACK signal_check_timeout(HWND window, UINT message,
                                          UINT_PTR timer_id, DWORD elapsed_ms) {
  (void)window;
  (void)message;
  (void)timer_id;
  (void)elapsed_ms;
  PyGILState_STATE gil_state = PyGILState_Ensure();
  if (PyErr_CheckSignals() < 0) {
    if (initialization_signal_check_active) {
      PostQuitMessage(0);
    } else {
      handle_ui_callback_exception();
    }
  }
  PyGILState_Release(gil_state);
}

static void reveal_native_window(HWND window) {
  if (window == nullptr || !IsWindow(window)) {
    return;
  }
  KillTimer(window, STARTUP_REVEAL_TIMER_ID);
  if (!IsWindowVisible(window)) {
    ShowWindow(window, SW_SHOW);
    UpdateWindow(window);
  }
}

static void CALLBACK startup_reveal_timeout(HWND window, UINT message,
                                            UINT_PTR timer_id,
                                            DWORD elapsed_ms) {
  (void)message;
  (void)timer_id;
  (void)elapsed_ms;
  reveal_native_window(window);
}

class FirstPaintHandler final : public ICoreWebView2ExecuteScriptCompletedHandler {
public:
  explicit FirstPaintHandler(HWND window) : m_window(window) {}

  HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid,
                                           void **object) override {
    if (object == nullptr) {
      return E_POINTER;
    }
    if (IsEqualIID(riid, IID_IUnknown) ||
        IsEqualIID(riid, IID_ICoreWebView2ExecuteScriptCompletedHandler)) {
      *object = static_cast<ICoreWebView2ExecuteScriptCompletedHandler *>(this);
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

  HRESULT STDMETHODCALLTYPE Invoke(HRESULT error_code,
                                   LPCWSTR result_object_as_json) override {
    (void)error_code;
    (void)result_object_as_json;
    reveal_native_window(m_window);
    return S_OK;
  }

private:
  HWND m_window;
  LONG m_ref_count = 1;
};

class DOMContentLoadedHandler final
    : public ICoreWebView2DOMContentLoadedEventHandler {
public:
  explicit DOMContentLoadedHandler(HWND window) : m_window(window) {}

  HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid,
                                           void **object) override {
    if (object == nullptr) {
      return E_POINTER;
    }
    if (IsEqualIID(riid, IID_IUnknown) ||
        IsEqualIID(riid, IID_ICoreWebView2DOMContentLoadedEventHandler)) {
      *object = static_cast<ICoreWebView2DOMContentLoadedEventHandler *>(this);
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
         ICoreWebView2DOMContentLoadedEventArgs *args) override {
    (void)args;
    if (sender == nullptr) {
      reveal_native_window(m_window);
      return E_POINTER;
    }
    if (InterlockedCompareExchange(&m_invoked, 1, 0) != 0) {
      return S_OK;
    }
    FirstPaintHandler *handler = new (std::nothrow) FirstPaintHandler(m_window);
    if (handler == nullptr) {
      reveal_native_window(m_window);
      return E_OUTOFMEMORY;
    }
    HRESULT result = sender->ExecuteScript(
        L"requestAnimationFrame(() => requestAnimationFrame(() => {}));",
        handler);
    handler->Release();
    if (FAILED(result)) {
      reveal_native_window(m_window);
    }
    return result;
  }

private:
  HWND m_window;
  LONG m_ref_count = 1;
  LONG m_invoked = 0;
};

class StandaloneShowSuppressor {
public:
  explicit StandaloneShowSuppressor(bool enabled) {
    if (enabled) {
      m_hook = SetWinEventHook(EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW, nullptr,
                               callback, GetCurrentProcessId(),
                               GetCurrentThreadId(), WINEVENT_INCONTEXT);
    }
  }

  ~StandaloneShowSuppressor() {
    if (m_hook != nullptr) {
      UnhookWinEvent(m_hook);
    }
  }

private:
  static void CALLBACK callback(HWINEVENTHOOK hook, DWORD event, HWND window,
                                LONG object_id, LONG child_id,
                                DWORD event_thread, DWORD event_time) {
    (void)hook;
    (void)event;
    (void)event_thread;
    (void)event_time;
    if (window == nullptr || object_id != OBJID_WINDOW || child_id != 0 ||
        GetParent(window) != nullptr) {
      return;
    }
    wchar_t class_name[16]{};
    if (GetClassNameW(window, class_name, 16) > 0 &&
        wcscmp(class_name, L"webview") == 0) {
      ShowWindow(window, SW_HIDE);
    }
  }

  HWINEVENTHOOK m_hook = nullptr;
};

class NewWindowRequestedHandler final
    : public ICoreWebView2NewWindowRequestedEventHandler {
public:
  HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid,
                                           void **object) override {
    if (object == nullptr) {
      return E_POINTER;
    }
    if (IsEqualIID(riid, IID_IUnknown) ||
        IsEqualIID(riid, IID_ICoreWebView2NewWindowRequestedEventHandler)) {
      *object = static_cast<ICoreWebView2NewWindowRequestedEventHandler *>(this);
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
         ICoreWebView2NewWindowRequestedEventArgs *args) override {
    (void)sender;
    if (args == nullptr) {
      return E_POINTER;
    }
    LPWSTR uri = nullptr;
    HRESULT result = args->get_Uri(&uri);
    if (FAILED(result)) {
      return result;
    }
    if (uri == nullptr) {
      return E_UNEXPECTED;
    }
    bool allowed = _wcsnicmp(uri, L"http://", 7) == 0 ||
                   _wcsnicmp(uri, L"https://", 8) == 0;
    // Wails-style policy, restricted to web URLs instead of arbitrary protocols.
    HINSTANCE shell_result = nullptr;
    if (allowed) {
      shell_result =
          ShellExecuteW(nullptr, L"open", uri, nullptr, nullptr, SW_SHOWNORMAL);
    }
    CoTaskMemFree(uri);
    HRESULT handled = args->put_Handled(TRUE);
    if (FAILED(handled)) {
      return handled;
    }
    if (allowed && reinterpret_cast<INT_PTR>(shell_result) <= 32) {
      return E_FAIL;
    }
    return S_OK;
  }

private:
  LONG m_ref_count = 1;
};

struct AutoSizeState {
  HWND parent;
  HWND widget;
  CompositionWebViewEngine *composition;
};

struct DispatchCall;

typedef struct {
  PyObject_HEAD
  webview_t webview;
  CompositionWebViewEngine *composition;
  PyObject *bindings;
  HWND parent;
  HWND widget;
  HICON icon;
  NewWindowRequestedHandler *new_window_handler;
  EventRegistrationToken new_window_token;
  int new_window_registered;
  DOMContentLoadedHandler *startup_handler;
  EventRegistrationToken startup_token;
  int startup_registered;
  int content_requested;
  int embedded;
  int autosize;
  AutoSizeState *auto_size_state;
  DispatchCall *pending_dispatch;
  std::mutex *lifecycle_mutex;
  DWORD ui_thread;
  int closed;
  int running;
  int initializing;
} WebViewObject;

struct DispatchCall {
  PyObject *callable;
  WebViewObject *owner;
  DispatchCall *next;
};

struct BindingCall {
  PyObject *callable;
  int release_queued;
};

struct NativeFinalizer {
  webview_t webview;
  PyObject *bindings;
  HICON icon;
  NewWindowRequestedHandler *new_window_handler;
  EventRegistrationToken new_window_token;
  int new_window_registered;
  DOMContentLoadedHandler *startup_handler;
  EventRegistrationToken startup_token;
  int startup_registered;
  AutoSizeState *auto_size_state;
  UINT_PTR subclass_id;
};

static int set_webview_error(const char *operation, webview_error_t error) {
  PyObject *exception = PyExc_RuntimeError;
  if (error == WEBVIEW_ERROR_INVALID_ARGUMENT) {
    exception = PyExc_ValueError;
  } else if (error == WEBVIEW_ERROR_DUPLICATE ||
             error == WEBVIEW_ERROR_NOT_FOUND) {
    exception = PyExc_KeyError;
  }
  PyErr_Format(exception, "%s failed (webview error %d)", operation,
               static_cast<int>(error));
  return -1;
}

static int set_webview2_error(const char *operation, HRESULT result) {
  PyErr_Format(PyExc_RuntimeError,
               "%s failed (HRESULT 0x%08lX); WebView2 Runtime may be too old",
               operation, static_cast<unsigned long>(result));
  return -1;
}

static void restore_initialization_quit() {
  const int exit_code = webview::detail::take_initialization_quit_code();
  if (exit_code >= 0 &&
      !PostThreadMessageW(GetCurrentThreadId(), WM_QUIT,
                          static_cast<WPARAM>(exit_code), 0)) {
    PostQuitMessage(exit_code);
  }
}

static int require_webview(WebViewObject *self) {
  if (self->closed || self->webview == nullptr) {
    PyErr_SetString(PyExc_RuntimeError, "WebView is not initialized or is closed");
    return -1;
  }
  return 0;
}

static int check_webview_error(webview_error_t error, const char *operation) {
  if (error != WEBVIEW_ERROR_OK) {
    return set_webview_error(operation, error);
  }
  return 0;
}

static int resize_embedded(WebViewObject *self, int width, int height) {
  if (!SetWindowPos(self->widget, nullptr, 0, 0, width, height,
                    SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOZORDER)) {
    PyErr_SetFromWindowsErr(0);
    return -1;
  }
  if (self->composition != nullptr) {
    self->composition->resize();
  }
  return 0;
}

static int resize_to_parent(WebViewObject *self) {
  RECT rect{};
  if (!GetClientRect(self->parent, &rect)) {
    PyErr_SetFromWindowsErr(0);
    return -1;
  }
  return resize_embedded(self, rect.right - rect.left, rect.bottom - rect.top);
}

static LRESULT CALLBACK auto_size_proc(HWND hwnd, UINT message, WPARAM wparam,
                                       LPARAM lparam, UINT_PTR subclass_id,
                                       DWORD_PTR ref_data) {
  AutoSizeState *state = reinterpret_cast<AutoSizeState *>(ref_data);
  if (message == WM_SIZE && wparam != SIZE_MINIMIZED && state->widget != nullptr) {
    SetWindowPos(state->widget, nullptr, 0, 0, LOWORD(lparam), HIWORD(lparam),
                 SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOZORDER);
    if (state->composition != nullptr) {
      state->composition->resize();
    }
  } else if (message == WM_NCDESTROY) {
    state->widget = nullptr;
    state->parent = nullptr;
    RemoveWindowSubclass(hwnd, auto_size_proc, subclass_id);
  }
  return DefSubclassProc(hwnd, message, wparam, lparam);
}

static int WebView_clear(WebViewObject *self) {
  if (self->bindings != nullptr) {
    Py_ssize_t position = 0;
    PyObject *name;
    PyObject *capsule;
    while (PyDict_Next(self->bindings, &position, &name, &capsule)) {
      void *pointer = PyCapsule_GetPointer(capsule, nullptr);
      if (pointer == nullptr) {
        PyErr_Clear();
        continue;
      }
      BindingCall *call = static_cast<BindingCall *>(pointer);
      clear_reference(&call->callable);
    }
  }
  DispatchCall *call = self->pending_dispatch;
  while (call != nullptr) {
    clear_reference(&call->callable);
    call = call->next;
  }
  return 0;
}

static void clear_pending_dispatch(WebViewObject *self) {
  DispatchCall *call;
  {
    std::lock_guard<std::mutex> lock(*self->lifecycle_mutex);
    call = self->pending_dispatch;
    self->pending_dispatch = nullptr;
  }
  while (call != nullptr) {
    DispatchCall *next = call->next;
    call->owner = nullptr;
    clear_reference(&call->callable);
    delete call;
    call = next;
  }
}

static int WebView_traverse(WebViewObject *self, visitproc visit, void *arg) {
  Py_VISIT(self->bindings);
  if (self->bindings != nullptr) {
    Py_ssize_t position = 0;
    PyObject *name;
    PyObject *capsule;
    while (PyDict_Next(self->bindings, &position, &name, &capsule)) {
      void *pointer = PyCapsule_GetPointer(capsule, nullptr);
      if (pointer == nullptr) {
        PyErr_Clear();
        continue;
      }
      BindingCall *call = static_cast<BindingCall *>(pointer);
      Py_VISIT(call->callable);
    }
  }
  DispatchCall *call = self->pending_dispatch;
  while (call != nullptr) {
    Py_VISIT(call->callable);
    call = call->next;
  }
  return 0;
}

static void detach_native(WebViewObject *self, NativeFinalizer *finalizer) {
  std::lock_guard<std::mutex> lock(*self->lifecycle_mutex);
  finalizer->webview = self->webview;
  finalizer->bindings = self->bindings;
  finalizer->icon = self->icon;
  finalizer->new_window_handler = self->new_window_handler;
  finalizer->new_window_token = self->new_window_token;
  finalizer->new_window_registered = self->new_window_registered;
  finalizer->startup_handler = self->startup_handler;
  finalizer->startup_token = self->startup_token;
  finalizer->startup_registered = self->startup_registered;
  finalizer->auto_size_state = self->auto_size_state;
  finalizer->subclass_id = reinterpret_cast<UINT_PTR>(self);
  self->webview = nullptr;
  self->composition = nullptr;
  self->bindings = nullptr;
  self->parent = nullptr;
  self->widget = nullptr;
  self->icon = nullptr;
  self->new_window_handler = nullptr;
  self->new_window_registered = 0;
  self->startup_handler = nullptr;
  self->startup_registered = 0;
  self->auto_size_state = nullptr;
  self->autosize = 0;
}

static webview_error_t
destroy_native_resources(NativeFinalizer *finalizer) {
  if (finalizer->auto_size_state != nullptr) {
    AutoSizeState *state = finalizer->auto_size_state;
    if (state->parent != nullptr) {
      RemoveWindowSubclass(state->parent, auto_size_proc,
                           finalizer->subclass_id);
      state->parent = nullptr;
      state->widget = nullptr;
    }
    delete state;
    finalizer->auto_size_state = nullptr;
  }
  if ((finalizer->new_window_registered || finalizer->startup_registered) &&
      finalizer->webview != nullptr) {
    void *handle = webview_get_native_handle(
        finalizer->webview, WEBVIEW_NATIVE_HANDLE_KIND_BROWSER_CONTROLLER);
    if (handle != nullptr) {
      auto *controller = static_cast<ICoreWebView2Controller *>(handle);
      ICoreWebView2 *core = nullptr;
      if (SUCCEEDED(controller->get_CoreWebView2(&core)) && core != nullptr) {
        if (finalizer->new_window_registered) {
          core->remove_NewWindowRequested(finalizer->new_window_token);
        }
        if (finalizer->startup_registered) {
          ICoreWebView2_2 *core2 = nullptr;
          if (SUCCEEDED(core->QueryInterface(IID_PPV_ARGS(&core2))) &&
              core2 != nullptr) {
            core2->remove_DOMContentLoaded(finalizer->startup_token);
            core2->Release();
          }
        }
        core->Release();
      }
    }
  }
  if (finalizer->new_window_handler != nullptr) {
    finalizer->new_window_handler->Release();
    finalizer->new_window_handler = nullptr;
  }
  if (finalizer->startup_handler != nullptr) {
    finalizer->startup_handler->Release();
    finalizer->startup_handler = nullptr;
  }
  webview_error_t error = WEBVIEW_ERROR_OK;
  if (finalizer->webview != nullptr) {
    error = webview_destroy(finalizer->webview);
    finalizer->webview = nullptr;
  }
  if (finalizer->icon != nullptr) {
    DestroyIcon(finalizer->icon);
    finalizer->icon = nullptr;
  }
  return error;
}

static int close_on_ui(WebViewObject *self) {
  {
    std::lock_guard<std::mutex> lock(*self->lifecycle_mutex);
    if (self->closed) {
      return 0;
    }
    self->closed = 1;
  }
  WebView_clear(self);
  NativeFinalizer finalizer{};
  detach_native(self, &finalizer);
  webview_error_t error = destroy_native_resources(&finalizer);
  clear_pending_dispatch(self);
  Py_DecRef(finalizer.bindings);
  if (self->running) {
    PostQuitMessage(0);
  }
  if (error != WEBVIEW_ERROR_OK) {
    return set_webview_error("webview_destroy", error);
  }
  return 0;
}

static void finalize_native_callback(webview_t webview, void *arg) noexcept {
  (void)webview;
  std::unique_ptr<NativeFinalizer> finalizer(
      static_cast<NativeFinalizer *>(arg));
  PyGILState_STATE gil_state = PyGILState_Ensure();
  destroy_native_resources(finalizer.get());
  Py_DecRef(finalizer->bindings);
  PyGILState_Release(gil_state);
}

static int set_icon(WebViewObject *self, const char *path) {
  int length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1,
                                   nullptr, 0);
  if (length <= 0) {
    PyErr_SetString(PyExc_ValueError, "icon must be a valid UTF-8 path");
    return -1;
  }
  std::wstring wide_path;
  try {
    wide_path.assign(static_cast<size_t>(length), L'\0');
  } catch (const std::bad_alloc &) {
    PyErr_NoMemory();
    return -1;
  } catch (...) {
    PyErr_SetString(PyExc_RuntimeError, "failed to allocate the icon path");
    return -1;
  }
  if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1,
                          &wide_path[0], length) <= 0) {
    PyErr_SetFromWindowsErr(0);
    return -1;
  }
  self->icon = static_cast<HICON>(
      LoadImageW(nullptr, wide_path.c_str(), IMAGE_ICON, 0, 0, LR_LOADFROMFILE));
  if (self->icon == nullptr) {
    PyErr_SetFromWindowsErr(0);
    return -1;
  }
  SetLastError(ERROR_SUCCESS);
  if (SetClassLongPtrW(self->parent, GCLP_HICON,
                       reinterpret_cast<LONG_PTR>(self->icon)) == 0 &&
      GetLastError() != ERROR_SUCCESS) {
    PyErr_SetFromWindowsErr(0);
    return -1;
  }
  return 0;
}

static int focus_webview(WebViewObject *self) {
  void *handle = webview_get_native_handle(
      self->webview, WEBVIEW_NATIVE_HANDLE_KIND_BROWSER_CONTROLLER);
  if (handle == nullptr) {
    PyErr_SetString(PyExc_RuntimeError, "WebView2 controller is unavailable");
    return -1;
  }
  auto *controller = static_cast<ICoreWebView2Controller *>(handle);
  HRESULT result = controller->MoveFocus(COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC);
  if (FAILED(result)) {
    PyErr_Format(PyExc_RuntimeError, "MoveFocus failed (HRESULT 0x%08lX)",
                 static_cast<unsigned long>(result));
    return -1;
  }
  return 0;
}

static int set_background_color(WebViewObject *self, COLORREF color, BYTE alpha) {
  void *handle = webview_get_native_handle(
      self->webview, WEBVIEW_NATIVE_HANDLE_KIND_BROWSER_CONTROLLER);
  if (handle == nullptr) {
    PyErr_SetString(PyExc_RuntimeError, "WebView2 controller is unavailable");
    return -1;
  }
  auto *controller = static_cast<ICoreWebView2Controller *>(handle);
  ICoreWebView2Controller2 *controller2 = nullptr;
  HRESULT result = controller->QueryInterface(IID_PPV_ARGS(&controller2));
  if (FAILED(result)) {
    PyErr_Format(PyExc_RuntimeError,
                 "ICoreWebView2Controller2 query failed (HRESULT 0x%08lX)",
                 static_cast<unsigned long>(result));
    return -1;
  }
  COREWEBVIEW2_COLOR background{};
  background.A = alpha;
  background.R = GetRValue(color);
  background.G = GetGValue(color);
  background.B = GetBValue(color);
  result = controller2->put_DefaultBackgroundColor(background);
  controller2->Release();
  if (FAILED(result)) {
    PyErr_Format(PyExc_RuntimeError,
                 "put_DefaultBackgroundColor failed (HRESULT 0x%08lX)",
                 static_cast<unsigned long>(result));
    return -1;
  }
  return 0;
}

static int configure_startup_reveal(WebViewObject *self) {
  void *handle = webview_get_native_handle(
      self->webview, WEBVIEW_NATIVE_HANDLE_KIND_BROWSER_CONTROLLER);
  if (handle == nullptr) {
    PyErr_SetString(PyExc_RuntimeError, "WebView2 controller is unavailable");
    return -1;
  }
  auto *controller = static_cast<ICoreWebView2Controller *>(handle);
  ICoreWebView2 *core = nullptr;
  HRESULT result = controller->get_CoreWebView2(&core);
  if (FAILED(result) || core == nullptr) {
    return set_webview2_error("get_CoreWebView2 for startup reveal", result);
  }
  ICoreWebView2_2 *core2 = nullptr;
  result = core->QueryInterface(IID_PPV_ARGS(&core2));
  core->Release();
  if (FAILED(result) || core2 == nullptr) {
    return set_webview2_error("ICoreWebView2_2 query for startup reveal", result);
  }
  DOMContentLoadedHandler *handler =
      new (std::nothrow) DOMContentLoadedHandler(self->parent);
  if (handler == nullptr) {
    core2->Release();
    PyErr_NoMemory();
    return -1;
  }
  EventRegistrationToken token{};
  result = core2->add_DOMContentLoaded(handler, &token);
  core2->Release();
  if (FAILED(result)) {
    handler->Release();
    return set_webview2_error("add_DOMContentLoaded for startup reveal", result);
  }
  self->startup_handler = handler;
  self->startup_token = token;
  self->startup_registered = 1;
  return 0;
}

static int configure_app_mode(WebViewObject *self,
                              int disable_browser_accelerators,
                              int disable_default_context_menus,
                              int disable_nc_region_support,
                              int redirect_new_window_to_system_browser) {
  void *handle = webview_get_native_handle(
      self->webview, WEBVIEW_NATIVE_HANDLE_KIND_BROWSER_CONTROLLER);
  if (handle == nullptr) {
    PyErr_SetString(PyExc_RuntimeError, "WebView2 controller is unavailable");
    return -1;
  }
  auto *controller = static_cast<ICoreWebView2Controller *>(handle);
  ICoreWebView2 *core = nullptr;
  HRESULT result = controller->get_CoreWebView2(&core);
  if (FAILED(result)) {
    return set_webview2_error("get_CoreWebView2 for configure_app_mode", result);
  }
  ICoreWebView2Settings *settings = nullptr;
  result = core->get_Settings(&settings);
  if (FAILED(result)) {
    core->Release();
    return set_webview2_error("get_Settings for configure_app_mode", result);
  }

  if (disable_browser_accelerators) {
    ICoreWebView2Settings3 *settings3 = nullptr;
    result = settings->QueryInterface(IID_PPV_ARGS(&settings3));
    if (FAILED(result)) {
      settings->Release();
      core->Release();
      return set_webview2_error(
          "ICoreWebView2Settings3 query for disable_browser_accelerators",
          result);
    }
    // Wails practice: keep F5/Ctrl+R/Ctrl+F from turning app UI into a browser.
    result = settings3->put_AreBrowserAcceleratorKeysEnabled(VARIANT_FALSE);
    settings3->Release();
    if (FAILED(result)) {
      settings->Release();
      core->Release();
      return set_webview2_error(
          "put_AreBrowserAcceleratorKeysEnabled for "
          "disable_browser_accelerators",
          result);
    }
  }

  if (disable_default_context_menus) {
    result = settings->put_AreDefaultContextMenusEnabled(VARIANT_FALSE);
    if (FAILED(result)) {
      settings->Release();
      core->Release();
      return set_webview2_error(
          "put_AreDefaultContextMenusEnabled for disable_default_context_menus",
          result);
    }
  }

  if (disable_nc_region_support) {
    ICoreWebView2Settings9 *settings9 = nullptr;
    result = settings->QueryInterface(IID_PPV_ARGS(&settings9));
    if (result == E_NOINTERFACE) {
      // Runtime <102 already lacks non-client region child windows entirely.
    } else if (FAILED(result)) {
      settings->Release();
      core->Release();
      return set_webview2_error(
          "ICoreWebView2Settings9 query for disable_nc_region_support", result);
    } else {
      // Prevent CSS app-region children from swallowing host WM_NCHITTEST.
      result = settings9->put_IsNonClientRegionSupportEnabled(VARIANT_FALSE);
      settings9->Release();
      if (FAILED(result)) {
        settings->Release();
        core->Release();
        return set_webview2_error(
            "put_IsNonClientRegionSupportEnabled for "
            "disable_nc_region_support",
            result);
      }
    }
  }

  if (redirect_new_window_to_system_browser && !self->new_window_registered) {
    auto *handler = new (std::nothrow) NewWindowRequestedHandler();
    if (handler == nullptr) {
      settings->Release();
      core->Release();
      PyErr_NoMemory();
      return -1;
    }
    EventRegistrationToken token{};
    result = core->add_NewWindowRequested(handler, &token);
    if (FAILED(result)) {
      handler->Release();
      settings->Release();
      core->Release();
      return set_webview2_error(
          "add_NewWindowRequested for redirect_new_window_to_system_browser",
          result);
    }
    self->new_window_handler = handler;
    self->new_window_token = token;
    self->new_window_registered = 1;
  }

  settings->Release();
  core->Release();
  return 0;
}

static PyObject *WebView_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
  (void)args;
  (void)kwds;
  WebViewObject *self =
      reinterpret_cast<WebViewObject *>(PyType_GenericAlloc(type, 0));
  if (self != nullptr) {
    self->ui_thread = GetCurrentThreadId();
    self->lifecycle_mutex = new (std::nothrow) std::mutex();
    self->bindings = PyDict_New();
    if (self->lifecycle_mutex == nullptr || self->bindings == nullptr) {
      if (!PyErr_Occurred()) {
        PyErr_NoMemory();
      }
      Py_DecRef(reinterpret_cast<PyObject *>(self));
      return nullptr;
    }
  }
  return reinterpret_cast<PyObject *>(self);
}

static void WebView_dealloc(WebViewObject *self) {
  PyObject_GC_UnTrack(self);
  PyObject *error_type, *error_value, *error_traceback;
  PyErr_Fetch(&error_type, &error_value, &error_traceback);

  if (self->lifecycle_mutex != nullptr) {
    if (GetCurrentThreadId() == self->ui_thread || self->webview == nullptr) {
      if (close_on_ui(self) < 0) {
        PyErr_PrintEx(0);
      }
    } else {
      {
        std::lock_guard<std::mutex> lock(*self->lifecycle_mutex);
        self->closed = 1;
      }
      WebView_clear(self);
      NativeFinalizer abandoned{};
      NativeFinalizer *finalizer = new (std::nothrow) NativeFinalizer{};
      bool can_queue = finalizer != nullptr;
      if (finalizer == nullptr) {
        finalizer = &abandoned;
      }
      detach_native(self, finalizer);
      {
        std::lock_guard<std::mutex> lock(*self->lifecycle_mutex);
        DispatchCall *call = self->pending_dispatch;
        while (call != nullptr) {
          call->owner = nullptr;
          call = call->next;
        }
        self->pending_dispatch = nullptr;
      }
      if (!can_queue) {
        // Detach without releasing on OOM so no native callback can dangle.
        PyErr_NoMemory();
        PyErr_PrintEx(0);
      } else {
        webview_error_t error = webview_dispatch(
            finalizer->webview, finalize_native_callback, finalizer);
        if (error != WEBVIEW_ERROR_OK) {
          // Native resources and their records intentionally outlive the object
          // if the UI queue is gone; destroying them here would be unsafe.
          set_webview_error("webview_dispatch finalizer", error);
          PyErr_PrintEx(0);
        }
      }
    }
  }
  clear_reference(&self->bindings);
  delete self->auto_size_state;
  delete self->lifecycle_mutex;
  PyTypeObject *type = Py_TYPE(self);
  freefunc free = reinterpret_cast<freefunc>(PyType_GetSlot(type, Py_tp_free));
  if (free != nullptr) {
    free(reinterpret_cast<PyObject *>(self));
  }
  Py_DecRef(reinterpret_cast<PyObject *>(type));
  PyErr_Restore(error_type, error_value, error_traceback);
}

static int WebView_init(WebViewObject *self, PyObject *args, PyObject *kwds) {
  int debug = 0;
  unsigned long long window = 0;
  int autosize = 0;
  int width = 320;
  int height = 240;
  const char *url = nullptr;
  const char *title = nullptr;
  const char *icon = nullptr;
  unsigned int bgcolor = 0xFFFFFF;
  const char *user_data_folder = nullptr;
  const char *app_name = "pyminiwebview";
  const char *clipboard_permission = "default";
  int composition_hosting = 0;
  int transparent = 0;
  static char *keywords[] = {
      (char *)"debug",       (char *)"window",       (char *)"autosize",
      (char *)"width",       (char *)"height",       (char *)"url",
      (char *)"title",       (char *)"icon",         (char *)"bgcolor",
      (char *)"user_data_folder", (char *)"app_name",
      (char *)"clipboard_permission", (char *)"composition_hosting",
      (char *)"transparent", nullptr};

  if (!PyArg_ParseTupleAndKeywords(args, kwds, "|pKpiizzzIzzspp:WebView", keywords,
                                   &debug, &window, &autosize, &width, &height,
                                   &url, &title, &icon, &bgcolor,
                                   &user_data_folder, &app_name,
                                   &clipboard_permission, &composition_hosting,
                                   &transparent)) {
    return -1;
  }
  if (self->webview != nullptr || self->closed || self->initializing) {
    PyErr_SetString(PyExc_RuntimeError,
                    "WebView is already initialized or is closed");
    return -1;
  }
  self->ui_thread = GetCurrentThreadId();
  if (width <= 0 || height <= 0) {
    PyErr_SetString(PyExc_ValueError, "width and height must be positive");
    return -1;
  }
  HWND parent = reinterpret_cast<HWND>(static_cast<ULONG_PTR>(window));
  if (parent != nullptr && !IsWindow(parent)) {
    PyErr_SetString(PyExc_ValueError, "window must be a valid HWND or zero");
    return -1;
  }
  if (composition_hosting && parent == nullptr) {
    PyErr_SetString(PyExc_ValueError,
                    "composition_hosting requires an embedded parent HWND");
    return -1;
  }

  int permission = COREWEBVIEW2_PERMISSION_STATE_DEFAULT;
  if (strcmp(clipboard_permission, "allow") == 0) {
    permission = COREWEBVIEW2_PERMISSION_STATE_ALLOW;
  } else if (strcmp(clipboard_permission, "deny") == 0) {
    permission = COREWEBVIEW2_PERMISSION_STATE_DENY;
  } else if (strcmp(clipboard_permission, "default") != 0) {
    PyErr_SetString(PyExc_ValueError,
                    "clipboard_permission must be 'default', 'allow', or 'deny'");
    return -1;
  }

  MSG pending_quit;
  if (PeekMessageW(&pending_quit, nullptr, WM_QUIT, WM_QUIT, PM_REMOVE)) {
    PostQuitMessage(static_cast<int>(pending_quit.wParam));
    PyErr_SetString(PyExc_RuntimeError, "WebView2 initialization canceled");
    return -1;
  }
  self->initializing = 1;
  UINT_PTR initialization_signal_timer =
      SetTimer(nullptr, 0, SIGNAL_CHECK_INTERVAL_MS, signal_check_timeout);
  initialization_signal_check_active = true;
  try {
    StandaloneShowSuppressor suppress_initial_show(parent == nullptr);
    if (composition_hosting) {
      self->composition = new CompositionWebViewEngine(
          debug, parent, user_data_folder, app_name, permission);
      self->webview = self->composition;
    } else {
      self->webview = webview_create_ex(debug, parent, user_data_folder, app_name,
                                        permission);
    }
  } catch (const webview::exception &error) {
    self->initializing = 0;
    initialization_signal_check_active = false;
    if (initialization_signal_timer != 0) {
      KillTimer(nullptr, initialization_signal_timer);
    }
    if (!PyErr_Occurred()) {
      PyErr_Format(PyExc_RuntimeError,
                   "WebView2 initialization failed: %s (webview error %d)",
                   error.what(), static_cast<int>(error.error().code()));
    }
    restore_initialization_quit();
    return -1;
  } catch (const std::bad_alloc &) {
    self->initializing = 0;
    initialization_signal_check_active = false;
    if (initialization_signal_timer != 0) {
      KillTimer(nullptr, initialization_signal_timer);
    }
    if (!PyErr_Occurred()) {
      PyErr_NoMemory();
    }
    restore_initialization_quit();
    return -1;
  } catch (...) {
    self->initializing = 0;
    initialization_signal_check_active = false;
    if (initialization_signal_timer != 0) {
      KillTimer(nullptr, initialization_signal_timer);
    }
    if (!PyErr_Occurred()) {
      PyErr_SetString(PyExc_RuntimeError, "WebView2 initialization failed");
    }
    restore_initialization_quit();
    return -1;
  }
  initialization_signal_check_active = false;
  if (initialization_signal_timer != 0) {
    KillTimer(nullptr, initialization_signal_timer);
  }
  if (PyErr_Occurred()) {
    if (self->webview != nullptr) {
      goto error;
    }
    self->initializing = 0;
    restore_initialization_quit();
    return -1;
  }
  if (self->webview == nullptr) {
    self->initializing = 0;
    const char *message = nullptr;
    const int initialization_error =
        webview::detail::get_last_initialization_error(&message);
    if (message != nullptr && *message != '\0') {
      PyErr_Format(PyExc_RuntimeError,
                   "WebView2 initialization failed: %s (webview error %d)",
                   message, initialization_error);
    } else {
      PyErr_Format(PyExc_RuntimeError,
                   "WebView2 initialization failed (webview error %d); check "
                   "the runtime, window, COM apartment, and user data folder",
                   initialization_error);
    }
    restore_initialization_quit();
    return -1;
  }

  if (set_background_color(self, static_cast<COLORREF>(bgcolor),
                           transparent ? 0 : 255) < 0) {
    goto error;
  }
  self->parent = parent;
  self->embedded = parent != nullptr;
  self->widget = static_cast<HWND>(webview_get_native_handle(
      self->webview, WEBVIEW_NATIVE_HANDLE_KIND_UI_WIDGET));
  if (self->widget == nullptr) {
    PyErr_SetString(PyExc_RuntimeError, "WebView2 widget is unavailable");
    goto error;
  }

  if (self->embedded) {
    if (autosize) {
      self->auto_size_state =
          new (std::nothrow) AutoSizeState{
              self->parent, self->widget, self->composition};
      if (self->auto_size_state == nullptr) {
        PyErr_NoMemory();
        goto error;
      }
      if (!SetWindowSubclass(
              self->parent, auto_size_proc, reinterpret_cast<UINT_PTR>(self),
              reinterpret_cast<DWORD_PTR>(self->auto_size_state))) {
        PyErr_SetFromWindowsErr(0);
        goto error;
      }
      self->autosize = 1;
      if (resize_to_parent(self) < 0) {
        goto error;
      }
    } else if (resize_embedded(self, width, height) < 0) {
      goto error;
    }
  } else {
    self->parent = static_cast<HWND>(webview_get_native_handle(
        self->webview, WEBVIEW_NATIVE_HANDLE_KIND_UI_WINDOW));
    if (self->parent == nullptr) {
      PyErr_SetString(PyExc_RuntimeError, "WebView2 window is unavailable");
      goto error;
    }
    ShowWindow(self->parent, SW_HIDE);
    if (title != nullptr &&
        check_webview_error(webview_set_title(self->webview, title),
                            "webview_set_title") < 0) {
      goto error;
    }
    if (icon != nullptr && set_icon(self, icon) < 0) {
      goto error;
    }
    if (check_webview_error(webview_set_size(self->webview, width, height,
                                             WEBVIEW_HINT_NONE),
                            "webview_set_size") < 0) {
      goto error;
    }
    if (configure_startup_reveal(self) < 0) {
      goto error;
    }
  }

  if (url != nullptr) {
    if (check_webview_error(webview_navigate(self->webview, url),
                            "webview_navigate") < 0) {
      goto error;
    }
    self->content_requested = 1;
  }
  self->initializing = 0;
  return 0;

error:
  self->initializing = 0;
  if (self->autosize) {
    RemoveWindowSubclass(self->parent, auto_size_proc,
                         reinterpret_cast<UINT_PTR>(self));
    self->autosize = 0;
  }
  delete self->auto_size_state;
  self->auto_size_state = nullptr;
  NativeFinalizer finalizer{};
  detach_native(self, &finalizer);
  destroy_native_resources(&finalizer);
  self->bindings = finalizer.bindings;
  finalizer.bindings = nullptr;
  self->content_requested = 0;
  restore_initialization_quit();
  return -1;
}

static PyObject *WebView_close(WebViewObject *self, PyObject *ignored) {
  (void)ignored;
  if (GetCurrentThreadId() != self->ui_thread) {
    PyErr_SetString(PyExc_RuntimeError,
                    "close() must be called on the creating UI thread");
    return nullptr;
  }
  if (close_on_ui(self) < 0) {
    return nullptr;
  }
  return new_none_reference();
}

static PyObject *WebView_enter(WebViewObject *self, PyObject *ignored) {
  (void)ignored;
  if (require_webview(self) < 0) {
    return nullptr;
  }
  Py_IncRef(reinterpret_cast<PyObject *>(self));
  return reinterpret_cast<PyObject *>(self);
}

static PyObject *WebView_exit(WebViewObject *self, PyObject *args) {
  (void)args;
  if (GetCurrentThreadId() != self->ui_thread) {
    PyErr_SetString(PyExc_RuntimeError,
                    "__exit__ must be called on the creating UI thread");
    return nullptr;
  }
  if (close_on_ui(self) < 0) {
    return nullptr;
  }
  return PyBool_FromLong(0);
}

static PyObject *WebView_configure_app_mode(WebViewObject *self, PyObject *args,
                                            PyObject *kwds) {
  int disable_browser_accelerators = 1;
  int disable_nc_region_support = 1;
  int redirect_new_window_to_system_browser = 1;
  int disable_default_context_menus = 1;
  static char *keywords[] = {
      (char *)"disable_browser_accelerators",
      (char *)"disable_nc_region_support",
      (char *)"redirect_new_window_to_system_browser",
      (char *)"disable_default_context_menus",
      nullptr};
  if (!PyArg_ParseTupleAndKeywords(
          args, kwds, "|ppp$p:configure_app_mode", keywords,
          &disable_browser_accelerators, &disable_nc_region_support,
          &redirect_new_window_to_system_browser, &disable_default_context_menus)) {
    return nullptr;
  }
  if (require_webview(self) < 0 ||
      configure_app_mode(self, disable_browser_accelerators,
                         disable_default_context_menus, disable_nc_region_support,
                         redirect_new_window_to_system_browser) < 0) {
    return nullptr;
  }
  return new_none_reference();
}

static PyObject *WebView_composition_resize(WebViewObject *self,
                                            PyObject *ignored) {
  (void)ignored;
  if (require_webview(self) < 0) {
    return nullptr;
  }
  if (self->composition == nullptr) {
    return PyBool_FromLong(0);
  }
  self->composition->resize();
  return PyBool_FromLong(1);
}

static PyObject *WebView_composition_mouse_input(WebViewObject *self,
                                                 PyObject *args) {
  unsigned int message;
  unsigned long long wparam;
  unsigned long long lparam;
  if (!PyArg_ParseTuple(args, "IKK:composition_mouse_input", &message, &wparam,
                        &lparam)) {
    return nullptr;
  }
  if (require_webview(self) < 0) {
    return nullptr;
  }
  if (self->composition == nullptr) {
    return PyBool_FromLong(0);
  }
  return PyBool_FromLong(self->composition->send_mouse_input(
      message, static_cast<WPARAM>(wparam), static_cast<LPARAM>(lparam)));
}

static PyObject *WebView_composition_pointer_input(WebViewObject *self,
                                                   PyObject *args) {
  unsigned int message;
  unsigned long long wparam;
  if (!PyArg_ParseTuple(args, "IK:composition_pointer_input", &message,
                        &wparam)) {
    return nullptr;
  }
  if (require_webview(self) < 0) {
    return nullptr;
  }
  if (self->composition == nullptr) {
    return PyBool_FromLong(0);
  }
  return PyBool_FromLong(self->composition->send_pointer_input(
      message, static_cast<WPARAM>(wparam)));
}

static PyObject *WebView_composition_cursor(WebViewObject *self,
                                            PyObject *ignored) {
  (void)ignored;
  if (require_webview(self) < 0) {
    return nullptr;
  }
  if (self->composition == nullptr) {
    return PyBool_FromLong(0);
  }
  return PyBool_FromLong(self->composition->update_cursor());
}

static PyObject *WebView_composition_visible(WebViewObject *self,
                                             PyObject *args) {
  int visible;
  if (!PyArg_ParseTuple(args, "p:composition_visible", &visible)) {
    return nullptr;
  }
  if (require_webview(self) < 0) {
    return nullptr;
  }
  if (self->composition == nullptr) {
    return PyBool_FromLong(0);
  }
  self->composition->set_visible(visible ? TRUE : FALSE);
  return PyBool_FromLong(1);
}

static PyObject *WebView_notify_parent_position(WebViewObject *self,
                                                PyObject *ignored) {
  (void)ignored;
  if (require_webview(self) < 0) {
    return nullptr;
  }
  void *handle = webview_get_native_handle(
      self->webview, WEBVIEW_NATIVE_HANDLE_KIND_BROWSER_CONTROLLER);
  if (handle == nullptr) {
    PyErr_SetString(PyExc_RuntimeError, "WebView2 controller is unavailable");
    return nullptr;
  }
  auto *controller = static_cast<ICoreWebView2Controller *>(handle);
  // Wails practice: call from host WM_MOVE so native popups track the window.
  HRESULT result = controller->NotifyParentWindowPositionChanged();
  if (FAILED(result)) {
    PyErr_Format(PyExc_RuntimeError,
                 "NotifyParentWindowPositionChanged failed (HRESULT 0x%08lX)",
                 static_cast<unsigned long>(result));
    return nullptr;
  }
  return new_none_reference();
}

static PyObject *WebView_run(WebViewObject *self, PyObject *args) {
  unsigned long long hwnd = 0;
  unsigned long long haccel = 0;
  if (!PyArg_ParseTuple(args, "|KK:run", &hwnd, &haccel)) {
    return nullptr;
  }
  if (require_webview(self) < 0) {
    return nullptr;
  }
  if (!self->embedded && !IsWindowVisible(self->parent)) {
    if (!self->content_requested || !self->startup_registered) {
      reveal_native_window(self->parent);
    } else if (SetTimer(self->parent, STARTUP_REVEAL_TIMER_ID, 10000,
                        startup_reveal_timeout) == 0) {
      reveal_native_window(self->parent);
    }
  }
  webview_error_t error;
  UINT_PTR signal_timer =
      SetTimer(nullptr, 0, SIGNAL_CHECK_INTERVAL_MS, signal_check_timeout);
  self->running = 1;
  // The message loop blocks for an arbitrary time and never needs the GIL.
  Py_BEGIN_ALLOW_THREADS
  error = webview_run_with_accelerators(self->webview,
                                        reinterpret_cast<HWND>(hwnd),
                                        reinterpret_cast<HACCEL>(haccel));
  Py_END_ALLOW_THREADS
  self->running = 0;
  if (signal_timer != 0) {
    KillTimer(nullptr, signal_timer);
  }
  if (check_webview_error(error, "webview_run_with_accelerators") < 0) {
    return nullptr;
  }
  return new_none_reference();
}

static PyObject *WebView_terminate(WebViewObject *self, PyObject *ignored) {
  (void)ignored;
  webview_error_t error;
  {
    std::lock_guard<std::mutex> lock(*self->lifecycle_mutex);
    if (self->closed || self->webview == nullptr) {
      PyErr_SetString(PyExc_RuntimeError,
                      "WebView is not initialized or is closed");
      return nullptr;
    }
    error = webview_terminate(self->webview);
  }
  if (check_webview_error(error, "webview_terminate") < 0) {
    return nullptr;
  }
  return new_none_reference();
}

static void dispatch_callback(webview_t webview, void *arg) noexcept {
  (void)webview;
  std::unique_ptr<DispatchCall> call(static_cast<DispatchCall *>(arg));
  PyGILState_STATE gil_state = PyGILState_Ensure();
  PyObject *callable = call->callable;
  call->callable = nullptr;
  bool should_call = false;
  WebViewObject *owner = call->owner;
  if (owner != nullptr) {
    std::lock_guard<std::mutex> lock(*owner->lifecycle_mutex);
    DispatchCall **link = &owner->pending_dispatch;
    while (*link != nullptr && *link != call.get()) {
      link = &(*link)->next;
    }
    if (*link == call.get()) {
      *link = call->next;
    }
    should_call = !owner->closed && callable != nullptr;
    call->owner = nullptr;
  }
  if (should_call) {
    PyObject *result = PyObject_CallObject(callable, nullptr);
    if (result == nullptr) {
      handle_ui_callback_exception();
    } else {
      Py_DecRef(result);
    }
  }
  Py_DecRef(callable);
  PyGILState_Release(gil_state);
}

static PyObject *WebView_dispatch(WebViewObject *self, PyObject *callable) {
  if (!PyCallable_Check(callable)) {
    PyErr_SetString(PyExc_TypeError, "dispatch argument must be callable");
    return nullptr;
  }
  DispatchCall *call = new (std::nothrow) DispatchCall{callable, self, nullptr};
  if (call == nullptr) {
    return PyErr_NoMemory();
  }
  Py_IncRef(callable);
  webview_error_t error = WEBVIEW_ERROR_OK;
  bool unavailable = false;
  {
    std::lock_guard<std::mutex> lock(*self->lifecycle_mutex);
    unavailable = self->closed || self->webview == nullptr;
    if (!unavailable) {
      call->next = self->pending_dispatch;
      self->pending_dispatch = call;
      error = webview_dispatch(self->webview, dispatch_callback, call);
      if (error != WEBVIEW_ERROR_OK) {
        self->pending_dispatch = call->next;
      }
    }
  }
  if (unavailable) {
    Py_DecRef(callable);
    delete call;
    PyErr_SetString(PyExc_RuntimeError, "WebView is not initialized or is closed");
    return nullptr;
  }
  if (error != WEBVIEW_ERROR_OK) {
    Py_DecRef(callable);
    delete call;
    set_webview_error("webview_dispatch", error);
    return nullptr;
  }
  return new_none_reference();
}



static void binding_call_destructor(PyObject *capsule) {
  void *pointer = PyCapsule_GetPointer(capsule, nullptr);
  if (pointer == nullptr) {
    PyErr_Clear();
    return;
  }
  BindingCall *call = static_cast<BindingCall *>(pointer);
  Py_DecRef(call->callable);
  if (!call->release_queued) {
    delete call;
  }
}

static void binding_call_release(webview_t webview, void *arg) noexcept {
  (void)webview;
  std::unique_ptr<BindingCall> call(static_cast<BindingCall *>(arg));
  PyGILState_STATE gil_state = PyGILState_Ensure();
  Py_DecRef(call->callable);
  PyGILState_Release(gil_state);
}

static void binding_callback(const char *id, const char *request,
                             void *arg) noexcept {
  BindingCall *call = static_cast<BindingCall *>(arg);
  // WebView2 invokes this on the UI thread, which may not currently hold the GIL.
  PyGILState_STATE gil_state = PyGILState_Ensure();
  if (call->callable == nullptr) {
    PyGILState_Release(gil_state);
    return;
  }
  PyObject *arguments = Py_BuildValue("(ss)", id, request);
  if (arguments == nullptr) {
    handle_ui_callback_exception();
  } else {
    // Keep a local reference in case the callback unbinds the Python callable.
    PyObject *callable = call->callable;
    Py_IncRef(callable);
    PyObject *result = PyObject_CallObject(callable, arguments);
    Py_DecRef(arguments);
    if (result == nullptr) {
      handle_ui_callback_exception();
    } else {
      Py_DecRef(result);
    }
    Py_DecRef(callable);
  }
  PyGILState_Release(gil_state);
}

static PyObject *WebView_js_bind(WebViewObject *self, PyObject *args) {
  const char *name;
  PyObject *callable;
  if (!PyArg_ParseTuple(args, "sO:js_bind", &name, &callable)) {
    return nullptr;
  }
  if (require_webview(self) < 0) {
    return nullptr;
  }
  if (!PyCallable_Check(callable)) {
    PyErr_SetString(PyExc_TypeError, "js_bind callback must be callable");
    return nullptr;
  }

  BindingCall *call;
  try {
    call = new BindingCall{callable, 0};
  } catch (const std::bad_alloc &) {
    return PyErr_NoMemory();
  }
  Py_IncRef(callable);
  PyObject *capsule = PyCapsule_New(call, nullptr, binding_call_destructor);
  if (capsule == nullptr) {
    Py_DecRef(callable);
    delete call;
    return nullptr;
  }
  webview_error_t error =
      webview_bind(self->webview, name, binding_callback, call);
  // The native binding is inserted before a canceled script refresh returns.
  if (error != WEBVIEW_ERROR_OK && error != WEBVIEW_ERROR_CANCELED) {
    Py_DecRef(capsule);
    set_webview_error("webview_bind", error);
    return nullptr;
  }
  // Ownership transfers to the release callback after a successful unbind.
  if (PyDict_SetItemString(self->bindings, name, capsule) < 0) {
    webview_unbind(self->webview, name);
    Py_DecRef(capsule);
    return nullptr;
  }
  Py_DecRef(capsule);
  return new_none_reference();
}

static PyObject *WebView_js_unbind(WebViewObject *self, PyObject *args) {
  const char *name;
  if (!PyArg_ParseTuple(args, "s:js_unbind", &name)) {
    return nullptr;
  }
  if (require_webview(self) < 0) {
    return nullptr;
  }
  PyObject *capsule = PyDict_GetItemString(self->bindings, name);
  if (capsule == nullptr) {
    if (check_webview_error(webview_unbind(self->webview, name),
                            "webview_unbind") < 0) {
      return nullptr;
    }
    if (PyDict_DelItemString(self->bindings, name) < 0) {
      return nullptr;
    }
    return new_none_reference();
  }
  Py_IncRef(capsule);
  BindingCall *call =
      static_cast<BindingCall *>(PyCapsule_GetPointer(capsule, nullptr));
  if (call == nullptr) {
    Py_DecRef(capsule);
    return nullptr;
  }
  PyObject *callable = call->callable;
  Py_IncRef(callable);
  clear_reference(&call->callable);
  webview_error_t error = webview_unbind(self->webview, name);
  // The native binding is erased before a canceled script refresh returns.
  if (error != WEBVIEW_ERROR_OK && error != WEBVIEW_ERROR_CANCELED) {
    Py_DecRef(call->callable);
    call->callable = callable;
    Py_DecRef(capsule);
    set_webview_error("webview_unbind", error);
    return nullptr;
  }
  error = self->webview == nullptr
              ? WEBVIEW_ERROR_INVALID_STATE
              : webview_dispatch(self->webview, binding_call_release, call);
  if (error != WEBVIEW_ERROR_OK) {
    if (PyDict_GetItemString(self->bindings, name) == capsule &&
        PyDict_DelItemString(self->bindings, name) < 0) {
      PyErr_Clear();
    }
    Py_DecRef(callable);
    // Native calls already queued by unbind may still retain this pointer.
    // Abandon the local capsule reference rather than risking an early delete.
    set_webview_error("webview_dispatch binding release", error);
    return nullptr;
  }
  call->release_queued = 1;
  if (PyDict_GetItemString(self->bindings, name) == capsule &&
      PyDict_DelItemString(self->bindings, name) < 0) {
    PyErr_Clear();
  }
  Py_DecRef(capsule);
  Py_DecRef(callable);
  return new_none_reference();
}

static PyObject *WebView_js_return(WebViewObject *self, PyObject *args) {
  const char *id;
  int status;
  const char *result;
  if (!PyArg_ParseTuple(args, "sis:js_return", &id, &status, &result)) {
    return nullptr;
  }
  if (require_webview(self) < 0 ||
      check_webview_error(webview_return(self->webview, id, status, result),
                          "webview_return") < 0) {
    return nullptr;
  }
  return new_none_reference();
}

static PyObject *WebView_js_eval(WebViewObject *self, PyObject *args) {
  const char *js;
  if (!PyArg_ParseTuple(args, "s:js_eval", &js)) {
    return nullptr;
  }
  if (require_webview(self) < 0 ||
      check_webview_error(webview_eval(self->webview, js), "webview_eval") < 0) {
    return nullptr;
  }
  return new_none_reference();
}

static PyObject *WebView_js_init(WebViewObject *self, PyObject *args) {
  const char *js;
  if (!PyArg_ParseTuple(args, "s:js_init", &js)) {
    return nullptr;
  }
  if (require_webview(self) < 0 ||
      check_webview_error(webview_init(self->webview, js), "webview_init") < 0) {
    return nullptr;
  }
  return new_none_reference();
}

static PyObject *WebView_navigate(WebViewObject *self, PyObject *args) {
  const char *url;
  if (!PyArg_ParseTuple(args, "s:navigate", &url)) {
    return nullptr;
  }
  if (require_webview(self) < 0 ||
      check_webview_error(webview_navigate(self->webview, url),
                          "webview_navigate") < 0) {
    return nullptr;
  }
  self->content_requested = 1;
  return new_none_reference();
}

static PyObject *WebView_set_html(WebViewObject *self, PyObject *args) {
  const char *html;
  if (!PyArg_ParseTuple(args, "s:set_html", &html)) {
    return nullptr;
  }
  if (require_webview(self) < 0 ||
      check_webview_error(webview_set_html(self->webview, html),
                          "webview_set_html") < 0) {
    return nullptr;
  }
  self->content_requested = 1;
  return new_none_reference();
}

static PyObject *WebView_set_title(WebViewObject *self, PyObject *args) {
  const char *title;
  if (!PyArg_ParseTuple(args, "s:set_title", &title)) {
    return nullptr;
  }
  if (require_webview(self) < 0) {
    return nullptr;
  }
  if (self->embedded) {
    PyErr_SetString(PyExc_RuntimeError,
                    "set_title is only available for standalone windows");
    return nullptr;
  }
  if (check_webview_error(webview_set_title(self->webview, title),
                          "webview_set_title") < 0) {
    return nullptr;
  }
  return new_none_reference();
}

static PyObject *WebView_set_size(WebViewObject *self, PyObject *args) {
  int width;
  int height;
  int hints = WEBVIEW_HINT_NONE;
  if (!PyArg_ParseTuple(args, "ii|i:set_size", &width, &height, &hints)) {
    return nullptr;
  }
  if (require_webview(self) < 0) {
    return nullptr;
  }
  if (width <= 0 || height <= 0) {
    PyErr_SetString(PyExc_ValueError, "width and height must be positive");
    return nullptr;
  }
  if (hints != WEBVIEW_HINT_NONE && hints != WEBVIEW_HINT_MIN &&
      hints != WEBVIEW_HINT_MAX && hints != WEBVIEW_HINT_FIXED) {
    PyErr_SetString(PyExc_ValueError, "invalid size hint");
    return nullptr;
  }
  if (self->embedded) {
    if (resize_embedded(self, width, height) < 0) {
      return nullptr;
    }
  } else if (check_webview_error(
                 webview_set_size(self->webview, width, height,
                                  static_cast<webview_hint_t>(hints)),
                 "webview_set_size") < 0) {
    return nullptr;
  }
  return new_none_reference();
}

static PyObject *WebView_set_focus(WebViewObject *self, PyObject *ignored) {
  (void)ignored;
  if (require_webview(self) < 0 || focus_webview(self) < 0) {
    return nullptr;
  }
  return new_none_reference();
}

static PyObject *WebView_get_native_handle(WebViewObject *self, PyObject *args) {
  int kind;
  if (!PyArg_ParseTuple(args, "i:get_native_handle", &kind)) {
    return nullptr;
  }
  if (require_webview(self) < 0) {
    return nullptr;
  }
  if (kind != WEBVIEW_NATIVE_HANDLE_KIND_UI_WINDOW &&
      kind != WEBVIEW_NATIVE_HANDLE_KIND_UI_WIDGET &&
      kind != WEBVIEW_NATIVE_HANDLE_KIND_BROWSER_CONTROLLER) {
    PyErr_SetString(PyExc_ValueError, "invalid native handle kind");
    return nullptr;
  }
  void *handle = webview_get_native_handle(
      self->webview, static_cast<webview_native_handle_kind_t>(kind));
  if (handle == nullptr) {
    PyErr_SetString(PyExc_RuntimeError, "native handle is unavailable");
    return nullptr;
  }
  return PyLong_FromUnsignedLongLong(reinterpret_cast<unsigned long long>(handle));
}

static PyMethodDef WebView_methods[] = {
    {"close", (PyCFunction)WebView_close, METH_NOARGS,
     "Close native resources on the UI thread and cancel queued callbacks."},
    {"__enter__", (PyCFunction)WebView_enter, METH_NOARGS,
     "Return the WebView for use as a context manager."},
    {"__exit__", (PyCFunction)WebView_exit, METH_VARARGS,
     "Close the WebView without suppressing Python exceptions."},
    {"configure_app_mode", (PyCFunction)WebView_configure_app_mode,
     METH_VARARGS | METH_KEYWORDS,
     "Apply desktop application policies through public WebView2 APIs."},
    {"composition_resize", (PyCFunction)WebView_composition_resize,
     METH_NOARGS, "Resize a composition WebView to its parent client area."},
    {"composition_mouse_input", (PyCFunction)WebView_composition_mouse_input,
     METH_VARARGS, "Forward Win32 mouse input to a composition WebView."},
    {"composition_pointer_input",
     (PyCFunction)WebView_composition_pointer_input, METH_VARARGS,
     "Forward Win32 pointer input to a composition WebView."},
    {"composition_cursor", (PyCFunction)WebView_composition_cursor, METH_NOARGS,
     "Apply the current composition WebView cursor."},
    {"composition_visible", (PyCFunction)WebView_composition_visible,
     METH_VARARGS, "Set composition WebView visibility."},
    {"notify_parent_position", (PyCFunction)WebView_notify_parent_position,
     METH_NOARGS, "Notify WebView2 that the host window position changed."},
    {"run", (PyCFunction)WebView_run, METH_VARARGS,
     "Run the UI message loop without holding the GIL."},
    {"terminate", (PyCFunction)WebView_terminate, METH_NOARGS,
     "Stop the UI message loop; safe to call from another thread."},
    {"dispatch", (PyCFunction)WebView_dispatch, METH_O,
     "Schedule a zero-argument callable on the UI thread."},
    {"js_bind", (PyCFunction)WebView_js_bind, METH_VARARGS,
     "Bind a JavaScript function to a Python callback."},
    {"js_unbind", (PyCFunction)WebView_js_unbind, METH_VARARGS,
     "Remove a JavaScript binding and release its callback."},
    {"js_return", (PyCFunction)WebView_js_return, METH_VARARGS,
     "Resolve a JavaScript binding request."},
    {"js_eval", (PyCFunction)WebView_js_eval, METH_VARARGS,
     "Evaluate JavaScript."},
    {"js_init", (PyCFunction)WebView_js_init, METH_VARARGS,
     "Inject JavaScript before page scripts run."},
    {"navigate", (PyCFunction)WebView_navigate, METH_VARARGS,
     "Navigate to a URL."},
    {"set_html", (PyCFunction)WebView_set_html, METH_VARARGS,
     "Load an HTML string."},
    {"set_title", (PyCFunction)WebView_set_title, METH_VARARGS,
     "Set the standalone window title."},
    {"set_size", (PyCFunction)WebView_set_size, METH_VARARGS,
     "Set the WebView or standalone window size."},
    {"set_focus", (PyCFunction)WebView_set_focus, METH_NOARGS,
     "Move keyboard focus to WebView2."},
    {"get_native_handle", (PyCFunction)WebView_get_native_handle, METH_VARARGS,
     "Return a native handle as an unsigned 64-bit integer."},
    {nullptr, nullptr, 0, nullptr}};

static PyType_Slot WebView_slots[] = {
    {Py_tp_dealloc, (void *)WebView_dealloc},
    {Py_tp_doc, (void *)"A native Windows WebView2 instance."},
    {Py_tp_init, (void *)WebView_init},
    {Py_tp_new, (void *)WebView_new},
    {Py_tp_methods, WebView_methods},
    {Py_tp_traverse, (void *)WebView_traverse},
    {Py_tp_clear, (void *)WebView_clear},
    {0, nullptr}};

static PyType_Spec WebView_spec = {
    "pyminiwebview.WebView", sizeof(WebViewObject), 0,
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC, WebView_slots};

static int add_constant(PyObject *module, const char *name, long value) {
  if (PyModule_AddIntConstant(module, name, value) < 0) {
    return -1;
  }
  return 0;
}

static struct PyModuleDef module_definition = {
    PyModuleDef_HEAD_INIT,
    "pyminiwebview",
    "Minimal, stable-ABI Python bindings for Microsoft WebView2.",
    0,
    nullptr,
    nullptr,
    nullptr,
    nullptr,
    nullptr};

PyMODINIT_FUNC PyInit_pyminiwebview(void) {
  PyObject *module = PyModule_Create(&module_definition);
  if (module == nullptr) {
    return nullptr;
  }
  PyObject *type = PyType_FromSpec(&WebView_spec);
  if (type == nullptr) {
    Py_DecRef(module);
    return nullptr;
  }
  if (PyModule_AddObject(module, "WebView", type) < 0) {
    Py_DecRef(reinterpret_cast<PyObject *>(type));
    Py_DecRef(module);
    return nullptr;
  }
  if (add_constant(module, "HINT_NONE", WEBVIEW_HINT_NONE) < 0 ||
      add_constant(module, "HINT_MIN", WEBVIEW_HINT_MIN) < 0 ||
      add_constant(module, "HINT_MAX", WEBVIEW_HINT_MAX) < 0 ||
      add_constant(module, "HINT_FIXED", WEBVIEW_HINT_FIXED) < 0 ||
      add_constant(module, "NATIVE_HANDLE_KIND_UI_WINDOW",
                   WEBVIEW_NATIVE_HANDLE_KIND_UI_WINDOW) < 0 ||
      add_constant(module, "NATIVE_HANDLE_KIND_UI_WIDGET",
                   WEBVIEW_NATIVE_HANDLE_KIND_UI_WIDGET) < 0 ||
      add_constant(module, "NATIVE_HANDLE_KIND_BROWSER_CONTROLLER",
                   WEBVIEW_NATIVE_HANDLE_KIND_BROWSER_CONTROLLER) < 0 ||
      PyModule_AddStringConstant(module, "__version__", PYMINIWEBVIEW_VERSION) < 0) {
    Py_DecRef(module);
    return nullptr;
  }
  return module;
}
