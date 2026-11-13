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
#include <memory>
#include <new>
#include <string>

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
    // Wails-style desktop app policy: open external pages in the system browser.
    ShellExecuteW(nullptr, L"open", uri, nullptr, nullptr, SW_SHOWNORMAL);
    CoTaskMemFree(uri);
    return args->put_Handled(TRUE);
  }

private:
  LONG m_ref_count = 1;
};

typedef struct {
  PyObject_HEAD
  webview_t webview;
  PyObject *bindings;
  HWND parent;
  HWND widget;
  HICON icon;
  NewWindowRequestedHandler *new_window_handler;
  EventRegistrationToken new_window_token;
  int new_window_registered;
  int embedded;
  int autosize;
} WebViewObject;

typedef struct {
  PyObject *callable;
} DispatchCall;

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

static int require_webview(WebViewObject *self) {
  if (self->webview == nullptr) {
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
  WebViewObject *self = reinterpret_cast<WebViewObject *>(ref_data);
  if (message == WM_SIZE && wparam != SIZE_MINIMIZED && self->widget != nullptr) {
    SetWindowPos(self->widget, nullptr, 0, 0, LOWORD(lparam), HIWORD(lparam),
                 SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOZORDER);
  } else if (message == WM_NCDESTROY) {
    self->autosize = 0;
    RemoveWindowSubclass(hwnd, auto_size_proc, subclass_id);
  }
  return DefSubclassProc(hwnd, message, wparam, lparam);
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

static int set_background_color(WebViewObject *self, COLORREF color) {
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
  background.A = 255;
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

static int configure_app_mode(WebViewObject *self,
                              int disable_browser_accelerators,
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
    self->bindings = PyDict_New();
    if (self->bindings == nullptr) {
      Py_DECREF(self);
      return nullptr;
    }
  }
  return reinterpret_cast<PyObject *>(self);
}

static void WebView_dealloc(WebViewObject *self) {
  PyObject *error_type, *error_value, *error_traceback;
  PyErr_Fetch(&error_type, &error_value, &error_traceback);

  webview_t webview = self->webview;
  self->webview = nullptr;
  if (self->autosize && self->parent != nullptr) {
    RemoveWindowSubclass(self->parent, auto_size_proc,
                         reinterpret_cast<UINT_PTR>(self));
    self->autosize = 0;
  }
  if (self->new_window_registered && webview != nullptr) {
    void *handle = webview_get_native_handle(
        webview, WEBVIEW_NATIVE_HANDLE_KIND_BROWSER_CONTROLLER);
    if (handle != nullptr) {
      auto *controller = static_cast<ICoreWebView2Controller *>(handle);
      ICoreWebView2 *core = nullptr;
      if (SUCCEEDED(controller->get_CoreWebView2(&core)) && core != nullptr) {
        core->remove_NewWindowRequested(self->new_window_token);
        core->Release();
      }
    }
    self->new_window_registered = 0;
  }
  if (self->new_window_handler != nullptr) {
    self->new_window_handler->Release();
    self->new_window_handler = nullptr;
  }
  if (webview != nullptr) {
    webview_error_t error = webview_destroy(webview);
    if (error != WEBVIEW_ERROR_OK) {
      set_webview_error("webview_destroy", error);
      PyErr_PrintEx(0);
    }
  }
  if (self->icon != nullptr) {
    DestroyIcon(self->icon);
    self->icon = nullptr;
  }

  // Each capsule in the dictionary releases its callback and native record.
  Py_CLEAR(self->bindings);
  PyTypeObject *type = Py_TYPE(self);
  freefunc free = reinterpret_cast<freefunc>(PyType_GetSlot(type, Py_tp_free));
  if (free != nullptr) {
    free(reinterpret_cast<PyObject *>(self));
  }
  Py_DECREF(type);
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
  static char *keywords[] = {
      (char *)"debug",       (char *)"window",       (char *)"autosize",
      (char *)"width",       (char *)"height",       (char *)"url",
      (char *)"title",       (char *)"icon",         (char *)"bgcolor",
      (char *)"user_data_folder", (char *)"app_name",
      (char *)"clipboard_permission", nullptr};

  if (!PyArg_ParseTupleAndKeywords(args, kwds, "|pKpiizzzIzzs:WebView", keywords,
                                   &debug, &window, &autosize, &width, &height,
                                   &url, &title, &icon, &bgcolor,
                                   &user_data_folder, &app_name,
                                   &clipboard_permission)) {
    return -1;
  }
  if (self->webview != nullptr) {
    PyErr_SetString(PyExc_RuntimeError, "WebView is already initialized");
    return -1;
  }
  if (width <= 0 || height <= 0) {
    PyErr_SetString(PyExc_ValueError, "width and height must be positive");
    return -1;
  }
  HWND parent = reinterpret_cast<HWND>(static_cast<ULONG_PTR>(window));
  if (parent != nullptr && !IsWindow(parent)) {
    PyErr_SetString(PyExc_ValueError, "window must be a valid HWND or zero");
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

  try {
    self->webview = webview_create_ex(debug, parent, user_data_folder, app_name,
                                      permission);
  } catch (const std::bad_alloc &) {
    PyErr_NoMemory();
    return -1;
  } catch (...) {
    PyErr_SetString(PyExc_RuntimeError, "WebView2 initialization failed");
    return -1;
  }
  if (self->webview == nullptr) {
    PyErr_SetString(PyExc_RuntimeError,
                    "WebView2 initialization failed; check the runtime, window, "
                    "COM apartment, and user data folder");
    return -1;
  }

  if (set_background_color(self, static_cast<COLORREF>(bgcolor)) < 0) {
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
      if (!SetWindowSubclass(self->parent, auto_size_proc,
                             reinterpret_cast<UINT_PTR>(self),
                             reinterpret_cast<DWORD_PTR>(self))) {
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
  }

  if (url != nullptr &&
      check_webview_error(webview_navigate(self->webview, url),
                          "webview_navigate") < 0) {
    goto error;
  }
  if (focus_webview(self) < 0) {
    goto error;
  }
  return 0;

error:
  if (self->autosize) {
    RemoveWindowSubclass(self->parent, auto_size_proc,
                         reinterpret_cast<UINT_PTR>(self));
    self->autosize = 0;
  }
  webview_t webview = self->webview;
  self->webview = nullptr;
  if (webview != nullptr) {
    webview_destroy(webview);
  }
  if (self->icon != nullptr) {
    DestroyIcon(self->icon);
    self->icon = nullptr;
  }
  return -1;
}

static PyObject *WebView_configure_app_mode(WebViewObject *self, PyObject *args,
                                            PyObject *kwds) {
  int disable_browser_accelerators = 1;
  int disable_nc_region_support = 1;
  int redirect_new_window_to_system_browser = 1;
  static char *keywords[] = {
      (char *)"disable_browser_accelerators",
      (char *)"disable_nc_region_support",
      (char *)"redirect_new_window_to_system_browser",
      nullptr};
  if (!PyArg_ParseTupleAndKeywords(
          args, kwds, "|ppp:configure_app_mode", keywords,
          &disable_browser_accelerators, &disable_nc_region_support,
          &redirect_new_window_to_system_browser)) {
    return nullptr;
  }
  if (require_webview(self) < 0 ||
      configure_app_mode(self, disable_browser_accelerators,
                         disable_nc_region_support,
                         redirect_new_window_to_system_browser) < 0) {
    return nullptr;
  }
  Py_RETURN_NONE;
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
  Py_RETURN_NONE;
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
  webview_error_t error;
  // The message loop blocks for an arbitrary time and never needs the GIL.
  Py_BEGIN_ALLOW_THREADS
  error = webview_run_with_accelerators(self->webview,
                                        reinterpret_cast<HWND>(hwnd),
                                        reinterpret_cast<HACCEL>(haccel));
  Py_END_ALLOW_THREADS
  if (check_webview_error(error, "webview_run_with_accelerators") < 0) {
    return nullptr;
  }
  Py_RETURN_NONE;
}

static PyObject *WebView_terminate(WebViewObject *self, PyObject *ignored) {
  (void)ignored;
  if (require_webview(self) < 0 ||
      check_webview_error(webview_terminate(self->webview),
                          "webview_terminate") < 0) {
    return nullptr;
  }
  Py_RETURN_NONE;
}

static void dispatch_callback(webview_t webview, void *arg) noexcept {
  (void)webview;
  std::unique_ptr<DispatchCall> call(static_cast<DispatchCall *>(arg));
  PyGILState_STATE gil_state = PyGILState_Ensure();
  PyObject *result = PyObject_CallObject(call->callable, nullptr);
  if (result == nullptr) {
    PyErr_PrintEx(0);
  } else {
    Py_DECREF(result);
  }
  Py_DECREF(call->callable);
  PyGILState_Release(gil_state);
}

static PyObject *WebView_dispatch(WebViewObject *self, PyObject *callable) {
  if (require_webview(self) < 0) {
    return nullptr;
  }
  if (!PyCallable_Check(callable)) {
    PyErr_SetString(PyExc_TypeError, "dispatch argument must be callable");
    return nullptr;
  }
  DispatchCall *call;
  try {
    call = new DispatchCall{callable};
  } catch (const std::bad_alloc &) {
    return PyErr_NoMemory();
  }
  // The queued call owns one reference until it runs or destruction drains it.
  Py_INCREF(callable);
  webview_error_t error = webview_dispatch(self->webview, dispatch_callback, call);
  if (error != WEBVIEW_ERROR_OK) {
    Py_DECREF(callable);
    delete call;
    set_webview_error("webview_dispatch", error);
    return nullptr;
  }
  Py_RETURN_NONE;
}

typedef struct {
  PyObject *callable;
} BindingCall;

static void binding_call_destructor(PyObject *capsule) {
  void *pointer = PyCapsule_GetPointer(capsule, nullptr);
  if (pointer == nullptr) {
    PyErr_Clear();
    return;
  }
  BindingCall *call = static_cast<BindingCall *>(pointer);
  Py_XDECREF(call->callable);
  delete call;
}

static void binding_callback(const char *id, const char *request,
                             void *arg) noexcept {
  BindingCall *call = static_cast<BindingCall *>(arg);
  // WebView2 invokes this on the UI thread, which may not currently hold the GIL.
  PyGILState_STATE gil_state = PyGILState_Ensure();
  PyObject *arguments = Py_BuildValue("(ss)", id, request);
  if (arguments == nullptr) {
    PyErr_PrintEx(0);
  } else {
    // Keep a local reference in case the callback unbinds and frees BindingCall.
    PyObject *callable = call->callable;
    Py_INCREF(callable);
    PyObject *result = PyObject_CallObject(callable, arguments);
    Py_DECREF(arguments);
    if (result == nullptr) {
      PyErr_PrintEx(0);
    } else {
      Py_DECREF(result);
    }
    Py_DECREF(callable);
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
    call = new BindingCall{callable};
  } catch (const std::bad_alloc &) {
    return PyErr_NoMemory();
  }
  Py_INCREF(callable);
  PyObject *capsule = PyCapsule_New(call, nullptr, binding_call_destructor);
  if (capsule == nullptr) {
    Py_DECREF(callable);
    delete call;
    return nullptr;
  }
  webview_error_t error =
      webview_bind(self->webview, name, binding_callback, call);
  if (error != WEBVIEW_ERROR_OK) {
    Py_DECREF(capsule);
    set_webview_error("webview_bind", error);
    return nullptr;
  }
  // The capsule owns the callback until js_unbind or object destruction.
  if (PyDict_SetItemString(self->bindings, name, capsule) < 0) {
    webview_unbind(self->webview, name);
    Py_DECREF(capsule);
    return nullptr;
  }
  Py_DECREF(capsule);
  Py_RETURN_NONE;
}

static PyObject *WebView_js_unbind(WebViewObject *self, PyObject *args) {
  const char *name;
  if (!PyArg_ParseTuple(args, "s:js_unbind", &name)) {
    return nullptr;
  }
  if (require_webview(self) < 0 ||
      check_webview_error(webview_unbind(self->webview, name),
                          "webview_unbind") < 0) {
    return nullptr;
  }
  if (PyDict_DelItemString(self->bindings, name) < 0) {
    return nullptr;
  }
  Py_RETURN_NONE;
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
  Py_RETURN_NONE;
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
  Py_RETURN_NONE;
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
  Py_RETURN_NONE;
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
  Py_RETURN_NONE;
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
  Py_RETURN_NONE;
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
  Py_RETURN_NONE;
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
  Py_RETURN_NONE;
}

static PyObject *WebView_set_focus(WebViewObject *self, PyObject *ignored) {
  (void)ignored;
  if (require_webview(self) < 0 || focus_webview(self) < 0) {
    return nullptr;
  }
  Py_RETURN_NONE;
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
    {"configure_app_mode", (PyCFunction)WebView_configure_app_mode,
     METH_VARARGS | METH_KEYWORDS,
     "Apply desktop application policies through public WebView2 APIs."},
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
    {0, nullptr}};

static PyType_Spec WebView_spec = {
    "pyminiwebview.WebView", sizeof(WebViewObject), 0, Py_TPFLAGS_DEFAULT,
    WebView_slots};

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
    Py_DECREF(module);
    return nullptr;
  }
  if (PyModule_AddObject(module, "WebView", type) < 0) {
    Py_DECREF(type);
    Py_DECREF(module);
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
      PyModule_AddStringConstant(module, "__version__", "0.1.1") < 0) {
    Py_DECREF(module);
    return nullptr;
  }
  return module;
}
